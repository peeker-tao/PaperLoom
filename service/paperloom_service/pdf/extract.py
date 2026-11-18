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

from .figures import insert_figures

log = logging.getLogger("paperloom.pdf")

# Bump whenever segmentation output changes: documents parsed by an older
# version are transparently re-parsed (translations are carried over by text).
# v3: cross-page continuation keeps a single-page bbox; rotated stamps filtered;
#     references/equations/table cells classified.
# v4: author affiliations above the abstract are no longer read as headings.
# v5: the area next to a figure/table caption becomes a ``figure`` segment, so
#     the reading view can show the real picture instead of dropping it.
# v6: table bodies are absorbed cell by cell, and prose that merely mentions a
#     table ("Table 1 shows ...") is no longer typed as a caption.
# v7: two-column papers keep paragraphs whole — a sentence that continues at the
#     top of the next column, or in one visual line that pdfminer split in two,
#     is joined; a heading can no longer swallow the paragraph below it.
# v8: a sentence interrupted by a display equation, a picture or a run-in label
#     ("Training." / "Datasets.") is rejoined, and `(cid:N)` glyph runs are typed
#     as formulas instead of being printed as one-line paragraphs.
PARSER_VERSION = 8

MIN_CHARS_PER_PAGE = 60
# Lines shorter than this carry no prose and only break paragraph merging.
# Real headings/labels in papers are longer (e.g. "3 Method" is 8 chars).
MIN_LINE_CHARS = 3
SENTENCE_END = tuple(".!?:。！？；;")
MATH_CHARS = set("∑∫√±≤≥≈∈∂∇αβγθλμσφωΩΔπ×÷≠∞")
# Math operators that show up in display equations but not in prose.
MATH_OPERATOR_RE = re.compile(r"[=∼∝∥▷◃⊤⊥⟨⟩→←↔∑∫√±≤≥≈∈∉⊂⊆∂∇^_]")
CAPTION_RE = re.compile(
    r"^(fig(?:ure)?\.?|table|tab\.|algorithm|scheme)\s*\d+", re.IGNORECASE
)
# A real caption continues with punctuation right after the label ("Fig. 2: An
# example"); running prose continues with a verb ("Table 1 shows the results",
# "Figure 8 shows qualitative comparison"). Treating that prose as a caption
# made the reading view print a whole paragraph at caption size.
CAPTION_MARK_RE = re.compile(r"[.:|\u2013\u2014-]")
SECTION_RE = re.compile(r"^\d+(\.\d+)*\s+\S")
REFERENCE_RE = re.compile(r"^\[\d+\]|^[A-Z][a-z]+,\s+[A-Z]\.|^doi:", re.IGNORECASE)
# Reference lists use many numbering styles; a single line rarely tells, but a
# run of them does. "1. Achiam, J., Adler, S., ..." is as common as "[12]".
REFERENCE_ENTRY_RE = re.compile(
    r"^(?:\[\d{1,3}\]|\d{1,3}\.)\s+[A-Z][A-Za-z'\-]+,"  # 1. Achiam, J.,
    r"|^\[\d{1,3}\]"
    r"|^[A-Z][a-z]+,\s+[A-Z]\."
    r"|^doi:|^arxiv preprint",
    re.IGNORECASE,
)
REFERENCES_HEADING_RE = re.compile(
    r"^(references?|bibliography|works cited|literature cited)(\s|$)", re.IGNORECASE
)
# A heading that ends the reference block and starts real content again.
POST_REFERENCES_RE = re.compile(
    r"^(appendix|appendices|supplement|supplementary)\b", re.IGNORECASE
)
PAGE_NUMBER_RE = re.compile(r"^\s*(page\s*)?\d{1,4}\s*$", re.IGNORECASE)
# Author/affiliation blocks: superscript markers, emails, institution words.
AUTHOR_MARKERS = re.compile(
    r"[\u2217\u2020\u2021\u00a7\u00b6*\u2020]|\b\d+\s*(?:,|and)\b"
)
AFFILIATION_RE = re.compile(
    r"(universit|institut|laborator|department|school of|college|academy|inc\.|ltd\.|correspond|@[a-z0-9.-]+\.[a-z]{2,})",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def _is_noise(text: str) -> bool:
    """True for fragments with no translatable prose (single chars, numbers)."""
    stripped = text.strip()
    if len(stripped) < 8:
        return True
    letters = sum(1 for c in stripped if c.isalpha())
    return letters < 4 or letters / max(1, len(stripped)) < 0.35


def _is_author_block(text: str) -> bool:
    """Author lists and affiliations should be kept verbatim, not translated."""
    stripped = text.strip()
    if len(stripped) > 400:
        return False
    if EMAIL_RE.search(stripped) or AFFILIATION_RE.search(stripped):
        return True
    # "{a@mails.,b@mails.}tsinghua.edu.cn" — addresses broken across lines defeat
    # the strict email pattern, but the at-signs plus a domain are conclusive.
    if stripped.count("@") >= 1 and re.search(r"\.[a-z]{2,4}\b", stripped):
        return True
    # "Wendi Zheng1∗‡, Jiayan Teng1∗‡, ..." — mostly names + superscripts.
    tokens = [t for t in stripped.split() if t]
    if len(tokens) < 3:
        return False
    marker_hits = len(AUTHOR_MARKERS.findall(stripped))
    capitalized = sum(1 for t in tokens if t[:1].isupper())
    return marker_hits >= 2 and capitalized / len(tokens) > 0.5


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
    # 0 = full width (above or below both columns), 1 = left, 2 = right,
    # 3 = full width below. Set by _order_page; used to tell a paragraph that
    # continues into the next column from two unrelated columns at the same
    # height.
    column: int = 0
    # True when this line is the second half of a visual line that pdfminer
    # split in two: it starts where its predecessor ended, so its left edge says
    # nothing about where the text column starts.
    continuation: bool = False

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


def _is_rotated(line: LTTextLine) -> bool:
    """True when the glyphs are rotated relative to the page.

    Margins stamps (the arXiv identifier, "Downloaded by ...", preprint
    banners) are usually set at 90 degrees. pdfminer exposes the rotation on
    each ``LTChar.matrix``, not on ``LTTextLine.matrix`` (which is the line's
    translation and therefore useless here), so the characters must be checked.
    Rotated text also has to be dropped because it is emitted one glyph at a
    time, which shreds every paragraph it intersects.
    """
    chars = [c for c in line if isinstance(c, LTChar)]
    if not chars:
        return False
    rotated = 0
    for char in chars:
        matrix = getattr(char, "matrix", (1, 0, 0, 1, 0, 0))
        if abs(matrix[1]) > 1e-3 or abs(matrix[2]) > 1e-3:
            rotated += 1
    return rotated * 2 > len(chars)


def _drop_noise_lines(lines: list[TextLine]) -> list[TextLine]:
    """Remove fragments that cannot be prose (bare numbers, stray glyphs).

    Such lines are already classified as ``noise`` later, but keeping them to
    that point corrupts merging: while they sit between two body lines, every
    ``_can_merge`` check sees the fragment instead of the previous sentence and
    breaks the paragraph.
    """
    kept: list[TextLine] = []
    for line in lines:
        text = line.text.strip()
        if len(text) < MIN_LINE_CHARS:
            continue
        # "12.5", "2024" or "-" alone are page furniture, not sentences.
        if not any(c.isalpha() for c in text):
            continue
        kept.append(line)
    return kept


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
                # Rotated text (margin stamps, watermarks) breaks reading order
                # and, being emitted glyph by glyph, shreds paragraphs.
                if _is_rotated(child):
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
        [ln for ln in inside if ln.x0 >= mid] + right, key=lambda ln: -ln.y1
    )
    for line in before:
        line.column = 0
    for line in left_col:
        line.column = 1
    for line in right_col:
        line.column = 2
    for line in after:
        line.column = 3
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


