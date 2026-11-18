"""PDF extraction and paragraph merging tests."""

from __future__ import annotations

from tests.fixtures import (
    hyphenation_pdf,
    paginated_paper_pdf,
    paper_pdf,
    scanned_pdf,
    two_column_pdf,
)


def test_extracts_paragraphs_and_merges_lines(tmp_path):
    from paperloom_service.pdf.extract import parse_pdf

    path = paper_pdf(tmp_path / "p.pdf", pages=2)
    doc = parse_pdf(path)
    assert doc["pages"] == 2
    assert doc["scanned"] is False
    assert doc["alignment"] == "segment"
    texts = [seg["text"] for seg in doc["segments"]]
    joined = " ".join(texts)
    assert "LoomAttention" in joined
    # Lines of the same paragraph are merged into one segment.
    abstract = next(
        seg for seg in doc["segments"] if seg["text"].startswith("Abstract.")
    )
    assert "efficient retrieval augmented generation" in abstract["text"]
    assert abstract["bbox"][2] > abstract["bbox"][0]
    assert doc["coverage"] > 0.8


def test_two_column_reading_order(tmp_path):
    from paperloom_service.pdf.extract import parse_pdf

    doc = parse_pdf(two_column_pdf(tmp_path / "two.pdf"))
    texts = [seg["text"] for seg in doc["segments"]]
    left = next(i for i, t in enumerate(texts) if "Left column line 0" in t)
    right = next(i for i, t in enumerate(texts) if "Right column line 0" in t)
    assert left < right, texts


def test_scanned_pdf_detected(tmp_path):
    from paperloom_service.pdf.extract import parse_pdf

    doc = parse_pdf(scanned_pdf(tmp_path / "scan.pdf"))
    assert doc["scanned"] is True
    assert doc["alignment"] == "none"
    assert doc["segments"] == []


def test_segment_ids_are_unique_per_document(tmp_path):
    from paperloom_service.pdf.extract import parse_pdf

    doc = parse_pdf(paper_pdf(tmp_path / "p.pdf", pages=2))
    ids = [seg["id"] for seg in doc["segments"]]
    assert len(ids) == len(set(ids))
    assert ids[0].startswith("p1-s")


def test_noise_and_author_blocks_are_classified():
    """Regression from a real paper: '2'/'r' fragments and author lines."""
    from paperloom_service.pdf.extract import _is_author_block, _is_noise

    assert _is_noise("2")
    assert _is_noise("r")
    assert _is_noise("0 2")
    assert not _is_noise(
        "We propose a relay diffusion model for text-to-image generation."
    )

    assert _is_author_block("Wendi Zheng1∗‡, Jiayan Teng1∗‡, Zhuoyi Yang1‡")
    assert _is_author_block("1 Tsinghua University, Beijing, China")
    assert _is_author_block("Correspondence: someone@example.edu")
    assert not _is_author_block(
        "We propose a relay diffusion model that generates images in two stages."
    )


def test_coverage_never_exceeds_one(tmp_path):
    from paperloom_service.pdf.extract import parse_pdf

    doc = parse_pdf(paper_pdf(tmp_path / "p.pdf", pages=2))
    assert 0 < doc["coverage"] <= 1.0


# --------------------------------------------------------------------------- #
# Segmentation quality: the difference between readable and gibberish output
# --------------------------------------------------------------------------- #


def test_rotated_margin_stamp_never_reaches_segments(tmp_path):
    """Regression: an arXiv-style 90-degree stamp used to shred every paragraph.

    pdfminer reports the rotation on each ``LTChar.matrix`` while
    ``LTTextLine.matrix`` is empty, so the filter silently did nothing and the
    stamp characters were interleaved between body lines.
    """
    from paperloom_service.pdf.extract import parse_pdf

    path = paginated_paper_pdf(tmp_path / "wm.pdf")
    doc = parse_pdf(path)
    joined = " ".join(seg["text"] for seg in doc["segments"])
    assert "2403" not in joined
    assert "05121" not in joined
    # No single-glyph segments survived either.
    assert all(len(seg["text"].strip()) >= 3 for seg in doc["segments"])


def test_paragraph_lines_merge_and_compound_hyphen_is_kept(tmp_path):
    from paperloom_service.pdf.extract import parse_pdf

    doc = parse_pdf(hyphenation_pdf(tmp_path / "hy.pdf"))
    joined = " ".join(seg["text"] for seg in doc["segments"])
    # "im-" + "plementing" is a typesetting hyphenation -> joined into a word.
    assert "implementing relay diffusion" in joined
    assert "im- plementing" not in joined
    # "text-" + "to-image" is a compound -> the hyphen must survive.
    assert "text-to-image generation" in joined
    assert "textto-image" not in joined


