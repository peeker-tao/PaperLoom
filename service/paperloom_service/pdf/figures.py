"""Locate the drawing area that belongs to each figure/table caption.

The text layer only knows where words are, so the space around a caption is
free: whatever sits between the caption and the nearest text block is the
figure (or the table body). Detecting that region lets the reading view show
the real picture instead of silently dropping it — a paper about image
generation is unreadable without its figures.

The region is computed from existing segment boxes, so no extra dependency and
no re-parsing of the drawing operators is needed. When the guess is ambiguous
(text inside the candidate area, or a gap too thin to be a picture) nothing is
emitted: a wrong crop is worse than no picture, because the reader cannot tell
that the image is a fragment of something else.
"""

from __future__ import annotations

import re

# "Figure 3.", "Fig. 2:", "TABLE IV", "Table 1 |" — the caption label.
CAPTION_LABEL_RE = re.compile(
    r"^(?P<label>figure|fig\.?|table|tab\.?)\s*(?P<num>[0-9]{1,3}|[IVX]{1,5})\b"
    r"(?P<rest>.*)$",
    re.IGNORECASE,
)
# A caption continues with punctuation or a capitalised word ("Fig. 2: An");
# running prose continues with a verb ("Table 1 shows the results ...").
CAPTION_CONTINUATION_RE = re.compile(r"^\s*(?:[.:|\u2013\u2014-]|$|[A-Z\u4e00-\u9fff])")

# A picture is at least this big; anything smaller is a gap between paragraphs.
MIN_FIGURE_WIDTH = 90.0
MIN_FIGURE_HEIGHT = 55.0
# A region taller than this share of the page is a failed guess, not a picture:
# it would cover most of the sheet and hide the text underneath.
MAX_FIGURE_PAGE_SHARE = 0.8
# A caption longer than this is a paragraph that happens to start with "Figure".
# Real captions are long: a caption that lists its sub-figures ("(a) ... (b) ...")
# runs to 600-900 characters in the papers this was measured on, and the old
# 400-character ceiling threw away four of the ten pictures in one of them. The
# prose case is caught by CAPTION_CONTINUATION_RE instead ("Table 1 shows ...").
MAX_CAPTION_CHARS = 1200
# Kinds that are part of the thing being drawn rather than text that would be
# covered by it. A table *is* a run of cells, and a chart's axis labels are
# short fragments: refusing the region because of them meant no table was ever
# shown, which is worse than showing a picture that contains its own labels.
ABSORB_KINDS = {"table", "noise", "formula", "meta"}
# Text blocks closer than this belong to the same visual group. Table rows sit
# about one line apart, and a chart's tick labels are separated by its own
# whitespace, so the gap has to cover both — at 20pt a 21pt gap between a plot's
# axis label and its frame ended the group early and the picture was cut to a
# strip of numbers. Only drawing parts (cells, labels, equations) are absorbed
# across it, never prose.
JOIN_GAP = 30.0
# Whitespace kept around the drawing on both sides. Text boxes end at the last
# glyph, while a table's rules and filled cells continue past it — 8.5pt in the
# paper that exposed this — so a crop measured on text alone decapitates the
# outermost column. Padding is dropped again if it would reach neighbouring
# prose, so this cannot grow a crop into the next column.
FIGURE_EDGE_PAD = 12.0
# A single short line inside this band at the very top or bottom of the sheet is
# a running head/foot ("W. Zhou et al."), not body text. Treating it as content
# ended a figure at the author line: the plot above the caption was cut down to
# its axis labels, and a full-page picture was refused altogether.
RUNNING_BAND = 40.0
RUNNING_MAX_HEIGHT = 26.0
# How close the topmost drawing part must already be to the page margin before
# the crop is allowed to run all the way there. Keeps a small table from
# dragging in a page's worth of white space.
MARGIN_REACH = 160.0
# A caption narrower than this share of the text column labels a narrow drawing.
NARROW_CAPTION_SHARE = 0.7


def _by_page(segments: list[dict]) -> dict[int, list[dict]]:
    pages: dict[int, list[dict]] = {}
    for seg in segments:
        pages.setdefault(int(seg["page"]), []).append(seg)
    return pages


def _is_running_line(seg: dict, page_height: float) -> bool:
    if not page_height:
        return False
    if seg.get("kind") == "caption":
        return False
    _x0, y0, _x1, y1 = seg["bbox"]
    if (y1 - y0) > RUNNING_MAX_HEIGHT:
        return False
    return y1 >= page_height - RUNNING_BAND or y0 <= RUNNING_BAND


def _content_blocks(segments: list[dict], page_height: float) -> list[dict]:
    """The blocks that are page content — running heads and feet removed."""
    return [seg for seg in segments if not _is_running_line(seg, page_height)]