def _can_merge(
    cur: list[TextLine], line: TextLine, median_width: float, body_size: float = 0.0
) -> bool:
    prev = cur[-1]
    if prev.page != line.page:
        return False
    if CAPTION_RE.match(line.text) or SECTION_RE.match(line.text):
        return False
    # Table cells are short, carry no verb chain, and must not be swallowed into
    # a paragraph: "Steps Time Cost SDXL [17] ..." is not a sentence. Display
    # type is exempt: "CogView3: Finer and Faster ..." has no lowercase words
    # either but is a title, not a cell.
    display = body_size > 0 and min(prev.size, line.size) >= body_size * 1.12
    if not display and (
        _looks_like_table_cell(prev.text) or _looks_like_table_cell(line.text)
    ):
        return False
    if line.bold and not prev.bold and line.size > prev.size * 1.05:
        return False

    # pdfminer sometimes splits ONE visual line into two objects when the space
    # before a word is wide. The halves share a baseline and sit side by side in
    # the same column, and all the checks below would treat the second half as a
    # new paragraph — cutting the sentence mid-word ("... directly in 3D space,"
    # + "learning self-" were emitted as two lines at y=401.84).
    same_column = prev.column == line.column
    same_baseline = abs(line.y1 - prev.y1) <= max(2.0, prev.height * 0.4)
    if same_column and same_baseline and line.x0 >= prev.x1 - 2.0:
        line.continuation = True
        return True

    # A paragraph that reaches the bottom of a column continues at the top of
    # the next one; that is how two-column papers are read. Spacing cannot tell
    # this apart from two unrelated columns, so the evidence is typesetting:
    # the last line is either broken mid-word (trailing hyphen) or runs to the
    # full measure without closing the sentence. A short line means the
    # paragraph ended there, and a single-line group is a heading, not prose.
    if not same_column:
        if {prev.column, line.column} - {1, 2}:
            return False
        if len(cur) < 2 or line.text.startswith(("•", "·", "-")):
            return False
        if body_size and (
            abs(prev.size - body_size) > max(0.8, body_size * 0.12)
            or abs(line.size - body_size) > max(0.8, body_size * 0.12)
        ):
            return False
        if prev.text.endswith("-"):
            return True
        open_sentence = not prev.text.endswith(SENTENCE_END)
        return open_sentence and prev.width >= median_width * 0.86

    gap = prev.y0 - line.y1
    if gap < -prev.height * 0.4 or gap > max(prev.size, line.size) * 0.9:
        return False
    if prev.size and line.size and not (0.72 <= line.size / prev.size <= 1.38):
        return False
    # Display type (titles, section headings) is centered or ragged-right, so its
    # left edge says nothing about continuation, and it is by definition not body
    # text. Merging on size + spacing keeps a wrapped title in one piece instead
    # of splitting it into fragments that translate badly on their own.
    if display:
        return not (prev.text.endswith(SENTENCE_END) and len(prev.text) > 40)
    if len(cur) == 1:
        # The first continuation drops back from the indented first line to the
        # column edge; only a real block change moves further than that.
        if abs(line.x0 - cur[0].x0) > max(60.0, median_width * 0.12):
            return False
    else:
        # Paragraph continuation lines all start at the column edge. A line
        # indented relative to that edge is a new paragraph, and one that is
        # outdented belongs to a different block (list, footnote, column).
        # Halves of a split line are excluded: they begin mid-line, so counting
        # them would move the edge to the right and reject every real
        # continuation after them.
        starts = [ln.x0 for ln in cur[1:] if not ln.continuation]
        edge = min(starts) if starts else cur[0].x0
        delta = line.x0 - edge
        tolerance = max(6.0, prev.size * 0.85)
        if delta > tolerance or delta < -tolerance:
            return False
    # Text set in a different size than the body is a caption/heading/footnote.
    # Both sides are checked: comparing only the incoming line let a heading
    # ("1. Introduction", 12pt) swallow the paragraph below it (10pt), which
    # put a chapter title at the head of a paragraph in the reading view.
    if body_size and (
        abs(line.size - body_size) > max(0.8, body_size * 0.12)
        or abs(prev.size - body_size) > max(0.8, body_size * 0.12)
    ):
        return False
    # A short line that closes with punctuation ends the paragraph.
    return not (prev.width < median_width * 0.72 and prev.text.endswith(SENTENCE_END))


