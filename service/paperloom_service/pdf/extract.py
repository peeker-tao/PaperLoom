"""Extract text lines with coordinates and merge them into paragraphs.

Only text-layer PDFs are supported. Scanned PDFs are detected and reported
instead of being silently translated into nonsense.
"""

from __future__ import annotations

import hashlib
import logging
import re
import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTChar, LTTextContainer, LTTextLine

log = logging.getLogger("paperloom.pdf")

MIN_CHARS_PER_PAGE = 60
SENTENCE_END = tuple(".!?:。！？；;")
MATH_CHARS = set("∑∫√±≤≥≈∈∂∇αβγθλμσφωΩΔπ×÷≠∞")
CAPTION_RE = re.compile(
    r"^(fig(?:ure)?\.?|table|tab\.|algorithm|scheme)\s*\d+", re.IGNORECASE
)
SECTION_RE = re.compile(r"^(\d+(\.\d+)*|[IVX]+\.)\s+\S")
REFERENCE_RE = re.compile(r"^\[\d+\]|^[A-Z][a-z]+,\s+[A-Z]\.|^doi:", re.IGNORECASE)
PAGE_NUMBER_RE = re.compile(r"^\s*(page\s*)?\d{1,4}\s*$", re.IGNORECASE)


@dataclass
class TextLine:
    page: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    bold: bool = False

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def _line_from_layout(line: LTTextLine, page: int) -> TextLine | None:
    text = line.get_text().strip()
    if not text:
        return None
    chars = [c for c in line if isinstance(c, LTChar)]
    if chars:
        size = statistics.median(c.size for c in chars)
        bold = any("bold" in (c.fontname or "").lower() for c in chars)
    else:
        size = line.height or 10.0
        bold = False
    return TextLine(
        page=page,
        text=text,
        x0=float(line.x0),
        y0=float(line.y0),
        x1=float(line.x1),
        y1=float(line.y1),
        size=float(size or 10.0),
        bold=bold,
    )


def extract_lines(path: Path) -> tuple[list[TextLine], dict[int, tuple[float, float]]]:
    """Return all horizontal text lines with page dimensions."""
    laparams = LAParams(
        line_margin=0.25, char_margin=2.0, word_margin=0.1, boxes_flow=None
    )
    lines: list[TextLine] = []
    sizes: dict[int, tuple[float, float]] = {}
    for page_number, layout in enumerate(
        extract_pages(str(path), laparams=laparams), start=1
    ):
        sizes[page_number] = (float(layout.width), float(layout.height))
        for element in layout:
            if not isinstance(element, LTTextContainer):
                continue
            for child in element:
                if not isinstance(child, LTTextLine):
                    continue
                # Skip rotated / vertical text: it breaks reading order.
                matrix = getattr(child, "matrix", (1, 0, 0, 1, 0, 0))
                if abs(matrix[1]) > 1e-3 or abs(matrix[2]) > 1e-3:
                    continue
                line = _line_from_layout(child, page_number)
                if line:
                    lines.append(line)
    return lines, sizes


def _order_page(lines: list[TextLine], width: float) -> list[TextLine]:
    """Order lines left-to-right, top-to-bottom, handling two-column layouts."""
    if not lines:
        return []
    mid = width / 2
    left = [
        ln for ln in lines if ln.x1 < mid + width * 0.02 and ln.x0 < mid - width * 0.05
    ]
    right = [
        ln for ln in lines if ln.x0 > mid - width * 0.02 and ln.x1 > mid + width * 0.05
    ]
    full = [ln for ln in lines if ln not in left and ln not in right]
    is_two_column = (
        len(left) >= 5
        and len(right) >= 5
        and len(full) <= max(6, int(len(lines) * 0.35))
    )
    if not is_two_column:
        return sorted(lines, key=lambda ln: (-round(ln.y1, 1), ln.x0))

    col_top = max(max(ln.y1 for ln in left), max(ln.y1 for ln in right))
    col_bottom = min(min(ln.y0 for ln in left), min(ln.y0 for ln in right))
    before = sorted(
        [ln for ln in full if ln.y0 >= col_top - 2], key=lambda ln: (-ln.y1, ln.x0)
    )
    after = sorted(
        [ln for ln in full if ln.y1 <= col_bottom + 2], key=lambda ln: (-ln.y1, ln.x0)
    )
    inside = [ln for ln in full if ln not in before and ln not in after]
    left_col = sorted(
        left + [ln for ln in inside if ln.x0 < mid], key=lambda ln: -ln.y1
    )
    right_col = sorted(
        right + [ln for ln in inside if ln.x0 >= mid], key=lambda ln: -ln.y1
    )
    return before + left_col + right_col + after


