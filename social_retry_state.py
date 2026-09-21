"""Bounded, resumable retry bookkeeping for social publication."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

MAX_ATTEMPTS = 5


def next_attempt(record: dict[str, Any]) -> dict[str, Any]:
    updated = dict(record)
    attempts = int(updated.get("attempts", 0)) + 1
    updated["attempts"] = attempts
    updated["last_attempt_at"] = datetime.now(timezone.utc).isoformat()
    updated["status"] = "exhausted" if attempts >= MAX_ATTEMPTS else "retry_pending"
    updated["next_retry_seconds"] = min(3600, 60 * (2 ** max(0, attempts - 1)))
    return updated


def can_retry(record: dict[str, Any]) -> bool:
    return record.get("status") in {"pending", "retry_pending", "failed"} and int(record.get("attempts", 0)) < MAX_ATTEMPTS