def _join(a: str, b: str, vocab: set[str] | None = None) -> str:
    """Join two physical lines, resolving end-of-line hyphens.

    A trailing hyphen is either a typesetting hyphenation ("im-" + "plementing"
    -> "implementing") or part of a compound ("text-" + "to-image" ->
    "text-to-image"). Removing it blindly produces "textto-image", which
    destroys the very terms these papers are about, so the document vocabulary
    decides and the hyphen is kept when there is no evidence either way.

    A space is never inserted after a trailing hyphen: "E-" + "RayZer" is
    "E-RayZer", and "E- RayZer" is not a word in any language.
    """
    if not a:
        return b
    if a.endswith("-"):
        prefix = a[:-1]
        head = re.search(r"([A-Za-z]+)$", prefix)
        tail = re.match(r"([A-Za-z]+)", b)
        if not (head and tail):
            return a + b
        # "E-" + "RayZer": a capital after the hyphen means a name or a
        # compound, never a hyphenated word ("pre-" + "dicts" is lowercase).
        if b[:1].isupper():
            return a + b
        joined = (head.group(1) + tail.group(1)).lower()
        hyphenated = f"{head.group(1)}-{tail.group(1)}".lower()
        if vocab and hyphenated in vocab and joined not in vocab:
            return a + b  # compound word: keep the hyphen
        if vocab and joined in vocab and hyphenated not in vocab:
            return prefix + b  # real hyphenation: drop it
        # "state-of-the-" is a compound continuation, never a hyphenation.
        token = re.search(r"[A-Za-z][A-Za-z-]*$", prefix)
        if token and "-" in token.group(0):
            return a + b
        # No evidence either way: a very short head ("exe-", "re-", "im-")
        # is almost always a broken word, a longer one is usually a compound.
        # A dictionary would settle the rest, but the document vocabulary cannot:
        # a fragment such as "plementing" enters it simply by starting a line.
        return prefix + b if len(head.group(1)) <= 3 else a + b
    if re.search(r"[\u4e00-\u9fff]$", a) or re.match(r"^[\u4e00-\u9fff]", b):
        return a + b
    return a + " " + b


HYPHEN_TOKEN_RE = re.compile(r"\b([A-Za-z]{2,})-([a-z]{2,})\b")


