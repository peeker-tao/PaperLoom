"""Context assembly and citation validation."""

from __future__ import annotations

from paperloom_service.context import build_context, validate_citations


def segments():
    return [
        {
            "id": "p1-s0",
            "page": 1,
            "text": "Title of the paper",
            "kind": "title",
            "bbox": [0, 0, 1, 1],
        },
        {
            "id": "p1-s1",
            "page": 1,
            "text": "We propose LoomAttention, a sparse attention method.",
            "kind": "body",
            "bbox": [0, 0, 1, 1],
        },
        {
            "id": "p1-s2",
            "page": 1,
            "text": "It reduces memory by 42 percent on three benchmarks.",
            "kind": "body",
            "bbox": [0, 0, 1, 1],
        },
        {
            "id": "p2-s0",
            "page": 2,
            "text": "2. Method",
            "kind": "heading",
            "bbox": [0, 0, 1, 1],
        },
        {
            "id": "p2-s1",
            "page": 2,
            "text": "The routing network selects key blocks.",
            "kind": "body",
            "bbox": [0, 0, 1, 1],
        },
    ]


def test_selection_scope_finds_block():
    ctx = build_context(
        segments(),
        scope="selection",
        selection={"text": "reduces memory by 42 percent", "page": 1},
    )
    assert ctx["anchorId"] == "p1-s2"
    assert "LoomAttention" in ctx["text"]
    assert ctx["segments"][0]["id"] == "p1-s0"


def test_section_scope_stops_at_heading():
    ctx = build_context(
        segments(), scope="section", selection={"text": "routing network", "page": 2}
    )
    assert ctx["anchorId"] == "p2-s1"
    ids = [s["id"] for s in ctx["segments"]]
    assert ids == ["p2-s0", "p2-s1"]


def test_unknown_selection_falls_back_with_note():
    ctx = build_context(
        segments(), scope="selection", selection={"text": "not in the paper", "page": 9}
    )
    assert ctx["note"]
    assert ctx["segments"]


def test_citations_drop_unknown_ids():
    cleaned, citations = validate_citations(
        "结论 A [[seg:p1-s1]]，结论 B [[seg:fake-id]]。", segments()
    )
    assert "fake-id" not in cleaned
    assert [c["segmentId"] for c in citations] == ["p1-s1"]
    assert citations[0]["page"] == 1
    assert citations[0]["quote"].startswith("We propose")


def test_uppercase_citation_markers_are_accepted_and_normalized():
    """Regression: real DeepSeek echoed [[SEG:...]] and the markers leaked."""
    cleaned, citations = validate_citations(
        "方法如下 [[SEG:p1-s1]]，另外 [[Seg:p2-s1]]。", segments()
    )
    assert "[[SEG:" not in cleaned
    assert "[[Seg:" not in cleaned
    assert cleaned.count("[[seg:") == 2
    assert [c["segmentId"] for c in citations] == ["p1-s1", "p2-s1"]


def test_mixed_case_unknown_marker_is_dropped():
    cleaned, citations = validate_citations("[[SEG:nope]]", segments())
    assert "nope" not in cleaned
    assert citations == []


def test_heading_only_section_is_widened():
    """A section anchored on a heading must include the body it introduces."""
    long_body = (
        "Relay diffusion splits generation into a base stage and a super-resolution "
        "stage that starts from a noised low-resolution image. " * 6
    )
    segs = [
        {
            "id": "p1-s0",
            "page": 1,
            "text": "1 Introduction",
            "kind": "heading",
            "bbox": [0, 0, 1, 1],
        },
        {
            "id": "p1-s1",
            "page": 1,
            "text": long_body,
            "kind": "body",
            "bbox": [0, 0, 1, 1],
        },
        {
            "id": "p2-s0",
            "page": 2,
            "text": "2 Method",
            "kind": "heading",
            "bbox": [0, 0, 1, 1],
        },
        {
            "id": "p2-s1",
            "page": 2,
            "text": "Should not be included.",
            "kind": "body",
            "bbox": [0, 0, 1, 1],
        },
    ]
    ctx = build_context(
        segs, scope="section", selection={"text": "1 Introduction", "page": 1}
    )
    ids = [s["id"] for s in ctx["segments"]]
    assert ids == ["p1-s0", "p1-s1"]
    assert "super-resolution" in ctx["text"]


def test_empty_answer_handled():
    cleaned, citations = validate_citations("", segments())
    assert cleaned == ""
    assert citations == []
