"""Authoritative stock-media adapter for Mint-YT-Factory.

Gemini may direct stock searches, but it is NOT used to visually verify or
reject downloaded candidates. Candidate selection is deterministic from the
stock-provider metadata/ranking, with provider fallback only.
"""
from __future__ import annotations

import stock_search

GEMINI_MODEL = stock_search.GEMINI_MODEL


def _metadata_pick(candidates, directed):
    """Pick the highest deterministic stock-search candidate.

    The candidate list is already ranked by stock_search.rank(). Do not send
    candidate previews to Gemini for a second visual verification pass.
    """
    if not candidates:
        return None
    chosen = dict(candidates[0])
    chosen["visual_score"] = float(chosen.get("metadata_score", 0) or 0)
    chosen["visual_subject_match"] = 0.0
    chosen["visual_action_match"] = 0.0
    chosen["visual_context_match"] = 0.0
    chosen["visual_reason"] = "Selected by deterministic stock metadata ranking; Gemini visual verification disabled."
    return chosen


def generate_media(script: dict, output_dir: str, config: dict, gim=None):
    """Generate 7x2 stock assets using search direction + deterministic ranking."""
    original_verify = stock_search.verify
    stock_search.verify = _metadata_pick
    try:
        print("🛡️ Stock media adapter: Gemini search direction only; visual verification DISABLED")
        return stock_search.generate_media(script, output_dir, config, gim=gim)
    finally:
        stock_search.verify = original_verify
