"""FastAPI application for the PaperLoom local service."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from . import SERVICE_API_VERSION, __version__
from .analysis import build_analysis_context, validate_multi_citations
from .analysis import build_messages as build_analysis_messages
from .config import (
    RuntimeConfig,
    Settings,
    api_key_status,
    clear_api_key,
    estimate_cost,
    load_api_key,
    load_pricing,
    load_settings,
    save_api_key,
    save_settings,
)
from .context import SYSTEM_GUARD, build_context, validate_citations
from .db import Database, now
from .deepseek import DeepSeekClient, DeepSeekError
from .glossary import extract_terms, glossary_block
from .jobs import JobManager
from .models import (
    AnalysisRequest,
    ChatRequest,
    ExtractTermsRequest,
    PersistMessage,
    ReadingStatePatch,
    RegisterDocumentRequest,
    SearchRequest,
    SettingsPatch,
    TermInput,
    TermPatch,
    TranslateRequest,
)
from .pdf.babeldoc import engine_info
from .pdf.extract import file_sha256, parse_pdf
from .translate import SKIP_KINDS, _has_prose, document_id_for
from .translation_config import TranslationConfig, evaluate
from .urls import OFFICIAL_BASE_URL, check_base_url, normalize_base_url

log = logging.getLogger("paperloom.app")

CHAT_SYSTEM = (
    "你是论文阅读助手。回答使用简体中文，先给结论，再给依据，必要时分点。"
    + SYSTEM_GUARD
    + "引用规则：每个关键论断后用 [[seg:ID]] 标注出处，ID 必须来自 <document> 中的片段；"
    "没有依据时明确说“原文未提及”，不得编造。"
)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class AppState:
    def __init__(self, cfg: RuntimeConfig):
        self.cfg = cfg
        self.db = Database(cfg.data_dir / "paperloom.sqlite")
        self.settings: Settings = load_settings(cfg)
        self.jobs: JobManager | None = None

    # -- helpers ------------------------------------------------------- #
    def client(self, settings: Settings | None = None) -> DeepSeekClient:
        effective = settings or self.settings
        return DeepSeekClient(
            base_url=effective.base_url,
            api_key=load_api_key(self.cfg),
            timeout=effective.timeout_seconds,
            connect_timeout=effective.connect_timeout_seconds,
            max_retries=effective.max_retries,
            qps=effective.qps,
            concurrency=effective.concurrency,
        )

    def key_configured(self) -> bool:
        return bool(load_api_key(self.cfg))

    def require_key(self) -> None:
        import os

        if not self.key_configured() and os.environ.get("PAPERLOOM_FAKE_LLM", "") in (
            "",
            "0",
            "false",
        ):
            raise HTTPException(
                status_code=412,
                detail={
                    "code": "no_api_key",
                    "message": "尚未配置 DeepSeek API Key，请在 PaperLoom 设置中填写并测试连接",
                },
            )

    def doc_or_404(self, document_id: str) -> dict:
        doc = self.db.get_document(document_id)
        if not doc:
            raise HTTPException(
                status_code=404, detail={"code": "not_found", "message": "文档未注册"}
            )
        return doc

    def document_payload(self, doc: dict) -> dict:
        return {
            "id": doc["id"],
            "libraryId": doc["library_id"],
            "itemKey": doc["item_key"],
            "attachmentKey": doc["attachment_key"],
            "fileHash": doc["file_hash"],
            "title": doc["title"],
            "pages": doc["pages"],
            "alignment": doc["alignment"],
            "alignmentNote": doc["alignment_note"],
            "scanned": bool(doc["scanned"]),
            "textChars": doc["text_chars"],
        }


def create_app(cfg: RuntimeConfig) -> FastAPI:
    state = AppState(cfg)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state.db.migrate()
        state.jobs = JobManager(
            state.db, state.cfg, lambda: state.settings, lambda: state.client()
        )
        await state.jobs.recover()
        (cfg.data_dir / "service.json").write_text(
            json.dumps(
                {
                    "service": "paperloom",
                    "version": __version__,
                    "apiVersion": SERVICE_API_VERSION,
                    "port": cfg.port,
                    "host": cfg.host,
                    "pid": __import__("os").getpid(),
                    "tokenFile": str(cfg.data_dir / "token"),
                    "dataDir": str(cfg.data_dir),
                    "startedAt": now(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        log.info(
            "PaperLoom service %s ready on http://%s:%s",
            __version__,
            cfg.host,
            cfg.port,
        )
        try:
            yield
        finally:
            if state.jobs:
                await state.jobs.shutdown()

    app = FastAPI(title="PaperLoom Service", version=__version__, lifespan=lifespan)
    app.state.paperloom = state

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path
        if path in {"/health", "/docs", "/openapi.json", "/redoc"}:
            return await call_next(request)
        token = request.headers.get("x-paperloom-token", "")
        if not token:
            auth = request.headers.get("authorization", "")
            if auth.lower().startswith("bearer "):
                token = auth[7:].strip()
        if not secrets.compare_digest(token, cfg.token):
            return JSONResponse(
                status_code=401,
                content={"detail": {"code": "unauthorized", "message": "实例令牌无效"}},
            )
        return await call_next(request)

    def manager() -> JobManager:
        assert state.jobs is not None
        return state.jobs

    # ------------------------------------------------------------------ #
    # Health / status / settings
    # ------------------------------------------------------------------ #
    @app.get("/health")
    async def health():
        return {
            "ok": True,
            "service": "paperloom",
            "version": __version__,
            "apiVersion": SERVICE_API_VERSION,
            "pid": __import__("os").getpid(),
        }

    @app.get("/v1/status")
    async def status():
        from .deepseek import fake_mode

        return {
            "version": __version__,
            "apiVersion": SERVICE_API_VERSION,
            "dataDir": str(cfg.data_dir),
            "llm": "fake" if fake_mode() else "live",
            "apiKey": api_key_status(cfg),
            "capabilities": {
                "babeldoc": {
                    **engine_info(),
                    "enabled": state.settings.babeldoc_enabled,
                    "timeoutSeconds": state.settings.babeldoc_timeout,
                },
                "fts5": True,
                "vision": True,
                "alignment": "segment",
            },
            "activeJobs": manager().active_count(),
            "documents": len(state.db.list_documents(limit=1000)),
        }

    @app.get("/v1/settings")
    async def get_settings():
        return {
            "settings": {
                **state.settings.public(),
                "baseUrlDefault": OFFICIAL_BASE_URL,
            },
            "baseUrlCheck": check_base_url(state.settings.base_url).as_dict(),
            "apiKey": api_key_status(cfg),
            "pricing": load_pricing(cfg),
            "models": [
                {
                    "id": "deepseek-flash",
                    "label": "DeepSeek Flash（1M 上下文，支持图片）",
                },
                {
                    "id": "deepseek-v4-pro",
                    "label": "DeepSeek V4 Pro（推理更强，无图片）",
                },
            ],
            "service": {"version": __version__, "apiVersion": SERVICE_API_VERSION},
        }

    @app.post("/v1/settings")
    async def update_settings(patch: SettingsPatch):
        data = patch.model_dump(exclude_none=True)
        api_key = data.pop("api_key", None)
        for key, value in data.items():
            if hasattr(state.settings, key):
                setattr(state.settings, key, value)
        try:
            state.settings.base_url = normalize_base_url(state.settings.base_url)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "bad_base_url", "message": f"Base URL 无效：{exc}"},
            ) from exc
        save_settings(cfg, state.settings)
        if api_key is not None:
            if api_key.strip():
                save_api_key(cfg, api_key)
            else:
                clear_api_key(cfg)
        return {
            "settings": {
                **state.settings.public(),
                "baseUrlDefault": OFFICIAL_BASE_URL,
            },
            "baseUrlCheck": check_base_url(state.settings.base_url).as_dict(),
            "apiKey": api_key_status(cfg),
        }

    @app.post("/v1/settings/test")
    async def test_settings(request: Request):
        body = {}
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = {}
        model = (body or {}).get("model") or state.settings.chat_model
        raw_base = (body or {}).get("baseUrl")
        if raw_base:
            check = check_base_url(raw_base)
            if not check.ok:
                return {
                    "ok": False,
                    "error": {"code": "bad_base_url", "message": check.message, "retryable": False},
                }
            settings = Settings(**{**state.settings.public(), "base_url": check.normalized})
            client = state.client(settings)
        else:
            client = state.client()
        try:
            result = await client.test_connection(model)
            return {"ok": True, "baseUrl": client.endpoint, **result}
        except DeepSeekError as exc:
            return {"ok": False, "error": exc.as_dict()}
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI as a diagnostic
            return {
                "ok": False,
                "error": {"code": "internal", "message": str(exc), "retryable": False},
            }

    # ------------------------------------------------------------------ #
    # Documents
    # ------------------------------------------------------------------ #
    @app.post("/v1/documents/register")
    async def register_document(req: RegisterDocumentRequest):
        path = Path(req.pdf_path).expanduser()
        if not path.is_absolute():
            raise HTTPException(
                status_code=400,
                detail={"code": "bad_path", "message": "pdfPath 必须是绝对路径"},
            )
        if path.suffix.lower() != ".pdf":
            raise HTTPException(
                status_code=400,
                detail={"code": "bad_path", "message": "仅支持 PDF 文件"},
            )
        if not path.exists() or not path.is_file():
            raise HTTPException(
                status_code=400,
                detail={"code": "file_missing", "message": f"文件不存在：{path}"},
            )
        if path.stat().st_size > 2 * 1024 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail={"code": "too_large", "message": "PDF 超过 2GB 限制"},
            )

        file_hash = req.file_hash or await asyncio.to_thread(file_sha256, path)
        doc_id = document_id_for(
            req.library_id, req.item_key, req.attachment_key, file_hash
        )
        existing = state.db.get_document(doc_id)
        if existing and existing["file_hash"] == file_hash and not req.force:
            segs = state.db.get_segments(doc_id)
            return {
                "document": state.document_payload(existing),
                "segmentCount": len(segs),
                "cached": True,
            }

        try:
            parsed = await asyncio.to_thread(parse_pdf, path, req.title)
        except Exception as exc:
            log.exception("parse failed")
            raise HTTPException(
                status_code=422,
                detail={"code": "parse_error", "message": f"PDF 解析失败：{exc}"},
            ) from exc

        base = {
            "id": doc_id,
            "library_id": req.library_id,
            "item_key": req.item_key,
            "attachment_key": req.attachment_key,
            "file_hash": parsed["file_hash"],
            "pdf_path": str(path),
            "title": req.title or parsed["title"],
            "pages": parsed["pages"],
            "alignment": parsed["alignment"],
            "alignment_note": parsed["alignment_note"],
            "scanned": parsed["scanned"],
            "text_chars": parsed["text_chars"],
        }
        state.db.upsert_document(base)
        state.db.replace_segments(doc_id, parsed["segments"])
        doc = state.db.get_document(doc_id) or base
        return {
            "document": state.document_payload(doc),
            "segmentCount": len(parsed["segments"]),
            "coverage": parsed["coverage"],
            "cached": False,
        }

    @app.get("/v1/documents")
    async def list_documents(limit: int = 20):
        docs = state.db.list_documents(limit=max(1, min(limit, 200)))
        return {"documents": [state.document_payload(d) for d in docs]}

    @app.get("/v1/documents/{document_id}")
    async def get_document(document_id: str):
        doc = state.doc_or_404(document_id)
        segments = state.db.get_segments(document_id)
        return {
            "document": state.document_payload(doc),
            "segmentCount": len(segments),
            "translatedCount": sum(1 for s in segments if s.get("translation")),
        }

    @app.get("/v1/documents/{document_id}/segments")
    async def get_segments(document_id: str, page: int | None = None):
        state.doc_or_404(document_id)
        segments = state.db.get_segments(document_id, page)
        return {"segments": segments, "count": len(segments)}

    @app.post("/v1/documents/{document_id}/reparse")
    async def reparse_document(document_id: str):
        doc = state.doc_or_404(document_id)
        pdf_path = Path(doc.get("pdf_path", ""))
        if not pdf_path.exists():
            raise HTTPException(
                status_code=400,
                detail={"code": "file_missing", "message": "PDF 文件已被移动或删除"},
            )
        parsed = await asyncio.to_thread(parse_pdf, pdf_path, doc.get("title", ""))
        state.db.upsert_document(
            {
                **doc,
                "id": document_id,
                "file_hash": parsed["file_hash"],
                "pages": parsed["pages"],
                "alignment": parsed["alignment"],
                "alignment_note": parsed["alignment_note"],
                "scanned": parsed["scanned"],
                "text_chars": parsed["text_chars"],
            }
        )
        state.db.replace_segments(document_id, parsed["segments"])
        updated = state.db.get_document(document_id) or doc
        return {
            "document": state.document_payload(updated),
            "segmentCount": len(parsed["segments"]),
        }

    @app.get("/v1/documents/{document_id}/translation-status")
    async def translation_status(document_id: str, model: str | None = None):
        doc = state.doc_or_404(document_id)
        segments = state.db.get_segments(document_id)
        terms = state.db.list_terms(document_id)
        config = TranslationConfig.build(
            model=model or state.settings.translate_model,
            base_url=state.settings.base_url,
            terms=terms,
            max_output=state.settings.max_output_tokens,
            document_hash=doc.get("file_hash", ""),
        )
        status = evaluate(
            segments,
            config,
            translatable=lambda seg: seg.get("kind") not in SKIP_KINDS
            and _has_prose(seg["text"]),
        )
        payload = status.as_dict()
        payload["config"] = config.as_dict()
        payload["promptVersion"] = config.prompt_version
        return payload

    # ------------------------------------------------------------------ #
    # Jobs
    # ------------------------------------------------------------------ #
    @app.post("/v1/jobs")
    async def create_job(req: TranslateRequest):
        state.require_key()
        state.doc_or_404(req.document_id)
        job = manager().create_translation_job(
            req.document_id,
            pages=req.pages,
            model=req.model,
            force=req.force,
            stale_only=req.stale_only,
            use_babeldoc=req.use_babeldoc,
        )
        return {"job": job}

    @app.get("/v1/jobs")
    async def list_jobs(documentId: str | None = None, limit: int = 20):
        jobs = state.db.list_jobs(documentId, limit=max(1, min(limit, 100)))
        return {"jobs": jobs}

    @app.get("/v1/jobs/{job_id}")
    async def get_job(job_id: str):
        job = state.db.get_job(job_id)
        if not job:
            raise HTTPException(
                status_code=404, detail={"code": "not_found", "message": "任务不存在"}
            )
        return {"job": job}

    @app.get("/v1/jobs/{job_id}/events")
    async def job_events(job_id: str, after: int = -1):
        if not state.db.get_job(job_id):
            raise HTTPException(
                status_code=404, detail={"code": "not_found", "message": "任务不存在"}
            )
        return StreamingResponse(
            manager().stream(job_id, after),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/v1/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str):
        try:
            job = await manager().cancel(job_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail={"code": "not_found", "message": "任务不存在"}
            ) from exc
        return {"job": job}

    @app.post("/v1/jobs/{job_id}/retry")
    async def retry_job(job_id: str):
        state.require_key()
        try:
            job = manager().retry(job_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail={"code": "not_found", "message": "任务不存在"}
            ) from exc
        return {"job": job}

    @app.get("/v1/jobs/{job_id}/artifacts/{kind}")
    async def job_artifact(job_id: str, kind: str):
        job = state.db.get_job(job_id)
        if not job:
            raise HTTPException(
                status_code=404, detail={"code": "not_found", "message": "任务不存在"}
            )
        artifact = next(
            (a for a in job.get("artifacts") or [] if a.get("kind") == kind), None
        )
        if not artifact:
            raise HTTPException(
                status_code=404,
                detail={"code": "no_artifact", "message": f"没有 {kind} 产物"},
            )
        path = Path(artifact["path"]).resolve()
        root = cfg.files_dir.resolve()
        if root not in path.parents and path != root:
            raise HTTPException(
                status_code=403, detail={"code": "forbidden", "message": "非法路径"}
            )
        if not path.exists():
            raise HTTPException(
                status_code=410, detail={"code": "gone", "message": "产物文件已被清理"}
            )
        return FileResponse(path, filename=path.name)

    # ------------------------------------------------------------------ #
    # Chat
    # ------------------------------------------------------------------ #
    @app.post("/v1/chat")
    async def chat(req: ChatRequest, request: Request):
        state.require_key()
        doc = state.doc_or_404(req.document_id)
        segments = state.db.get_segments(req.document_id)
        if not segments:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "not_parsed",
                    "message": "论文尚未解析，请先翻译或重新解析",
                },
            )
        if not req.messages:
            raise HTTPException(
                status_code=400, detail={"code": "no_message", "message": "消息为空"}
            )

        settings = state.settings
        selection = req.selection.model_dump() if req.selection else None
        question = next(
            (m.content for m in reversed(req.messages) if m.role == "user"), ""
        )
        ctx = build_context(
            segments,
            scope=req.scope,
            selection=selection,
            max_chars=req.context_chars or settings.context_chars,
            question=question,
        )
        conversation_id = req.conversation_id or uuid.uuid4().hex[:16]
        state.db.ensure_conversation(
            conversation_id, req.document_id, title=question[:80]
        )

        history = state.db.get_messages(conversation_id)
        if not any(
            m["role"] == "user" and m["content"] == question for m in history[-5:]
        ):
            state.db.add_message(
                {
                    "id": uuid.uuid4().hex,
                    "document_id": req.document_id,
                    "conversation_id": conversation_id,
                    "role": "user",
                    "content": question,
                    "model": "",
                }
            )

        context_block = f"<document>\n{ctx['text']}\n</document>"
        if ctx.get("note"):
            context_block += f"\n（定位说明：{ctx['note']}）"
        terms = state.db.list_terms(req.document_id)
        glossary = glossary_block(terms)
        system = (
            CHAT_SYSTEM
            + (f"\n\n{glossary}" if glossary else "")
            + f"\n\n当前上下文范围：{req.scope}。"
            + "\n\n"
            + context_block
        )
        messages = [{"role": "system", "content": system}]
        for item in req.messages[-12:]:
            if item.role == "system":
                continue
            messages.append({"role": item.role, "content": item.content})
        if not any(
            m["role"] == "user" and m["content"] == question for m in messages[-2:]
        ):
            messages.append({"role": "user", "content": question})

        model = req.model or settings.chat_model
        max_tokens = req.max_output_tokens or settings.max_output_tokens
        if req.image:
            if not req.image.startswith("data:image/") or len(req.image) > 8_000_000:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "image_invalid",
                        "message": "图片必须是 data:image/* 的 Data URL，且不超过 8MB",
                    },
                )
            user_indexes = [i for i, m in enumerate(messages) if m["role"] == "user"]
            if user_indexes:
                index = user_indexes[-1]
                messages[index] = {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": str(messages[index]["content"])},
                        {"type": "image_url", "image_url": {"url": req.image}},
                    ],
                }
        client = state.client()

        async def event_stream():
            buffer: list[str] = []
            usage: dict | None = None
            error: dict | None = None
            cancelled = False
            yield sse(
                "context",
                {
                    "conversationId": conversation_id,
                    "scope": req.scope,
                    "segmentCount": len(ctx["segments"]),
                    "alignment": doc.get("alignment"),
                    "note": ctx.get("note", ""),
                    "documentId": req.document_id,
                },
            )
            try:
                async for event in client.chat_stream(
                    messages,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=0.35,
                    thinking=settings.thinking,
                ):
                    if await request.is_disconnected():
                        cancelled = True
                        break
                    if event["type"] == "delta":
                        buffer.append(event["text"])
                        yield sse("delta", {"text": event["text"]})
                    elif event["type"] == "usage":
                        usage = event["usage"]
                        yield sse("usage", {"usage": usage})
            except DeepSeekError as exc:
                error = exc.as_dict()
                yield sse("error", {"error": error})
            except asyncio.CancelledError:
                cancelled = True
                raise

            answer = "".join(buffer)
            cleaned, citations = validate_citations(answer, ctx["segments"])
            final_usage = usage or {
                "promptTokens": 0,
                "completionTokens": 0,
                "estimated": True,
            }
            cost = estimate_cost(
                model,
                int(final_usage.get("promptTokens", 0)),
                int(final_usage.get("completionTokens", 0)),
                load_pricing(cfg),
            )
            if cost is not None:
                final_usage["costUsd"] = cost
            if not error:
                state.db.add_message(
                    {
                        "id": uuid.uuid4().hex,
                        "document_id": req.document_id,
                        "conversation_id": conversation_id,
                        "role": "assistant",
                        "content": cleaned,
                        "citations": citations,
                        "model": model,
                        "usage": final_usage,
                        "status": "cancelled" if cancelled else "done",
                    }
                )
            yield sse("citations", {"citations": citations})
            yield sse(
                "done",
                {
                    "conversationId": conversation_id,
                    "text": cleaned,
                    "status": (
                        "failed" if error else ("cancelled" if cancelled else "done")
                    ),
                    "usage": final_usage,
                    "model": model,
                },
            )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ------------------------------------------------------------------ #
    # Analysis
    # ------------------------------------------------------------------ #
    @app.post("/v1/analysis")
    async def analysis(req: AnalysisRequest, request: Request):
        state.require_key()
        if not req.document_ids:
            raise HTTPException(
                status_code=400,
                detail={"code": "no_documents", "message": "未选择论文"},
            )
        for document_id in req.document_ids:
            state.doc_or_404(document_id)
        settings = state.settings
        selection = req.selection.model_dump() if req.selection else None
        text, marker_map, docs = build_analysis_context(
            state.db,
            req.document_ids,
            kind=req.kind,
            selection=selection,
            max_chars=max(settings.context_chars, 8000),
        )
        if not marker_map:
            raise HTTPException(
                status_code=409,
                detail={"code": "not_parsed", "message": "所选论文尚未解析，无法分析"},
            )
        messages = build_analysis_messages(
            req.kind,
            text,
            docs,
            duration_minutes=req.duration_minutes,
            focus=req.focus,
        )
        model = req.model or settings.analysis_model
        client = state.client()

        async def event_stream():
            buffer: list[str] = []
            usage: dict | None = None
            error: dict | None = None
            yield sse("context", {"kind": req.kind, "documents": docs, "model": model})
            try:
                async for event in client.chat_stream(
                    messages,
                    model=model,
                    max_tokens=min(settings.max_output_tokens * 2, 16384),
                    temperature=0.3,
                    thinking=settings.thinking,
                ):
                    if await request.is_disconnected():
                        break
                    if event["type"] == "delta":
                        buffer.append(event["text"])
                        yield sse("delta", {"text": event["text"]})
                    elif event["type"] == "usage":
                        usage = event["usage"]
            except DeepSeekError as exc:
                error = exc.as_dict()
                yield sse("error", {"error": error})

            raw = "".join(buffer)
            cleaned, citations = validate_multi_citations(raw, marker_map)
            final_usage = usage or {
                "promptTokens": 0,
                "completionTokens": 0,
                "estimated": True,
            }
            cost = estimate_cost(
                model,
                int(final_usage.get("promptTokens", 0)),
                int(final_usage.get("completionTokens", 0)),
                load_pricing(cfg),
            )
            if cost is not None:
                final_usage["costUsd"] = cost
            if cleaned and not error:
                state.db.save_analysis(
                    {
                        "id": uuid.uuid4().hex,
                        "document_ids": req.document_ids,
                        "kind": req.kind,
                        "input": {
                            "focus": req.focus,
                            "durationMinutes": req.duration_minutes,
                            "selection": selection,
                        },
                        "result": cleaned,
                        "model": model,
                    }
                )
            yield sse("citations", {"citations": citations})
            yield sse(
                "done",
                {
                    "kind": req.kind,
                    "text": cleaned,
                    "status": "failed" if error else "done",
                    "usage": final_usage,
                    "model": model,
                },
            )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ------------------------------------------------------------------ #
    # Glossary
    # ------------------------------------------------------------------ #
    @app.get("/v1/glossary")
    async def list_glossary(documentId: str | None = None):
        return {"terms": state.db.list_terms(documentId)}

    @app.post("/v1/glossary")
    async def create_term(term: TermInput):
        saved = state.db.upsert_term(
            {
                "id": uuid.uuid4().hex[:12],
                "document_id": term.document_id,
                "source": term.source,
                "target": term.target,
                "scope": term.scope,
                "status": term.status,
                "note": term.note,
            }
        )
        affected = 0
        if term.document_id:
            affected = sum(
                1
                for seg in state.db.get_segments(term.document_id)
                if seg.get("translation") and term.source.lower() in seg["text"].lower()
            )
        return {"term": saved, "affectedSegments": affected}

    @app.patch("/v1/glossary/{term_id}")
    async def patch_term(term_id: str, patch: TermPatch):
        terms = {t["id"]: t for t in state.db.list_terms()}
        if term_id not in terms:
            raise HTTPException(
                status_code=404, detail={"code": "not_found", "message": "术语不存在"}
            )
        current = terms[term_id]
        updated = state.db.upsert_term(
            {
                "id": term_id,
                "document_id": current.get("document_id"),
                "source": current["source"],
                "target": patch.target or current["target"],
                "scope": current["scope"],
                "status": patch.status or current["status"],
                "note": (
                    patch.note if patch.note is not None else current.get("note", "")
                ),
            }
        )
        return {"term": updated}

    @app.delete("/v1/glossary/{term_id}")
    async def delete_term(term_id: str):
        if not state.db.delete_term(term_id):
            raise HTTPException(
                status_code=404, detail={"code": "not_found", "message": "术语不存在"}
            )
        return {"deleted": True}

    @app.post("/v1/glossary/extract")
    async def glossary_extract(req: ExtractTermsRequest):
        state.require_key()
        state.doc_or_404(req.document_id)
        segments = state.db.get_segments(req.document_id)
        model = req.model or state.settings.chat_model
        try:
            candidates = await extract_terms(
                state.client(), segments, model=model, max_terms=req.max_terms
            )
        except DeepSeekError as exc:
            raise HTTPException(status_code=502, detail=exc.as_dict()) from exc
        saved = []
        for candidate in candidates:
            saved.append(
                state.db.upsert_term(
                    {
                        "id": uuid.uuid4().hex[:12],
                        "document_id": req.document_id,
                        "source": candidate["source"],
                        "target": candidate["target"],
                        "scope": "paper",
                        "status": "suggested",
                        "note": candidate.get("note", ""),
                    }
                )
            )
        return {"terms": saved, "count": len(saved)}

    # ------------------------------------------------------------------ #
    # Reading state / conversations / search
    # ------------------------------------------------------------------ #
    @app.get("/v1/reading/{document_id}")
    async def get_reading(document_id: str):
        state.doc_or_404(document_id)
        return {"state": state.db.get_reading_state(document_id) or {}}

    @app.put("/v1/reading/{document_id}")
    async def put_reading(document_id: str, patch: ReadingStatePatch):
        state.doc_or_404(document_id)
        data = patch.model_dump(exclude_none=True)
        return {"state": state.db.save_reading_state(document_id, **data)}

    @app.get("/v1/conversations")
    async def list_conversations(documentId: str):
        return {"conversations": state.db.list_conversations(documentId)}

    @app.get("/v1/analyses")
    async def list_analyses(documentId: str, limit: int = 10):
        state.doc_or_404(documentId)
        return {
            "analyses": state.db.list_analyses(documentId, limit=max(1, min(limit, 50)))
        }

    @app.get("/v1/conversations/{conversation_id}/messages")
    async def conversation_messages(conversation_id: str, limit: int = 200):
        return {"messages": state.db.get_messages(conversation_id, limit=limit)}

    @app.post("/v1/conversations/{conversation_id}/messages")
    async def persist_message(conversation_id: str, message: PersistMessage):
        if message.document_id:
            state.db.ensure_conversation(
                conversation_id,
                message.document_id,
                title=message.content[:80] if message.role == "user" else "",
            )
        state.db.add_message(
            {
                "id": uuid.uuid4().hex,
                "document_id": message.document_id or "",
                "conversation_id": conversation_id,
                "role": message.role,
                "content": message.content,
                "citations": message.citations,
                "model": message.model,
                "usage": message.usage,
                "status": message.status,
            }
        )
        return {"ok": True}

    @app.post("/v1/search")
    async def search(req: SearchRequest):
        state.doc_or_404(req.document_id)
        hits = state.db.search(
            req.document_id, req.query, limit=max(1, min(req.limit, 30))
        )
        return {"hits": hits}

    return app
