"""PDF extraction and paragraph merging tests."""

from __future__ import annotations

from tests.fixtures import paper_pdf, scanned_pdf, two_column_pdf


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
