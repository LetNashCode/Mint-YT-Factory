"""Compatibility entrypoint for story-driven Pexels media.

Actual media selection lives in pexels_media.py. Gemini acts only as the
Visual/Search Director and Pexels is the sole production media provider.
"""
from __future__ import annotations

from pexels_media import generate_media


def generate_images(script, output_dir, config):
    """Compatibility wrapper returning 7 scenes × 2 Pexels assets."""
    return generate_media(script, output_dir, config)


__all__ = ["generate_images", "generate_media"]
