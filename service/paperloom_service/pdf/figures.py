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
MAX_CAPTION_CHARS = 400
# Kinds that are part of the thing being drawn rather than text that would be
# covered by it. A table *is* a run of cells, and a chart's axis labels are
# short fragments: refusing the region because of them meant no table was ever
# shown, which is worse than showing a picture that contains its own labels.
ABSORB_KINDS = {"table", "noise", "formula", "meta"}
# Text blocks closer than this belong to the same visual group. Table rows sit
# about one line apart, so this has to cover normal leading.
JOIN_GAP = 20.0


def _by_page(segments: list[dict]) -> dict[int, list[dict]]:
    pages: dict[int, list[dict]] = {}
    for seg in segments:
        pages.setdefault(int(seg["page"]), []).append(seg)
    return pages


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
        if height and segs:
            gaps.append(height - max(seg["bbox"][3] for seg in segs))
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


def _neighbour_top(caption: dict, segments: list[dict], span: tuple[float, float]):
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
    for seg in above[1:]:
        if seg.get("kind") not in ABSORB_KINDS:
            break
        if seg["bbox"][1] > reach + JOIN_GAP:
            break
        reach = max(reach, seg["bbox"][3])
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
        edge = _neighbour_top(caption, segments, span)
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
    for page, segs in _by_page(segments).items():
        span = _column_span(segs)
        if span[1] - span[0] < MIN_FIGURE_WIDTH:
            continue
        page_height = (page_sizes or {}).get(page, (0.0, 0.0))[1]
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
            candidates: list[tuple[float, bool, list[float]]] = []
            for above in (preferred, not preferred):
                region = _region(
                    seg, segs, span, above=above, page_height=page_height, margin=margin
                )
                if region is not None:
                    candidates.append((_gap(seg, region, above), above, region))
            if not candidates:
                continue
            candidates.sort(key=lambda item: (item[0], item[1] != preferred))
            region = candidates[0][2]
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
