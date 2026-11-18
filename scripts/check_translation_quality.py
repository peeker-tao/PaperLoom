"""Run a translation job and print source/translation pairs for quality review.

This is the honest way to judge translation quality: it shows what the model
actually returned for real paragraphs, next to the source, and flags output that
looks truncated or untranslated.

Usage (service must be running, a real API key must be configured):

    python scripts/check_translation_quality.py --document-id <id> --pages 1-2
    python scripts/check_translation_quality.py --pdf paper.pdf --pages 1 --register
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SENTENCE_END = tuple(".!?:。！？；;")


def request(
    base: str, path: str, token: str, *, method: str = "GET", body: dict | None = None
):
    data = None
    headers = {"X-PaperLoom-Token": token}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"{base}{path}", data=data, headers=headers, method=method
    )
    with urllib.request.urlopen(req, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_pages(spec: str) -> list[int] | None:
    if not spec:
        return None
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            pages.update(range(int(start), int(end) + 1))
        elif part:
            pages.add(int(part))
    return sorted(pages)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-id", default="")
    parser.add_argument("--pdf", default="", help="register this PDF first")
    parser.add_argument("--register", action="store_true", help="force re-parse")
    parser.add_argument("--library-id", default="1")
    parser.add_argument("--item-key", default="QUALITYCHECK")
    parser.add_argument("--attachment-key", default="QUALITY01")
    parser.add_argument("--pages", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--port", type=int, default=23151)
    parser.add_argument("--limit", type=int, default=8, help="pairs to print")
    parser.add_argument("--wait", type=int, default=600)
    args = parser.parse_args()

    base = f"http://127.0.0.1:{args.port}"
    token = (
        (Path.home() / "AppData" / "Roaming" / "PaperLoom" / "token")
        .read_text(encoding="utf-8")
        .strip()
    )

    status = request(base, "/v1/status", token)
    print(
        f"service {status['version']} llm={status.get('llm')} key={status['apiKey']['configured']}"
    )
    if status.get("llm") != "live":
        print("! service is in fake-LLM mode; set a real API key for meaningful output")

    document_id = args.document_id
    if args.pdf:
        body = {
            "libraryId": args.library_id,
            "itemKey": args.item_key,
            "attachmentKey": args.attachment_key,
            "pdfPath": str(Path(args.pdf).resolve()),
            "title": Path(args.pdf).stem,
        }
        if args.register:
            body["force"] = True
        registered = request(
            base, "/v1/documents/register", token, method="POST", body=body
        )
        document_id = registered["document"]["id"]
        print(
            f"document {document_id} segments={registered['segmentCount']} "
            f"cached={registered.get('cached')} reparsed={registered.get('reparsed')}"
        )
    if not document_id:
        print("need --document-id or --pdf", file=sys.stderr)
        return 2

    pages = parse_pages(args.pages)
    job_body: dict = {"documentId": document_id, "force": True}
    if pages:
        job_body["pages"] = pages
    if args.model:
        job_body["model"] = args.model
    job = request(base, "/v1/jobs", token, method="POST", body=job_body)["job"]
    print(f"job {job['id']} state={job['state']}")

    deadline = time.time() + args.wait
    final = job
    while time.time() < deadline:
        time.sleep(1.5)
        final = request(base, f"/v1/jobs/{job['id']}", token)["job"]
        if final["state"] in {"succeeded", "failed", "cancelled", "interrupted"}:
            break
        progress = final.get("progress") or {}
        print(
            f"  {final['state']} {progress.get('done', 0)}/{progress.get('total', 0)} "
            f"{progress.get('message', '')}",
            flush=True,
        )
    print(
        f"final state={final['state']} usage={final.get('usage')} layout={(final.get('layout') or {}).get('state')}"
    )
    if final.get("error"):
        print("error:", final["error"])
        return 1

    segments = request(base, f"/v1/documents/{document_id}/segments", token)["segments"]
    pairs = [s for s in segments if s.get("translation")]
    if pages:
        pairs = [s for s in pairs if s["page"] in pages]
    print(f"\ntranslated {len(pairs)} segments\n")

    problems = 0
    for seg in pairs[: args.limit]:
        src, dst = seg["text"], seg["translation"]
        print("=" * 78)
        print(
            f"[{seg['id']}] p{seg['page']} kind={seg['kind']} src={len(src)} dst={len(dst)}"
        )
        print("SRC:", src[:500])
        print("DST:", dst[:500])
        flags = []
        if len(dst) < len(src) * 0.25 and len(src) >= 120:
            flags.append("too_short")
        if not re.search(r"[\u4e00-\u9fff]", dst):
            flags.append("no_chinese")
        if dst.strip() == src.strip():
            flags.append("untranslated")
        # Only prose is expected to end with punctuation; titles, headings and
        # keyword lines legitimately do not.
        if seg["kind"] in {"body", "abstract"} and not dst.rstrip().endswith(
            tuple("。！？；：”）」")
        ):
            flags.append("no_final_punct")
        if flags:
            problems += 1
            print("FLAGS:", ", ".join(flags))

    ratios = sorted(len(s["translation"]) / max(1, len(s["text"])) for s in pairs)
    if ratios:
        print(
            f"\nlength ratio min={ratios[0]:.2f} median={ratios[len(ratios) // 2]:.2f} "
            f"max={ratios[-1]:.2f} | flagged {problems}/{len(pairs)}"
        )
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
