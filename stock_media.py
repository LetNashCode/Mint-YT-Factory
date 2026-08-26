"""Gemini-directed stock media orchestration for Mint-YT-Factory.

Provider priority per shot:
    1. Pexels VIDEO
    2. Pixabay VIDEO
    3. Pexels PHOTO
    4. Pixabay PHOTO

Gemini is only the Visual/Search Director. It never receives candidate media
and never generates replacement visuals. Pixabay is a stock-media fallback,
not an AI fallback.
"""
from __future__ import annotations

import json
import os
from typing import Any

import requests

import pexels_media

PIXABAY_API = "https://pixabay.com/api"
PIXABAY_VIDEO_API = "https://pixabay.com/api/videos"
PIXABAY_TIMEOUT = 45
USER_AGENT = "Mint-YT-Factory/StockMedia/1.0"


def _pixabay_key() -> str:
    return os.environ.get("PIXABAY_API_KEY", "").strip()


def _pixabay_search(query: str, video: bool = True) -> list[dict]:
    key = _pixabay_key()
    if not key:
        return []
    endpoint = PIXABAY_VIDEO_API if video else PIXABAY_API
    params: dict[str, Any] = {
        "key": key,
        "q": query,
        "lang": "en",
        "per_page": 20,
        "safesearch": "true",
        "order": "popular",
    }
    if video:
        params["video_type"] = "film"
    else:
        params["image_type"] = "photo"
        params["orientation"] = "vertical"
    try:
        response = requests.get(endpoint, params=params, headers={"User-Agent": USER_AGENT}, timeout=PIXABAY_TIMEOUT)
        if response.status_code != 200:
            print(f"⚠️ Pixabay {'video' if video else 'photo'} search: HTTP {response.status_code}")
            return []
        payload = response.json()
        return payload.get("hits", [])
    except Exception as exc:
        print(f"⚠️ Pixabay search failed: {type(exc).__name__}: {exc}")
        return []


def _pixabay_text(item: dict, video: bool) -> str:
    return " ".join([
        pexels_media.clean(item.get("tags"), 600),
        pexels_media.clean(item.get("pageURL"), 300),
    ])


def _pixabay_score(item: dict, plan: dict[str, Any], video: bool) -> float:
    required = pexels_media._tokens(" ".join(plan.get("must_match", [])))
    queries = pexels_media._tokens(" ".join(plan.get("queries", [])))
    result = pexels_media._tokens(_pixabay_text(item, video))
    score = len(required & result) * 4.0 + len(queries & result) * 0.5
    actions = pexels_media._action_tokens(" ".join(plan.get("must_match", [])))
    score += len(actions & result) * 2.0

    if video:
        duration = float(item.get("duration") or 0)
        if 2 <= duration <= 20:
            score += 2
        variants = item.get("videos") or {}
        best = variants.get("large") or variants.get("medium") or variants.get("small") or {}
        width = int(best.get("width") or 0)
        height = int(best.get("height") or 0)
        if height > width:
            score += 2
    else:
        width = int(item.get("imageWidth") or 0)
        height = int(item.get("imageHeight") or 0)
        if height >= width and height:
            score += 2
    return score


def _select_pixabay_video(results: list[dict], plan: dict[str, Any], used_pages: set[str]) -> dict | None:
    candidates = []
    seen = set(used_pages)
    for item in results:
        page = str(item.get("pageURL") or "")
        if not page or page in seen:
            continue
        variants = item.get("videos") or {}
        choice = variants.get("large") or variants.get("medium") or variants.get("small") or variants.get("tiny")
        if not choice or not choice.get("url"):
            continue
        score = _pixabay_score(item, plan, True)
        candidates.append((score, item, choice))
    candidates.sort(key=lambda x: x[0], reverse=True)
    if not candidates:
        return None
    score, item, choice = candidates[0]
    if score < 1:
        return None
    return {
        "url": choice["url"],
        "page": item.get("pageURL", ""),
        "creator": item.get("user", ""),
        "score": round(score, 2),
    }


def _select_pixabay_photo(results: list[dict], plan: dict[str, Any], used_pages: set[str]) -> dict | None:
    candidates = []
    seen = set(used_pages)
    for item in results:
        page = str(item.get("pageURL") or "")
        if not page or page in seen:
            continue
        url = item.get("largeImageURL") or item.get("fullHDURL") or item.get("imageURL")
        if not url:
            continue
        score = _pixabay_score(item, plan, False)
        candidates.append((score, item, url))
    candidates.sort(key=lambda x: x[0], reverse=True)
    if not candidates:
        return None
    score, item, url = candidates[0]
    if score < 1:
        return None
    return {
        "url": url,
        "page": item.get("pageURL", ""),
        "creator": item.get("user", ""),
        "score": round(score, 2),
    }


