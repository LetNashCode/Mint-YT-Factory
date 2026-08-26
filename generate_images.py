"""Compatibility entrypoint for story-driven Pexels media.

Image generation has been removed from the production path.
Mint-YT-Factory now uses Gemini only as the Visual/Search Director and Pexels
as the sole media provider. No Pollinations/FLUX generation and no Gemini
candidate-image verification are performed here.
"""
from __future__ import annotations

from pexels_media import generate_media


# Kept for compatibility with older imports. Production_entry.py and main.py
# should use generate_media(), which returns 7 scenes × 2 Pexels assets.
def generate_images(script, output_dir, config):
    return generate_media(script, output_dir, config)


__all__ = ["generate_images", "generate_media"]
