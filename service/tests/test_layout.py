"""Paragraph assembly: column breaks, split lines, and end-of-line hyphens.

Every case here comes from measured coordinates of a real two-column paper
(E-RayZer). The failures they pin down were visible in the reading view as
sentences cut in half:

    "... operates directly in 3D space,"        <- one visual line, half of it
    "learning self-"                            <- became its own paragraph
    "supervised 3D reconstruction. ... pre-"     <- and another one after that

    "... We highlight key conclusions"          <- bottom of the left column
    "and summarize our contributions ..."        <- top of the right column,
                                                   never joined to the above
"""

from __future__ import annotations

from paperloom_service.pdf.extract import TextLine, _join, _merge_page


def line(
    text: str,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    column: int,
    size: float = 10.0,
) -> TextLine:
    return TextLine(
        page=1,
        text=text,
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        size=size,
        column=column,
    )


LEFT = (58.5, 294.75)
RIGHT = (317.25, 553.5)


def left(text: str, y0: float, *, x0: float | None = None, x1: float | None = None):
    return line(
        text,
        LEFT[0] if x0 is None else x0,
        LEFT[1] if x1 is None else x1,
        y0,
        y0 + 10.2,
        1,
    )


def right(text: str, y0: float):
    return line(text, RIGHT[0], RIGHT[1], y0, y0 + 10.2, 2)


def test_one_visual_line_split_in_two_is_reassembled():
    """pdfminer emitted these two objects at the same baseline (y=401.84)."""
    lines = [
        left("E-RayZer operates directly in 3D space,", 401.84, x1=233.07),
        line("learning self-", 239.09, 294.75, 401.84, 411.80, 1),
        left("supervised 3D reconstruction. Concretely, E-RayZer pre-", 389.88),
        left("dicts camera parameters and 3D Gaussians.", 377.92),
    ]
    segments = _merge_page(lines, 1, 10.0, {"self-supervised", "predicts"})
    assert len(segments) == 1, [s["text"] for s in segments]
    text = segments[0]["text"]
    # The sentence survives the split line and the column-edge heuristic.
    assert "3D space, learning self-supervised 3D reconstruction" in text
    # The compound keeps its hyphen; the hyphenation loses it.
    assert "self-supervised" in text
    assert text.endswith("E-RayZer predicts camera parameters and 3D Gaussians.")


def test_paragraph_continues_from_the_bottom_of_one_column_to_the_next():
    lines = [
        left("We systematically study E-RayZer performance across", 100.0),
        left("different training data scales. We highlight key conclusions", 88.0),
        right("and summarize our contributions as follows:", 700.0),
        right("• E-RayZer is the first self-supervised model", 688.0),
    ]
    segments = _merge_page(lines, 1, 10.0, set())
    assert len(segments) == 2, [s["text"][:40] for s in segments]
    assert segments[0]["text"].endswith("contributions as follows:")


def test_short_last_line_ends_the_paragraph_at_the_column_break():
    """A short line means the paragraph stopped there; do not swallow the column."""
    lines = [
        left("The remainder of this section discusses the training data.", 100.0),
        left("This ends here.", 88.0, x1=180.0),
        right("2. Related Work", 700.0),
        right("Supervised pose estimation and 3D reconstruction.", 688.0),
    ]
    segments = _merge_page(lines, 1, 10.0, set())
    texts = [s["text"] for s in segments]
    assert "This ends here." in texts or any(t.endswith("This ends here.") for t in texts)
    assert any(t.startswith("2. Related Work") for t in texts)


def test_a_heading_at_the_column_bottom_does_not_absorb_the_next_column():
    lines = [
        left("4.4. Ablation Study", 78.85, x1=148.63),
        right("Data mixing and scaling is studied below.", 700.0),
    ]
    segments = _merge_page(lines, 1, 10.0, set())
    assert len(segments) == 2, [s["text"] for s in segments]