def _repair_hyphenation(text: str, vocab: set[str]) -> str:
    """Resolve leftovers such as "exe-cuting" using the document vocabulary.

    Only touches tokens whose hyphenated form never occurs in the document while
    the glued form does, so legitimate compounds such as ``text-to`` or
    ``super-resolution`` are preserved.
    """
    if not vocab:
        return text

    def fix(match: re.Match) -> str:
        whole = match.group(0)
        glued = match.group(1) + match.group(2)
        if whole.lower() in vocab:
            return whole
        if glued.lower() in vocab:
            return glued
        return whole

    return HYPHEN_TOKEN_RE.sub(fix, text)


def _document_vocab(lines: Iterable[TextLine]) -> set[str]:
    """Lowercased word forms, used only to resolve end-of-line hyphens."""
    vocab: set[str] = set()
    for line in lines:
        for token in re.findall(r"[A-Za-z][A-Za-z-]*[A-Za-z]", line.text):
            vocab.add(token.lower())
    return vocab


def _looks_bibliographic(text: str) -> bool:
    """True for a bibliography entry, whatever numbering style is used.

    Translating a reference list wastes tokens and produces text nobody reads,
    so these are excluded from translation (they stay visible in the PDF).
    """
    stripped = text.strip()
    if len(stripped) < 20 or len(stripped) > 2000:
        return False
    if not REFERENCE_ENTRY_RE.match(stripped):
        return False
    # A bibliographic entry carries a venue, a year or a volume.
    return bool(
        re.search(r"\((?:19|20)\d{2}[a-z]?\)", stripped)
        or re.search(r"\bpp?\.\s*\d", stripped)
        or re.search(r"arXiv[:\s]|doi[:\.]|vol\.\s*\d|Proceedings|Conference", stripped)
    )


def _mark_reference_sections(segments: list[dict]) -> None:
    """Flag everything under a "References" heading as ``reference``.

    Per-segment detection misses entries whose numbering style is unusual, and a
    heading plus a run of entries is a far stronger signal.
    """
    in_references = False
    for seg in segments:
        text = seg["text"].strip()
        kind = seg["kind"]
        if kind == "heading" or len(text) < 40:
            if REFERENCES_HEADING_RE.match(text):
                in_references = True
                continue
            if in_references and POST_REFERENCES_RE.match(text):
                in_references = False
                continue
        if in_references and kind != "title":
            seg["kind"] = "reference"


def _classify(seg: dict, page: int, pages: int, body_size: float) -> str:
    text = seg["text"]
    size = seg.get("size", body_size)
    if _is_noise(text):
        return "noise"
    if _is_author_block(text):
        return "meta"
    if (
        page == 1
        and seg["ordinal"] <= 1
        and size >= body_size * 1.25
        and len(text) < 400
    ):
        return "title"
    if _looks_like_caption(text):
        return "caption"
    if len(text) < 160 and size >= body_size * 1.08 and not text.rstrip().endswith("."):
        return "heading"
    if _looks_like_section_heading(text):
        return "heading"
    if pages and page >= pages * 0.75 and REFERENCE_RE.match(text):
        return "reference"
    if page >= 2 and _looks_bibliographic(text):
        return "reference"
    if _is_math_fragment(text):
        return "formula"
    if len(text) < 200 and _math_ratio(text) >= 0.12:
        return "formula"
    if page == 1 and re.match(r"^abstract\b", text, re.IGNORECASE):
        return "abstract"
    return "body"


def _looks_like_caption(text: str) -> bool:
    """True for "Fig. 2: An example", false for "Table 1 shows the results".

    Both start with a figure/table label, but only the caption is followed by a
    separator. Without this check a full paragraph that merely mentions a table
    is typed as a caption and printed at caption size in the reading view.
    """
    match = CAPTION_RE.match(text.strip())
    if not match:
        return False
    rest = text.strip()[match.end() :].lstrip()
    return bool(rest) and bool(CAPTION_MARK_RE.match(rest))


def _looks_like_section_heading(text: str) -> bool:
    """True for "3 Method", "2.1 Text-to-Image Models", "IV. Results".

    A leading number alone is not enough: figures, tables and equations start
    with numbers too ("1024 (bottom). All prompts are ...", "0 + σtϵ, t, ctext)").
    Real headings are short, the number is small, and a capitalised word follows.
    """
    stripped = text.strip()
    if len(stripped) >= 160:
        return False
    # "1. Achiam, J., Adler, S., et al.: Gpt-4 ..." starts like a section number.
    if _looks_bibliographic(stripped):
        return False
    match = re.match(
        r"^(?P<num>\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+(?P<rest>\S.*)$", stripped
    )
    if match:
        rest = match.group("rest")
        # "0 + σtϵ" / "1024 × 1024" are not headings; "2 Background" is.
        return bool(re.match(r"^[A-Z\u4e00-\u9fff]", rest)) and not _is_math_fragment(
            stripped
        )
    return bool(re.match(r"^[IVX]{1,4}\.\s+[A-Z]", stripped))


