"""Person-specific archival media retrieval for Story Shorts."""
from __future__ import annotations

import os
import re
import shutil
from typing import Any
from urllib.parse import quote, urlparse

import requests
from story_media_quality import relevance_score

API = "https://commons.wikimedia.org/w/api.php"
SEARCH_TIMEOUT = 20
DOWNLOAD_TIMEOUT = (10, 60)
UA = "Mint-YT-Factory/StoryArchivalMedia/2.8"
VIDEO_MIMES = {"video/mp4", "video/webm", "video/ogg", "video/quicktime", "video/x-msvideo"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogv", ".mov", ".avi", ".m4v", ".mkv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
TRANSIENT_STATUS = {408, 425, 500, 502, 503, 504}
MIN_RELEVANCE_SCORE = 5.0


def _clean(value: Any, limit: int = 300) -> str:
    return " ".join(str(value or "").split())[:limit]


def _terms(script: dict, scene: dict) -> list[str]:
    person = _clean(script.get("story_person"), 120)
    narration = _clean(scene.get("narration"), 220)
    visuals = scene.get("visuals") or []
    focus_terms: list[str] = []
    if isinstance(visuals, list):
        for visual in visuals:
            if not isinstance(visual, dict):
                continue
            for key in ("visual_focus", "must_show", "visual_action"):
                value = visual.get(key)
                if isinstance(value, list):
                    focus_terms.extend(_clean(x, 100) for x in value[:2])
                elif value:
                    focus_terms.append(_clean(value, 160))
    raw = [f"{person} {' '.join(focus_terms[:2])}".strip(), f"{person} historical photograph", f"{person} video", person, narration]
    result: list[str] = []
    for query in raw:
        query = re.sub(r"[^\w\s-]", " ", query).strip()
        query = re.sub(r"\s+", " ", query)
        if query and query not in result:
            result.append(query)
    return result


def _search(query: str, want_video: bool) -> list[dict]:
    params = {"action": "query", "format": "json", "generator": "search", "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": 30, "prop": "imageinfo", "iiprop": "url|mime|extmetadata"}
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
        is_image = mime.startswith("image/") and extension in IMAGE_EXTENSIONS
        if not url or (want_video and not is_video) or (not want_video and not is_image):
            continue
        meta = info.get("extmetadata") or {}
        results.append({"id": page.get("pageid"), "title": _clean(page.get("title"), 240), "url": url,
                        "descriptionurl": info.get("descriptionurl") or "", "mime": mime, "is_video": is_video,
                        "artist": _clean((meta.get("Artist") or {}).get("value")),
                        "description": _clean((meta.get("ImageDescription") or {}).get("value"), 300)})
    return results


def _download_once(url: str, path: str) -> int:
    temp = path + ".part"
    try:
        with requests.get(url, headers={"User-Agent": UA}, stream=True, timeout=DOWNLOAD_TIMEOUT) as response:
            if response.status_code == 429:
                return 429
            if response.status_code in TRANSIENT_STATUS:
                raise RuntimeError(f"Transient HTTP {response.status_code}; candidate skipped")
            response.raise_for_status()
            with open(temp, "wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        if not os.path.exists(temp) or os.path.getsize(temp) == 0:
            raise RuntimeError("Downloaded media file is empty")
        os.replace(temp, path)
        return 200
    finally:
        if os.path.exists(temp):
            try: os.remove(temp)
            except OSError: pass


def _download(url: str, path: str) -> None:
    status = _download_once(url, path)
    if status == 200: return
    extension = os.path.splitext(urlparse(url).path)[1].lower()
    if "upload.wikimedia.org" in url and extension in IMAGE_EXTENSIONS:
        proxy_url = "https://images.weserv.nl/?url=" + quote(url, safe="")
        if _download_once(proxy_url, path) == 200: return
    raise RuntimeError("HTTP 429 from Wikimedia Commons; candidate skipped")


def _candidate_pool(script: dict, scene: dict, want_video: bool) -> list[dict]:
    person = _clean(script.get("story_person"), 120)
    candidates: list[dict] = []
    seen: set[str] = set()
    for query in _terms(script, scene):
        try: found = _search(query, want_video)
        except Exception as exc:
            print(f"      ⚠️ Wikimedia search failed for {query!r}: {type(exc).__name__}: {exc}")
            continue
        for item in found:
            key = str(item.get("id") or item.get("url") or "")
            if not key or key in seen: continue
            score = relevance_score(person, query, item.get("title"), item.get("description"), item.get("artist"))
            if score < MIN_RELEVANCE_SCORE:
                continue
            item["relevance_score"] = score
            seen.add(key)
            candidates.append(item)
    candidates.sort(key=lambda item: float(item.get("relevance_score", 0)), reverse=True)
    return candidates


def _try_download_candidates(candidates: list[dict], used: set[str], output_path: str, media_type: str) -> tuple[dict, str] | None:
    for item in candidates:
        url = str(item.get("url") or "")
        asset_key = str(item.get("id") or url)
        if not url or url in used or asset_key in used: continue
        try:
            _download(url, output_path)
            used.update((url, asset_key))
            return item, url
        except Exception as exc:
            print(f"      ⚠️ Skipping archival {media_type} {url}: {type(exc).__name__}: {exc}")
            try:
                if os.path.exists(output_path): os.remove(output_path)
            except OSError: pass
    return None


def _reuse_archival_asset(*args, **kwargs):
    return None


def generate_media(script: dict, output_dir: str, config: dict, gim=None) -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    scenes = script.get("scene_plan")
    if not isinstance(scenes, list) or len(scenes) != 7:
        raise RuntimeError("Story archival media requires exactly 7 scenes.")
    person = _clean(script.get("story_person"), 120)
    used: set[str] = set(); groups: list[dict] = []
    for scene_no, scene in enumerate(scenes, 1):
        video_candidates = _candidate_pool(script, scene, True)
        image_candidates = None
        for shot_no in range(1, 3):
            video_path = os.path.join(output_dir, f"scene_{scene_no}_shot_{shot_no}.mp4")
            selected = _try_download_candidates(video_candidates, used, video_path, "video")
            media_type, path = "video", video_path
            if selected is None:
                if image_candidates is None: image_candidates = _candidate_pool(script, scene, False)
                image_path = os.path.join(output_dir, f"scene_{scene_no}_shot_{shot_no}.jpg")
                selected = _try_download_candidates(image_candidates, used, image_path, "image")
                media_type, path = "photo", image_path
            if selected is None:
                raise RuntimeError(f"No relevant downloadable archival media found for scene {scene_no}, shot {shot_no} ({person}).")
            item, url = selected
            groups.append({"scene": scene_no, "shot": shot_no, "path": path, "type": media_type, "provider": "Wikimedia Commons",
                           "creator": item.get("artist", ""), "query": item.get("title", ""), "source_url": item.get("descriptionurl", ""),
                           "asset_key": f"wikimedia:{media_type}:{item.get('id') or url}", "score": float(item.get("relevance_score", 0))})
    return groups
