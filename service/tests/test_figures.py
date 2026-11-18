"""Figure-region detection: the picture a caption refers to.

The reading view is reflowed text, so a figure has to be cut out of the page
bitmap. These tests pin the rules that decide where the cut is.
"""

from __future__ import annotations

from paperloom_service.pdf.figures import detect_figures, insert_figures


def seg(seg_id: str, page: int, kind: str, text: str, bbox: list[float]) -> dict:
    return {"id": seg_id, "page": page, "kind": kind, "text": text, "bbox": bbox}


def test_figure_above_its_caption_is_found():
    segments = [
        seg("p1-s0", 1, "body", "Text at the top of the page.", [40, 640, 560, 660]),
        seg("p1-s1", 1, "caption", "Fig. 1: A generated image.", [40, 380, 560, 400]),
        seg("p1-s2", 1, "body", "Text below the caption.", [40, 300, 560, 360]),
    ]
    figures = detect_figures(segments, {1: (595.0, 792.0)})
    assert len(figures) == 1
    figure = figures[0]
    assert figure["before"] == "p1-s1"
    assert figure["kind"] == "figure"
    # From the caption's top edge up to the bottom edge of the paragraph above.
    assert figure["bbox"] == [40.0, 400.0, 560.0, 640.0]


def test_gap_too_thin_is_not_a_figure():
    segments = [
        seg("p1-s0", 1, "body", "Text above.", [40, 420, 560, 440]),
        seg("p1-s1", 1, "caption", "Fig. 1: Tiny.", [40, 400, 560, 415]),
    ]
    assert detect_figures(segments, {1: (595.0, 792.0)}) == []


def test_prose_inside_the_region_disqualifies_it():
    """A crop that would cover a paragraph is worse than no picture."""
    segments = [
        seg("p1-s0", 1, "body", "A paragraph that must stay visible.", [40, 500, 560, 520]),
        seg("p1-s1", 1, "body", "Text above.", [40, 420, 560, 440]),
        seg("p1-s2", 1, "caption", "Fig. 1: Something.", [40, 380, 560, 400]),
    ]
    assert detect_figures(segments, {1: (595.0, 792.0)}) == []


def test_table_body_is_absorbed_cell_by_cell():
    """A table is a run of cells, not one block: it must not be clipped."""
    segments = [
        seg("p1-s0", 1, "caption", "Table 1: Results.", [40, 380, 560, 400]),
        seg("p1-s1", 1, "table", "Model", [60, 420, 140, 432]),
        seg("p1-s2", 1, "table", "Score", [300, 420, 360, 432]),
        seg("p1-s3", 1, "table", "CogView3", [60, 432, 140, 444]),
        seg("p1-s4", 1, "table", "0.77", [300, 432, 360, 444]),
        seg("p1-s5", 1, "table", "SDXL", [60, 444, 140, 456]),
        seg("p1-s6", 1, "table", "0.43", [300, 444, 360, 456]),
        seg("p1-s7", 1, "body", "Prose below the table stays out.", [40, 300, 560, 360]),
    ]
    figures = detect_figures(segments, {1: (595.0, 792.0)})
    assert len(figures) == 1
    # Down from the caption, through every row, stopping before the prose.
    assert figures[0]["bbox"] == [40.0, 400.0, 560.0, 456.0]


def test_the_closer_side_wins_for_stacked_tables():
    """Regression from a real paper: two tables on one page.

    The lower table's caption also had a valid-looking area *below* it — its own
    rows — while its real body sat above. The tighter crop wins, and each table
    keeps its own rows instead of swallowing the other's.
    """
    segments = [
        seg("p1-s0", 1, "caption", "Table 2: Upper.", [40, 620, 560, 640]),
        seg("p1-s1", 1, "table", "Row A", [60, 560, 200, 572]),
        seg("p1-s2", 1, "table", "Row B", [60, 572, 200, 584]),
        seg("p1-s3", 1, "caption", "Table 1: Lower.", [40, 500, 560, 520]),
        seg("p1-s4", 1, "table", "Row C", [60, 440, 200, 452]),
        seg("p1-s5", 1, "table", "Row D", [60, 452, 200, 464]),
    ]
    figures = detect_figures(segments, {1: (595.0, 792.0)})
    by_caption = {figure["before"]: figure["bbox"] for figure in figures}
    assert by_caption["p1-s0"] == [40.0, 560.0, 560.0, 620.0]
    assert by_caption["p1-s3"] == [40.0, 440.0, 560.0, 500.0]


def test_prose_that_mentions_a_table_is_not_a_caption():
    segments = [
        seg("p1-s0", 1, "body", "Table 1 shows the results on DrawBench.", [40, 700, 560, 720]),
        seg("p1-s1", 1, "body", "More prose.", [40, 660, 560, 680]),
    ]
    assert detect_figures(segments, {1: (595.0, 792.0)}) == []


def test_figures_are_placed_before_their_caption():
    segments = [
        seg("p1-s0", 1, "body", "Intro.", [40, 640, 560, 660]),
        seg("p1-s1", 1, "caption", "Fig. 1: A picture.", [40, 380, 560, 400]),
        seg("p1-s2", 1, "body", "After.", [40, 300, 560, 360]),
    ]
    ordered = insert_figures(segments, {1: (595.0, 792.0)})
    kinds = [item["kind"] for item in ordered]
    # picture first, caption underneath — the order a reader expects.
    assert kinds == ["body", "figure", "caption", "body"]