def test_cross_column_box_stays_inside_one_column():
    """A box spanning both columns would be most of the sheet to the overlay."""
    lines = [
        left("We systematically study E-RayZer performance across all", 100.0),
        left("different training data scales. We highlight key conclusions", 88.0),
        right("and summarize our contributions as follows:", 700.0),
    ]
    segments = _merge_page(lines, 1, 10.0, set())
    x0, _y0, x1, _y1 = segments[0]["bbox"]
    assert x1 <= LEFT[1] + 1, segments[0]["bbox"]
    assert x0 >= LEFT[0] - 1


def test_hyphen_before_a_capital_never_becomes_a_space():
    """\"E-\" + \"RayZer\" is \"E-RayZer\"; \"E- RayZer\" is not a word."""
    assert _join("we use E-", "RayZer as the baseline", set()) == "we use E-RayZer as the baseline"
    assert _join("its predecessor E-", "RayZer [25]", set()) == "its predecessor E-RayZer [25]"


def test_hyphenation_and_compounds_still_resolve_with_the_vocabulary():
    vocab = {"implementing", "text-to-image", "predicts", "convergence"}
    assert _join("im-", "plementing the model", vocab) == "implementing the model"
    assert _join("a text-", "to-image model", vocab) == "a text-to-image model"
    assert _join("E-RayZer pre-", "dicts cameras", vocab) == "E-RayZer predicts cameras"
    assert _join("To ensure conver-", "gence and scalability", vocab) == (
        "To ensure convergence and scalability"
    )


def test_a_paragraph_split_by_an_equation_is_rejoined():
    """"… as self-supervision:" / [equation] / "where Percep denotes …".

    The clause after a display equation explains that equation, so it belongs to
    the paragraph that introduced it. Sent as its own paragraph it starts with a
    lowercase word and translates as a fragment.
    """
    from paperloom_service.pdf.extract import _join_broken_segments

    segments = [
        {
            "page": 3,
            "ordinal": 0,
            "kind": "body",
            "text": "We use the photometric loss as self-supervision:",
            "bbox": (58.5, 700.0, 294.0, 712.0),
        },
        {
            "page": 3,
            "ordinal": 1,
            "kind": "formula",
            "text": "L = MSE(I, ˆI) + λ · Percep(I, ˆI)",
            "bbox": (110.0, 690.0, 250.0, 698.0),
        },
        {
            "page": 3,
            "ordinal": 2,
            "kind": "body",
            "text": "where Percep denotes the perceptual loss [27].",
            "bbox": (58.5, 680.0, 294.0, 690.0),
        },
    ]
    result = _join_broken_segments(segments, set())
    assert [s["kind"] for s in result] == ["body", "formula"], result
    assert result[0]["text"].endswith("where Percep denotes the perceptual loss [27].")


def test_a_run_in_label_does_not_split_its_sentence():
    """"… results of E-RayZer" / "Datasets." / "trained on both …"."""
    from paperloom_service.pdf.extract import _lift_inline_labels

    segments = [
        {
            "page": 5,
            "ordinal": 0,
            "kind": "body",
            "text": "Training. We present results of E-RayZer",
            "bbox": (58.5, 700.0, 294.0, 712.0),
        },
        {
            "page": 5,
            "ordinal": 1,
            "kind": "body",
            "text": "Datasets.",
            "bbox": (58.5, 690.0, 120.0, 700.0),
        },
        {
            "page": 5,
            "ordinal": 2,
            "kind": "body",
            "text": "trained on both single-dataset and multi-dataset settings.",
            "bbox": (58.5, 680.0, 294.0, 690.0),
        },
    ]
    _lift_inline_labels(segments, set())
    assert len(segments) == 2, [s["text"] for s in segments]
    assert segments[0]["text"] == (
        "Training. We present results of E-RayZer"
        " trained on both single-dataset and multi-dataset settings."
    )
    assert segments[1]["kind"] == "heading"
    assert segments[1]["text"] == "Datasets."


def test_cid_glyph_runs_are_not_printed_as_paragraphs():
    """pdfminer prints unmappable glyphs as (cid:1); they are equation debris."""
    from paperloom_service.pdf.extract import _is_math_fragment

    assert _is_math_fragment("tgt )(cid:1).")
    assert _is_math_fragment(", Linear(Iref, Rplk")
    assert not _is_math_fragment("RayZer uses predicted cameras of target views.")

