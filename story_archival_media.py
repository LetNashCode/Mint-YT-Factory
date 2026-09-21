"""Person-specific archival media retrieval for Story Shorts.

Video-first retrieval uses Wikimedia Commons. Every candidate is validated by
file type before download, and failed/rate-limited candidates are skipped so
one bad archive URL cannot abort the whole scene.
"""
from __future__ import annotations

import os
import re
import time
from typing import Any
from urllib.parse import urlparse

import requests

API = "https://commons.wikimedia.org/w/api.php"
SEARCH_TIMEOUT = 30
DOWNLOAD_TIMEOUT = (15, 90)
UA = "Mint-YT-Factory/StoryArchivalMedia/2.2 (archival-media-retrieval)"
VIDEO_MIMES = {"video/mp4", "video/webm", "video/ogg", "video/quicktime", "video/x-msvideo"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogv", ".mov", ".avi", ".m4v", ".mkv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _clean(value: Any, limit: int = 300) -> str:
    return " ".join(str(value or "").split())[:limit]


def _terms(script: dict, scene: dict) -> list[str]:
    person = _clean(script.get("story_person"), 120)
    narration = _clean(scene.get("narration"), 300)
    visuals = scene.get("visuals") or []
    focus = ""
    if isinstance(visuals, list):
        for visual in visuals:
            if isinstance(visual, dict):
                focus = _clean(visual.get("visual_focus") or visual.get("spoken_line"), 180)
                if focus:
                    break
    raw = [f"{person} {focus}", f"{person} video", person, narration]
    result: list[str] = []
    for query in raw:
        query = re.sub(r"[^\w\s-]", " ", query).strip()
        if query and query not in result:
            result.append(query)
    return result


def _search(query: str, want_video: bool) -> list[dict]:
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": 30,
        "prop": "imageinfo", "iiprop": "url|mime|extmetadata",
    }
    response = requests.get(API, params=params, headers={"User-Agent": UA}, timeout=SEARCH_TIMEOUT)
    response.raise_for_status()
    pages = (response.json().get("query") or {}).get("pages") or {}
    results: list[dict] = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        url = str(info.get("url") or "")
        mime = str(info.get("mime") or "").lower()
        extension = os.path.splitext(urlparse(url).path)[1].lower()
        is_video = mime in VIDEO_MIMES or extension in VIDEO_EXTENSIONS or mime.startswith("video/")
        # PDFs, SVGs, and arbitrary documents must never become image fallbacks.
        is_image = mime.startswith("image/") and extension in IMAGE_EXTENSIONS
        if not url or (want_video and not is_video) or (not want_video and not is_image):
            continue
        meta = info.get("extmetadata") or {}
        results.append({
            "id": page.get("pageid"), "title": page.get("title"), "url": url,
            "descriptionurl": info.get("descriptionurl") or "", "mime": mime,
            "is_video": is_video, "artist": _clean((meta.get("Artist") or {}).get("value")),
        })
    return results


def _download(url: str, path: str) -> None:
    """Download an archival asset with rate-limit-aware bounded retries."""
    temp = path + ".part"
    last_error: Exception | None = None
    try:
        for attempt in range(1, 5):
            try:
                with requests.get(url, headers={"User-Agent": UA}, stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After", "")
                        try:
                            delay = min(45, max(8, int(float(retry_after))))
                        except (TypeError, ValueError):
                            delay = min(45, 8 * (2 ** (attempt - 1)))
                        raise RuntimeError(f"HTTP 429; retry suggested after {delay}s")
                    if response.status_code in {408, 425, 500, 502, 503, 504}:
                        raise RuntimeError(f"Transient HTTP {response.status_code}")
                    response.raise_for_status()
                    with open(temp, "wb") as handle:
                        for chunk in response.iter_content(1024 * 1024):
                            if chunk:
                                handle.write(chunk)
                if not os.path.exists(temp) or os.path.getsize(temp) == 0:
                    raise RuntimeError("Downloaded media file is empty")
                os.replace(temp, path)
                return
            except Exception as exc:
                last_error = exc
                if attempt < 4:
                    delay = min(30, 2 ** (attempt - 1))
                    if "HTTP 429" in str(exc):
                        delay = min(45, 8 * (2 ** (attempt - 1)))
                    print(f"      ⚠️ Archival download retry {attempt}/3 for {url}: {type(exc).__name__}: {exc}; waiting {delay}s")
                    time.sleep(delay)
        raise RuntimeError(f"Archival download failed after 4 attempts: {last_error}") from last_error
    finally:
        if os.path.exists(temp):
            try:
                os.remove(temp)
            except OSError:
                pass


def _candidate_pool(script: dict, scene: dict, want_video: bool) -> list[dict]:
    candidates: list[dict] = []
    seen: set[str] = set()
    for query in _terms(script, scene):
        try:
            found = _search(query, want_video)
        except Exception as exc:
            print(f"      ⚠️ Wikimedia {'video' if want_video else 'image'} search failed for {query!r}: {type(exc).__name__}: {exc}")
            continue
        for item in found:
            if item["url"] not in seen:
                seen.add(item["url"])
                candidates.append(item)
    return candidates


def _try_download_candidates(candidates: list[dict], used: set[str], output_path: str, media_type: str) -> tuple[dict, str] | None:
    for item in candidates:
        url = str(item.get("url") or "")
        if not url or url in used:
            continue
        try:
            _download(url, output_path)
            return item, url
        except Exception as exc:
            print(f"      ⚠️ Skipping unavailable archival {media_type} {url}: {type(exc).__name__}: {exc}")
            used.discard(url)
            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
            except OSError:
                pass
    return None


def generate_media(script: dict, output_dir: str, config: dict, gim=None) -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    scenes = script.get("scene_plan")
    if not isinstance(scenes, list) or len(scenes) != 7:
        raise RuntimeError("Story archival media requires exactly 7 scenes.")

    used: set[str] = set()
    groups: list[dict] = []
    for scene_no, scene in enumerate(scenes, 1):
        video_candidates = _candidate_pool(script, scene, want_video=True)
        image_candidates: list[dict] | None = None
        for shot_no in range(1, 3):
            video_path = os.path.join(output_dir, f"scene_{scene_no}_shot_{shot_no}.mp4")
            selected = _try_download_candidates(video_candidates, used, video_path, "video")
            media_type = "video"
            path = video_path
            if selected is None:
                if image_candidates is None:
                    image_candidates = _candidate_pool(script, scene, want_video=False)
                image_path = os.path.join(output_dir, f"scene_{scene_no}_shot_{shot_no}.jpg")
                selected = _try_download_candidates(image_candidates, used, image_path, "image")
                media_type = "photo"
                path = image_path
            if selected is None:
                raise RuntimeError(f"No downloadable archival video or image found for Story scene {scene_no}, shot {shot_no} ({script.get('story_person', '')}).")

            item, url = selected
            used.add(url)
            groups.append({
                "scene": scene_no, "shot": shot_no, "path": path, "type": media_type,
                "provider": "Wikimedia Commons", "creator": item.get("artist", ""),
                "query": item.get("title", ""), "source_url": item.get("descriptionurl", ""),
                "asset_key": f"wikimedia:{media_type}:{item.get('id') or url}",
                "score": 8.0 if media_type == "video" else 7.0,
            })
            print(f"      ✅ ARCHIVAL {media_type.upper()}: Scene {scene_no} Shot {shot_no} — {item.get('title', '')}")
    return groups
