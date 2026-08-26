"""Gemini-directed Pexels media selection for Mint-YT-Factory.

ARCHITECTURE
------------
Gemini is the Visual/Search Director. It receives the exact spoken beat and
visual contract from the story generator and produces concrete Pexels search
queries plus a short casting brief for each shot.

Pexels is the only media provider. This module never sends candidate images or
video previews to Gemini. There is deliberately NO Gemini visual verification,
ranking, image download for inspection, Pollinations fallback, or FLUX fallback.

Flow:
    story -> Gemini visual/search director -> Pexels search -> deterministic
    metadata ranking -> verified Pexels asset -> assembly

If Gemini cannot produce a valid search plan, production stops instead of
silently falling back to generic or unrelated queries.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

PEXELS_API = "https://api.pexels.com/v1"
PEXELS_TIMEOUT = 45
DOWNLOAD_TIMEOUT = 120
USER_AGENT = "Mint-YT-Factory/PexelsMedia/5.0"
DIRECTOR_MODEL = "gemini-flash-lite-latest"
EXPECTED_SCENES = 7
VISUALS_PER_SCENE = 2

STOP_WORDS = {
    "this", "that", "with", "from", "your", "into", "about", "just", "they",
    "them", "their", "very", "have", "will", "what", "when", "where", "which",
    "because", "while", "then", "than", "like", "gets", "make", "makes", "made",
    "thing", "things", "exact", "physical", "show", "showing", "scene", "shot",
    "visible", "action", "state", "realistic", "cinematic", "photo", "photograph",
    "video", "image", "someone", "something", "person", "people", "close", "camera",
    "natural", "looking", "moment", "also", "really", "tiny", "microscopic", "single",
    "entire", "every", "time", "next", "remember", "designed", "actually", "basically",
    "literally", "nobody", "touched", "cursed", "very", "only", "must", "contain",
}

ACTION_WORDS = {
    "cling", "clinging", "stick", "sticking", "pull", "pulling", "grab", "grabbing",
    "hold", "holding", "touch", "touching", "rub", "rubbing", "fall", "falling", "drop",
    "dropping", "jump", "jumping", "run", "running", "pour", "pouring", "spill", "spilling",
    "open", "opening", "close", "closing", "break", "breaking", "tear", "tearing", "bend",
    "bending", "shake", "shaking", "twist", "twisting", "stretch", "stretching", "slide",
    "sliding", "move", "moving", "tumble", "tumbling", "wash", "washing", "dry", "drying",
    "iron", "ironing", "sew", "sewing", "wear", "wearing", "remove", "removing", "press",
    "pressing", "boil", "boiling", "freeze", "freezing", "melt", "melting", "steam", "steaming",
    "squeeze", "squeezing", "crush", "crushing", "bounce", "bouncing", "spin", "spinning",
    "plug", "plugging", "drip", "dripping", "float", "floating", "burst", "bursting", "snap",
    "snapping", "crack", "cracking", "lift", "lifting", "collapse", "collapsing", "tangle",
    "tangled", "knot", "knotted",
}


def clean(value: Any, limit: int = 700) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()[:limit]


def _tokens(value: Any) -> set[str]:
    return {
        w for w in re.findall(r"[a-z0-9]+", clean(value, 2000).lower())
        if len(w) >= 4 and w not in STOP_WORDS
    }


def _action_tokens(value: Any) -> set[str]:
    return _tokens(value) & ACTION_WORDS


def _visual_contract(scene: dict, visual: dict) -> dict[str, Any]:
    return {
        "spoken_beat": clean(visual.get("spoken_line") or scene.get("narration"), 600),
        "visual_focus": clean(visual.get("visual_focus"), 300),
        "visual_action": clean(visual.get("visual_action"), 300),
        "must_show": [clean(x, 180) for x in (visual.get("must_show") or []) if clean(x)],
        "must_not_show": [clean(x, 180) for x in (visual.get("must_not_show") or []) if clean(x)],
        "camera": clean(visual.get("camera"), 120),
        "image_prompt": clean(visual.get("image_prompt"), 700),
    }


def _director_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required for the Gemini Visual/Search Director.")
    return key


def _parse_json(text: str) -> Any:
    text = str(text or "").strip()
    text = re.sub(r"^```(?:json)?", "", text, flags=re.I).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
        if not match:
            raise RuntimeError("Gemini Visual/Search Director returned invalid JSON.")
        return json.loads(match.group(0))


def _director_request(scene_index: int, scene: dict, visual_index: int, visual: dict) -> dict[str, Any]:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("google-genai is required for the Gemini Visual/Search Director.") from exc

    contract = _visual_contract(scene, visual)
    prompt = f"""You are the dedicated VISUAL SEARCH DIRECTOR for a fast, fun YouTube Short.

