"""Authoritative stock-media adapter for Mint-YT-Factory.

The actual media selection, semantic search, candidate verification and provider
fallback live in stock_search.py. This module intentionally contains no second
Gemini implementation or model fallback list, preventing stale model references
from bypassing the single-model policy.
"""
from __future__ import annotations

import os

import stock_search

GEMINI_MODEL = stock_search.GEMINI_MODEL


def generate_media(script: dict, output_dir: str, config: dict, gim=None):
    """Generate the required 7x2 stock assets through the authoritative pipeline."""
    print(f"🛡️ Stock media adapter: using authoritative stock_search ({GEMINI_MODEL})")
    return stock_search.generate_media(script, output_dir, config, gim=gim)
