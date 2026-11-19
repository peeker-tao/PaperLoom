"""Segment classification: what is prose, and what only looks like it.

Two kinds of text used to reach the reading view as stray one-line paragraphs,
both measured on a real paper (MINIMA):

* a sub-figure annotation set at 8pt while the body is 10pt
  ("Making two cameras as close as possible, thus considering they share a
  common camera pose.") — it sat between two real paragraphs as if it were one;
* a lone table header carrying metric arrows ("SSIM ↑ LPIPS ↓"), which the
  "a table needs several cells" rule deliberately left alone.

The guards matter as much as the fixes: references and display equations are
also set smaller than the body, and a short single sentence must still be body.
"""

from __future__ import annotations

from paperloom_service.pdf.extract import _classify, _mark_layout_fragments


def seg(text: str, *, size: float = 10.0, ordinal: int = 5, page: int = 5) -> dict:
    return {
        "text": text,
        "size": size,
        "ordinal": ordinal,
        "page": page,
        "id": f"p{page}-s{ordinal}",
        "bbox": [0, 0, 100, 10],
        "align": "exact",
        "kind": "body",
    }


def classify(text: str, *, size: float = 10.0, page: int = 5, pages: int = 17) -> str:
    return _classify(seg(text, size=size, page=page), page, pages, 10.0)


def test_body_sized_prose_stays_body():
    assert classify("The encoder maps volumes to a latent space.") == "body"


def test_a_sub_figure_annotation_is_not_a_paragraph():
    text = (
        "Making two cameras as close as possible, thus considering they share "
        "a common camera pose."
    )
    assert classify(text, size=8.0) == "caption"


def test_a_smaller_bibliography_entry_stays_a_reference():
    # The numbering style the parser recognises: "12. Author, J., ...".
    text = (
        "12. Schonberger, J. L. and Frahm, J.-M. Structure-from-motion "
        "revisited. In Proceedings of CVPR, 2016."
    )
    assert classify(text, size=8.0, page=14) == "reference"


def test_a_smaller_entry_with_a_year_is_never_a_caption():
    """Reference lists are set smaller than the body in most papers."""
    text = "A. Author. A paper title without a venue abbreviation. 2019."
    assert classify(text, size=8.0, page=14) != "caption"


def test_a_smaller_display_equation_stays_a_formula():
    assert classify("q(zt|z0) = N (zt|F (x0, t), \u03c3t", size=8.0) == "formula"


def test_a_short_body_sentence_at_normal_size_is_still_body():
    assert classify("This ends here.", size=10.0) == "body"


def test_metric_arrows_mark_a_lone_table_header():
    table = seg("SSIM \u2191 LPIPS \u2193", size=9.0, ordinal=11, page=12)
    other = seg("A single short label.", size=10.0, ordinal=12, page=12)
    _mark_layout_fragments([table, other])
    assert table["kind"] == "table"
    # The company rule still protects an ordinary short paragraph.
    assert other["kind"] == "body"


def test_a_run_of_cells_is_still_detected_without_arrows():
    cells = [
        seg("Category Method", size=9.0, ordinal=index, page=6)
        for index in range(3)
    ]
    _mark_layout_fragments(cells)
    assert all(cell["kind"] == "table" for cell in cells)