def _is_math_fragment(text: str) -> bool:
    """True for display equations and their fragments.

    Such text must not be translated: it carries no prose, and sending it to the
    model produces gibberish that also displaces real paragraphs in a batch.
    """
    stripped = text.strip()
    if not stripped:
        return False
    # pdfminer fails to map some glyphs and prints them as (cid:1) / (cid:0).
    # Those runs are always parts of an equation, never prose: keeping them as
    # body text left fragments like "tgt )(cid:1)." as standalone paragraphs.
    if "(cid:" in stripped:
        return True
    # A line that opens with a closing bracket or a comma is the tail of an
    # equation that was split into two objects ("ψ ), and rendering (f rend").
    if stripped[0] in ",)]}" and len(stripped) < 90:
        return True
    words = re.findall(r"[A-Za-z]{2,}", stripped)
    # "ψ ), and rendering (f rend" — a bracket-riddled short run with no
    # sentence punctuation is a sliced equation line, not a sentence.
    if (
        len(words) <= 8
        and "(" in stripped
        and len(stripped) < 90
        and not re.search(r"\.\s", stripped)
    ):
        return True
    # "q(zt|z0) = N (zt|F (x0, t), σt" — an operator with almost no words.
    if MATH_OPERATOR_RE.search(stripped) and len(words) <= 6:
        return True
    if _math_ratio(stripped) >= 0.06:
        return True
    # Equation number on its own, e.g. "(3)".
    return bool(re.fullmatch(r"\(\s*\d{1,3}[a-z]?\s*\)", stripped))


def _looks_like_table_cell(text: str) -> bool:
    """True for a short cell such as "SDXL [17]" or "Steps Time Cost".

    Cells are terse, contain no sentence verb chain, and are usually a model or
    dataset name: translating them in isolation invents meaning that is not
    there.
    """
    stripped = text.strip()
    if not (0 < len(stripped) < 80):
        return False
    if stripped.endswith(tuple(".!?:;。！？；")):
        return False
    # Metric headers such as "Aes↑ HPS v2↑ ImageReward↑" are never prose.
    if re.search(r"[↑↓▲▼]", stripped):
        return True
    # Prose carries punctuation *between* words, followed by lowercase
    # (". Concretely, E-RayZer"). An abbreviation inside a cell (
    # "Percep. Encoder [7]") is followed by a capital, so it does not count.
    if re.search(r"[.,;:]\s+[a-z]", stripped):
        return False
    tokens = [t for t in stripped.split() if t]
    if not tokens:
        return False
    # A row of words is a header, not a sentence: real prose of this length
    # contains verbs and would carry punctuation (handled above).
    if len(tokens) > 6:
        return False
    # Strip the wrapping punctuation before deciding whether a token is an
    # ordinary lowercase word: "pre-" and "(CID)" are words, not labels.
    bare = [t.strip(".,;:()[]{}\"'") for t in tokens]
    lowercase_words = [t for t in bare if re.fullmatch(r"[a-z]{2,}", t)]
    has_digit = any(c.isdigit() for c in stripped)
    # A short line with no ordinary lowercase word is a label, not a sentence:
    # "Self-supervised?" (a table column header) used to be printed as a
    # one-line paragraph in the middle of the reading view.
    if not lowercase_words and len(stripped) <= 40:
        return True
    # "SDXL [17]" / "0.5, MVImgNet". The token limit matters: without it any
    # sentence carrying a number was taken for a cell, and
    # "supervised 3D reconstruction. Concretely, E-RayZer pre-" disappeared from
    # the reading view along with the rest of its paragraph.
    return has_digit and len(tokens) <= 3 and len(lowercase_words) <= 1


def _mark_layout_fragments(segments: list[dict]) -> None:
    """Reclassify equation fragments and table cells after merging.

    A page-level pass is needed for tables: an isolated short label is often a
    real (if short) sentence, while a run of them is a table.
    """
    by_page: dict[int, list[dict]] = {}
    for seg in segments:
        by_page.setdefault(seg["page"], []).append(seg)
    for page_segments in by_page.values():
        cell_candidates = [
            seg
            for seg in page_segments
            if seg["kind"] == "body" and _looks_like_table_cell(seg["text"])
        ]
        # A table has several such cells; a lone short label is usually a
        # sentence, so require company before flagging them.
        if len(cell_candidates) >= 3:
            for seg in cell_candidates:
                seg["kind"] = "table"


def _mark_affiliations_as_meta(segments: list[dict]) -> None:
    """Flag the author/affiliation block at the top of page 1.

    Affiliation lines such as "2 Zhipu AI" or "1 Tsinghua University" match the
    section-number pattern, so they were classified as headings and showed up in
    the Markdown outline as fake chapters. Real headings never appear before the
    abstract on page 1, which makes them safe to demote.
    """
    abstract_index = None
    for index, seg in enumerate(segments):
        if seg["page"] != 1:
            break
        if seg.get("kind") == "abstract" or re.match(
            r"^abstract\b", seg["text"].strip(), re.IGNORECASE
        ):
            abstract_index = index
            break
    if abstract_index is None:
        return
    for seg in segments[:abstract_index]:
        if seg.get("kind") in {"title"}:
            continue
        text = seg["text"].strip()
        if len(text) > 160:
            continue
        # Keep the visible paper title: it is the only large line in this block.
        if seg.get("kind") == "heading" and len(text) > 40:
            continue
        seg["kind"] = "meta"


