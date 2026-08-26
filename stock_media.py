"""Gemini-directed stock media with candidate-level visual verification.

Provider priority per shot:
    1. Pexels VIDEO
    2. Pixabay VIDEO
    3. Pexels PHOTO
    4. Pixabay PHOTO

Gemini has two visual roles:
    * Visual/Search Director: creates the search plan.
    * Visual Verifier: inspects a small candidate pool and rejects media that
      does not actually show the spoken beat.

Gemini never generates replacement media. Pexels/Pixabay are the only media
providers. If neither provider can produce a visually relevant asset, the
shot fails instead of accepting unrelated footage.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

import pexels_media

PIXABAY_API = "https://pixabay.com/api"
PIXABAY_VIDEO_API = "https://pixabay.com/api/videos"
PIXABAY_TIMEOUT = 45
USER_AGENT = "Mint-YT-Factory/StockMedia/7.0"
VERIFY_MODEL = "gemini-flash-lite-latest"
VERIFY_LIMIT = 6
VERIFY_THRESHOLD = 7.5


def _pixabay_key() -> str:
    return os.environ.get("PIXABAY_API_KEY", "").strip()


def _pixabay_search(query: str, video: bool = True) -> list[dict]:
    key = _pixabay_key()
    if not key:
        return []
    endpoint = PIXABAY_VIDEO_API if video else PIXABAY_API
    params: dict[str, Any] = {
        "key": key, "q": query, "lang": "en", "per_page": 20,
        "safesearch": "true", "order": "popular",
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
        return response.json().get("hits", [])
    except Exception as exc:
        print(f"⚠️ Pixabay search failed: {type(exc).__name__}: {exc}")
        return []


def _pixabay_text(item: dict) -> str:
    return " ".join([pexels_media.clean(item.get("tags"), 600), pexels_media.clean(item.get("pageURL"), 300)])


def _pixabay_score(item: dict, plan: dict[str, Any], video: bool) -> float:
    required = pexels_media._tokens(" ".join(plan.get("must_match", [])))
    queries = pexels_media._tokens(" ".join(plan.get("queries", [])))
    result = pexels_media._tokens(_pixabay_text(item))
    score = len(required & result) * 4.0 + len(queries & result) * 0.5
    actions = pexels_media._action_tokens(" ".join(plan.get("must_match", [])))
    score += len(actions & result) * 2.0
    if video:
        duration = float(item.get("duration") or 0)
        if 2 <= duration <= 20:
            score += 2
        variants = item.get("videos") or {}
        best = variants.get("large") or variants.get("medium") or variants.get("small") or {}
        if int(best.get("height") or 0) > int(best.get("width") or 0):
            score += 2
    else:
        width, height = int(item.get("imageWidth") or 0), int(item.get("imageHeight") or 0)
        if height >= width and height:
            score += 2
    return score


def _pixabay_video_choice(item: dict) -> dict | None:
    variants = item.get("videos") or {}
    for name in ("large", "medium", "small", "tiny"):
        choice = variants.get(name) or {}
        if choice.get("url"):
            return choice
    return None


def _pixabay_thumbnail(item: dict) -> str:
    picture_id = str(item.get("picture_id") or "").strip()
    if picture_id:
        return f"https://i.vimeocdn.com/video/{picture_id}_640x360.jpg"
    return ""


def _download_bytes(url: str, timeout: int = 30) -> bytes | None:
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        response.raise_for_status()
        return response.content
    except Exception:
        return None


def _gemini_verify(candidates: list[dict], directed: dict) -> list[dict]:
    """Inspect candidate thumbnails in one Gemini call and return scored candidates."""
    if not candidates:
        return []
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("google-genai is required for Gemini visual verification.") from exc

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required for Gemini visual verification.")

    parts: list[Any] = []
    usable: list[dict] = []
    for index, candidate in enumerate(candidates[:VERIFY_LIMIT]):
        image_url = str(candidate.get("preview_url") or "")
        data = _download_bytes(image_url) if image_url else None
        if not data:
            continue
        parts.append(types.Part.from_bytes(data=data, mime_type="image/jpeg"))
        parts.append(types.Part.from_text(text=f"CANDIDATE {len(usable)+1}"))
        usable.append(candidate)

    if not usable:
        return []

    prompt = f"""You are the FINAL VISUAL VERIFIER for a YouTube Short.
