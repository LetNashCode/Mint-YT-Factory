"""Real-person visual layer for Story Shorts.

Actual-person identity is the primary visual objective. Candidates are collected
from archival/photo sources, then Gemini verifies identity. If Gemini vision is
temporarily unavailable, only strongly person-matching archival metadata may be
used as a controlled fallback; generic images are never promoted as person media.
Story Shorts only; Publish Shorts is untouched.
"""
from __future__ import annotations

import io
import json
import os
import re
import time
from typing import Any

import requests
from PIL import Image

from story_person_sources import search_person_media

TIMEOUT = 25
VERIFY_CANDIDATES = 6
VERIFY_THRESHOLD = 6.5
TARGET_SCENES = (1, 2, 3, 4, 5, 6, 7)
PERSON_UA = "Mint-YT-Factory/StoryPersonMedia/1.7"

# Titles containing these terms are not safe identity evidence. This is
# intentionally conservative: a correct-looking image of a relative, namesake,
# memorial, place, or fictional character is worse than falling back to stock.
IDENTITY_BLOCK_TERMS = {
    "daughter", "son", "wife", "husband", "father", "mother", "brother", "sister",
    "relative", "family", "granddaughter", "grandson", "parent", "parents",
    "statue", "monument", "residence", "house", "home", "road", "street",
    "school", "museum", "memorial", "tribute", "painting", "sculpture",
    "grave", "tomb", "plaque", "theatre", "theater", "station", "airport",
    "trainor", "tribute", "impersonator", "lookalike", "fictional", "character",
}


def _clean(value: Any, maximum: int = 500) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()[:maximum]


def _key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()


def _json(text: str) -> dict:
    text = _clean(text, 12000)
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", text):
            try:
                value, _ = decoder.raw_decode(text[match.start():])
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                continue
    return {}


def _candidate_image(item: dict) -> str:
    """Prefer provider thumbnails; original Wikimedia files can trigger 429s."""
    return str(item.get("thumburl") or item.get("url") or "").strip()


def _identity_candidate_allowed(person: str, item: dict) -> bool:
    """Reject obvious indirect/related-person candidates before vision or fallback."""
    title = _clean(item.get("title"), 500).lower()
    creator = _clean(item.get("creator"), 250).lower()
    haystack = f"{title} {creator}"
    if any(re.search(rf"\b{re.escape(term)}\b", haystack) for term in IDENTITY_BLOCK_TERMS):
        return False

    # Explicitly reject common namesakes/fictional people. In particular,
    # Tenzing Norgay Trainor must never be treated as Tenzing Norgay.
    requested = " ".join(re.findall(r"[a-z][a-z'-]{2,}", person.lower()))
    if requested and "trainor" in haystack:
        return False

    # If a title contains a clearly different full person name after the
    # requested name, don't let a loose archival search turn that into identity.
    if requested and re.search(rf"\b{re.escape(requested)}\b", title):
        return True
    return True