def _top_margin(
    segments: list[dict], page_sizes: dict[int, tuple[float, float]] | None
) -> float:
    """The document's own top margin, measured from the pages.

    Used only to close a region that runs off the top of the page — a teaser
    figure with nothing above it. A single page cannot answer this (its top may
    be entirely figure), so the *tightest* top text position across the document
    is taken: pages whose text starts low get ignored by the min.
    """
    if not page_sizes:
        return 45.0
    gaps = []
    for page, segs in _by_page(segments).items():
        height = (page_sizes.get(page) or (0.0, 0.0))[1]
        content = _content_blocks(segs, height)
        if height and content:
            gaps.append(height - max(seg["bbox"][3] for seg in content))
    if not gaps:
        return 45.0
    return min(max(min(gaps), 18.0), 72.0)


def _column_span(segments: list[dict]) -> tuple[float, float]:
    """Horizontal extent of the text column, ignoring narrow outliers.

    Using the caption's own width would crop the sides off a figure that is
    wider than its caption; the column width is the safe upper bound.
    """
    widths = [seg["bbox"][2] - seg["bbox"][0] for seg in segments]
    if not widths:
        return (0.0, 0.0)
    widest = max(widths)
    keep = [
        seg
        for seg in segments
        if (seg["bbox"][2] - seg["bbox"][0]) >= max(40.0, widest * 0.45)
    ]
    if not keep:
        keep = segments
    return (
        min(seg["bbox"][0] for seg in keep),
        max(seg["bbox"][2] for seg in keep),
    )


def _candidate_spans(caption: dict, segments: list[dict]) -> list[tuple[float, float]]:
    """Horizontal extents worth trying for this caption, widest first.

    The page's text column is the safe choice for a full-width figure. But a
    picture that occupies one column of a two-column page — caption and drawing
    on the right, prose on the left — fails there: the neighbouring paragraph is
    inside the region, so the crop is refused and the picture is simply missing.
    Half the column (the side the caption sits on) and the caption's own width
    are the two narrower answers, in that order: the half column still covers a
    drawing that fills its column, while the caption's width can clip one.
    """
    cb = caption["bbox"]
    wide = _column_span(segments)
    spans: list[tuple[float, float]] = []
    width = wide[1] - wide[0]
    middle = (wide[0] + wide[1]) / 2
    caption_mid = (cb[0] + cb[2]) / 2
    caption_width = cb[2] - cb[0]
    half = (wide[0], middle) if caption_mid < middle else (middle, wide[1])
    # A caption clearly narrower than the column labels a narrow drawing, so its
    # own side of the gutter is tried first — otherwise the wide span's *other*
    # direction can win on height and crop the whitespace under the caption.
    if width and caption_width < width * NARROW_CAPTION_SHARE:
        narrower = [half, (cb[0], cb[2]), wide]
    else:
        narrower = [wide, half, (cb[0], cb[2])]
    for span in narrower:
        if span[1] - span[0] < MIN_FIGURE_WIDTH:
            continue
        if any(abs(span[0] - other[0]) < 1.0 and abs(span[1] - other[1]) < 1.0 for other in spans):
            continue
        spans.append(span)
    return spans


def _neighbour_top(
    caption: dict,
    segments: list[dict],
    span: tuple[float, float],
    page_height: float | None = None,
):
    """Where the picture area ends, going up from the caption.

    A prose block above the picture is the boundary: the region stops at its
    bottom edge. A block that is *part of* the picture (a table cell, a chart's
    axis label, an equation) is absorbed, and the region keeps growing until the
    group ends — otherwise a table is clipped to its bottom row.
    """
    floor = caption["bbox"][3]
    above = [
        seg
        for seg in segments
        if seg is not caption
        and _overlaps(seg, span)
        and seg["bbox"][1] >= floor - 0.5
    ]
    if not above:
        return None
    above.sort(key=lambda seg: seg["bbox"][1])
    first = above[0]
    if first.get("kind") not in ABSORB_KINDS:
        return first["bbox"][1]
    reach = first["bbox"][3]
    consumed = 1
    for seg in above[1:]:
        if seg.get("kind") not in ABSORB_KINDS:
            break
        if seg["bbox"][1] > reach + JOIN_GAP:
            break
        reach = max(reach, seg["bbox"][3])
        consumed += 1
    # Nothing but drawing parts above the caption: the picture may run all the
    # way to the page margin. Stopping at the last label cut plots off at their
    # axis text — the reader saw a strip of numbers. This is only believed when
    # the drawing already reaches near the margin; otherwise the region would
    # swallow a large empty area above a small table.
    if consumed == len(above) and page_height and page_height - reach <= MARGIN_REACH:
        return None
    return reach