Inspect the candidate images in order. Do not judge search-query quality; judge what is actually visible.

SPOKEN BEAT:
{directed.get('spoken_beat', '')}

IDEAL VISUAL:
{directed.get('casting_brief', '')}

MUST MATCH:
{json.dumps(directed.get('must_match', []), ensure_ascii=False)}

AVOID:
{json.dumps(directed.get('avoid', []), ensure_ascii=False)}

Rules:
1. The actual visible subject must match the narration.
2. The visible action/state must match when the beat describes one.
3. A generic or merely related image is NOT a match.
4. Do not give a high score because the footage is cinematic or attractive.
5. Reject wrong objects, wrong actions, decorative textures, and generic substitutes.
6. If the image cannot visibly support the spoken beat, reject it.

Return ONLY JSON:
{{"results":[{{"candidate":1,"score":0,"subject_match":0,"action_match":0,"context_match":0,"reject":true,"reason":"brief reason"}}]}}
Score 0-10. A candidate is usable only when score >= {VERIFY_THRESHOLD} and reject=false.
"""

    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model=VERIFY_MODEL,
        contents=parts + [types.Part.from_text(text=prompt)],
        config=types.GenerateContentConfig(temperature=0),
    )
    text = str(getattr(response, "text", "") or "").strip()
    text = re.sub(r"^```(?:json)?", "", text, flags=re.I).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        payload = json.loads(text)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return []
        payload = json.loads(match.group(0))

    output = []
    for result in payload.get("results", []):
        try:
            idx = int(result.get("candidate", 0)) - 1
            if idx < 0 or idx >= len(usable):
                continue
            item = dict(usable[idx])
            item["visual_score"] = float(result.get("score", 0) or 0)
            item["visual_reason"] = str(result.get("reason", ""))[:500]
            item["visual_subject_match"] = float(result.get("subject_match", 0) or 0)
            item["visual_action_match"] = float(result.get("action_match", 0) or 0)
            item["visual_context_match"] = float(result.get("context_match", 0) or 0)
            item["visual_rejected"] = bool(result.get("reject", True))
            output.append(item)
        except Exception:
            continue
    output.sort(key=lambda x: x.get("visual_score", 0), reverse=True)
    return [x for x in output if not x.get("visual_rejected") and x.get("visual_score", 0) >= VERIFY_THRESHOLD]


def _verified_choice(candidates: list[dict], directed: dict) -> dict | None:
    verified = _gemini_verify(candidates, directed)
    return verified[0] if verified else None


def _pexels_video_candidates(videos: list[dict], plan: dict, used_pages: set[str]) -> list[dict]:
    pool = pexels_media._dedupe(videos, used_pages)
    pool.sort(key=lambda item: pexels_media._score(item, plan, "video"), reverse=True)
    out = []
    for item in pool[:VERIFY_LIMIT]:
        link = pexels_media._video_download_url(item)
        if not link:
            continue
        out.append({
            "provider": "Pexels", "kind": "video", "url": link,
            "page": item.get("url", ""), "creator": (item.get("user") or {}).get("name", ""),
            "metadata_score": pexels_media._score(item, plan, "video"),
            "preview_url": item.get("image", ""),
        })
    return out


def _pexels_photo_candidates(photos: list[dict], plan: dict, used_pages: set[str]) -> list[dict]:
    pool = pexels_media._dedupe(photos, used_pages)
    pool.sort(key=lambda item: pexels_media._score(item, plan, "photo"), reverse=True)
    out = []
    for item in pool[:VERIFY_LIMIT]:
        src = item.get("src") or {}
        url = src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
        preview = src.get("medium") or src.get("large") or url
        if url:
            out.append({
                "provider": "Pexels", "kind": "photo", "url": url,
                "page": item.get("url", ""), "creator": item.get("photographer", ""),
                "metadata_score": pexels_media._score(item, plan, "photo"), "preview_url": preview,
            })
    return out


def _pixabay_video_candidates(results: list[dict], plan: dict, used_pages: set[str]) -> list[dict]:
    out = []
    seen = set(used_pages)
    ranked = sorted(results, key=lambda x: _pixabay_score(x, plan, True), reverse=True)
    for item in ranked:
        page = str(item.get("pageURL") or "")
        choice = _pixabay_video_choice(item)
        preview = _pixabay_thumbnail(item)
        if page in seen or not page or not choice or not preview:
            continue
        out.append({
            "provider": "Pixabay", "kind": "video", "url": choice["url"],
            "page": page, "creator": item.get("user", ""),
            "metadata_score": _pixabay_score(item, plan, True), "preview_url": preview,
        })
        if len(out) >= VERIFY_LIMIT:
            break
    return out


def _pixabay_photo_candidates(results: list[dict], plan: dict, used_pages: set[str]) -> list[dict]:
    out = []
    seen = set(used_pages)
    ranked = sorted(results, key=lambda x: _pixabay_score(x, plan, False), reverse=True)
    for item in ranked:
        page = str(item.get("pageURL") or "")
        url = item.get("largeImageURL") or item.get("fullHDURL") or item.get("imageURL")
        preview = item.get("previewURL") or url
        if page in seen or not page or not url or not preview:
            continue
        out.append({
            "provider": "Pixabay", "kind": "photo", "url": url,
            "page": page, "creator": item.get("user", ""),
            "metadata_score": _pixabay_score(item, plan, False), "preview_url": preview,
        })
        if len(out) >= VERIFY_LIMIT:
            break
    return out


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


def _write_credit(path: str, selected: dict, directed: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({
            "type": selected.get("kind"),
            "provider": selected.get("provider"),
            "page": selected.get("page", ""),
            "creator": selected.get("creator", ""),
            "search_query": " | ".join(directed.get("queries", [])),
            "metadata_score": selected.get("metadata_score", 0),
            "gemini_visual_verification": {
                "enabled": True,
                "score": selected.get("visual_score", 0),
                "subject_match": selected.get("visual_subject_match", 0),
                "action_match": selected.get("visual_action_match", 0),
                "context_match": selected.get("visual_context_match", 0),
                "reason": selected.get("visual_reason", ""),
            },
            "visual_search_director": {
                "queries": directed.get("queries", []),
                "casting_brief": directed.get("casting_brief", ""),
                "must_match": directed.get("must_match", []),
                "avoid": directed.get("avoid", []),
            },
        }, handle, ensure_ascii=False, indent=2)


def generate_media(script: dict, output_dir: str, config: dict, gim=None):
    """Select exactly 2 stock assets per scene, verified by Gemini vision."""
    if not os.environ.get("PEXELS_API_KEY", "").strip() and not _pixabay_key():
        raise RuntimeError("At least one stock provider API key is required: PEXELS_API_KEY or PIXABAY_API_KEY.")

    os.makedirs(output_dir, exist_ok=True)
    plan = pexels_media.build_search_plan(script)
    groups: list[list[str]] = []
    used_pages: set[str] = set()

    print("=" * 80)
    print("📚 GEMINI-DIRECTED STOCK MEDIA v7.0")
    print("Gemini role: VISUAL/SEARCH DIRECTOR + FINAL VISUAL VERIFIER")
    print(f"Gemini visual verification: ENABLED (threshold={VERIFY_THRESHOLD}/10, max candidates={VERIFY_LIMIT})")
    print("AI image generation: DISABLED")
    print("Provider priority: Pexels VIDEO → Pixabay VIDEO → Pexels PHOTO → Pixabay PHOTO")
    print("Unrelated fallback: DISABLED")
    print("=" * 80)

    for scene_index, scene_plan in enumerate(plan, 1):
        scene_paths: list[str] = []
        for shot_index, directed in enumerate(scene_plan, 1):
            selected = None

            # Provider 1: Pexels video.
            if os.environ.get("PEXELS_API_KEY", "").strip():
                videos = []
                for query in directed["queries"]:
                    videos.extend(pexels_media.search("videos/search", query, {"orientation": "portrait", "size": "medium"}))
                selected = _verified_choice(_pexels_video_candidates(videos, directed, used_pages), directed)
                if selected:
                    print(f"   🔎 Scene {scene_index} Shot {shot_index}: Gemini verified Pexels VIDEO score={selected['visual_score']:.1f}")

            # Provider 2: Pixabay video.
            if selected is None and _pixabay_key():
                print(f"   ↪️ Scene {scene_index} Shot {shot_index}: Pexels video rejected → verifying Pixabay VIDEO")
                videos = []
                for query in directed["queries"]:
                    videos.extend(_pixabay_search(query, video=True))
                selected = _verified_choice(_pixabay_video_candidates(videos, directed, used_pages), directed)
                if selected:
                    print(f"   🔎 Scene {scene_index} Shot {shot_index}: Gemini verified Pixabay VIDEO score={selected['visual_score']:.1f}")

            # Provider 3: Pexels photo.
            if selected is None and os.environ.get("PEXELS_API_KEY", "").strip():
                print(f"   ↪️ Scene {scene_index} Shot {shot_index}: video candidates rejected → verifying Pexels PHOTO")
                photos = []
                for query in directed["queries"]:
                    photos.extend(pexels_media.search("search", query, {"orientation": "portrait", "size": "large"}))
                selected = _verified_choice(_pexels_photo_candidates(photos, directed, used_pages), directed)
                if selected:
                    print(f"   🔎 Scene {scene_index} Shot {shot_index}: Gemini verified Pexels PHOTO score={selected['visual_score']:.1f}")

            # Provider 4: Pixabay photo.
            if selected is None and _pixabay_key():
                print(f"   ↪️ Scene {scene_index} Shot {shot_index}: no acceptable Pexels photo → verifying Pixabay PHOTO")
                photos = []
                for query in directed["queries"]:
                    photos.extend(_pixabay_search(query, video=False))
                selected = _verified_choice(_pixabay_photo_candidates(photos, directed, used_pages), directed)
                if selected:
                    print(f"   🔎 Scene {scene_index} Shot {shot_index}: Gemini verified Pixabay PHOTO score={selected['visual_score']:.1f}")

            if selected is None:
                raise RuntimeError(
                    f"No visually relevant stock asset found for Scene {scene_index} Shot {shot_index}. "
                    "Pexels and Pixabay candidates failed Gemini visual verification; no unrelated or AI-generated fallback is allowed."
                )

            page = str(selected.get("page") or "")
            used_pages.add(page)
            extension = "mp4" if selected.get("kind") == "video" else "jpg"
            path = os.path.join(output_dir, f"scene_{scene_index:02d}_shot_{shot_index:02d}.{extension}")
            if not _download(str(selected.get("url")), path, str(selected.get("provider"))):
                raise RuntimeError(f"{selected.get('provider')} asset download failed for Scene {scene_index} Shot {shot_index}.")
            _write_credit(path + ".credit.json", selected, directed)
            scene_paths.append(path)
            print(
                f"   ✅ Scene {scene_index} Shot {shot_index}: {selected.get('provider')} {selected.get('kind')} "
                f"VISUALLY VERIFIED {selected.get('visual_score', 0):.1f}/10 | {page}"
            )

        groups.append(scene_paths)

    if len(groups) != 7 or any(len(group) != 2 for group in groups):
        raise RuntimeError("Stock media contract failed: expected 7 scenes × 2 assets.")
    return groups
