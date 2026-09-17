"""Helpers for resilient stock-search fallback behavior.

This module is intentionally dependency-light. It provides conservative checks
used by runtime integrations when Gemini vision is unavailable or rate-limited.
"""
from __future__ import annotations

import re
from typing import Any


def is_quota_exhausted(exc: BaseException) -> bool:
    """Return True for Gemini/API quota exhaustion errors, including HTTP 429."""
    text = str(exc).lower()
    return any(token in text for token in (
        "429", "resource_exhausted", "resource exhausted", "quota exceeded",
        "generaterequestsperminute", "ratelimitexceeded",
    ))


def metadata_text(item: dict[str, Any], query: str = "") -> str:
    """Build searchable metadata without treating provider URLs as subject text."""
    values = [query, item.get("alt"), item.get("description"), item.get("tags")]
    return " ".join(str(value or "") for value in values).lower()


def conservative_relevance(
    item: dict[str, Any],
    query: str,
    anchors: list[str] | None = None,
) -> float:
    """Score concrete subject overlap for a no-vision fallback.

    The query itself contributes only once; repeated query words cannot inflate
    the score. Exact anchor matches receive additional weight.
    """
    text = metadata_text(item, query)
    query_words = {word for word in re.findall(r"[a-z0-9]+", query.lower()) if len(word) > 2}
    anchor_words = {
        word for anchor in (anchors or [])
        for word in re.findall(r"[a-z0-9]+", str(anchor).lower())
        if len(word) > 2
    }
    score = float(sum(1 for word in query_words if re.search(rf"\b{re.escape(word)}\b", text)))
    score += 2.0 * sum(1 for word in anchor_words if re.search(rf"\b{re.escape(word)}\b", text))
    return score


def acceptable_fallback(
    item: dict[str, Any],
    query: str,
    anchors: list[str] | None = None,
    minimum: float = 2.0,
) -> bool:
    """Allow a candidate only when concrete metadata overlaps the subject."""
    return conservative_relevance(item, query, anchors) >= minimum
