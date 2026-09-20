"""Runtime integration for Story Shorts archive/topic history.

This layer augments the existing stock pipeline without replacing its stable
rendering contract. It records story topics, discovers person-specific archive
records, and exposes the archive candidates to the runtime for diagnostics and
future media adapters.
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
    people[archive.normalize_topic(person)] = {
        "person": person,
        "records": records[:100],
    }
    DISCOVERY_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def install(production_module) -> None:
    """Install non-invasive Story history/archive hooks once."""
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
            if person:
                if archive.topic_seen(topic):
                    raise RuntimeError(f"Story topic already used; refusing duplicate Story Short: {topic!r}")
                records = archive.discover_person_media(person, limit=20)
                _save_discovery(person, records)
                print(f"🗂️ Archive discovery: {person} → {len(records)} unused Wikimedia/Internet Archive records")
            result = original_generate(script, output_dir, config, gim=gim)
            if person:
                archive.record_topic(topic, person)
            return result

        generate_media._mint_story_archive_history = True
        stock_search.generate_media = generate_media
        print("🛡️ Story archive/topic integration: ACTIVE")

    production_module._patch_stock_media_quality = patched_patch_stock_media_quality
    production_module._mint_story_archive_integration = True
