"""Deprecated media override.

Mint-YT-Factory is Pexels-only in production.
AI image generation, Pollinations and FLUX are intentionally disabled.

This compatibility module is retained so stale imports cannot accidentally
restore the previous hybrid-media behaviour.
"""
from __future__ import annotations


def patch_hybrid_media(pexels_media, generate_images_module=None):
    """Compatibility no-op. Production media selection is Pexels-only."""
    print("🛑 Hybrid media override disabled — Pexels-only production mode")
    return None
