"""Person-specific archival video routing for Story Shorts.

Story Shorts must not use generic stock footage or stock images. This hook
replaces every Story media-provider search with person-specific archival video
records discovered from supported archive sources. If no suitable archival
video is available, the search fails loudly instead of silently falling back to
Pexels/Pixabay.
"""
from __future__ import annotations

import story_archive_media as archive

_INSTALLED = False


def _adapt(record: dict, person: str, index: int) -> dict:
    archive_provider = str(record.get("provider") or "archive")
    record_id = str(record.get("id") or index)
    source = str(record.get("source_url") or "")
    media = str(record.get("media_url") or "")
    title = str(record.get("title") or "").strip()
    label = f"{person} — {title or 'archival footage'}"
    # The downstream selector expects the Pexels video schema. Keep the
    # original archive provider in metadata while presenting a compatible
    # video_files structure to the existing downloader.
    return {
        "id": f"archive-{archive_provider.lower().replace(' ', '-')}-{record_id}",
        "url": source,
        "alt": label,
        "description": label,
        "tags": label,
        "video_files": [{"link": media, "width": 1280, "height": 720}],
        "provider": "Pexels",
        "archive_provider": archive_provider,
        "person_match": True,
        "person_visual": True,
        "archive_source_url": source,
        "archive_asset_key": record.get("asset_key", ""),
        "license_checked": False,
    }


def install() -> None:
    """Install an idempotent archival-only provider hook for Story Shorts."""
    global _INSTALLED
    if _INSTALLED:
        return

    import stock_search

    original_pexels = getattr(stock_search, "pexels", None)
    original_pixabay = getattr(stock_search, "pixabay", None)
    if not callable(original_pexels) or not callable(original_pixabay):
        raise RuntimeError("Story archival media hook cannot install: media providers unavailable")

    def archive_only(query, video):
        person = str(getattr(stock_search, "_mint_story_person", "") or "").strip()
        if not person:
            raise RuntimeError("Story archival media requested without an identified story person")
        if not video:
            raise RuntimeError("Story Shorts archival-only mode rejects image assets")

        records = archive.discover_person_video_records(person, limit=40)
        if not records:
            raise RuntimeError(
                f"No person-specific archival video found for {person!r}; "
                "generic stock footage and stock images are disabled for Story Shorts"
            )

        print(
            f"🎞️ Archival-only Story routing: {person} → "
            f"{len(records)} person-specific video candidates"
        )
        return [_adapt(item, person, i) for i, item in enumerate(records, 1)][:8]

    stock_search.pexels = archive_only
    stock_search.pixabay = archive_only
    stock_search._mint_identity_original_pexels = original_pexels
    stock_search._mint_identity_original_pixabay = original_pixabay
    _INSTALLED = True
    print("🎞️ Story archival-only media routing installed — stock footage/images disabled")


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