def _math_ratio(text: str) -> float:
    meaningful = [c for c in text if not c.isspace()]
    if not meaningful:
        return 0.0
    return sum(1 for c in meaningful if c in MATH_CHARS) / len(meaningful)


def _merge_page(
    lines: list[TextLine], page: int, body_size: float, vocab: set[str] | None = None
) -> list[dict]:
    if not lines:
        return []
    # Measure the body column only: titles, captions and short heading lines
    # would drag the median down and reject valid continuations.
    body_widths = [
        ln.width
        for ln in lines
        if ln.width > 0 and abs(ln.size - body_size) <= max(0.8, body_size * 0.12)
    ]
    widths = body_widths or [ln.width for ln in lines if ln.width > 0]
    median_width = statistics.median(widths) if widths else 300.0
    groups: list[list[TextLine]] = []
    for line in lines:
        if groups and _can_merge(groups[-1], line, median_width, body_size):
            groups[-1].append(line)
        else:
            groups.append([line])

    segments: list[dict] = []
    for index, group in enumerate(groups):
        first, _last = group[0], group[-1]
        text = first.text
        for line in group[1:]:
            text = _join(text, line.text, vocab)
        if vocab:
            text = _repair_hyphenation(text, vocab)
        # A paragraph that runs from one column into the next would otherwise
        # get a box spanning both columns — i.e. most of the sheet — which the
        # overlay view paints over (hiding figures and the rest of the page).
        # Same rule as the cross-page merge below: the part holding more text
        # keeps the box.
        columns = {ln.column for ln in group}
        if len(columns) > 1:
            primary = max(
                columns,
                key=lambda col: sum(len(ln.text) for ln in group if ln.column == col),
            )
            box_lines = [ln for ln in group if ln.column == primary]
        else:
            box_lines = group
        seg = {
            "id": f"p{page}-s{index}",
            "page": page,
            "ordinal": index,
            "text": text,
            "bbox": [
                round(min(ln.x0 for ln in box_lines), 2),
                round(min(ln.y0 for ln in box_lines), 2),
                round(max(ln.x1 for ln in box_lines), 2),
                round(max(ln.y1 for ln in box_lines), 2),
            ],
            "size": round(statistics.median(ln.size for ln in group), 2),
            "align": "merged" if len(group) > 1 else "exact",
        }
        seg["kind"] = _classify(seg, page, 0, body_size)
        segments.append(seg)
    return segments


# A paragraph interrupted by a display equation or a picture keeps going after
# it, so the continuation search has to look past these kinds. Headings and the
# title are *not* in this set: they really do start a new paragraph.
CONTINUATION_TRANSPARENT = {"formula", "table", "figure", "noise", "meta", "caption"}

# "Training." / "Datasets." — a run-in label is never longer than this.
INLINE_LABEL_MAX = 30

# A paragraph that stops after one of these words did not finish its sentence:
# "… are conducted on" / "… performs comparably to the".
FUNCTION_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "been",
    "both",
    "but",
    "by",
    "for",
    "from",
    "if",
    "in",
    "into",
    "is",
    "are",
    "was",
    "were",
    "not",
    "of",
    "on",
    "or",
    "our",
    "such",
    "than",
    "that",
    "the",
    "their",
    "then",
    "these",
    "this",
    "those",
    "to",
    "via",
    "we",
    "which",
    "while",
    "with",
}


def _is_dangling(text: str) -> bool:
    """True when a paragraph clearly stops in the middle of its sentence.

    Used as an extra signal for rejoining: pdfminer splits a sentence whenever a
    display equation or a picture sits inside it, and the second half often
    starts with a capital ("… of target views" / "(Itgt) to render …"), so the
    "starts lowercase" test alone misses those.
    """
    stripped = text.rstrip()
    if not stripped or stripped.endswith(SENTENCE_END):
        return False
    if stripped.endswith((",", "(", ")", "\u2013", "\u2014")):
        return True
    last_word = stripped.rsplit(" ", 1)[-1].strip(".,;:").lower()
    if last_word in FUNCTION_WORDS:
        return True
    return len(stripped) > 120


