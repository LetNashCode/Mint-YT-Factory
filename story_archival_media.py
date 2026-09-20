"""Person-specific archival media retrieval for Story Shorts.

Uses Wikimedia Commons search results for real-person and scene-specific
images. Images are returned as production media and can be animated by the
existing assembler; no commercial stock-provider fallback is used here.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests

API = "https://commons.wikimedia.org/w/api.php"
TIMEOUT = 30
UA = "Mint-YT-Factory/StoryArchivalMedia/1.0"


def _clean(value: Any, limit: int = 300) -> str:
    return " ".join(str(value or "").split())[:limit]


def _terms(script: dict, scene: dict) -> list[str]:
    person = _clean(script.get("story_person"), 120)
    narration = _clean(scene.get("narration"), 240)
    focus = ""
    visuals = scene.get("visuals") or []
    if isinstance(visuals, list) and visuals and isinstance(visuals[0], dict):
        focus = _clean(visuals[0].get("visual_focus") or visuals[0].get("spoken_line"), 180)
    queries = [f"{person} {focus}", f"{person}", narration]
    result = []
    for query in queries:
        query = re.sub(r"[^\w\s-]", " ", query).strip()
        if query and query not in result:
            result.append(query)
    return result


def _search(query: str) -> list[dict]:
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": 12,
        "prop": "imageinfo", "iiprop": "url|mime|extmetadata",
    }
    response = requests.get(API, params=params, headers={"User-Agent": UA}, timeout=TIMEOUT)
    response.raise_for_status()
    pages = (response.json().get("query") or {}).get("pages") or {}
    results = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        url = info.get("url") or ""
        mime = info.get("mime") or ""
        if not url or not mime.startswith("image/"):
            continue
        meta = info.get("extmetadata") or {}
        results.append({
            "id": page.get("pageid"), "title": page.get("title"),
            "url": url, "descriptionurl": info.get("descriptionurl") or "",
            "mime": mime, "artist": _clean((meta.get("Artist") or {}).get("value")),
        })
    return results


def _download(url: str, path: str) -> None:
    temp = path + ".part"
    with requests.get(url, headers={"User-Agent": UA}, stream=True, timeout=TIMEOUT) as response:
        response.raise_for_status()
        with open(temp, "wb") as handle:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    handle.write(chunk)
    os.replace(temp, path)


def generate_media(script: dict, output_dir: str, config: dict, gim=None) -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    scenes = script.get("scene_plan")
    if not isinstance(scenes, list) or len(scenes) != 7:
        raise RuntimeError("Story archival media requires exactly 7 scenes.")
    used: set[str] = set()
    groups: list[dict] = []
    for scene_no, scene in enumerate(scenes, 1):
        candidates: list[dict] = []
        for query in _terms(script, scene):
            try:
                candidates.extend(_search(query))
            except Exception as exc:
                print(f"      ⚠️ Wikimedia search failed for {query!r}: {type(exc).__name__}: {exc}")
        unique = []
        for item in candidates:
            if item["url"] not in used and item["url"] not in {x["url"] for x in unique}:
                unique.append(item)
        if not unique:
            raise RuntimeError(f"No archival image found for Story scene {scene_no} ({script.get('story_person', '')}).")
        for shot_no in range(1, 3):
            item = unique.pop(0) if unique else candidates[0]
            url = item["url"]
            used.add(url)
            path = os.path.join(output_dir, f"scene_{scene_no}_shot_{shot_no}.jpg")
            _download(url, path)
            groups.append({
                "scene": scene_no, "shot": shot_no, "path": path, "type": "photo",
                "provider": "Wikimedia Commons", "creator": item.get("artist", ""),
                "query": item.get("title", ""), "source_url": item.get("descriptionurl", ""),
                "asset_key": f"wikimedia:photo:{item.get('id') or url}", "score": 8.0,
            })
            print(f"      ✅ ARCHIVAL IMAGE: Scene {scene_no} Shot {shot_no} — {item.get('title', '')}")
    return groups
