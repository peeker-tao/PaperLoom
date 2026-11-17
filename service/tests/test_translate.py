"""Translation pipeline unit tests that do not need the network."""

from __future__ import annotations

from paperloom_service.translate import SKIP_KINDS, _has_prose, _parse_translations


def test_has_prose_rejects_fragments():
    assert _has_prose("We propose a relay diffusion model for text-to-image generation.")
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


def test_parse_translations_accepts_wrapped_json():
    payload = '```json\n{"translations":[{"id":"p1-s0","text":"你好"}]}\n```'
    assert _parse_translations(payload) == {"p1-s0": "你好"}


def test_parse_translations_accepts_dict_form():
    payload = '{"translations":{"p1-s0":"你好","p1-s1":"世界"}}'
    assert _parse_translations(payload) == {"p1-s0": "你好", "p1-s1": "世界"}


def test_parse_translations_ignores_broken_entries():
    payload = '{"translations":[{"id":"","text":"x"},{"id":"p1-s0"},{"id":"p1-s1","text":"ok"}]}'
    assert _parse_translations(payload) == {"p1-s1": "ok"}
