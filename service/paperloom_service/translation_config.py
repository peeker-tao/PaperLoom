"""Provenance of a translated segment.

A translation is only reusable while the configuration that produced it is
still in effect. This module builds the identity, compares stored identities
with the current one, and explains *what* changed so the UI can ask the user
instead of silently mixing incompatible translations.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .urls import normalize_base_url

# Bump whenever the translation prompt changes in a way that affects output.
PROMPT_VERSION = 2

REASON_LABELS = {
    "model": "翻译模型已变更",
    "base_url": "服务地址已变更",
    "prompt": "翻译提示模板已升级",
    "glossary": "术语表已变更",
    "max_output": "输出长度上限已变更",
    "document": "PDF 文件已变更",
}


def glossary_digest(terms: list[dict]) -> str:
    """Order-independent digest of the effective glossary."""
    pairs = sorted(
        f"{t.get('source', '').strip().lower()}=>{t.get('target', '').strip()}"
        for t in terms
        if t.get("source") and t.get("target")
    )
    return hashlib.sha1("|".join(pairs).encode("utf-8")).hexdigest()[:12]


@dataclass
class TranslationConfig:
    model: str
    base_url: str
    prompt_version: int = PROMPT_VERSION
    glossary: str = ""
    max_output: int = 0
    document_hash: str = ""

    def as_dict(self) -> dict:
        return {
            "model": self.model,
            "base_url": self.base_url,
            "prompt_version": self.prompt_version,
            "glossary": self.glossary,
            "max_output": self.max_output,
            "document_hash": self.document_hash,
            "key": self.key,
        }

    @property
    def key(self) -> str:
        parts = "|".join(
            [
                self.model,
                self.base_url,
                str(self.prompt_version),
                self.glossary,
                str(self.max_output),
                self.document_hash,
            ]
        )
        return hashlib.sha1(parts.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def build(
        cls,
        *,
        model: str,
        base_url: str,
        terms: list[dict],
        max_output: int,
        document_hash: str,
    ) -> TranslationConfig:
        return cls(
            model=model,
            base_url=normalize_base_url(base_url),
            prompt_version=PROMPT_VERSION,
            glossary=glossary_digest(terms),
            max_output=int(max_output),
            document_hash=document_hash or "",
        )


def diff_reasons(stored: dict | None, current: TranslationConfig) -> list[str]:
    """Return human-readable change reasons between a stored and current config."""
    if not stored:
        return ["unknown"]
    now = current.as_dict()
    reasons = []
    for key in ("model", "base_url", "prompt_version", "glossary", "max_output"):
        if key in stored and stored.get(key) != now.get(key):
            reasons.append(
                {
                    "prompt_version": "prompt",
                    "base_url": "base_url",
                }.get(key, key)
            )
    if stored.get("document_hash") and stored["document_hash"] != now["document_hash"]:
        reasons.append("document")
    return reasons


@dataclass
class TranslationStatus:
    total: int = 0
    current: int = 0
    stale: int = 0
    unknown: int = 0
    missing: int = 0
    reasons: list[str] = field(default_factory=list)
    stale_ids: list[str] = field(default_factory=list)
    config_key: str = ""

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "current": self.current,
            "stale": self.stale,
            "unknown": self.unknown,
            "missing": self.missing,
            "reasons": self.reasons,
            "reasonsText": [REASON_LABELS.get(r, r) for r in self.reasons],
            "staleSegmentIds": self.stale_ids[:200],
            "configKey": self.config_key,
            "needsAttention": self.stale > 0 or self.unknown > 0,
        }


def _stored_config(seg: dict) -> dict | None:
    stored = seg.get("translationConfig")
    if stored is None:
        stored = seg.get("translation_config")
    if isinstance(stored, str):
        import json

        try:
            stored = json.loads(stored)
        except json.JSONDecodeError:
            return None
    return stored or None


def evaluate(
    segments: list[dict], current: TranslationConfig, *, translatable
) -> TranslationStatus:
    """Classify every segment against the current translation configuration.

    ``translatable`` is the predicate matching the set the translator would
    work on, so ``missing`` means "prose that has no translation yet".
    """
    status = TranslationStatus(config_key=current.key)
    reasons: set[str] = set()
    for seg in segments:
        translation = seg.get("translation")
        if translation:
            status.total += 1
            stored = _stored_config(seg)
            if not stored:
                status.unknown += 1
                reasons.add("unknown")
                # An explicit "re-translate outdated" request should also refresh
                # rows whose provenance predates this feature.
                status.stale_ids.append(seg["id"])
            elif stored.get("key") == current.key:
                status.current += 1
            else:
                status.stale += 1
                status.stale_ids.append(seg["id"])
                reasons.update(diff_reasons(stored, current))
        elif translatable(seg):
            status.missing += 1
    status.reasons = sorted(r for r in reasons if r != "unknown")
    if "unknown" in reasons:
        status.reasons.append("unknown")
    return status