You are NOT reviewing media. You are NOT looking at candidate images. Your only job is to turn the spoken beat into excellent search instructions for Pexels.

SCENE: {scene_index}
SHOT: {visual_index}
SPOKEN BEAT:
{contract['spoken_beat']}

VISUAL FOCUS:
{contract['visual_focus']}

VISUAL ACTION:
{contract['visual_action']}

MUST SHOW:
{json.dumps(contract['must_show'], ensure_ascii=False)}

MUST NOT SHOW:
{json.dumps(contract['must_not_show'], ensure_ascii=False)}

EXISTING STORYBOARD VISUAL DESCRIPTION:
{contract['image_prompt']}

RULES:
1. Search for what the viewer should literally see, not the abstract lesson.
2. Prefer concrete nouns, visible physical states and visible actions.
3. Preserve the exact object. Do not substitute a similar-looking object.
4. If the sentence describes a mechanism, search for the mechanism's visible physical manifestation.
5. Avoid broad topic words such as science, technology, mystery, education, experiment, concept.
6. Avoid metaphors unless the spoken beat itself requires a metaphorical visual.
7. Queries must work on Pexels stock search.
8. Give 4 different query formulations, from literal to contextual, but keep every query tightly relevant.
9. Give a short casting brief describing the ideal footage/photo. This is guidance for deterministic selection; it is NOT a visual-QC step.
10. Do not invent a different topic, object or action.

