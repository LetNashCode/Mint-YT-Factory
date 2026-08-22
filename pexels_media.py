"""Pexels-first visual media provider for Mint-YT-Factory.

For every storyboard shot:
1. Search Pexels for a matching VIDEO first.
2. If no sufficiently relevant video exists, search Pexels PHOTOS.
3. If neither is available/relevant, fall back to the existing Pollinations
   image generator.

The provider returns the same 7x2 nested media structure expected by the
existing pipeline. Video paths are consumed directly by the assembler.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests

PEXELS_API = "https://api.pexels.com/v1"
TIMEOUT = 45
MIN_VIDEO_DURATION = 2
MAX_VIDEO_DURATION = 20


def _clean(value: str, limit: int = 300) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()[:limit]


def _tokens(text: str) -> set[str]:
    stop = {
        "this", "that", "with", "from", "your", "into", "about", "just",
        "they", "them", "their", "very", "have", "will", "what", "when",
        "where", "which", "because", "while", "then", "than", "like", "gets",
        "make", "makes", "made", "thing", "things", "exact", "physical", "show",
        "showing", "scene", "shot", "visible", "action", "state", "realistic",
        "cinematic", "photo", "photograph", "video", "image",
    }
    words = re.findall(r"[a-z0-9]+", _clean(text, 800).lower())
    return {w for w in words if len(w) >= 4 and w not in stop}


def _query_for(scene: dict, visual: dict) -> str:
    focus = _clean(visual.get("visual_focus"), 100)
    action = _clean(visual.get("visual_action"), 160)
    spoken = _clean(visual.get("spoken_line") or scene.get("narration"), 220)
    words = []
    for source in (focus, action, spoken):
        for token in re.findall(r"[A-Za-z0-9'-]+", source):
            token = token.lower().strip("'-")
            if len(token) >= 4 and token not in words:
                words.append(token)
    return " ".join(words[:8]) or "everyday object close up"


def _score_result(result: dict, required: set[str], media_type: str) -> float:
    """Score format suitability while trusting Pexels search ranking for relevance."""
    score = 0.0
    if media_type == "video":
        duration = float(result.get("duration") or 0)
        if MIN_VIDEO_DURATION <= duration <= MAX_VIDEO_DURATION:
            score += 2.0
        width = int(result.get("width") or 0)
        height = int(result.get("height") or 0)
        if height > width:
            score += 2.0
        elif width > 0 and height > 0:
            score += 1.0
    else:
        src = result.get("src") or {}
        if isinstance(src, dict) and src.get("portrait"):
            score += 2.0
        if int(result.get("height") or 0) >= int(result.get("width") or 0):
            score += 1.0
    return score


def _headers():
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return None
    return {
        "Authorization": key,
        "User-Agent": "Mint-YT-Factory/PexelsMedia/1.0",
    }


def _search(endpoint: str, query: str, params: dict) -> list[dict]:
    headers = _headers()
    if not headers:
        return []
    response = requests.get(
        f"{PEXELS_API}/{endpoint}",
        headers=headers,
        params={"query": query, "per_page": 15, **params},
        timeout=TIMEOUT,
    )
    if response.status_code != 200:
        print(f"⚠️ Pexels {endpoint} search failed: HTTP {response.status_code}")
        return []
    data = response.json()
    return data.get("videos", []) if endpoint == "videos/search" else data.get("photos", [])


def _download(url: str, path: str) -> bool:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mint-YT-Factory/PexelsMedia/1.0"},
            timeout=120,
            stream=True,
        )
        response.raise_for_status()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
        return os.path.getsize(path) > 10_000
    except Exception as exc:
        print(f"⚠️ Pexels download failed: {exc}")
        try:
            os.remove(path)
        except OSError:
            pass
        return False


def _pick_video(results: list[dict], required: set[str]) -> dict | None:
    ranked = sorted(results, key=lambda item: _score_result(item, required, "video"), reverse=True)
    for item in ranked:
        if _score_result(item, required, "video") < 3.0:
            continue
        files = item.get("video_files") or []
        candidates = []
        for video_file in files:
            link = video_file.get("link")
            width = int(video_file.get("width") or 0)
            height = int(video_file.get("height") or 0)
            if not link or width <= 0 or height <= 0:
                continue
            orientation_bonus = 2 if height >= width else 0
            quality = 2 if str(video_file.get("quality", "")).lower() == "hd" else 0
            candidates.append((orientation_bonus + quality, width * height, link))
        if candidates:
            return {
                "video": max(candidates)[2],
                "page": item.get("url", ""),
                "photographer": (item.get("user") or {}).get("name", ""),
            }
    return None


def _pick_photo(results: list[dict], required: set[str]) -> dict | None:
    ranked = sorted(results, key=lambda item: _score_result(item, required, "photo"), reverse=True)
    for item in ranked:
        if _score_result(item, required, "photo") < 2.0:
            continue
        src = item.get("src") or {}
        link = src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
        if link:
            return {
                "photo": link,
                "page": item.get("url", ""),
                "photographer": item.get("photographer") or "",
            }
    return None


def _write_credit(path: str, media_type: str, page: str, photographer: str):
    record = {
        "type": media_type,
        "page": page,
        "photographer": photographer,
        "provider": "Pexels",
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)


def _pollinations_fallback(generate_images_module, scene, visual, output_path, width, height, seed, scene_index, visual_index):
    prompt = generate_images_module.build_prompt(
        scene,
        visual,
        {},
        scene_index=scene_index,
        visual_index=visual_index,
        correction="Pexels did not have a sufficiently relevant photo or video. Generate the exact literal physical moment.",
    )
    content = generate_images_module.generate_image(prompt, width, height, seed)
    return generate_images_module._save_image(content, output_path, width, height)


def generate_media(script: dict, output_dir: str, config: dict, generate_images_module):
    scenes = script.get("scene_plan") or []
    image_cfg = config.get("image", {}) if isinstance(config, dict) else {}
    width = int(image_cfg.get("width", 2160))
    height = int(image_cfg.get("height", 3840))
    base_seed = int(time.time())

    os.makedirs(output_dir, exist_ok=True)
    credits = []
    groups = []
    pexels_available = bool(_headers())

    print("=" * 80)
    print("📚 PEXELS-FIRST STORY MEDIA")
    print("=" * 80)
    print(f"Pexels API: {'AVAILABLE' if pexels_available else 'NOT CONFIGURED'}")
    print("Provider order: Pexels video → Pexels photo → Pollinations FLUX")
    print("=" * 80)

    for scene_index, scene in enumerate(scenes, 1):
        scene_paths = []
        visuals = scene.get("visuals") or []
        for visual_index, visual in enumerate(visuals[:2], 1):
            query = _query_for(scene, visual)
            required = _tokens(" ".join([
                _clean(visual.get("visual_focus")),
                _clean(visual.get("visual_action")),
            ]))
            stem = f"scene_{scene_index:02d}_shot_{visual_index:02d}"
            print(f"🎬 Scene {scene_index}/7 Shot {visual_index}/2 | query={query}")

            selected = None
            if pexels_available:
                try:
                    videos = _search("videos/search", query, {"orientation": "portrait", "size": "medium"})
                    selected = _pick_video(videos, required)
                    if selected:
                        path = os.path.join(output_dir, stem + ".mp4")
                        if _download(selected["video"], path):
                            _write_credit(os.path.join(output_dir, stem + ".credit.json"), "video", selected["page"], selected["photographer"])
                            credits.append(selected)
                            scene_paths.append(path)
                            print("✅ Pexels VIDEO selected")
                            continue

                    photos = _search("search", query, {"orientation": "portrait", "size": "large"})
                    selected = _pick_photo(photos, required)
                    if selected:
                        path = os.path.join(output_dir, stem + ".jpg")
                        if _download(selected["photo"], path):
                            _write_credit(os.path.join(output_dir, stem + ".credit.json"), "photo", selected["page"], selected["photographer"])
                            credits.append(selected)
                            scene_paths.append(path)
                            print("✅ Pexels PHOTO selected")
                            continue
                except Exception as exc:
                    print(f"⚠️ Pexels lookup failed: {exc}")

            path = os.path.join(output_dir, stem + ".png")
            fallback = _pollinations_fallback(
                generate_images_module,
                scene,
                visual,
                path,
                width,
                height,
                base_seed + scene_index * 100 + visual_index,
                scene_index,
                visual_index,
            )
            scene_paths.append(fallback)
            print("🧠 Pollinations FLUX fallback selected")

        if len(scene_paths) != 2:
            raise RuntimeError(f"Scene {scene_index} did not produce exactly 2 media assets.")
        groups.append(scene_paths)

    manifest = {
        "provider_order": ["pexels_video", "pexels_photo", "pollinations"],
        "pexels_used": bool(credits),
        "credits": credits,
    }
    with open(os.path.join(output_dir, "media_manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)

    # main.py builds YouTube metadata after media generation. These fields let
    # the production entrypoint add the required Pexels attribution only when
    # Pexels media was actually used.
    script["_pexels_used"] = bool(credits)
    script["_pexels_credits"] = credits

    print(f"✅ Media complete: {sum(len(x) for x in groups)} assets")
    return groups
