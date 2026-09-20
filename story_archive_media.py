"""Archive-media and story-topic history helpers for Story Shorts.

This module deliberately has no licensing decision logic. It only discovers
public archive records and prevents reuse of previously recorded topics/assets.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parent
HISTORY_PATH = ROOT / "story_media_history.json"
TOPICS_PATH = ROOT / "story_topic_history.json"
UA = "Mint-YT-Factory/StoryArchiveMedia/1.0"
TIMEOUT = 25


def _load(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default.copy()
    except Exception:
        return default.copy()


def _save(path: Path, value: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def normalize_topic(topic: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", (topic or "").lower()).strip()


def topic_seen(topic: str) -> bool:
    key = normalize_topic(topic)
    return bool(key) and key in set(_load(TOPICS_PATH, {"topics": []}).get("topics", []))


def record_topic(topic: str, person: str = "") -> None:
    key = normalize_topic(topic)
    if not key:
        return
    data = _load(TOPICS_PATH, {"topics": [], "records": []})
    topics = data.setdefault("topics", [])
    if key not in topics:
        topics.append(key)
        data.setdefault("records", []).append({"topic": topic, "person": person, "recorded_at": int(time.time())})
        _save(TOPICS_PATH, data)


def asset_key(provider: str, record_id: str = "", url: str = "") -> str:
    identity = record_id or hashlib.sha256(url.encode("utf-8")).hexdigest()
    return f"{provider.lower()}:{identity}"


def asset_seen(key: str) -> bool:
    return key in {str(x.get("asset_key")) for x in _load(HISTORY_PATH, {"assets": []}).get("assets", []) if isinstance(x, dict)}


def record_asset(key: str, provider: str, source_url: str, person: str, media_url: str) -> None:
    if not key or asset_seen(key):
        return
    data = _load(HISTORY_PATH, {"assets": []})
    data.setdefault("assets", []).append({"asset_key": key, "provider": provider, "source_url": source_url, "media_url": media_url, "person": person, "recorded_at": int(time.time())})
    _save(HISTORY_PATH, data)


def _get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=TIMEOUT)
    response.raise_for_status()
    value = response.json()
    return value if isinstance(value, dict) else {}


def search_wikimedia(person: str, limit: int = 20) -> list[dict[str, Any]]:
    query = f'"{person}"'
    data = _get("https://commons.wikimedia.org/w/api.php", {"action": "query", "format": "json", "generator": "search", "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": min(limit, 50), "prop": "imageinfo", "iiprop": "url|mime|extmetadata"})
    results = []
    for page in (data.get("query", {}).get("pages", {}) or {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        url = info.get("url") or ""
        mime = info.get("mime") or ""
        if url and (mime.startswith("video/") or mime.startswith("image/")):
            results.append({"provider": "Wikimedia Commons", "id": str(page.get("pageid", "")), "title": page.get("title", ""), "source_url": "https://commons.wikimedia.org/wiki?curid=" + str(page.get("pageid", "")), "media_url": url, "mime": mime})
    return results


def search_internet_archive(person: str, limit: int = 20) -> list[dict[str, Any]]:
    data = _get("https://archive.org/advancedsearch.php", {"q": f'title:({person}) OR description:({person})', "fl[]": ["identifier", "title", "description", "mediatype"], "rows": min(limit, 50), "output": "json"})
    results = []
    for doc in data.get("response", {}).get("docs", []) or []:
        identifier = doc.get("identifier")
        if identifier:
            results.append({"provider": "Internet Archive", "id": identifier, "title": doc.get("title", ""), "source_url": f"https://archive.org/details/{quote(str(identifier))}", "media_url": f"https://archive.org/download/{quote(str(identifier))}/", "mediatype": doc.get("mediatype", "")})
    return results


def discover_person_media(person: str, limit: int = 20) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for fn in (search_wikimedia, search_internet_archive):
        try:
            results.extend(fn(person, limit))
        except Exception as exc:
            print(f"Archive search failed for {fn.__name__}: {type(exc).__name__}: {exc}")
    return [item for item in results if not asset_seen(asset_key(item["provider"], item.get("id", ""), item.get("media_url", "")))]
