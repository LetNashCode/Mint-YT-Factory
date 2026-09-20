"""Identity-first media routing for Story Shorts.

Uses public archival video records for the named subject before ordinary stock
searches. The existing downloader/renderer remains responsible for fetching and
rendering the selected assets. Archive records are only offered for scenes
where the subject is the visual focus; contextual scenes continue through the
normal Pexels/Pixabay path.
"""
from __future__ import annotations

from pathlib import Path
import json

import story_archive_media as archive

_INSTALLED = False


def _adapt(record: dict, person: str, index: int) -> dict:
    provider = str(record.get("provider") or "archive")
    record_id = str(record.get("id") or index)
    source = str(record.get("source_url") or "")
    media = str(record.get("media_url") or "")
    label = f"{person} {record.get('title', '')} verified archival footage"
    return {
        "id": f"archive-{provider.lower().replace(' ', '-')}-{record_id}",
        "url": source,
        "alt": label,
        "description": label,
        "tags": label,
        "video_files": [{"link": media, "width": 1280, "height": 720}],
        "provider": provider,
        "person_match": True,
        "person_visual": True,
        "archive_source_url": source,
        "archive_asset_key": record.get("asset_key", ""),
    }


def install() -> None:
    """Install an idempotent archive-first provider hook for Story generation."""
    global _INSTALLED
    if _INSTALLED:
        return
    import stock_search

    original = getattr(stock_search, "pexels", None)
    if not callable(original):
        print("⚠️ Identity media hook skipped: stock_search.pexels unavailable")
        return

    def archive_first(query, video):
        # The caller's query is intentionally used as a conservative signal:
        # only exact-person queries are eligible for archive substitution.
        person = str(getattr(stock_search, "_mint_story_person", "") or "").strip()
        if person and video and query and person.lower() in str(query).lower():
            try:
                records = archive.discover_person_video_records(person, limit=20)
                if records:
                    print(f"👤 Identity-first routing: {person} → {len(records)} archival video candidates")
                    return [_adapt(item, person, i) for i, item in enumerate(records, 1)][:8]
            except Exception as exc:
                print(f"⚠️ Identity archive routing failed: {type(exc).__name__}: {exc}")
        return original(query, video)

    stock_search.pexels = archive_first
    stock_search._mint_identity_original_pexels = original
    _INSTALLED = True
    print("🛡️ Identity-first Story media routing installed")


def begin_story(person: str) -> None:
    install()
    import stock_search
    stock_search._mint_story_person = str(person or "").strip()


def end_story() -> None:
    try:
        import stock_search
        stock_search._mint_story_person = ""
    except Exception:
        pass
