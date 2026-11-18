"""Export a registered paper as Markdown (English first, Chinese after).

Usage:
    python scripts/export_markdown.py --document-id <id> [--out paper.md]
    python scripts/export_markdown.py --document-id <id> --references

The service must be running. The output is the same text the plugin's
"复制 Markdown" button produces, so this doubles as a way to check the reading
view without opening Zotero.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def api(base: str, path: str, token: str) -> dict:
    request = urllib.request.Request(f"{base}{path}", headers={"X-PaperLoom-Token": token})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def default_token() -> str:
    candidate = Path(os.environ.get("APPDATA", "")) / "PaperLoom" / "token"
    if candidate.is_file():
        return candidate.read_text(encoding="utf-8").strip()
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--port", type=int, default=23151)
    parser.add_argument("--token", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--original", action="store_true", help="include the English source")
    parser.add_argument("--translation", action="store_true", help="include the translation")
    parser.add_argument("--no-pages", action="store_true", help="omit page markers")
    parser.add_argument("--references", action="store_true", help="include the reference list")
    args = parser.parse_args()

    token = args.token or default_token()
    if not token:
        print("no instance token found (start the service once)", file=sys.stderr)
        return 2
    base = f"http://127.0.0.1:{args.port}"

    params: list[str] = []
    if args.original:
        params.append("original=true")
    if args.translation:
        params.append("translation=true")
    if not args.original and not args.translation:
        # Default is bilingual; be explicit for clarity.
        params.extend(["original=true", "translation=true"])
    if args.no_pages:
        params.append("pages=false")
    if args.references:
        params.append("references=true")
    query = ("?" + "&".join(params)) if params else ""

    try:
        payload = api(base, f"/v1/documents/{args.document_id}/markdown{query}", token)
    except urllib.error.HTTPError as exc:
        print(f"request failed: {exc.code} {exc.reason}", file=sys.stderr)
        return 1

    markdown = payload["markdown"]
    target = Path(args.out) if args.out else Path(payload["filename"])
    # Always UTF-8 without BOM: this file is meant to be opened in an editor.
    target.write_text(markdown, encoding="utf-8")

    stats = payload["stats"]
    print(f"wrote {target} ({stats['chars']} chars, {stats['bytes']} bytes)")
    print(
        f"  english words: {stats['englishWords']}  "
        f"chinese chars: {stats['chineseChars']}  segments: {stats['segments']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