def _gemini_verify(person: str, scene_narration: str, candidates: list[dict]) -> int | None:
    key = _key()
    if not key or not candidates:
        return None
    parts, usable = [], []
    for item in candidates[:VERIFY_CANDIDATES]:
        try:
            raw_response = requests.get(
                _candidate_image(item),
                headers={"User-Agent": PERSON_UA, "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"},
                timeout=(10, TIMEOUT),
            )
            raw_response.raise_for_status()
            image = Image.open(io.BytesIO(raw_response.content)).convert("RGB")
            image.thumbnail((512, 512))
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=76, optimize=True)
            from google import genai
            from google.genai import types
            parts.append(types.Part.from_bytes(data=out.getvalue(), mime_type="image/jpeg"))
            usable.append(item)
        except Exception as exc:
            print(f"      ⚠️ Person candidate preview failed: {type(exc).__name__}: {_clean(exc, 180)}")
    if not usable:
        return None

    prompt = f"""You are the identity and scene-relevance verifier for a factual YouTube Story Short.
Requested real person: {person}
Scene narration: {scene_narration}
Candidates are supplied in order from archival/photo/video sources.
REAL PERSON IDENTITY IS THE TOP PRIORITY. Select the clearest unmistakable
photo or video frame of the requested person. Prefer authentic historical
photos, interviews, events, work, performances, or other footage where the
person is visibly identifiable. Do not select relatives, namesakes, statues,
memorials, paintings, logos, or generic stock imagery. If no candidate clearly
shows the requested person, return best_index 0 and identity_score 0.
Return ONLY JSON: {{\"best_index\": 1, \"identity_score\": 0, \"relevance_score\": 0, \"reason\": \"short reason\"}}
Score identity and scene relevance from 0-10. Accept identity 6.5+.
The best_index is 1-based."""

    last_exc = None
    for attempt in range(1, 3):
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=key)
            response = client.models.generate_content(
                model="gemini-flash-lite-latest",
                contents=[prompt, *parts],
                config=types.GenerateContentConfig(temperature=0.05, response_mime_type="application/json"),
            )
            payload = _json(getattr(response, "text", "") or "")
            index = int(payload.get("best_index", 0) or 0) - 1
            score = float(payload.get("identity_score", payload.get("score", 0)) or 0)
            if 0 <= index < len(usable) and score >= VERIFY_THRESHOLD:
                return candidates.index(usable[index])
            print(f"      ⚠️ Person vision rejected candidates: best_index={index + 1} identity={score:.1f}")
            return None
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(1.0)
                continue
    if last_exc:
        print(f"      ⚠️ Person identity verification unavailable: {type(last_exc).__name__}: {_clean(last_exc, 500)}")
    return None


def _metadata_fallback_index(person: str, candidates: list[dict]) -> int | None:
    """Use only a highly explicit archival name match when vision is unavailable."""
    person_words = re.findall(r"[a-z][a-z'-]{2,}", person.lower())
    if len(person_words) < 2:
        return None
    full_name = " ".join(person_words)
    surname = person_words[-1]
    best = None
    best_score = 0
    for index, item in enumerate(candidates[:VERIFY_CANDIDATES]):
        title = _clean(item.get("title"), 500).lower()
        source = _clean(item.get("source"), 120).lower()
        if not _identity_candidate_allowed(person, item):
            continue
        if not ("wikimedia" in source or "archive" in source or "europeana" in source):
            continue
        if not re.search(rf"\b{re.escape(full_name)}\b", title):
            continue
        score = 5
        if re.search(rf"\b{re.escape(surname)}\b", title):
            score += 1
        if "wikimedia" in source:
            score += 1
        if score > best_score:
            best = index
            best_score = score
    return best if best_score >= 6 else None


