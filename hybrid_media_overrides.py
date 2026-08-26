"""Deprecated compatibility module.

Production media is owned exclusively by pexels_media.py. This module is kept
only so stale imports fail safely without changing the active pipeline.
"""
from __future__ import annotations


def patch_hybrid_media(pexels_media, generate_images_module=None):
    """Compatibility no-op; never alters the production media provider."""
    print("🛑 Legacy media override disabled — Pexels-only production mode")
    return None