def _neighbour_bottom(caption: dict, segments: list[dict], span: tuple[float, float]):
    """Where the picture area ends, going down from the caption (tables)."""
    ceiling = caption["bbox"][1]
    below = [
        seg
        for seg in segments
        if seg is not caption
        and _overlaps(seg, span)
        and seg["bbox"][3] <= ceiling + 0.5
    ]
    if not below:
        return None
    below.sort(key=lambda seg: -seg["bbox"][3])
    first = below[0]
    if first.get("kind") not in ABSORB_KINDS:
        return first["bbox"][3]
    reach = first["bbox"][1]
    for seg in below[1:]:
        if seg.get("kind") not in ABSORB_KINDS:
            break
        if seg["bbox"][3] < reach - JOIN_GAP:
            break
        reach = min(reach, seg["bbox"][1])
    return reach


def _overlaps(seg: dict, span: tuple[float, float]) -> bool:
    return seg["bbox"][0] < span[1] and seg["bbox"][2] > span[0]


def _has_text_inside(region: list[float], segments: list[dict], caption: dict) -> bool:
    """True when readable prose sits inside the candidate picture area.

    Only prose counts. Table cells, equation fragments and stray labels are
    what the picture is made of; treating them as an obstruction rejected every
    table in the document.
    """
    x0, y0, x1, y1 = region
    for seg in segments:
        if seg is caption or seg.get("kind") in ABSORB_KINDS:
            continue
        bx0, by0, bx1, by1 = seg["bbox"]
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            return True
    return False


def _valid(region: list[float], segments: list[dict], caption: dict) -> bool:
    x0, y0, x1, y1 = region
    if (x1 - x0) < MIN_FIGURE_WIDTH or (y1 - y0) < MIN_FIGURE_HEIGHT:
        return False
    return not _has_text_inside(region, segments, caption)


def _widen_to_content(
    region: list[float], segments: list[dict], caption: dict
) -> list[float]:
    """Extend the region sideways until it covers the drawing's own row.

    The horizontal span is measured on the page's *wide* blocks (see
    ``_column_span``), so the outermost columns of a table — narrow cells, well
    under the width threshold — fall outside it and were cut off. Anything that
    is part of the drawing and sits at this height belongs to it, so the region
    keeps growing while such blocks touch it. Only blocks that already reach the
    region are absorbed; a label in the next column over is its own object.
    """
    x0, y0, x1, y1 = region
    for _ in range(8):
        grew = False
        for seg in segments:
            if seg is caption or seg.get("kind") not in ABSORB_KINDS:
                continue
            bx0, by0, bx1, by1 = seg["bbox"]
            if not (y0 - 1.0 <= (by0 + by1) / 2 <= y1 + 1.0):
                continue
            if bx1 < x0 - JOIN_GAP or bx0 > x1 + JOIN_GAP:
                continue
            nx0, nx1 = min(x0, bx0), max(x1, bx1)
            if nx0 < x0 - 0.01 or nx1 > x1 + 0.01:
                x0, x1, grew = nx0, nx1, True
        if not grew:
            break
    return [x0, y0, x1, y1]


def _padded(
    region: list[float], pad: float, page_width: float | None = None
) -> list[float]:
    """The region with room to breathe on both sides, kept on the page."""
    x0 = max(0.0, region[0] - pad)
    x1 = region[2] + pad
    if page_width:
        x1 = min(page_width, x1)
    return [x0, region[1], x1, region[3]]


def _gap(caption: dict, region: list[float], above: bool) -> float:
    """How much of the page the candidate region claims.

    Between two candidates the smaller one wins: a crop that is too tight still
    shows most of the picture, while one that is too large covers unrelated
    content the reader cannot recover from.
    """
    return region[3] - region[1]


def _region(
    caption: dict,
    segments: list[dict],
    span: tuple[float, float],
    *,
    above: bool,
    page_height: float | None = None,
    page_width: float | None = None,
    margin: float = 45.0,
) -> list[float] | None:
    """Return ``[x0, y0, x1, y1]`` for the picture area, or None.

    ``above`` is the usual direction for figures (caption underneath) and
    ``below`` for tables (caption on top), but both conventions exist in the
    wild — and stacked tables put a plausible-looking area on the wrong side —
    so the caller compares both candidates instead of trusting one.

    The region is bounded by a neighbouring text block. The one exception is a
    caption with no text at all above it: that is the signature of a full-width
    teaser figure at the top of a page, where the page margin is the only honest
    boundary. Downward there is no such case, and the fallback there produced
    whole-page crops.
    """
    x0, x1 = span
    cb = caption["bbox"]
    if above:
        edge = _neighbour_top(caption, segments, span, page_height)
        if edge is None:
            if page_height is None:
                return None
            edge = page_height - margin
        # bbox is [x0, y0(bottom), x1, y1(top)]: the picture sits between the
        # caption's top edge and the bottom edge of the block above it.
        region = [x0, cb[3], x1, edge]
    else:
        edge = _neighbour_bottom(caption, segments, span)
        if edge is None:
            return None
        region = [x0, edge, x1, cb[1]]
    if not _valid(region, segments, caption):
        return None
    widened = _widen_to_content(region, segments, caption)
    # A text box ends at its last glyph; a table's rules and filled cells carry
    # on past it (8.5pt in the paper that exposed this), so a crop that stops at
    # the text still decapitates the outermost column. Pad until the drawing has
    # room, and give the padding back if it would swallow neighbouring prose.
    for pad in (FIGURE_EDGE_PAD, FIGURE_EDGE_PAD / 2):
        candidate = _padded(widened, pad, page_width)
        if _valid(candidate, segments, caption):
            widened = candidate
            break
    # Widening is only an improvement if it does not drag prose into the crop.
    if widened != region and _valid(widened, segments, caption):
        region = widened
    return region