Return ONLY JSON in this exact shape:
{{
  "queries": ["query 1", "query 2", "query 3", "query 4"],
  "casting_brief": "one concise description of the ideal visible shot",
  "must_match": ["object or visible state", "action or physical detail"],
  "avoid": ["wrong object", "wrong action", "generic substitute"]
}}"""

    client = genai.Client(api_key=_director_key())
    response = client.models.generate_content(
        model=DIRECTOR_MODEL,
        contents=[prompt],
        config=types.GenerateContentConfig(temperature=0.2),
    )
    data = _parse_json(getattr(response, "text", "") or "")
    if not isinstance(data, dict):
        raise RuntimeError(f"Gemini Visual/Search Director returned non-object for Scene {scene_index} Shot {visual_index}.")

    queries = data.get("queries")
    if not isinstance(queries, list):
        raise RuntimeError(f"Gemini Visual/Search Director returned no queries for Scene {scene_index} Shot {visual_index}.")
    queries = [clean(q, 160) for q in queries if clean(q)]
    if len(queries) < 2:
        raise RuntimeError(f"Gemini Visual/Search Director returned too few queries for Scene {scene_index} Shot {visual_index}.")

    return {
        "queries": queries[:4],
        "casting_brief": clean(data.get("casting_brief"), 500),
        "must_match": [clean(x, 160) for x in (data.get("must_match") or []) if clean(x)][:6],
        "avoid": [clean(x, 160) for x in (data.get("avoid") or []) if clean(x)][:6],
    }


def build_search_plan(script: dict) -> list[list[dict[str, Any]]]:
    scenes = script.get("scene_plan")
    if not isinstance(scenes, list) or len(scenes) != EXPECTED_SCENES:
        raise RuntimeError(f"Expected exactly {EXPECTED_SCENES} scenes for visual direction.")

    plan: list[list[dict[str, Any]]] = []
    print("🧠 GEMINI VISUAL/SEARCH DIRECTOR — generating Pexels search plans")
    for scene_index, scene in enumerate(scenes, 1):
        visuals = scene.get("visuals")
        if not isinstance(visuals, list) or len(visuals) != VISUALS_PER_SCENE:
            raise RuntimeError(f"Scene {scene_index} must contain exactly {VISUALS_PER_SCENE} visuals.")
        scene_plan = []
        for visual_index, visual in enumerate(visuals, 1):
            directed = _director_request(scene_index, scene, visual_index, visual)
            directed["scene"] = scene_index
            directed["shot"] = visual_index
            scene_plan.append(directed)
            print(f"   🎯 Scene {scene_index} Shot {visual_index}: {' | '.join(directed['queries'])}")
        plan.append(scene_plan)
    return plan


def headers() -> dict[str, str] | None:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return None
    return {"Authorization": key, "User-Agent": USER_AGENT}


def search(endpoint: str, query: str, params: dict | None = None) -> list[dict]:
    hdrs = headers()
    if not hdrs:
        return []
    request_params = {"query": query, "per_page": 20}
    request_params.update(params or {})
    try:
        response = requests.get(
            f"{PEXELS_API}/{endpoint}",
            headers=hdrs,
            params=request_params,
            timeout=PEXELS_TIMEOUT,
        )
        if response.status_code != 200:
            print(f"⚠️ Pexels {endpoint}: HTTP {response.status_code}")
            return []
        payload = response.json()
        return payload.get("videos", []) if endpoint == "videos/search" else payload.get("photos", [])
    except Exception as exc:
        print(f"⚠️ Pexels search failed: {type(exc).__name__}: {exc}")
        return []


def _dedupe(results: list[dict], excluded_pages: set[str]) -> list[dict]:
    seen = set(excluded_pages)
    output = []
    for item in results:
        page = str(item.get("url") or "")
        if not page or page in seen:
            continue
        seen.add(page)
        output.append(item)
    return output


def _metadata_text(item: dict, kind: str) -> str:
    if kind == "video":
        return " ".join([
            clean(item.get("url"), 400),
            clean(item.get("image"), 300),
            clean(item.get("video_pictures"), 500),
        ])
    src = item.get("src") or {}
    return " ".join([clean(item.get("alt"), 500), clean(item.get("url"), 300), clean(src.get("portrait"), 200)])


def _score(item: dict, plan: dict[str, Any], kind: str) -> float:
    required = _tokens(" ".join(plan.get("must_match", [])))
    query_tokens = _tokens(" ".join(plan.get("queries", [])))
    result = _tokens(_metadata_text(item, kind))
    score = len(required & result) * 4.0 + len(query_tokens & result) * 0.5
    actions = _action_tokens(" ".join(plan.get("must_match", [])))
    score += len(actions & result) * 2.0

    if kind == "video":
        duration = float(item.get("duration") or 0)
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        if 2 <= duration <= 20:
            score += 2
        if height > width:
            score += 2
    else:
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        if height >= width and height:
            score += 2

    return score


def _video_download_url(item: dict) -> str | None:
    choices = []
    for video_file in item.get("video_files") or []:
        link = video_file.get("link")
        width = int(video_file.get("width") or 0)
        height = int(video_file.get("height") or 0)
        quality = str(video_file.get("quality") or "").lower()
        if not link or not width or not height:
            continue
        choices.append((1 if height > width else 0, 1 if quality == "hd" else 0, width * height, link))
    return max(choices)[3] if choices else None


def _select_video(results: list[dict], plan: dict[str, Any], excluded_pages: set[str]) -> dict | None:
    pool = _dedupe(results, excluded_pages)
    pool.sort(key=lambda item: _score(item, plan, "video"), reverse=True)
    for item in pool[:12]:
        link = _video_download_url(item)
        if link:
            score = _score(item, plan, "video")
            if score >= 1:
                return {
                    "video": link,
                    "page": item.get("url", ""),
                    "photographer": (item.get("user") or {}).get("name", ""),
                    "score": round(score, 2),
                }
    return None


def _select_photo(results: list[dict], plan: dict[str, Any], excluded_pages: set[str]) -> dict | None:
    pool = _dedupe(results, excluded_pages)
    pool.sort(key=lambda item: _score(item, plan, "photo"), reverse=True)
    for item in pool[:12]:
        src = item.get("src") or {}
        link = src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
        if link:
            score = _score(item, plan, "photo")
            if score >= 1:
                return {
                    "photo": link,
                    "page": item.get("url", ""),
                    "photographer": item.get("photographer", "") or "",
                    "score": round(score, 2),
                }
    return None


def download(url: str, path: str) -> bool:
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=DOWNLOAD_TIMEOUT, stream=True)
        response.raise_for_status()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as handle:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    handle.write(chunk)
        return os.path.getsize(path) > 10_000
    except Exception as exc:
        print(f"⚠️ Pexels download failed: {type(exc).__name__}: {exc}")
        try:
            os.remove(path)
        except OSError:
            pass
        return False


def credit(path: str, kind: str, page: str, photographer: str, query: str, score: float, director: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({
            "type": kind,
            "page": page,
            "photographer": photographer,
            "provider": "Pexels",
            "search_query": query,
            "metadata_score": score,
            "visual_search_director": {
                "queries": director.get("queries", []),
                "casting_brief": director.get("casting_brief", ""),
                "must_match": director.get("must_match", []),
                "avoid": director.get("avoid", []),
            },
        }, handle, ensure_ascii=False, indent=2)


def generate_media(script: dict, output_dir: str, config: dict, gim=None):
    """Generate exactly two Pexels assets per scene using Gemini-directed search."""
    if not headers():
        raise RuntimeError("PEXELS_API_KEY is required for Pexels-only production.")

    os.makedirs(output_dir, exist_ok=True)
    plan = build_search_plan(script)
    groups: list[list[str]] = []
    used_pages: set[str] = set()

    print("=" * 80)
    print("📚 GEMINI-DIRECTED PEXELS MEDIA v5.0")
    print("Gemini role: VISUAL/SEARCH DIRECTOR ONLY")
    print("Gemini visual verification: DISABLED")
    print("Candidate image/video uploads to Gemini: DISABLED")
    print("Provider: Pexels VIDEO → Pexels PHOTO")
    print("Pollinations/FLUX: DISABLED")
    print("=" * 80)

    for scene_index, scene_plan in enumerate(plan, 1):
        scene_paths: list[str] = []
        for shot_index, directed in enumerate(scene_plan, 1):
            videos: list[dict] = []
            for query in directed["queries"]:
                videos.extend(search("videos/search", query, {"orientation": "portrait", "size": "medium"}))
            selected = _select_video(videos, directed, used_pages)
            kind = "video"

            if selected is None:
                photos: list[dict] = []
                for query in directed["queries"]:
                    photos.extend(search("search", query, {"orientation": "portrait", "size": "large"}))
                selected = _select_photo(photos, directed, used_pages)
                kind = "photo"

            if selected is None:
                raise RuntimeError(
                    f"No relevant Pexels asset found for Scene {scene_index} Shot {shot_index}. "
                    "Production stopped; no unrelated fallback is allowed."
                )

            page = str(selected.get("page") or "")
            used_pages.add(page)
            extension = "mp4" if kind == "video" else "jpg"
            path = os.path.join(output_dir, f"scene_{scene_index:02d}_shot_{shot_index:02d}.{extension}")
            url = selected.get("video") if kind == "video" else selected.get("photo")
            if not download(str(url), path):
                raise RuntimeError(f"Pexels asset download failed for Scene {scene_index} Shot {shot_index}.")

            credit(
                path + ".credit.json",
                kind,
                page,
                str(selected.get("photographer") or ""),
                " | ".join(directed["queries"]),
                float(selected.get("score", 0)),
                directed,
            )
            scene_paths.append(path)
            print(
                f"   ✅ Scene {scene_index} Shot {shot_index}: {kind.upper()} "
                f"score={selected.get('score', 0)} | {page}"
            )

        groups.append(scene_paths)

    if len(groups) != EXPECTED_SCENES or any(len(group) != VISUALS_PER_SCENE for group in groups):
        raise RuntimeError("Pexels media contract failed: expected 7 scenes × 2 assets.")

    return groups
