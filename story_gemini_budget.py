"""Run-wide Gemini request budget for one Story Shorts production run.

Every real Gemini generate_content request made by Story generation, scripting,
visual verification, or stock search consumes one unit. The budget is reset only
when a new Story production process starts; subject retries must share it.

When the visual Gemini cap is reached, GitHub Actions must stop/defer rather than
fall back to CPU Qwen. Local development may opt into Qwen explicitly.
"""
from __future__ import annotations

import os
from pathlib import Path

BUDGET_DEFER_FILE = ".story_gemini_budget_deferred"
DEFAULT_MAX_REQUESTS = 64
# Keep a protected slice of the run-wide Gemini budget for story scripting and
# any later Gemini work. Once the visual verifier reaches this cap, production
# must stop/defer instead of burning the remaining run-wide Gemini budget on
# archival-frame rejection loops.
DEFAULT_MAX_VISUAL_GEMINI_REQUESTS = 56

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
    if str(stage or "").strip() == "visual_verification" and _BUDGET["used"] >= visual_gemini_limit():
        reason = (
            f"Story Gemini visual verification budget exhausted after {_BUDGET['used']} requests "
            f"(visual_limit={visual_gemini_limit()}, total_limit={_BUDGET['limit']})"
        )
        Path(BUDGET_DEFER_FILE).write_text(reason + "\\n", encoding="utf-8")
        print(f"🛑 {reason}; deferring Story publication", flush=True)
        raise RuntimeError(reason)
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


def visual_gemini_limit() -> int:
    """Maximum run-wide Gemini calls reserved for real-video visual verification."""
    ensure()
    limit = int(_BUDGET["limit"])
    raw = os.environ.get(
        "STORY_GEMINI_MAX_VISUAL_REQUESTS",
        str(DEFAULT_MAX_VISUAL_GEMINI_REQUESTS),
    ).strip()
    try:
        configured = int(raw)
    except (TypeError, ValueError):
        configured = DEFAULT_MAX_VISUAL_GEMINI_REQUESTS
    # Keep at least eight calls available for script/title/final Story work.
    # For smaller test budgets, scale the visual cap down instead of consuming
    # the entire run budget.
    reserve = 8
    return min(limit, max(14, min(configured, max(14, limit - reserve))))


def should_use_qwen_for_visual_verification(qwen_enabled: bool) -> bool:
    """Return whether local Qwen may take over visual verification.

    Never use CPU Qwen on GitHub-hosted production runners. A single Qwen
    verification can take several minutes and malformed JSON can trigger a
    second inference, which can consume the entire workflow timeout. CI must
    stop at the Gemini visual budget and let the caller fail/defer cleanly.
    Local development may still opt into Qwen explicitly.
    """
    if not qwen_enabled:
        return False
    if str(os.environ.get("GITHUB_ACTIONS", "")).strip().lower() == "true":
        return False
    ensure()
    return int(_BUDGET["used"]) >= visual_gemini_limit()
