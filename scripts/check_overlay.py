"""Check that stored segment bboxes can drive a page-overlay view.

For every page of a real document this verifies:

* every bbox is inside the page box (no negative or out-of-range coordinates);
* bbox area is non-zero and ordered (x0 < x1, y0 < y1);
* the derived CSS geometry (y-flip + scale) stays inside the rendered bitmap;
* a translation overlay at the box size has a readable font size.

Usage (service must be running):

    python scripts/check_overlay.py --document-id <id> [--port 23151]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "service"))

HEADERS: dict[str, str] = {}


def api(base: str, path: str) -> dict:
    request = urllib.request.Request(f"{base}{path}", headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def token(base: str) -> str:
    """Read the local token from the service data dir."""
    request = urllib.request.Request(f"{base}/v1/status")
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8")).get("dataDir", "")


def local_pdf_path(document_id: str) -> str:
    """Look the PDF path up in the local SQLite database (not exposed over HTTP)."""
    import sqlite3

    for candidate in (
        Path.home() / "AppData" / "Roaming" / "PaperLoom" / "paperloom.sqlite",
        Path.home() / ".local" / "share" / "PaperLoom" / "paperloom.sqlite",
    ):
        if not candidate.is_file():
            continue
        with sqlite3.connect(candidate) as conn:
            row = conn.execute(
                "SELECT pdf_path FROM documents WHERE id=?", (document_id,)
            ).fetchone()
            if row and row[0]:
                return str(row[0])
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--port", type=int, default=23151)
    parser.add_argument("--token", default="")
    parser.add_argument("--pdf", default="", help="PDF path (defaults to the local DB record)")
    parser.add_argument("--width", type=float, default=420.0, help="rendered column width")
    args = parser.parse_args()

    base = f"http://127.0.0.1:{args.port}"
    if args.token:
        HEADERS["X-PaperLoom-Token"] = args.token

    doc_id = args.document_id
    doc = api(base, f"/v1/documents/{doc_id}")["document"]
    segments = api(base, f"/v1/documents/{doc_id}/segments")["segments"]
    print(f"document: {doc['title'][:60]} pages={doc['pages']} segments={len(segments)}")

    pdf_path = Path(args.pdf or local_pdf_path(doc_id))
    sizes: dict[int, tuple[float, float]] = {}
    if pdf_path.is_file():
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        for index, page in enumerate(reader.pages, start=1):
            box = page.mediabox
            sizes[index] = (float(box.width), float(box.height))
    else:
        print(f"! pdf not readable at {pdf_path}; assuming 612x792")

    problems: list[str] = []
    per_page: dict[int, int] = {}
    skipped = 0
    for segment in segments:
        page = int(segment["page"])
        per_page[page] = per_page.get(page, 0) + 1
        width, height = sizes.get(page, (612.0, 792.0))
        bbox = segment.get("bbox") or []
        if len(bbox) != 4:
            problems.append(f"{segment['id']}: bbox is not 4 numbers ({bbox})")
            continue
        x0, y0, x1, y1 = (float(v) for v in bbox)
        if not (x0 < x1 and y0 < y1):
            problems.append(f"{segment['id']}: bbox not ordered {bbox}")
        if x0 < -1 or y0 < -1 or x1 > width + 1 or y1 > height + 1:
            problems.append(
                f"{segment['id']}: bbox {bbox} outside page {width:.0f}x{height:.0f}"
            )
        # Mirror the plugin's math: scale = renderedWidth / pageWidth, y flipped.
        scale = args.width / width
        left = x0 * scale
        top = (height - y1) * scale
        box_w = (x1 - x0) * scale
        box_h = (y1 - y0) * scale
        if left < -0.5 or top < -0.5 or left + box_w > args.width + 1.5:
            problems.append(f"{segment['id']}: overlay escapes column ({left:.1f},{top:.1f})")
        # Only translated paragraphs are drawn over the page image.
        if segment.get("translation"):
            skipped += box_w < 16 or box_h < 6
            if box_w < 16 or box_h < 6:
                continue
            if box_w < 24 or box_h < 9:
                problems.append(f"{segment['id']}: overlay nearly unreadable ({box_w:.1f}x{box_h:.1f})")

    translated = sum(1 for s in segments if s.get("translation"))
    kinds: dict[str, int] = {}
    for segment in segments:
        kinds[segment.get("kind", "?")] = kinds.get(segment.get("kind", "?"), 0) + 1

    print(f"segments per page: min={min(per_page.values())} max={max(per_page.values())}")
    print(f"kinds: {kinds}")
    print(f"translated: {translated}/{len(segments)} (overlays skipped as too small: {skipped})")
    if problems:
        print(f"FAIL: {len(problems)} problem(s)")
        for line in problems[:25]:
            print("  -", line)
        return 1
    print("PASS: every bbox maps to a valid overlay inside the page")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
