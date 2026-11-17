"""Background job manager with persisted events and SSE replay."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import AsyncIterator, Callable

from .config import RuntimeConfig, Settings
from .db import Database, now
from .deepseek import DeepSeekClient, DeepSeekError
from .translate import TranslationCancelled, TranslationError, translate_document

log = logging.getLogger("paperloom.jobs")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class JobManager:
    def __init__(
        self,
        db: Database,
        cfg: RuntimeConfig,
        get_settings: Callable[[], Settings],
        make_client: Callable[[], DeepSeekClient],
    ):
        self.db = db
        self.cfg = cfg
        self.get_settings = get_settings
        self.make_client = make_client
        self._tasks: dict[str, asyncio.Task] = {}
        self._cancels: dict[str, asyncio.Event] = {}
        self._seq: dict[str, int] = {}
        self._subscribers: dict[str, set[asyncio.Queue]] = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def create_translation_job(
        self,
        document_id: str,
        *,
        pages: list[int] | None = None,
        model: str | None = None,
        force: bool = False,
        use_babeldoc: bool | None = None,
    ) -> dict:
        job_id = uuid.uuid4().hex[:16]
        job = {
            "id": job_id,
            "document_id": document_id,
            "state": "queued",
            "stage": "queued",
            "progress": {"done": 0, "total": 0, "message": "排队中"},
            "artifacts": [],
            "options": {
                "pages": pages,
                "model": model,
                "force": force,
                "useBabeldoc": use_babeldoc,
            },
            "created_at": now(),
        }
        self.db.create_job(job)
        self._seq[job_id] = 0
        self._emit(job_id, "job", self._snapshot(job_id))
        self._spawn(job_id)
        return self.db.get_job(job_id) or {}

    def retry(self, job_id: str) -> dict:
        job = self.db.get_job(job_id)
        if not job:
            raise KeyError("job not found")
        options = job.get("options") or {}
        return self.create_translation_job(
            job["documentId"],
            pages=options.get("pages"),
            model=options.get("model"),
            force=options.get("force", False),
            use_babeldoc=options.get("useBabeldoc"),
        )

    async def cancel(self, job_id: str) -> dict:
        job = self.db.get_job(job_id)
        if not job:
            raise KeyError("job not found")
        if job["state"] in {"succeeded", "failed", "cancelled", "interrupted"}:
            return job
        token = self._cancels.get(job_id)
        if token:
            token.set()
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
        self.db.update_job(job_id, state="cancelled", stage="done", progress=job.get("progress"))
        self._emit(job_id, "job", self._snapshot(job_id))
        self._emit(job_id, "done", {"state": "cancelled"})
        return self.db.get_job(job_id) or job

    async def stream(self, job_id: str, after: int = -1) -> AsyncIterator[str]:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(job_id, set()).add(queue)
        last_seq = after
        finished = False
        try:
            for event in self.db.get_events(job_id, after):
                last_seq = max(last_seq, event["seq"])
                yield _sse(event["event"], {"seq": event["seq"], **event["data"]})
                if event["event"] == "done":
                    finished = True
            if finished:
                return
            job = self.db.get_job(job_id)
            if job and job["state"] in {"succeeded", "failed", "cancelled", "interrupted"}:
                return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if event["seq"] <= last_seq:
                    continue
                last_seq = event["seq"]
                yield _sse(event["event"], {"seq": event["seq"], **event["data"]})
                if event["event"] == "done":
                    return
        finally:
            subs = self._subscribers.get(job_id)
            if subs:
                subs.discard(queue)
                if not subs:
                    self._subscribers.pop(job_id, None)

    async def recover(self) -> None:
        """Mark jobs that were running when the service died as interrupted."""
        for job in self.db.latest_unfinished_jobs():
            self.db.update_job(
                job["id"],
                state="interrupted",
                stage="done",
                error={
                    "code": "interrupted",
                    "message": "服务在任务完成前退出，可重试（已完成的段落不会重复翻译）",
                    "retryable": True,
                },
            )
            self._seq[job["id"]] = self._next_seq(job["id"])
            self._append_event(
                job["id"], "error", {"error": {"code": "interrupted", "message": "任务被中断"}}
            )
            self._append_event(job["id"], "done", {"state": "interrupted"})

    async def shutdown(self) -> None:
        for token in self._cancels.values():
            token.set()
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def active_count(self) -> int:
        return sum(1 for task in self._tasks.values() if not task.done())

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _spawn(self, job_id: str) -> None:
        token = asyncio.Event()
        self._cancels[job_id] = token
        task = asyncio.create_task(self._run(job_id, token), name=f"paperloom-job-{job_id}")
        self._tasks[job_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(job_id, None))

    async def _run(self, job_id: str, token: asyncio.Event) -> None:
        job = self.db.get_job(job_id)
        if not job:
            return
        options = job.get("options") or {}
        settings = self.get_settings()
        client = self.make_client()

        async def on_progress(data: dict) -> None:
            self.db.update_job(job_id, progress=data, state="running")
            self._emit(job_id, "progress", data)

        async def on_segment(segment_id: str, text: str, source: str) -> None:
            self._emit(job_id, "segment", {"id": segment_id, "translation": text, "source": source})

        async def on_log(message: str) -> None:
            self._emit(job_id, "log", {"message": message})

        self.db.update_job(job_id, state="running", stage="extracting")
        self._emit(job_id, "job", self._snapshot(job_id))

        try:
            result = await translate_document(
                db=self.db,
                cfg=self.cfg,
                settings=settings,
                client=client,
                document_id=job["documentId"],
                pages=options.get("pages"),
                model=options.get("model"),
                force=bool(options.get("force")),
                use_babeldoc=options.get("useBabeldoc"),
                cancel_token=token,
                on_progress=on_progress,
                on_segment=on_segment,
                on_log=on_log,
            )
            progress = {
                "done": result["translated"],
                "total": result["total"],
                "message": "完成",
            }
            self.db.update_job(
                job_id,
                state="succeeded",
                stage="done",
                progress=progress,
                usage=result["usage"],
                artifacts=result["artifacts"],
            )
            for warning in result.get("warnings", []):
                self._emit(job_id, "log", {"message": warning, "level": "warning"})
            if result.get("failures"):
                self._emit(
                    job_id,
                    "log",
                    {
                        "message": f"{len(result['failures'])} 段翻译失败，可重试补齐",
                        "level": "warning",
                    },
                )
            self._emit(job_id, "job", self._snapshot(job_id))
            self._emit(job_id, "done", {"state": "succeeded", **result})
        except (TranslationCancelled, asyncio.CancelledError):
            self.db.update_job(job_id, state="cancelled", stage="done")
            self._emit(job_id, "job", self._snapshot(job_id))
            self._emit(job_id, "done", {"state": "cancelled"})
        except TranslationError as exc:
            self._fail(job_id, exc.code, exc.message, exc.retryable)
        except DeepSeekError as exc:
            self._fail(job_id, exc.code, exc.message, exc.retryable)
        except Exception as exc:  # noqa: BLE001 - job boundary must not crash the service
            log.exception("job %s crashed", job_id)
            self._fail(job_id, "internal", f"内部错误：{exc}", True)
        finally:
            self._cancels.pop(job_id, None)

    def _fail(self, job_id: str, code: str, message: str, retryable: bool) -> None:
        error = {"code": code, "message": message, "retryable": retryable}
        self.db.update_job(job_id, state="failed", stage="done", error=error)
        self._emit(job_id, "error", {"error": error})
        self._emit(job_id, "job", self._snapshot(job_id))
        self._emit(job_id, "done", {"state": "failed", "error": error})

    def _snapshot(self, job_id: str) -> dict:
        job = self.db.get_job(job_id) or {}
        return {
            "id": job_id,
            "state": job.get("state"),
            "stage": job.get("stage"),
            "progress": job.get("progress"),
            "error": job.get("error"),
            "usage": job.get("usage"),
            "artifacts": job.get("artifacts") or [],
            "documentId": job.get("documentId"),
            "createdAt": job.get("createdAt"),
            "updatedAt": job.get("updatedAt"),
        }

    def _next_seq(self, job_id: str) -> int:
        events = self.db.get_events(job_id, -1)
        return (events[-1]["seq"] + 1) if events else 0

    def _append_event(self, job_id: str, event: str, data: dict) -> int:
        seq = self._seq.get(job_id)
        if seq is None:
            seq = self._next_seq(job_id)
        self._seq[job_id] = seq + 1
        self.db.append_event(job_id, seq, event, data)
        return seq

    def _emit(self, job_id: str, event: str, data: dict) -> None:
        seq = self._append_event(job_id, event, data)
        payload = {"seq": seq, **data}
        for queue in list(self._subscribers.get(job_id, ())):
            try:
                queue.put_nowait({"seq": seq, "event": event, "data": data})
            except asyncio.QueueFull:  # pragma: no cover
                pass