def _drop_running_heads(
    pages: dict[int, list[TextLine]], sizes: dict[int, tuple[float, float]]
) -> dict[int, list[TextLine]]:
    repeated: dict[str, int] = {}
    for lines in pages.values():
        for text in {ln.text for ln in lines}:
            repeated[text] = repeated.get(text, 0) + 1
    total_pages = max(1, len(pages))
    threshold = max(2, int(total_pages * 0.3))
    cleaned: dict[int, list[TextLine]] = {}
    for page, lines in pages.items():
        _, height = sizes.get(page, (612.0, 792.0))
        kept: list[TextLine] = []
        for ln in lines:
            in_margin = ln.y1 > height * 0.94 or ln.y0 < height * 0.055
            if not in_margin:
                kept.append(ln)
                continue
            if PAGE_NUMBER_RE.match(ln.text):
                continue
            if repeated.get(ln.text, 0) >= threshold:
                continue
            if page == 1 and ln.size >= 14:
                kept.append(ln)  # keep the title block
                continue
            if len(ln.text) <= 4:
                continue
            kept.append(ln)
        cleaned[page] = kept
    return cleaned


def _can_merge(cur: list[TextLine], line: TextLine, median_width: float) -> bool:
    prev = cur[-1]
    if prev.page != line.page:
        return False
    if CAPTION_RE.match(line.text) or SECTION_RE.match(line.text):
        return False
    if line.bold and not prev.bold and line.size > prev.size * 1.05:
        return False
    gap = prev.y0 - line.y1
    if gap < -prev.height * 0.4 or gap > max(prev.size, line.size) * 0.9:
        return False
    # Allow small first-line indentation of a paragraph continuation.
    if abs(line.x0 - cur[0].x0) > max(60.0, median_width * 0.12):
        return False
    if prev.size and line.size and not (0.72 <= line.size / prev.size <= 1.38):
        return False
    return not (prev.width < median_width * 0.72 and prev.text.endswith(SENTENCE_END))


def _join(a: str, b: str) -> str:
    if not a:
        return b
    if a.endswith("-") and b[:1].islower():
        return a[:-1] + b
    if re.search(r"[\u4e00-\u9fff]$", a) or re.match(r"^[\u4e00-\u9fff]", b):
        return a + b
    return a + " " + b


def _classify(seg: dict, page: int, pages: int, body_size: float) -> str:
    text = seg["text"]
    size = seg.get("size", body_size)
    if (
        page == 1
        and seg["ordinal"] <= 1
        and size >= body_size * 1.25
        and len(text) < 400
    ):
        return "title"
    if CAPTION_RE.match(text):
        return "caption"
    if len(text) < 160 and size >= body_size * 1.08 and not text.rstrip().endswith("."):
        return "heading"
    if SECTION_RE.match(text) and len(text) < 160:
        return "heading"
    if pages and page >= pages * 0.75 and REFERENCE_RE.match(text):
        return "reference"
    if len(text) < 200 and _math_ratio(text) >= 0.12:
        return "formula"
    if page == 1 and re.match(r"^abstract\b", text, re.IGNORECASE):
        return "abstract"
    return "body"


def _math_ratio(text: str) -> float:
    meaningful = [c for c in text if not c.isspace()]
    if not meaningful:
        return 0.0
    return sum(1 for c in meaningful if c in MATH_CHARS) / len(meaningful)


