"""Deprecated compatibility module.

Media selection is now implemented directly in pexels_media.py.
The active architecture is Gemini Visual/Search Director -> Pexels search -> deterministic selection.
This module intentionally performs no Gemini candidate inspection and no alternate-provider fallback.
"""
from __future__ import annotations


def patch_media_selection(media):
    """Compatibility no-op; pexels_media owns media selection now."""
    print("ℹ️ Media selection override retired; using pexels_media.py directly")
    return media
