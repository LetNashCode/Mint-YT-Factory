"""Metadata-based quality checks for Story Shorts archival assets.

This gate cannot prove image-level identity, but it rejects assets whose
Wikimedia metadata has no meaningful overlap with the requested person or
scene query. It is intentionally conservative: weak evidence fails closed.
"""
from __future__ import annotations

import re
from typing import Any

_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "about",
    "historical", "history", "photograph", "photo", "image", "video", "archival",
    "documented", "show", "use", "clearly", "identified", "context", "specific",
}


def _tokens(value: Any) -> set[str]:
    words = re.findall(r"[a-z0-9]{3,}", str(value or "").lower())
    return {word for word in words if word not in _STOPWORDS}


def score_candidate(person: str, query: str, candidate: dict[str, Any]) -> tuple[float, set[str]]:
    requested = _tokens(f"{person} {query}")
    metadata = _tokens(" ".join(str(candidate.get(key) or "") for key in ("title", "description", "artist")))
    overlap = requested & metadata
    person_tokens = _tokens(person)
    person_match = bool(person_tokens and person_tokens <= metadata)
    score = float(len(overlap))
    if person_match:
        score += 4.0
    return score, overlap


def require_relevant_candidate(person: str, query: str, candidate: dict[str, Any], minimum: float = 2.0) -> float:
    score, overlap = score_candidate(person, query, candidate)
    if score < minimum:
        title = candidate.get("title") or candidate.get("url") or "unknown asset"
        raise RuntimeError(
            f"Archival relevance gate rejected {title!r}: score={score:.1f}, "
            f"required={minimum:.1f}, matched={sorted(overlap)}"
        )
    return score


def validate_groups(groups: list[dict[str, Any]], expected: int = 14) -> None:
    if len(groups) != expected:
        raise RuntimeError(f"Story visual quality gate failed: expected {expected} assets, got {len(groups)}")
    identities = [str(item.get("source_url") or item.get("asset_key") or "").strip() for item in groups]
    if any(not value for value in identities):
        raise RuntimeError("Story visual quality gate failed: asset has no source identity")
    if len(identities) != len(set(identities)):
        raise RuntimeError("Story visual quality gate failed: archival asset reused across shots")
