"""Authoritative media adapter for Mint-YT-Factory."""
from __future__ import annotations

import stock_search
import story_archival_media

GEMINI_MODEL = stock_search.GEMINI_MODEL


def _is_story(script: dict) -> bool:
    return isinstance(script, dict) and bool(
        str(script.get("story_person") or "").strip()
        or str(script.get("interactive_pillar") or "").strip()
        or str(script.get("story_visual_mode") or "").strip()
    )


def generate_media(script: dict, output_dir: str, config: dict, gim=None):
    """Use person/scene-specific archival images for Story Shorts.

    Story Shorts never fall back to the commercial stock providers or YouTube
    downloads. Non-Story/Publish workflows retain the existing stock adapter.
    """
    if _is_story(script):
        person = str(script.get("story_person") or "").strip()
        print(f"📖 STORY ARCHIVAL ROUTING: {person or 'historical subject'}")
        return story_archival_media.generate_media(script, output_dir, config, gim=gim)
    return stock_search.generate_media(script, output_dir, config, gim=gim)