def test_indented_line_starts_a_new_segment(tmp_path):
    from paperloom_service.pdf.extract import parse_pdf

    doc = parse_pdf(paginated_paper_pdf(tmp_path / "p.pdf"))
    texts = [seg["text"] for seg in doc["segments"]]
    first = next(t for t in texts if t.startswith("We propose a cascaded framework"))
    second = next(t for t in texts if t.startswith("Second paragraph starts"))
    assert first != second
    assert "Second paragraph" not in first
    # The flush continuation still belongs to the indented paragraph.
    assert "continues flush with the column edge" in second


def test_equation_fragments_are_classified_as_formula(tmp_path):
    from paperloom_service.pdf.extract import parse_pdf
    from paperloom_service.translate import is_translatable

    doc = parse_pdf(paginated_paper_pdf(tmp_path / "p.pdf"))
    formula = next(s for s in doc["segments"] if s["text"].startswith("q(xt|x0)"))
    assert formula["kind"] == "formula"
    assert not is_translatable(formula)


def test_table_cells_are_not_translatable(tmp_path):
    from paperloom_service.pdf.extract import parse_pdf
    from paperloom_service.translate import is_translatable

    doc = parse_pdf(paginated_paper_pdf(tmp_path / "p.pdf"))
    cells = [s for s in doc["segments"] if s["text"] in {"SDXL [17]", "LCM-SDXL [14]"}]
    assert cells, [s["text"] for s in doc["segments"]]
    assert all(cell["kind"] == "table" for cell in cells)
    assert not any(is_translatable(cell) for cell in cells)


def test_reference_section_is_not_translatable(tmp_path):
    from paperloom_service.pdf.extract import parse_pdf
    from paperloom_service.translate import is_translatable

    doc = parse_pdf(paginated_paper_pdf(tmp_path / "p.pdf"))
    entries = [
        s for s in doc["segments"] if "Achiam" in s["text"] or "Ho, J." in s["text"]
    ]
    assert entries
    assert all(entry["kind"] == "reference" for entry in entries), [
        (e["text"][:40], e["kind"]) for e in entries
    ]
    assert not any(is_translatable(entry) for entry in entries)


def test_prose_is_still_translatable(tmp_path):
    from paperloom_service.pdf.extract import parse_pdf
    from paperloom_service.translate import is_translatable

    doc = parse_pdf(paginated_paper_pdf(tmp_path / "p.pdf"))
    body = [s for s in doc["segments"] if s["kind"] == "body"]
    assert body
    assert all(is_translatable(seg) for seg in body), [
        (s["text"][:50], s["kind"]) for s in body
    ]


def test_every_document_records_its_parser_version(tmp_path):
    from paperloom_service.pdf.extract import PARSER_VERSION, parse_pdf

    doc = parse_pdf(paginated_paper_pdf(tmp_path / "p.pdf"))
    assert doc["parser_version"] == PARSER_VERSION


def test_affiliations_before_the_abstract_are_not_headings():
    """Regression: '2 Zhipu AI' matched the section-number pattern and became an H2."""
    from paperloom_service.pdf.extract import _mark_affiliations_as_meta

    segments = [
        {"page": 1, "kind": "title", "text": "CogView3: Finer and Faster"},
        {"page": 1, "kind": "meta", "text": "Wendi Zheng1, Jiayan Teng1"},
        {"page": 1, "kind": "heading", "text": "1 Tsinghua University"},
        {"page": 1, "kind": "heading", "text": "2 Zhipu AI"},
        {"page": 1, "kind": "abstract", "text": "Abstract. Recent advancements ..."},
        {"page": 1, "kind": "heading", "text": "2 Background"},
    ]
    _mark_affiliations_as_meta(segments)
    kinds = [seg["kind"] for seg in segments]
    assert kinds == ["title", "meta", "meta", "meta", "abstract", "heading"]


def test_cross_page_merge_keeps_a_single_page_bbox(tmp_path):
    """Regression: mixing the coordinates of two pages produced a page-size box.

    The bilingual view paints an opaque panel into the box, so such a segment
    covered the whole sheet — figures and every other paragraph disappeared.
    """
    from paperloom_service.pdf.extract import parse_pdf

    doc = parse_pdf(paper_pdf(tmp_path / "p.pdf", pages=2))
    page_heights = {}
    for segment in doc["segments"]:
        _x0, y0, _x1, y1 = segment["bbox"]
        assert y1 > y0, segment
        # A paragraph occupies a portion of one page, never most of it.
        assert (y1 - y0) <= 0.7 * 792, (segment["id"], segment["bbox"])
        page_heights.setdefault(segment["page"], []).append(y1)
    assert page_heights
