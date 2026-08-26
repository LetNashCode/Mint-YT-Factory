"""Compatibility entrypoint for verified stock media.

Actual media selection lives in stock_media.py. Gemini is used as the
Visual/Search Director and as the final candidate-level Visual Verifier.
Pexels and Pixabay are the only production media providers.
"""
from __future__ import annotations

from stock_media import generate_media


def generate_images(script, output_dir, config):
    """Compatibility wrapper returning 7 scenes × 2 verified stock assets."""
    return generate_media(script, output_dir, config)


__all__ = ["generate_images", "generate_media"]