def _download(url: str, path: str) -> bool:
    tmp = f"{path}.part"
    try:
        with requests.get(url, headers={"User-Agent": PERSON_UA, "Accept": "*/*"}, stream=True, timeout=(10, TIMEOUT)) as response:
            response.raise_for_status()
            with open(tmp, "wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        if os.path.getsize(tmp) <= 0:
            return False
        os.replace(tmp, path)
        return True
    except Exception as exc:
        print(f"      ⚠️ Person media download failed: {type(exc).__name__}: {_clean(exc, 300)}")
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def _safe_filename(index: int, mime: str) -> str:
    if str(mime).startswith("video/"):
        ext = ".webm" if "webm" in str(mime) else ".ogv" if "ogg" in str(mime) else ".mp4"
    else:
        ext = ".jpg"
    return f"person_{index:02d}{ext}"


def generate_person_media(script: dict, output_dir: str, person: str) -> dict:
    person = _clean(person, 180)
    if not person:
        return {"assets": [], "credits": []}
    os.makedirs(output_dir, exist_ok=True)
    scenes = script.get("scene_plan") or []
    assets, credits, seen = [], [], set()
    vision_failures = 0
    vision_disabled = False
    print(f"👤 REAL PERSON MEDIA — multi-source identity-first search: {person}")

    for scene_no in TARGET_SCENES:
        if scene_no > len(scenes):
            continue
        narration = _clean(scenes[scene_no - 1].get("narration"), 500)
        raw_candidates = search_person_media(person, narration)
        candidates = [
            x for x in raw_candidates
            if (x.get("source_url") or x.get("url")) not in seen
            and _identity_candidate_allowed(person, x)
        ]
        filtered = len(raw_candidates) - len(candidates)
        if filtered:
            print(f"      🛡️ Scene {scene_no}: rejected {filtered} obvious non-person/related candidates before verification")
        if not candidates:
            print(f"   ↪️ Scene {scene_no}: no safe person-media candidates found")
            continue
        remaining = list(candidates)
        while remaining:
            batch = remaining[:VERIFY_CANDIDATES]
            chosen_index = None
            if not vision_disabled:
                chosen_index = _gemini_verify(person, narration, batch)
                if chosen_index is None:
                    vision_failures += 1
                    if vision_failures >= 2:
                        vision_disabled = True
                        print("   🛑 Person vision circuit breaker: Gemini identity verification disabled for this run")
            if chosen_index is None and vision_disabled:
                chosen_index = _metadata_fallback_index(person, batch)
                if chosen_index is not None:
                    print("      🛡️ Using explicit-name archival metadata fallback (vision unavailable)")
            if chosen_index is None:
                remaining = remaining[VERIFY_CANDIDATES:]
                if remaining and not vision_disabled:
                    print(f"      ↪️ Scene {scene_no}: verifying next candidate batch")
                    continue
                print(f"   ↪️ Scene {scene_no}: no confidently verified real-person asset")
                break

            chosen = batch[chosen_index]
            source_key = chosen.get("source_url") or chosen.get("url")
            seen.add(source_key)
            download_url = chosen.get("thumburl") or chosen.get("url")
            path = os.path.join(output_dir, _safe_filename(len(assets) + 1, chosen.get("mime", "image/jpeg")))
            if not _download(download_url, path):
                remaining = remaining[chosen_index + 1:]
                print(f"      ↪️ Scene {scene_no}: download failed, trying another candidate")
                continue
            asset = {
                "scene": scene_no, "path": path,
                "type": "video" if str(chosen.get("mime", "")).startswith("video/") else "photo",
                "provider": chosen.get("source", "Unknown"), "creator": chosen.get("creator", ""),
                "license": chosen.get("license", "Unknown / not supplied"),
                "source_url": chosen.get("source_url", ""), "query": chosen.get("query", ""),
                "title": chosen.get("title", ""), "person_visual": True,
            }
            assets.append(asset); credits.append(asset)
            print(f"   ✅ Scene {scene_no}: VERIFIED {asset['type'].upper()} — {asset['title']} | source={asset['provider']}")
            break

    return {
        "assets": assets,
        "credits": credits,
        "person": person,
        "priority": "real_person_first",
        "generated_at": int(time.time()),
    }


def apply_person_media(visuals: list, person_media: dict) -> list:
    assets = {int(x.get("scene")): x for x in (person_media or {}).get("assets", []) if isinstance(x, dict) and x.get("path")}
    for group in visuals or []:
        scene = int(group.get("scene", 0) or 0)
        if scene not in assets:
            continue
        asset = assets[scene]
        if not os.path.isfile(asset["path"]):
            continue
        group.update({"path": asset["path"], "type": asset["type"], "provider": asset["provider"], "creator": asset.get("creator", ""), "query": asset.get("query", ""), "source_url": asset.get("source_url", ""), "license": asset.get("license", "Unknown / not supplied"), "person_visual": True, "asset_title": asset.get("title", "")})
        assets.pop(scene, None)
    return visuals