def _lift_inline_labels(segments: list[dict], vocab: set[str]) -> None:
    """Rejoin a sentence that a run-in label was laid out in the middle of.

    Papers set section labels inline at the start of a paragraph ("Training. We
    present results of E-RayZer trained on both ..."), but a two-column layout
    can emit that label as its own block between the two halves of the sentence:
    "... We present results of E-RayZer" / "Datasets." / "trained on both ...".
    The halves then became separate paragraphs, the second one starting with a
    lowercase word. The label is moved out of the flow and the sentence rejoined.
    """
    index = 1
    while index < len(segments) - 1:
        label = segments[index]
        before = segments[index - 1]
        after = segments[index + 1]
        text = label["text"].strip()
        is_label = (
            label.get("kind") == "body"
            and 0 < len(text) <= INLINE_LABEL_MAX
            and text.endswith(".")
            # A label is a single capitalised word, not a short sentence.
            and len(text.split()) <= 3
            and text[:1].isupper()
        )
        if (
            is_label
            and before.get("kind") in {"body", "abstract"}
            and after.get("kind") in {"body", "abstract"}
            and not before["text"].rstrip().endswith(SENTENCE_END)
            and re.match(r"^[a-z]", after["text"].lstrip())
            and int(after.get("page") or 0) - int(before.get("page") or 0) in (0, 1)
        ):
            before_length = len(before["text"])
            before["text"] = _join(before["text"], after["text"], vocab)
            before["align"] = "merged"
            if len(after["text"]) > before_length:
                before["page"] = after["page"]
                before["ordinal"] = after["ordinal"]
                before["bbox"] = after["bbox"]
            label["kind"] = "heading"
            del segments[index + 1]
        index += 1


def _join_broken_segments(segments: list[dict], vocab: set[str]) -> list[dict]:
    """Re-attach tails that a display equation, figure or page break interrupted.

    Merging works line by line, so anything that sits *between* two parts of a
    sentence — a formula, a table, a page boundary — separates them for good.
    The result reads as broken paragraphs ("... to ensure conver-" followed by
    "gence and scalability, we introduce ..."), and each half is translated on
    its own, which is where fragments in the finished text come from.

    Only a clear signal is used: the previous paragraph ends with a hyphen, or
    the next one starts with a lowercase word while the previous did not close
    its sentence. Prose is never joined across a caption, heading, table or
    formula, and never across a paragraph that ended properly.
    """
    kept: list[dict] = []

    def _previous_prose() -> int | None:
        """Index of the nearest body paragraph, looking past an interruption."""
        for index in range(len(kept) - 1, -1, -1):
            if kept[index].get("kind") in {"body", "abstract"}:
                return index
            if kept[index].get("kind") not in CONTINUATION_TRANSPARENT:
                return None
        return None

    for seg in segments:
        prev = kept[-1] if kept else None
        if prev is None:
            kept.append(seg)
            continue
        joinable = (
            prev.get("kind") in {"body", "abstract"}
            and seg.get("kind") in {"body", "abstract"}
            and int(seg.get("page") or 0) - int(prev.get("page") or 0) in (0, 1)
        )
        if not joinable and seg.get("kind") in {"body", "abstract"}:
            # The sentence may continue after a formula or a picture that sits
            # in between: "... refined via transformer" / [equation] /
            # ", Linear(Iref, Rplk". Look for the paragraph that owns the tail.
            index = _previous_prose()
            if index is not None:
                candidate = kept[index]
                gap = int(seg.get("page") or 0) - int(candidate.get("page") or 0)
                candidate_tail = candidate["text"].rstrip()
                # "… the frozen-backbone setting, E-" / [table] / "RayZer …":
                # a line broken mid-word names its own continuation, capital or
                # not.
                broken_word = candidate_tail.endswith("-")
                # "…as follows:" / [equation] / "where K denotes …" — the colon
                # introduces the equation, so the clause after it is the same
                # paragraph even though a ":" looks like a sentence end.
                open_after = not candidate_tail.endswith(
                    SENTENCE_END
                ) or candidate_tail.endswith((":", "："))
                if gap in (0, 1) and (
                    broken_word
                    or (open_after and re.match(r"^[a-z]", seg["text"].lstrip()))
                ):
                    prev = candidate
                    joinable = True
        if joinable:
            previous_text = prev["text"].rstrip()
            next_text = seg["text"].lstrip()
            hyphenated = previous_text.endswith("-")
            lowercase_tail = bool(re.match(r"^[a-z]", next_text))
            open_sentence = not previous_text.endswith(SENTENCE_END)
            # "The loss is:" / [equation] / "where Percep denotes ..." — the
            # colon introduces the equation and the lowercase clause explains
            # it, so they are one paragraph however the paper laid them out.
            led_by_colon = previous_text.endswith((":", "："))
            # The next half may start with a capital or a bracket when an
            # equation was sitting in between, so fall back to the shape of the
            # tail itself: a paragraph that stops at "the" or after a comma has
            # not finished.
            resumed = open_sentence and (
                _is_dangling(previous_text) or next_text.startswith("(")
            )
            if (
                hyphenated
                or (lowercase_tail and (open_sentence or led_by_colon))
                or resumed
            ):
                previous_length = len(prev["text"])
                prev["text"] = _join(prev["text"], seg["text"], vocab)
                prev["align"] = "merged"
                # Keep the box where most of the text is, so a joined paragraph
                # stays anchored to one place on one page.
                if len(seg["text"]) > previous_length:
                    prev["page"] = seg["page"]
                    prev["ordinal"] = seg["ordinal"]
                    prev["bbox"] = seg["bbox"]
                continue
        kept.append(seg)
    return kept


