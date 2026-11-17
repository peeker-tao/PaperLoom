"""Translation pipeline unit tests that do not need the network."""

from __future__ import annotations

from paperloom_service.translate import (
    MIN_TRANSLATE_CHARS,
    SKIP_KINDS,
    _has_prose,
    _output_problem,
    _parse_translations,
    _translate_prompt,
    is_translatable,
)


def test_has_prose_rejects_fragments():
    assert _has_prose(
        "We propose a relay diffusion model for text-to-image generation."
    )
    assert _has_prose("基于中继扩散的文生图模型")
    assert not _has_prose("2")
    assert not _has_prose("r")
    assert not _has_prose("0 2")
    assert not _has_prose("...")
    assert not _has_prose("1234567890")


def test_skip_kinds_exclude_meta_and_noise():
    assert "reference" in SKIP_KINDS
    assert "meta" in SKIP_KINDS
    assert "noise" in SKIP_KINDS
    # Equations and table cells must never be translated: they carry no prose.
    assert "formula" in SKIP_KINDS
    assert "table" in SKIP_KINDS


def test_is_translatable_requires_real_prose():
    body = {
        "kind": "body",
        "text": "CogView3 is the first model implementing relay diffusion at scale.",
    }
    assert is_translatable(body)
    # Too short to survive translation on its own (figure labels, cells).
    assert not is_translatable({"kind": "body", "text": "Alignment"})
    assert not is_translatable({"kind": "formula", "text": body["text"]})
    assert not is_translatable({"kind": "reference", "text": body["text"]})
    assert not is_translatable({"kind": "body", "text": "3"})
    assert len("Alignment") < MIN_TRANSLATE_CHARS


def test_output_problem_flags_truncated_translation():
    source = (
        "Recent advancements in text-to-image generative systems have been largely "
        "driven by diffusion models. However, single-stage models still face "
        "challenges in computational efficiency and image detail refinement."
    )
    assert (
        _output_problem(source, "近期文本到图像系统的进展由扩散模型推动。")
        == "too_short"
    )
    # Echoing the source is reported as non-Chinese, not "too short".
    assert (
        _output_problem(source, "Recent advancements in text-to-image") == "no_chinese"
    )


def test_output_problem_accepts_faithful_translation():
    source = (
        "We propose a cascaded framework that first generates low-resolution images."
    )
    good = "我们提出一种级联框架，先生成低分辨率图像。"
    assert _output_problem(source, good) == ""


def test_output_problem_flags_non_chinese_and_identity():
    source = (
        "We propose a cascaded framework that first generates low-resolution images."
    )
    assert _output_problem(source, "We propose a cascaded framework.") == "no_chinese"
    assert _output_problem(source, source) == "untranslated"


def test_prompt_includes_context_when_given():
    batch = [{"id": "p1-s0", "text": "Relay diffusion reduces inference cost."}]
    plain = _translate_prompt(batch, [])
    assert "<context>" not in plain
    assert "[[SEG:p1-s0]]" in plain
    with_context = _translate_prompt(
        batch, [], context="论文标题：CogView3\n上一段原文：Diffusion models emerged."
    )
    assert "<context>" in with_context
    assert "CogView3" in with_context
    # Context is reference material, not a translation target.
    assert with_context.index("</context>") < with_context.index("<segments>")


def test_parse_translations_accepts_wrapped_json():
    payload = '```json\n{"translations":[{"id":"p1-s0","text":"你好"}]}\n```'
    assert _parse_translations(payload) == {"p1-s0": "你好"}


def test_parse_translations_accepts_dict_form():
    payload = '{"translations":{"p1-s0":"你好","p1-s1":"世界"}}'
    assert _parse_translations(payload) == {"p1-s0": "你好", "p1-s1": "世界"}


def test_parse_translations_ignores_broken_entries():
    payload = '{"translations":[{"id":"","text":"x"},{"id":"p1-s0"},{"id":"p1-s1","text":"ok"}]}'
    assert _parse_translations(payload) == {"p1-s1": "ok"}
