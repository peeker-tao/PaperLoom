"""Translation provenance: identity, staleness and change reasons."""

from __future__ import annotations

from paperloom_service.translation_config import (
    PROMPT_VERSION,
    TranslationConfig,
    diff_reasons,
    evaluate,
    glossary_digest,
)

TERMS = [
    {"source": "relay diffusion", "target": "中继扩散"},
    {"source": "latent space", "target": "潜空间"},
]


def build(**overrides):
    params = {
        "model": "deepseek-flash",
        "base_url": "https://api.deepseek.com",
        "terms": TERMS,
        "max_output": 8192,
        "document_hash": "abc123",
    }
    params.update(overrides)
    return TranslationConfig.build(**params)


def segment(seg_id: str, translation: str | None, config: dict | None, kind="body"):
    return {
        "id": seg_id,
        "kind": kind,
        "text": "We propose a relay diffusion model for text-to-image generation.",
        "translation": translation,
        "translationConfig": config,
    }


def translatable(seg: dict) -> bool:
    return seg["kind"] not in {"reference", "meta", "noise"}


def test_identity_is_stable_and_order_independent():
    a = build()
    b = build(terms=list(reversed(TERMS)))
    assert a.key == b.key
    assert glossary_digest(TERMS) == glossary_digest(list(reversed(TERMS)))


def test_identity_changes_with_model():
    assert build().key != build(model="deepseek-v4-pro").key


def test_identity_changes_with_glossary():
    changed = [{"source": "relay diffusion", "target": "接力扩散"}]
    assert build().key != build(terms=changed).key


def test_identity_changes_with_base_url_and_normalizes():
    official = build()
    with_v1 = build(base_url="https://api.deepseek.com/v1")
    assert official.key != with_v1.key
    # Trailing slash must not create a new identity.
    assert build(base_url="https://api.deepseek.com/").key == official.key


def test_identity_changes_with_document_hash_and_prompt():
    assert build().key != build(document_hash="other").key
    other = build()
    other.prompt_version = PROMPT_VERSION + 1
    assert other.key != build().key


def test_diff_reasons_explains_each_change():
    current = build()
    stored = build(model="deepseek-v4-pro").as_dict()
    assert diff_reasons(stored, current) == ["model"]

    stored = build(terms=[{"source": "x", "target": "y"}]).as_dict()
    assert diff_reasons(stored, current) == ["glossary"]


def test_historical_rows_are_unknown_not_stale():
    current = build()
    status = evaluate(
        [segment("p1-s0", "旧译文", None)],
        current,
        translatable=translatable,
    )
    assert status.unknown == 1
    assert status.stale == 0
    assert status.current == 0
    assert status.reasons == ["unknown"]
    assert status.as_dict()["needsAttention"] is True
    # An explicit re-translate request must cover these rows too.
    assert status.stale_ids == ["p1-s0"]


def test_current_config_counts_as_current():
    current = build()
    status = evaluate(
        [segment("p1-s0", "译文", current.as_dict())], current, translatable=translatable
    )
    assert status.current == 1
    assert status.stale == 0
    assert status.as_dict()["needsAttention"] is False


def test_model_change_marks_segments_stale():
    current = build()
    stored = build(model="deepseek-v4-pro").as_dict()
    status = evaluate(
        [segment("p1-s0", "译文", stored), segment("p1-s1", "译文2", stored)],
        current,
        translatable=translatable,
    )
    assert status.stale == 2
    assert status.stale_ids == ["p1-s0", "p1-s1"]
    assert "model" in status.reasons


def test_glossary_change_marks_stale_with_readable_reason():
    current = build()
    stored = build(terms=[{"source": "relay diffusion", "target": "旧译名"}]).as_dict()
    status = evaluate(
        [segment("p1-s0", "译文", stored)], current, translatable=translatable
    )
    assert status.stale == 1
    assert "glossary" in status.reasons
    assert "术语表已变更" in status.as_dict()["reasonsText"]


def test_missing_counts_only_translatable_prose():
    current = build()
    segs = [
        segment("p1-s0", None, None, kind="body"),
        segment("p1-s1", None, None, kind="noise"),
        segment("p1-s2", None, None, kind="reference"),
    ]
    status = evaluate(segs, current, translatable=translatable)
    assert status.missing == 1