def parse_pdf(path: Path, title: str = "") -> dict:
    """Parse a PDF into a document dict with segments and alignment quality."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    lines, sizes = extract_lines(path)
    # Fragments (bare numbers, stray glyphs) must go before merging, otherwise
    # they interrupt every paragraph they sit between.
    lines = _drop_noise_lines(lines)
    vocab = _document_vocab(lines)
    page_count = max(sizes) if sizes else 1
    by_page: dict[int, list[TextLine]] = {p: [] for p in sizes}
    for line in lines:
        by_page.setdefault(line.page, []).append(line)
    by_page = _drop_running_heads(by_page, sizes)

    ordered = {
        p: _order_page(by_page.get(p, []), sizes.get(p, (612.0, 0))[0]) for p in sizes
    }
    # Body text dominates the page, so the median of all line sizes is the body
    # size; caps and headings are the outliers.
    all_sizes = [ln.size for p in ordered for ln in ordered[p] if ln.size > 0]
    body_size = statistics.median(all_sizes) if all_sizes else 10.0

    segments: list[dict] = []
    for page in sorted(ordered):
        page_segments = _merge_page(ordered[page], page, body_size, vocab)
        for seg in page_segments:
            seg["kind"] = _classify(seg, page, page_count, body_size)
            segments.append(seg)

    # Merge paragraphs that continue across a page break.
    #
    # The text is joined so the translation is a complete sentence, but the
    # bounding box must stay inside ONE page: mixing the coordinates of two
    # pages produces a box covering the whole sheet, which the bilingual view
    # would paint over the entire page (hiding figures and every other
    # paragraph). The part holding more text keeps the box, so the translation
    # is drawn where most of the paragraph actually is.
    merged_segments: list[dict] = []
    for seg in segments:
        prev = merged_segments[-1] if merged_segments else None
        if (
            prev
            and prev["page"] == seg["page"] - 1
            and not prev["text"].rstrip().endswith(SENTENCE_END)
            and re.match(r"^[a-z0-9(\[]", seg["text"])
            and prev["kind"] in {"body", "abstract"}
            and seg["kind"] in {"body", "abstract"}
        ):
            carried = len(prev["text"])
            prev["text"] = _join(prev["text"], seg["text"], vocab)
            prev["align"] = "merged"
            if len(seg["text"]) > carried:
                prev["page"] = seg["page"]
                prev["ordinal"] = seg["ordinal"]
                prev["bbox"] = seg["bbox"]
            continue
        merged_segments.append(seg)

    # A "References" heading plus a run of entries is far more reliable than
    # per-segment pattern matching: translating a bibliography helps nobody.
    _mark_reference_sections(merged_segments)
    # Equations and table cells look like short "body" paragraphs otherwise.
    _mark_layout_fragments(merged_segments)
    # "2 Zhipu AI" looks like a section number; it is an affiliation.
    _mark_affiliations_as_meta(merged_segments)
    # Last pass: paragraphs that a display equation, a figure or a page break
    # interrupts leave a tail starting mid-sentence ("... to ensure conver-" /
    # "gence and scalability") or a fragment starting with a lowercase word.
    # Those were shown as separate paragraphs and translated as fragments.
    _lift_inline_labels(merged_segments, vocab)
    merged_segments = _join_broken_segments(merged_segments, vocab)
    # A caption plus the empty space next to it is a picture; the reading view
    # draws it from the page bitmap instead of pretending it does not exist.
    merged_segments = insert_figures(merged_segments, sizes)

    # Re-number ids sequentially per page: the injected figure segments need
    # their own slot, and stable ids keep reading state and citations valid.
    counters: dict[int, int] = {}
    for index, seg in enumerate(merged_segments):
        page = int(seg["page"])
        ordinal = counters.get(page, 0)
        counters[page] = ordinal + 1
        seg["ordinal"] = ordinal
        seg["id"] = f"p{page}-s{ordinal}"
        seg["index"] = index

    extracted_chars = sum(len(ln.text) for p in by_page for ln in by_page[p])
    segment_chars = sum(
        len(seg["text"]) for seg in merged_segments if seg.get("kind") != "figure"
    )
    pages_with_text = sum(
        1
        for p in by_page
        if sum(len(ln.text) for ln in by_page[p]) >= MIN_CHARS_PER_PAGE
    )
    scanned = pages_with_text < max(1, int(page_count * 0.5))
    coverage = min(1.0, segment_chars / extracted_chars) if extracted_chars else 0.0

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
        "parser_version": PARSER_VERSION,
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