def _download(url: str, path: str, provider: str) -> bool:
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120, stream=True)
        response.raise_for_status()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    handle.write(chunk)
        if os.path.getsize(path) <= 10_000:
            raise RuntimeError("downloaded file is unexpectedly small")
        return True
    except Exception as exc:
        print(f"⚠️ {provider} download failed: {type(exc).__name__}: {exc}")
        try:
            os.remove(path)
        except OSError:
            pass
        return False


def _write_credit(path: str, provider: str, kind: str, selected: dict, directed: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({
            "type": kind,
            "provider": provider,
            "page": selected.get("page", ""),
            "creator": selected.get("creator", ""),
            "search_query": " | ".join(directed.get("queries", [])),
            "metadata_score": selected.get("score", 0),
            "visual_search_director": {
                "queries": directed.get("queries", []),
                "casting_brief": directed.get("casting_brief", ""),
                "must_match": directed.get("must_match", []),
                "avoid": directed.get("avoid", []),
            },
        }, handle, ensure_ascii=False, indent=2)


def generate_media(script: dict, output_dir: str, config: dict, gim=None):
    """Select exactly 2 stock assets per scene, with Pixabay as stock fallback."""
    if not os.environ.get("PEXELS_API_KEY", "").strip() and not _pixabay_key():
        raise RuntimeError("At least one stock provider API key is required: PEXELS_API_KEY or PIXABAY_API_KEY.")

    os.makedirs(output_dir, exist_ok=True)
    plan = pexels_media.build_search_plan(script)
    groups: list[list[str]] = []
    used_pages: set[str] = set()

    print("=" * 80)
    print("📚 GEMINI-DIRECTED STOCK MEDIA v6.0")
    print("Gemini role: VISUAL/SEARCH DIRECTOR ONLY")
    print("Gemini visual verification: DISABLED")
    print("AI image generation: DISABLED")
    print("Provider priority: Pexels VIDEO → Pixabay VIDEO → Pexels PHOTO → Pixabay PHOTO")
    print("=" * 80)

    for scene_index, scene_plan in enumerate(plan, 1):
        scene_paths: list[str] = []
        for shot_index, directed in enumerate(scene_plan, 1):
            selected = None
            provider = None
            kind = None

            # Preferred provider: Pexels video.
            if os.environ.get("PEXELS_API_KEY", "").strip():
                videos: list[dict] = []
                for query in directed["queries"]:
                    videos.extend(pexels_media.search("videos/search", query, {"orientation": "portrait", "size": "medium"}))
                selected = pexels_media._select_video(videos, directed, used_pages)
                if selected:
                    provider, kind = "Pexels", "video"

            # Stock-only fallback: Pixabay video.
            if selected is None and _pixabay_key():
                print(f"   ↪️ Scene {scene_index} Shot {shot_index}: Pexels video unavailable/rejected → trying Pixabay video")
                videos = []
                for query in directed["queries"]:
                    videos.extend(_pixabay_search(query, video=True))
                selected = _select_pixabay_video(videos, directed, used_pages)
                if selected:
                    provider, kind = "Pixabay", "video"

            # Preserve the existing photo fallback order after both video providers.
            if selected is None and os.environ.get("PEXELS_API_KEY", "").strip():
                photos: list[dict] = []
                for query in directed["queries"]:
                    photos.extend(pexels_media.search("search", query, {"orientation": "portrait", "size": "large"}))
                selected = pexels_media._select_photo(photos, directed, used_pages)
                if selected:
                    provider, kind = "Pexels", "photo"

            if selected is None and _pixabay_key():
                print(f"   ↪️ Scene {scene_index} Shot {shot_index}: no acceptable Pexels photo → trying Pixabay photo")
                photos = []
                for query in directed["queries"]:
                    photos.extend(_pixabay_search(query, video=False))
                selected = _select_pixabay_photo(photos, directed, used_pages)
                if selected:
                    provider, kind = "Pixabay", "photo"

            if selected is None:
                raise RuntimeError(
                    f"No relevant stock asset found for Scene {scene_index} Shot {shot_index}. "
                    "Pexels and Pixabay were exhausted; no unrelated or AI-generated fallback is allowed."
                )

            page = str(selected.get("page") or "")
            used_pages.add(page)
            extension = "mp4" if kind == "video" else "jpg"
            path = os.path.join(output_dir, f"scene_{scene_index:02d}_shot_{shot_index:02d}.{extension}")
            if provider == "Pexels":
                url = selected.get("video") if kind == "video" else selected.get("photo")
            else:
                url = selected.get("url")

            if not _download(str(url), path, provider):
                raise RuntimeError(f"{provider} asset download failed for Scene {scene_index} Shot {shot_index}.")

            _write_credit(path + ".credit.json", provider, kind, selected, directed)
            scene_paths.append(path)
            print(
                f"   ✅ Scene {scene_index} Shot {shot_index}: {provider.upper()} {kind.upper()} "
                f"score={selected.get('score', 0)} | {page}"
            )

        groups.append(scene_paths)

    if len(groups) != 7 or any(len(group) != 2 for group in groups):
        raise RuntimeError("Stock media contract failed: expected 7 scenes × 2 assets.")
    return groups
