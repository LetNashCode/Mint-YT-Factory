"""Authoritative stock-media adapter for Mint-YT-Factory.

Gemini directs stock searches AND verifies downloaded stock candidates.
ALL Gemini calls use the single canonical model configured by stock_search.
"""
from __future__ import annotations

import stock_search

GEMINI_MODEL = stock_search.GEMINI_MODEL


def generate_media(script: dict, output_dir: str, config: dict, gim=None):
    """Generate 7x2 stock assets using Gemini direction + visual verification."""
    print(f"🛡️ Stock media adapter: Gemini search + visual verification ENABLED ({GEMINI_MODEL}; no fallback model)")
    return stock_search.generate_media(script, output_dir, config, gim=gim)