def _merge_page(lines: list[TextLine], page: int, body_size: float) -> list[dict]:
    if not lines:
        return []
    widths = [ln.width for ln in lines if ln.width > 0]
    median_width = statistics.median(widths) if widths else 300.0
    groups: list[list[TextLine]] = []
    for line in lines:
        if groups and _can_merge(groups[-1], line, median_width):
            groups[-1].append(line)
        else:
            groups.append([line])

    segments: list[dict] = []
    for index, group in enumerate(groups):
        first, _last = group[0], group[-1]
        text = first.text
        for line in group[1:]:
            text = _join(text, line.text)
        seg = {
            "id": f"p{page}-s{index}",
            "page": page,
            "ordinal": index,
            "text": text,
            "bbox": [
                round(min(ln.x0 for ln in group), 2),
                round(min(ln.y0 for ln in group), 2),
                round(max(ln.x1 for ln in group), 2),
                round(max(ln.y1 for ln in group), 2),
            ],
            "size": round(statistics.median(ln.size for ln in group), 2),
            "align": "merged" if len(group) > 1 else "exact",
        }
        seg["kind"] = _classify(seg, page, 0, body_size)
        segments.append(seg)
    return segments


def parse_pdf(path: Path, title: str = "") -> dict:
    """Parse a PDF into a document dict with segments and alignment quality."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    lines, sizes = extract_lines(path)
    page_count = max(sizes) if sizes else 1
    by_page: dict[int, list[TextLine]] = {p: [] for p in sizes}
    for line in lines:
        by_page.setdefault(line.page, []).append(line)
    by_page = _drop_running_heads(by_page, sizes)

    ordered = {
        p: _order_page(by_page.get(p, []), sizes.get(p, (612.0, 0))[0]) for p in sizes
    }
    all_sizes = [ln.size for p in ordered for ln in ordered[p] if ln.size > 0]
    body_size = statistics.median(all_sizes) if all_sizes else 10.0

    segments: list[dict] = []
    for page in sorted(ordered):
        page_segments = _merge_page(ordered[page], page, body_size)
        for seg in page_segments:
            seg["kind"] = _classify(seg, page, page_count, body_size)
            segments.append(seg)

    # Merge paragraphs that continue across a page break.
    merged_segments: list[dict] = []
    for seg in segments:
        prev = merged_segments[-1] if merged_segments else None
        if (
            prev
            and prev["page"] == seg["page"] - 1
            and not prev["text"].rstrip().endswith(SENTENCE_END)
            and re.match(r"^[a-z(]", seg["text"])
            and prev["kind"] in {"body", "abstract"}
            and seg["kind"] in {"body", "abstract"}
        ):
            prev["text"] = _join(prev["text"], seg["text"])
            prev["bbox"] = [
                min(prev["bbox"][0], seg["bbox"][0]),
                prev["bbox"][1],
                max(prev["bbox"][2], seg["bbox"][2]),
                seg["bbox"][3],
            ]
            prev["align"] = "merged"
            continue
        merged_segments.append(seg)

    # Re-number ids sequentially so they remain stable and readable.
    for index, seg in enumerate(merged_segments):
        seg["id"] = f"p{seg['page']}-s{seg['ordinal']}"
        seg["index"] = index

    extracted_chars = sum(len(ln.text) for p in by_page for ln in by_page[p])
    segment_chars = sum(len(seg["text"]) for seg in merged_segments)
    pages_with_text = sum(
        1
        for p in by_page
        if sum(len(ln.text) for ln in by_page[p]) >= MIN_CHARS_PER_PAGE
    )
    scanned = pages_with_text < max(1, int(page_count * 0.5))
    coverage = (segment_chars / extracted_chars) if extracted_chars else 0.0

    alignment = "segment"
    note = "段落级对齐（按文本块合并）"
    if scanned:
        alignment = "none"
        note = "未检测到可用文本层，疑似扫描件"
    elif coverage < 0.5 or len(merged_segments) < 3:
        alignment = "page"
        note = "段落合并置信度低，仅提供页面级定位"

    return {
        "title": title or _guess_title(merged_segments, path),
        "pages": page_count,
        "segments": merged_segments,
        "alignment": alignment,
        "alignment_note": note,
        "scanned": scanned,
        "text_chars": extracted_chars,
        "coverage": round(coverage, 3),
        "file_hash": file_sha256(path),
    }


def _guess_title(segments: Iterable[dict], path: Path) -> str:
    for seg in segments:
        if seg.get("kind") in {"title", "heading"}:
            return seg["text"][:300]
    for seg in segments:
        if len(seg["text"]) > 20:
            return seg["text"][:300]
    return path.stem


def extract_document(path: Path, title: str = "") -> dict:
    return parse_pdf(path, title=title)
