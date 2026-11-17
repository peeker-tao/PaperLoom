"""Live end-to-end verification against the real DeepSeek API.

The script never reads or prints the API key: it only uses the loopback
instance token and asks the service to make the calls. Use it to check the
real reading flow on a paper you already have.

    python scripts/verify_live.py --pdf "D:/papers/paper.pdf" --pages 1
    python scripts/verify_live.py --document-id 328058f91a82239c --pages 1

Exit code 0 means every checked step passed. A short JSON report is written to
``--report`` (default ``%TEMP%/paperloom-live-report.json``) without secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

DEFAULT_PORT = 23124


def data_dir() -> pathlib.Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(pathlib.Path.home() / "AppData/Roaming")
        return pathlib.Path(base) / "PaperLoom"
    return pathlib.Path.home() / ".local" / "share" / "PaperLoom"


class Client:
    def __init__(self, port: int):
        self.base = f"http://127.0.0.1:{port}"
        token_file = data_dir() / "token"
        if not token_file.exists():
            raise SystemExit(f"实例令牌不存在：{token_file}（先启动本地服务）")
        self.token = token_file.read_text(encoding="utf-8").strip()

    def _request(self, method: str, path: str, payload=None, timeout: float = 180):
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-PaperLoom-Token": self.token,
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get(self, path: str):
        return self._request("GET", path)

    def post(self, path: str, payload=None):
        return self._request("POST", path, payload)

    def stream(self, path: str, payload):
        """Yield (event, data) tuples from an SSE response."""
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-PaperLoom-Token": self.token,
                "Accept": "text/event-stream",
            },
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            name = None
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if line.startswith("event:"):
                    name = line[6:].strip()
                elif line.startswith("data:"):
                    yield name, json.loads(line[5:])


def cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return cjk / max(1, len(text))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--pdf", default="")
    parser.add_argument("--document-id", default="")
    parser.add_argument("--pages", default="1")
    parser.add_argument("--force", action="store_true", help="ignore the translation cache")
    parser.add_argument("--test-connection", action="store_true", default=True)
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    report: dict = {"steps": {}, "ok": True}

    def record(name: str, ok: bool, **extra):
        report["steps"][name] = {"ok": ok, **extra}
        if not ok:
            report["ok"] = False
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name} " + " ".join(f"{k}={v}" for k, v in extra.items()))

    client = Client(args.port)

    health = client.get("/health")
    record("health", health.get("service") == "paperloom", version=health.get("version"))

    status = client.get("/v1/status")
    if status.get("llm") == "fake":
        print("! 服务运行在假 LLM 模式（PAPERLOOM_FAKE_LLM=1），本报告不代表真实调用")
    record("api_key", bool(status["apiKey"]["configured"]), source=status["apiKey"]["source"])
    if not status["apiKey"]["configured"]:
        print("未配置 API Key，跳过真实调用步骤")
        _write_report(args.report, report)
        return 1

    if args.test_connection:
        test = client.post("/v1/settings/test", {"model": "deepseek-flash"})
        record(
            "test_connection",
            bool(test.get("ok")),
            latencyMs=test.get("latencyMs"),
            endpoint=test.get("baseUrl"),
        )
        if not test.get("ok"):
            print("  错误：", test.get("error", {}).get("message"))

    document_id = args.document_id
    if args.pdf:
        resolved = pathlib.Path(args.pdf).expanduser().resolve()
        if not resolved.is_file():
            raise SystemExit(f"PDF 不存在：{resolved}")
        registered = client.post(
            "/v1/documents/register",
            {
                "libraryId": "verify",
                "itemKey": "VERIFY",
                "attachmentKey": resolved.parent.name,
                "pdfPath": str(resolved),
                "title": resolved.stem,
            },
        )
        document_id = registered["document"]["id"]
        record(
            "register",
            registered["segmentCount"] > 0,
            pages=registered["document"]["pages"],
            segments=registered["segmentCount"],
            alignment=registered["document"]["alignment"],
            scanned=registered["document"]["scanned"],
            coverage=registered.get("coverage"),
        )
    if not document_id:
        raise SystemExit("需要 --pdf 或 --document-id")

    pages = [int(p) for p in str(args.pages).split(",") if p.strip()]
    started = time.time()
    job = client.post(
        "/v1/jobs",
        {
            "documentId": document_id,
            "pages": pages,
            "useBabeldoc": False,
            "force": args.force,
        },
    )["job"]
    while True:
        state = client.get(f"/v1/jobs/{job['id']}")["job"]
        if state["state"] not in {"queued", "running"}:
            break
        if time.time() - started > 300:
            record("translate", False, reason="timeout")
            _write_report(args.report, report)
            return 1
        time.sleep(0.5)
    record(
        "translate",
        state["state"] == "succeeded",
        state=state["state"],
        done=f"{state['progress']['done']}/{state['progress']['total']}",
        seconds=round(time.time() - started, 1),
        promptTokens=(state.get("usage") or {}).get("promptTokens"),
        completionTokens=(state.get("usage") or {}).get("completionTokens"),
        costUsd=(state.get("usage") or {}).get("costUsd"),
        error=(state.get("error") or {}).get("code"),
    )

    segments = client.get(f"/v1/documents/{document_id}/segments?page={pages[0]}")["segments"]
    translated = [s for s in segments if s.get("translation")]
    ratios = [cjk_ratio(s["translation"]) for s in translated]
    record(
        "translations_are_chinese",
        bool(translated) and sum(ratios) / max(1, len(ratios)) > 0.3,
        translated=len(translated),
        page_segments=len(segments),
        avgCjkRatio=round(sum(ratios) / max(1, len(ratios)), 2),
    )
    meta_translated = [
        s["id"] for s in segments if s.get("kind") in {"meta", "noise"} and s.get("translation")
    ]
    record("meta_noise_not_translated", not meta_translated, offenders=len(meta_translated))

    sample = next((s for s in translated if len(s["text"]) > 80), None)
    selection_text = sample["text"][:120] if sample else ""
    conversation = client.stream(
        "/v1/chat",
        {
            "documentId": document_id,
            "scope": "section",
            "selection": {"text": selection_text, "page": pages[0]},
            "messages": [{"role": "user", "content": "这一节的主要论点是什么？请用两句话回答。"}],
        },
    )
    conv_id, answer, citations, usage = None, "", [], None
    for name, data in conversation:
        if name == "context":
            conv_id = data.get("conversationId")
        elif name == "citations":
            citations = data.get("citations") or []
        elif name == "usage":
            usage = data.get("usage")
        elif name == "done":
            answer = data.get("text") or ""
            usage = data.get("usage") or usage
    # Canonical lowercase markers are expected (the UI renders them as citation
    # chips); an uppercase marker means validation did not run.
    leaked = "[[SEG:" in answer or "[[Seg:" in answer
    record(
        "streaming_answer",
        bool(answer) and not leaked,
        chars=len(answer),
        upperMarkersLeaked=leaked,
        canonicalMarkers=answer.count("[[seg:"),
    )
    record("citations_validated", bool(citations), count=len(citations))
    record(
        "answer_is_chinese",
        cjk_ratio(answer) > 0.25,
        avgCjkRatio=round(cjk_ratio(answer), 2),
        costUsd=(usage or {}).get("costUsd"),
    )

    if conv_id:
        followup = client.stream(
            "/v1/chat",
            {
                "documentId": document_id,
                "conversationId": conv_id,
                "scope": "section",
                "selection": {"text": selection_text, "page": pages[0]},
                "messages": [
                    {"role": "user", "content": "这一节的主要论点是什么？请用两句话回答。"},
                    {"role": "assistant", "content": answer},
                    {"role": "user", "content": "那它的实验设置有什么不足？"},
                ],
            },
        )
        follow_text = ""
        for name, data in followup:
            if name == "done":
                follow_text = data.get("text") or ""
        record("follow_up", bool(follow_text), chars=len(follow_text))

        messages = client.get(f"/v1/conversations/{conv_id}/messages")["messages"]
        restore = client.get(f"/v1/conversations?documentId={document_id}")["conversations"]
        record(
            "conversation_persisted",
            len(messages) >= 4 and any(c["id"] == conv_id for c in restore),
            messages=len(messages),
            conversations=len(restore),
        )

    reading = client._request(
        "PUT",
        f"/v1/reading/{document_id}",
        {
            "page": pages[0],
            "mode": "dual",
            "sidebarWidth": 400,
            "selection": {"text": selection_text[:80], "page": pages[0]},
        },
    )["state"]
    record("reading_state", reading["page"] == pages[0], mode=reading["mode"])

    _write_report(args.report, report)
    print("\nOK" if report["ok"] else "\nFAILED")
    return 0 if report["ok"] else 1


def _write_report(path: str, report: dict) -> None:
    target = pathlib.Path(
        path or (pathlib.Path(os.environ.get("TEMP", ".")) / "paperloom-live-report.json")
    )
    report["generatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report: {target}")


if __name__ == "__main__":
    raise SystemExit(main())
