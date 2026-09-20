"""Authoritative media adapter for Mint-YT-Factory.

Story Shorts intentionally do not use commercial stock providers. YouTube
video downloads are also not supported. Story media must be supplied by the
archival-media pipeline (for example, Wikimedia Commons, Internet Archive, or
an explicitly configured institutional source).
"""
from __future__ import annotations

import stock_search

GEMINI_MODEL = stock_search.GEMINI_MODEL


def _is_story(script: dict) -> bool:
    return isinstance(script, dict) and bool(
        str(script.get("story_person") or "").strip()
        or str(script.get("interactive_pillar") or "").strip()
        or str(script.get("story_visual_mode") or "").strip()
    )


def generate_media(script: dict, output_dir: str, config: dict, gim=None):
    """Generate media while preventing forbidden Story Shorts providers.

    Story Shorts are fail-closed here until the archival-media adapter is used.
    This prevents accidental fallback to Pexels/Pixabay or YouTube downloads.
    Publish/non-Story workflows retain their existing stock-media behavior.
    """
    if _is_story(script):
        raise RuntimeError(
            "Story Shorts media generation is blocked: Pexels, Pixabay, and "
            "YouTube downloads are disabled. Configure the archival-media "
            "pipeline using permitted downloadable sources such as Wikimedia "
            "Commons, Internet Archive, or an authorized institutional archive."
        )
    return stock_search.generate_media(script, output_dir, config, gim=gim)