def _overlap_ratio(a: list[float], b: list[float]) -> float:
    """Intersection area as a fraction of the smaller rectangle."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    if smaller <= 0:
        return 1.0
    return (ix * iy) / smaller


def detect_figures(
    segments: list[dict], page_sizes: dict[int, tuple[float, float]] | None = None
) -> list[dict]:
    """Build ``figure`` segments for the pictures the captions refer to.

    Returns the segments to *insert*, each with a ``before`` key naming the
    caption id it belongs to, so the caller can place them in reading order
    (picture first, caption underneath) without guessing.
    """
    figures: list[dict] = []
    margin = _top_margin(segments, page_sizes)
    for page, raw_segs in _by_page(segments).items():
        page_size = (page_sizes or {}).get(page, (0.0, 0.0))
        page_width, page_height = page_size[0], page_size[1]
        # Running heads and feet are not content: they must not end a figure,
        # and they must not disqualify a region for "having text inside".
        segs = _content_blocks(raw_segs, page_height)
        if _column_span(segs)[1] - _column_span(segs)[0] < MIN_FIGURE_WIDTH:
            continue
        for seg in segs:
            text = (seg.get("text") or "").strip()
            if not text or len(text) > MAX_CAPTION_CHARS:
                continue
            match = CAPTION_LABEL_RE.match(text)
            if not match:
                continue
            # "Table 1 shows the results ..." is prose that mentions a table.
            if not CAPTION_CONTINUATION_RE.match(match.group("rest")):
                continue
            if seg.get("kind") not in {"caption", "body"}:
                continue
            is_table = match.group("label").lower().startswith("tab")
            # A picture touches its caption. Stacked tables give both directions
            # a plausible-looking answer, so preference goes to the tighter
            # crop: that is the block the caption actually labels.
            preferred = not is_table
            region = None
            for span in _candidate_spans(seg, segs):
                candidates: list[tuple[float, bool, list[float]]] = []
                for above in (preferred, not preferred):
                    found = _region(
                        seg,
                        segs,
                        span,
                        above=above,
                        page_height=page_height,
                        page_width=page_width,
                        margin=margin,
                    )
                    if found is not None:
                        candidates.append((_gap(seg, found, above), above, found))
                if candidates:
                    candidates.sort(key=lambda item: (item[0], item[1] != preferred))
                    region = candidates[0][2]
                    break
            if region is None:
                continue
            # Safety net: a region covering most of the sheet means the guess
            # went wrong (it would hide the text the reader needs).
            if page_height and (region[3] - region[1]) > page_height * MAX_FIGURE_PAGE_SHARE:
                continue
            label = f"{'Table' if is_table else 'Figure'} {match.group('num')}"
            # Two captions can point at the same picture (a figure and the table
            # beneath it); keeping both would draw the same crop twice.
            if any(
                other["page"] == page and _overlap_ratio(other["bbox"], region) > 0.5
                for other in figures
            ):
                continue
            figures.append(
                {
                    "before": seg["id"],
                    "page": page,
                    "text": label,
                    "bbox": [round(value, 2) for value in region],
                    "kind": "figure",
                    "align": "region",
                }
            )
    return figures


def insert_figures(
    segments: list[dict], page_sizes: dict[int, tuple[float, float]] | None = None
) -> list[dict]:
    """Return a new list with the picture segments placed before their caption."""
    figures = detect_figures(segments, page_sizes)
    if not figures:
        return list(segments)
    by_caption: dict[str, list[dict]] = {}
    for figure in figures:
        by_caption.setdefault(figure["before"], []).append(figure)
    out: list[dict] = []
    for seg in segments:
        out.extend(by_caption.get(seg["id"], []))
        out.append(seg)
    return out
