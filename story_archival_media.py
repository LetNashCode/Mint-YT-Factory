"""Person-specific archival media retrieval for Story Shorts.

Video-first retrieval is intentional: each shot first searches Wikimedia
Commons for downloadable archival video. If no usable video is found, the
adapter falls back to a relevant archival image. The returned contract is
compatible with the existing assembler, which supports both media types.
"""
from __future__ import annotations

import mimetypes
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

import requests

API = "https://commons.wikimedia.org/w/api.php"
TIMEOUT = 30
UA = "Mint-YT-Factory/StoryArchivalMedia/2.1"
VIDEO_MIMES = {"video/mp4", "video/webm", "video/ogg", "video/quicktime", "video/x-msvideo"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogv", ".mov", ".avi", ".m4v"}


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
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": 30,
        "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata",
    }
    response = requests.get(API, params=params, headers={"User-Agent": UA}, timeout=TIMEOUT)
    response.raise_for_status()
    pages = (response.json().get("query") or {}).get("pages") or {}
    results: list[dict] = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        url = str(info.get("url") or "")
        mime = str(info.get("mime") or "").lower()
        extension = os.path.splitext(urlparse(url).path)[1].lower()
        is_video = mime in VIDEO_MIMES or extension in VIDEO_EXTENSIONS or mime.startswith("video/")
        if not url or is_video != want_video:
            continue
        meta = info.get("extmetadata") or {}
        results.append({
            "id": page.get("pageid"),
            "title": page.get("title"),
            "url": url,
            "descriptionurl": info.get("descriptionurl") or "",
            "mime": mime,
            "is_video": is_video,
            "artist": _clean((meta.get("Artist") or {}).get("value")),
        })
    return results


def _download(url: str, path: str) -> None:
    """Download an archival asset with bounded retries for transient failures."""
    temp = path + ".part"
    last_error: Exception | None = None
    try:
        for attempt in range(1, 4):
            try:
                with requests.get(
                    url,
                    headers={"User-Agent": UA},
                    stream=True,
                    timeout=(15, 90),
                ) as response:
                    if response.status_code in {408, 425, 429, 500, 502, 503, 504}:
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
                if attempt < 3:
                    delay = 2 ** (attempt - 1)
                    print(f"      ⚠️ Archival download retry {attempt}/2 for {url}: {type(exc).__name__}: {exc}")
                    time.sleep(delay)
        raise RuntimeError(f"Archival download failed after 3 attempts: {last_error}") from last_error
    finally:
        if os.path.exists(temp):
            try:
                os.remove(temp)
            except OSError:
                pass


def _extension(item: dict, video: bool) -> str:
    if not video:
        return ".jpg"
    extension = os.path.splitext(urlparse(item.get("url", "")).path)[1].lower()
    return extension if extension in VIDEO_EXTENSIONS else ".mp4"


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


def generate_media(script: dict, output_dir: str, config: dict, gim=None) -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    scenes = script.get("scene_plan")
    if not isinstance(scenes, list) or len(scenes) != 7:
        raise RuntimeError("Story archival media requires exactly 7 scenes.")

    used: set[str] = set()
    groups: list[dict] = []
    for scene_no, scene in enumerate(scenes, 1):
        video_candidates = _candidate_pool(script, scene, want_video=True)
        image_candidates: list[dict] = []
        for shot_no in range(1, 3):
            item = next((candidate for candidate in video_candidates if candidate["url"] not in used), None)
            media_type = "video"
            if item is None:
                if not image_candidates:
                    image_candidates = _candidate_pool(script, scene, want_video=False)
                item = next((candidate for candidate in image_candidates if candidate["url"] not in used), None)
                media_type = "photo"
            if item is None:
                raise RuntimeError(f"No archival video or fallback image found for Story scene {scene_no}, shot {shot_no} ({script.get('story_person', '')}).")

            url = item["url"]
            used.add(url)
            extension = _extension(item, media_type == "video")
            path = os.path.join(output_dir, f"scene_{scene_no}_shot_{shot_no}{extension}")
            try:
                _download(url, path)
            except Exception as exc:
                print(f"      ⚠️ Download failed for {url}: {type(exc).__name__}: {exc}")
                used.discard(url)
                if media_type == "video":
                    video_candidates = [candidate for candidate in video_candidates if candidate["url"] != url]
                    replacement = next((candidate for candidate in video_candidates if candidate["url"] not in used), None)
                    if replacement is not None:
                        item = replacement
                        url = item["url"]
                        used.add(url)
                        extension = _extension(item, True)
                        path = os.path.join(output_dir, f"scene_{scene_no}_shot_{shot_no}{extension}")
                        try:
                            _download(url, path)
                            media_type = "video"
                        except Exception as replacement_exc:
                            print(f"      ⚠️ Replacement archival video failed: {type(replacement_exc).__name__}: {replacement_exc}")
                            used.discard(url)
                            replacement = None
                    if replacement is None:
                        if not image_candidates:
                            image_candidates = _candidate_pool(script, scene, want_video=False)
                        item = next((candidate for candidate in image_candidates if candidate["url"] not in used), None)
                        if item is None:
                            raise RuntimeError(f"No downloadable archival fallback for Story scene {scene_no}, shot {shot_no}.") from exc
                        media_type = "photo"
                        url = item["url"]
                        used.add(url)
                        path = os.path.join(output_dir, f"scene_{scene_no}_shot_{shot_no}.jpg")
                        _download(url, path)

            groups.append({
                "scene": scene_no,
                "shot": shot_no,
                "path": path,
                "type": media_type,
                "provider": "Wikimedia Commons",
                "creator": item.get("artist", ""),
                "query": item.get("title", ""),
                "source_url": item.get("descriptionurl", ""),
                "asset_key": f"wikimedia:{media_type}:{item.get('id') or url}",
                "score": 8.0 if media_type == "video" else 7.0,
            })
            print(f"      ✅ ARCHIVAL {media_type.upper()}: Scene {scene_no} Shot {shot_no} — {item.get('title', '')}")
    return groups
