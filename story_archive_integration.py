"""Runtime integration for Story Shorts archive/topic history.

Archive video candidates are adapted to the existing stock-search contract so
Story Shorts can download them without changing the renderer or MoviePy path.
"""
from __future__ import annotations

import json
from pathlib import Path

import story_archive_media as archive

ROOT = Path(__file__).resolve().parent
DISCOVERY_PATH = ROOT / "story_archive_discovery.json"


def _save_discovery(person: str, records: list[dict]) -> None:
    try:
        existing = json.loads(DISCOVERY_PATH.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            existing = {"people": {}}
    except Exception:
        existing = {"people": {}}
    people = existing.setdefault("people", {})
    people[archive.normalize_topic(person)] = {"person": person, "records": records[:100]}
    DISCOVERY_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _as_stock_video(record: dict, person: str, index: int) -> dict:
    """Adapt an archive record to the Pexels video shape expected by stock_search."""
    url = str(record.get("media_url") or "")
    record_id = str(record.get("id") or index)
    title = str(record.get("title") or record_id)
    provider = str(record.get("provider") or "Archive")
    # Include broad concrete story anchors so the existing deterministic
    # selector can recognize a real-person archive clip without Gemini.
    searchable = f"{person} {title} historical person biography documentary footage {provider}".strip()
    return {
        "id": f"archive-{provider.lower().replace(' ', '-')}-{record_id}",
        "url": record.get("source_url", ""),
        "alt": searchable,
        "description": searchable,
        "tags": searchable,
        "video_files": [{"link": url, "width": 1280, "height": 720}],
        "_archive_provider": provider,
        "_archive_record": record,
    }


def install(production_module) -> None:
    """Install archive-first Story video routing and topic history hooks once."""
    if getattr(production_module, "_mint_story_archive_integration", False):
        return

    original_patch = production_module._patch_stock_media_quality

    def patched_patch_stock_media_quality():
        original_patch()
        import stock_search

        original_generate = stock_search.generate_media
        if getattr(original_generate, "_mint_story_archive_history", False):
            return

        def generate_media(script, output_dir, config, gim=None):
            person = str(script.get("story_person") or "").strip()
            topic = str(script.get("topic") or "").strip()
            archive_candidates = []
            if person:
                if archive.topic_seen(topic):
                    raise RuntimeError(f"Story topic already used; refusing duplicate Story Short: {topic!r}")
                records = archive.discover_person_video_records(person, limit=30)
                _save_discovery(person, records)
                archive_candidates.extend(_as_stock_video(item, person, index) for index, item in enumerate(records, 1))
                print(f"🗂️ Archive video discovery: {person} → {len(archive_candidates)} downloadable Wikimedia/Internet Archive videos")

            original_pexels = stock_search.pexels

            def archive_first_pexels(query, video):
                if person and video and archive_candidates:
                    available = [item for item in archive_candidates if not archive.asset_seen(archive.asset_key(item["_archive_provider"], item["_archive_record"].get("id", ""), item["_archive_record"].get("media_url", "")))]
                    if available:
                        return available[:8]
                return original_pexels(query, video)

            stock_search.pexels = archive_first_pexels
            try:
                result = original_generate(script, output_dir, config, gim=gim)
            finally:
                stock_search.pexels = original_pexels

            if person:
                archive.record_topic(topic, person)
            return result

        generate_media._mint_story_archive_history = True
        stock_search.generate_media = generate_media
        print("🛡️ Story archive/topic integration: ACTIVE — archive videos first")

    production_module._patch_stock_media_quality = patched_patch_stock_media_quality
    production_module._mint_story_archive_integration = True
