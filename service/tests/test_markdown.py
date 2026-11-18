"""Markdown rendering: English first, Chinese after (the reading/export format)."""

from __future__ import annotations

from paperloom_service.markdown import (
    markdown_stats,
    render_markdown,
    suggested_filename,
)


def segment(seg_id: str, page: int, kind: str, text: str, translation: str | None = None):
    return {
        "id": seg_id,
        "page": page,
        "kind": kind,
        "text": text,
        "translation": translation,
        "bbox": [0, 0, 100, 20],
        "align": "exact",
        "ordinal": 0,
    }


DOC = {"id": "doc1", "title": "CogView3: Finer and Faster", "pages": 2}

SEGMENTS = [
    segment("p1-s0", 1, "title", "CogView3: Finer and Faster", "CogView3：更精细更快速"),
    segment("p1-s1", 1, "body", "Diffusion models drive progress.", "扩散模型推动了进展。"),
    segment("p1-s2", 1, "formula", "q(xt|x0) = N (xt|F), st"),
    segment("p1-s3", 1, "table", "SDXL [17]"),
    segment("p1-s4", 1, "noise", "1"),
    segment("p1-s5", 1, "meta", "someone@example.edu"),
    segment("p1-s6", 1, "heading", "2.1 Text-to-Image Models", "2.1 文本到图像模型"),
    segment("p1-s7", 1, "body", "Relay diffusion reduces cost.", "接力扩散降低了成本。"),
    segment("p2-s0", 2, "reference", "1. Achiam, J.: Gpt-4 report. (2023)"),
    segment("p2-s1", 2, "body", "Experiments confirm the claim.", "实验验证了这一结论。"),
]


def test_english_comes_first_then_chinese():
    markdown = render_markdown(DOC, SEGMENTS, include_pages=False)
    body = markdown.split("\n\n")
    english = body.index("Diffusion models drive progress.")
    chinese = body.index("扩散模型推动了进展。")
    assert english < chinese, markdown
    # They are separate blocks, so the browser renders them as two paragraphs.
    assert "Diffusion models drive progress.\n\n扩散模型推动了进展。" in markdown


def test_non_prose_is_excluded():
    markdown = render_markdown(DOC, SEGMENTS)
    for unwanted in ["q(xt|x0)", "SDXL [17]", "someone@example.edu"]:
        assert unwanted not in markdown, unwanted


def test_references_are_optional():
    without = render_markdown(DOC, SEGMENTS)
    assert "Achiam" not in without
    with_refs = render_markdown(DOC, SEGMENTS, include_references=True)
    assert "Achiam" in with_refs


def test_headings_become_markdown_headings_with_translation_bold():
    markdown = render_markdown(DOC, SEGMENTS)
    # "2.1 ..." is a subsection -> "###".
    assert "### 2.1 Text-to-Image Models" in markdown
    assert "**2.1 文本到图像模型**" in markdown
    # The title is the document heading.
    assert markdown.startswith("# CogView3: Finer and Faster")


def test_page_markers_are_comments():
    markdown = render_markdown(DOC, SEGMENTS)
    assert "<!-- p1 -->" in markdown
    assert "<!-- p2 -->" in markdown
    # Markers are invisible when rendered and do not add headings.
    assert markdown.count("<!-- p") == 2


def test_original_only_and_translation_only():
    original = render_markdown(DOC, SEGMENTS, include_translation=False)
    assert "Diffusion models drive progress." in original
    assert "扩散模型推动了进展。" not in original

    chinese = render_markdown(DOC, SEGMENTS, include_original=False)
    assert "扩散模型推动了进展。" in chinese
    assert "Diffusion models drive progress." not in chinese


def test_untranslated_paragraph_still_shows_the_source():
    """A partly translated document must stay readable, not silently lose text."""
    segments = [segment("p1-s0", 1, "body", "Not translated yet.")]
    markdown = render_markdown(DOC, segments)
    assert "Not translated yet." in markdown


def test_front_matter_reports_progress():
    markdown = render_markdown(DOC, SEGMENTS)
    assert "共 2 页" in markdown
    assert "段已译" in markdown


def test_newlines_are_flattened():
    segments = [segment("p1-s0", 1, "body", "line one\nline two", "第一行\n第二行")]
    markdown = render_markdown(DOC, segments)
    assert "line one line two" in markdown
    assert "第一行 第二行" in markdown


def test_stats_and_filename():
    markdown = render_markdown(DOC, SEGMENTS)
    stats = markdown_stats(markdown, SEGMENTS)
    assert stats["chars"] == len(markdown)
    assert stats["englishWords"] > 0
    assert stats["chineseChars"] > 0
    assert suggested_filename(DOC).endswith(".md")
    assert suggested_filename({"title": 'a/b:c*?"<>|'}) == "a b c.md"


def test_paper_title_wins_over_the_zotero_filename():
    """Zotero titles look like "Zheng 等 - 2024 - CogView3"; that is not the H1."""
    document = {"id": "doc1", "title": "Zheng 等 - 2024 - CogView3", "pages": 2}
    markdown = render_markdown(document, SEGMENTS)
    assert markdown.startswith("# CogView3: Finer and Faster\n")
    # Exactly one H1: the real title, not the filename and not a duplicate.
    assert markdown.count("\n# ") == 0
    assert "Zheng 等" not in markdown

