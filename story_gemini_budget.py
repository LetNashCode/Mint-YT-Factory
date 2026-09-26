"""Run-wide Gemini request budget for one Story Shorts production run.

Every real Gemini generate_content request made by Story generation, scripting,
visual verification, or stock search consumes one unit. The budget is reset only
when a new Story production process starts; subject retries must share it.
"""
from __future__ import annotations

import os
from pathlib import Path

BUDGET_DEFER_FILE = ".story_gemini_budget_deferred"
DEFAULT_MAX_REQUESTS = 64

_BUDGET = None


def begin():
    global _BUDGET
    raw = os.environ.get("STORY_GEMINI_MAX_REQUESTS", "").strip()
    if not raw:
        # Backward compatibility with the old verifier-only setting.
        raw = os.environ.get("STORY_VERIFIER_MAX_REQUESTS", str(DEFAULT_MAX_REQUESTS))
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        limit = DEFAULT_MAX_REQUESTS
    _BUDGET = {"limit": max(1, limit), "used": 0}
    return dict(_BUDGET)


def ensure():
    if _BUDGET is None:
        begin()


def reset():
    global _BUDGET
    _BUDGET = None


def consume(stage: str):
    """Reserve one request immediately before a real Gemini API call."""
    if _BUDGET is None:
        return 0
    if _BUDGET["used"] >= _BUDGET["limit"]:
        reason = (
            f"Story Gemini request budget exhausted after {_BUDGET['used']} requests "
            f"(limit={_BUDGET['limit']}, stage={str(stage).strip() or 'unknown'})"
        )
        Path(BUDGET_DEFER_FILE).write_text(reason + "\n", encoding="utf-8")
        print(f"🛑 {reason}; deferring Story publication", flush=True)
        raise RuntimeError(reason)
    _BUDGET["used"] += 1
    return _BUDGET["used"]


def status():
    if _BUDGET is None:
        return {"limit": None, "used": 0}
    return dict(_BUDGET)
