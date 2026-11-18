"""Render the bilingual view to a PNG so it can be reviewed without Zotero.

This uses the same geometry as ``plugin/src/ui/overlay.ts``:

* the PDF page is rasterised with pdfium at the column width;
* each translated paragraph is drawn inside its original bounding box;
* the y axis is flipped (PDF user space is bottom-left, the bitmap is top-left);
* boxes too small for text, and rotated pages, are skipped exactly as the plugin
  does, so the picture shows what the reader would actually see.

Unlike ``preview_overlay.py`` (which needs a browser and pdf.js), this runs fully
offline in Python.

Usage:
    python scripts/preview_overlay_png.py --pdf paper.pdf --pages 1,2
    python scripts/preview_overlay_png.py --document-id <id> --pages 1
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

from overlay_layout import LINE_HEIGHT, fit_font_size, wrap_estimated

MIN_OVERLAY_WIDTH = 16.0
MIN_OVERLAY_HEIGHT = 6.0
# Opaque: a translucent panel lets the English show through and makes the page
# look like it has doubled text.
BACKGROUND = (255, 253, 248, 255)
BORDER = (45, 106, 79, 90)
ACCENT = (45, 106, 79)
INK = (20, 24, 27)
MUTED = (107, 116, 110)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhl.ttc",
    r"C:\Windows\Fonts\simsun.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if os.path.exists(candidate):
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def api(base: str, path: str, token: str) -> dict:
    request = urllib.request.Request(f"{base}{path}", headers={"X-PaperLoom-Token": token})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def local_pdf_path(document_id: str) -> str:
    for candidate in (
        Path(os.environ.get("APPDATA", "")) / "PaperLoom" / "paperloom.sqlite",
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


def wrap(text: str, font: ImageFont.FreeTypeFont, width: float) -> list[str]:
    """Kept for callers that want real metrics; the layout uses estimates."""
    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        if font.getlength(trial) <= width or not current:
            current = trial
            continue
        lines.append(current)
        current = char
    if current:
        lines.append(current)
    return lines


def draw_overlay(
    canvas: Image.Image,
    segment: dict,
    *,
    scale: float,
    page_height: float,
    page_width: float,
) -> bool:
    bbox = segment.get("bbox") or []
    if len(bbox) < 4:
        return False
    x0, y0, x1, y1 = (float(v) for v in bbox)
    if not (x1 > x0 and y1 > y0):
        return False
    # Defensive: a box covering the page would paint over figures and every
    # other paragraph, so it is treated as a bad bbox and skipped.
    if (y1 - y0) > page_height * 0.9 or (x1 - x0) > page_width * 0.98:
        return False
    width = (x1 - x0) * scale
    height = (y1 - y0) * scale
    if width < MIN_OVERLAY_WIDTH or height < MIN_OVERLAY_HEIGHT:
        return False
    text = (segment.get("translation") or "").strip()
    if not text:
        return False
    size = fit_font_size(text, width, height)
    if size is None:
        return False
    left = x0 * scale
    top = (page_height - y1) * scale

    # Draw at an integer size so the estimate and the real glyph advances agree.
    size = max(6, round(size))
    font = load_font(size)
    lines = wrap_estimated(text, size, width - 2)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rectangle([left, top, left + width, top + height], fill=BACKGROUND, outline=BORDER)

    # Top-align: the translation starts where the original paragraph starts, so
    # the eye can follow the same reading order. Centring leaves a large blank
    # strip at the top that reads like a rendering bug.
    y = top + 1
    for line in lines:
        draw.text((left + 1, y), line, font=font, fill=INK)
        y += size * LINE_HEIGHT
    canvas.alpha_composite(layer)
    return True


def build_page(
    pdf_path: Path,
    page_number: int,
    segments: list[dict],
    *,
    column_width: int,
    show_original: bool,
) -> tuple[Image.Image, dict]:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(pdf_path))
    page = document[page_number - 1]
    page_width = float(page.get_width())
    page_height = float(page.get_height())
    scale = column_width / page_width
    bitmap = page.render(scale=scale)
    base = bitmap.to_pil().convert("RGBA")

    page_segments = [s for s in segments if int(s["page"]) == page_number]
    translated = [s for s in page_segments if s.get("translation")]

    translated_column = base.copy()
    drawn = 0
    skipped = 0
    for segment in translated:
        if draw_overlay(
            translated_column,
            segment,
            scale=scale,
            page_height=page_height,
            page_width=page_width,
        ):
            drawn += 1
        else:
            skipped += 1

    if show_original:
        gap = 16
        header = 26
        height = base.height + header
        canvas = Image.new("RGBA", (column_width * 2 + gap, height), (244, 242, 236, 255))
        canvas.alpha_composite(base, (0, header))
        canvas.alpha_composite(translated_column, (column_width + gap, header))
        label_font = load_font(14)
        draw = ImageDraw.Draw(canvas)
        draw.text((4, 4), "原文", font=label_font, fill=MUTED)
        draw.text((column_width + gap + 4, 4), "译文 · 保留版式", font=label_font, fill=ACCENT)
    else:
        header = 26
        canvas = Image.new(
            "RGBA", (column_width, base.height + header), (244, 242, 236, 255)
        )
        canvas.alpha_composite(translated_column, (0, header))
        draw = ImageDraw.Draw(canvas)
        draw.text((4, 4), "译文 · 保留版式", font=load_font(14), fill=ACCENT)

    stats = {
        "page": page_number,
        "segments": len(page_segments),
        "translated": len(translated),
        "drawn": drawn,
        "skipped": skipped,
        "page_width": round(page_width, 1),
        "page_height": round(page_height, 1),
    }
    return canvas, stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-id", default="")
    parser.add_argument("--pdf", default="")
    parser.add_argument("--pages", default="1")
    parser.add_argument("--port", type=int, default=23151)
    parser.add_argument("--token", default="")
    parser.add_argument("--width", type=int, default=820, help="column width in pixels")
    parser.add_argument("--out", default="")
    parser.add_argument("--minimal", action="store_true", help="translated column only")
    args = parser.parse_args()

    base = f"http://127.0.0.1:{args.port}"
    token = args.token or (
        Path(os.environ.get("APPDATA", "")) / "PaperLoom" / "token"
    ).read_text(encoding="utf-8").strip()

    document_id = args.document_id
    if not document_id and args.pdf:
        registered = api(base, "/v1/documents", token)
        for item in registered.get("documents", []):
            if Path(args.pdf).name.split(" - ")[-1][:12] in item.get("title", ""):
                document_id = item["id"]
                break
    if not document_id:
        print("need --document-id (or --pdf for a registered document)", file=sys.stderr)
        return 2

    api(base, f"/v1/documents/{document_id}", token)
    segments = api(base, f"/v1/documents/{document_id}/segments", token)["segments"]
    pdf_path = Path(args.pdf or local_pdf_path(document_id))
    if not pdf_path.is_file():
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        return 2

    pages = [int(p) for p in args.pages.split(",") if p.strip()]
    outputs: list[Path] = []
    for page_number in pages:
        canvas, stats = build_page(
            pdf_path,
            page_number,
            segments,
            column_width=args.width,
            show_original=not args.minimal,
        )
        out_dir = Path(os.environ.get("TEMP", ".")) / "paperloom-preview"
        out_dir.mkdir(parents=True, exist_ok=True)
        target = Path(args.out) if args.out and len(pages) == 1 else (
            out_dir / f"page-{page_number}.png"
        )
        canvas.convert("RGB").save(target)
        outputs.append(target)
        translated_total = sum(1 for s in segments if s.get("translation"))
        print(
            f"page {stats['page']}: {stats['translated']}/{stats['segments']} segments "
            f"translated, {stats['drawn']} overlays drawn, {stats['skipped']} skipped "
            f"| document total {translated_total}/{len(segments)} | {target}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
