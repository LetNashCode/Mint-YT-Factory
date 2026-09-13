"""Real-person visual layer for Story Shorts.

Real-person identity is the primary visual objective. Wikimedia Commons is
searched broadly for the featured person and scene context, with Gemini
Vision used to verify that a selected image actually depicts the person.
Rights metadata is retained for attribution/audit purposes and reusable
licenses are preferred, but missing license metadata does not silently make
an identity match look like a generic stock result.

Story Shorts-only; Publish Shorts state is untouched.
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

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "Mint-YT-Factory/StoryPersonMedia/1.2 (YouTube Story Shorts)"
TIMEOUT = 25
MAX_RESULTS = 24
VERIFY_CANDIDATES = 10
VERIFY_THRESHOLD = 6.5
TARGET_SCENES = (1, 2, 3, 4, 5, 6, 7)


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


def _license_text(metadata: dict) -> str:
    ext = metadata.get("extmetadata") or {}
    for key in ("LicenseShortName", "UsageTerms", "LicenseUrl"):
        value = ext.get(key)
        value = value.get("value") if isinstance(value, dict) else value
        if value:
            return _clean(value, 250)
    return "Unknown / not supplied"


def _license_preference(text: str) -> int:
    """Rank rights metadata without making it an identity-search blocker."""
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    if any(x in normalized for x in ("noncommercial", "non commercial", "no derivatives", "no derivative")):
        return 0
    if normalized in {"cc0", "pdm", "pd us", "pd old", "public domain"}:
        return 3
    if re.fullmatch(r"cc by(?: sa)?(?: [0-9]+(?: [0-9]+)*)?", normalized):
        return 2
    if normalized and normalized != "unknown not supplied":
        return 1
    return 0


def _search_commons(query: str) -> list[dict]:
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"File:{query}",
        "gsrnamespace": 6,
        "gsrlimit": MAX_RESULTS,
        "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata",
        "iiurlwidth": 1400,
        "format": "json",
        "origin": "*",
    }
    try:
        response = requests.get(COMMONS_API, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        response.raise_for_status()
        pages = (response.json().get("query") or {}).get("pages") or {}
    except Exception as exc:
        print(f"      ⚠️ Wikimedia Commons search failed: {type(exc).__name__}")
        return []

    result = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        mime = str(info.get("mime") or "").lower()
        url = info.get("url") or ""
        thumb = info.get("thumburl") or url
        title = _clean(page.get("title"), 300)
        if not url or not thumb or not mime:
            continue
        if not (mime.startswith("image/") or mime.startswith("video/")):
            continue
        ext = info.get("extmetadata") or {}
        artist = ext.get("Artist") or {}
        creator = artist.get("value") if isinstance(artist, dict) else artist
        license_name = _license_text(info)
        result.append({
            "title": title,
            "url": url,
            "thumburl": thumb,
            "mime": mime,
            "license": license_name,
            "license_preference": _license_preference(license_name),
            "source_page": f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
            "creator": _clean(creator, 250),
        })
    return result


def _gemini_verify(person: str, scene_narration: str, candidates: list[dict]) -> int | None:
    key = _key()
    if not key or not candidates:
        return None
    try:
        from google import genai
        from google.genai import types
        parts = []
        usable = []
        for item in candidates[:VERIFY_CANDIDATES]:
            try:
                raw = requests.get(item["thumburl"], headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT).content
                image = Image.open(io.BytesIO(raw)).convert("RGB")
                image.thumbnail((768, 768))
                out = io.BytesIO()
                image.save(out, format="JPEG", quality=82, optimize=True)
                parts.append(types.Part.from_bytes(data=out.getvalue(), mime_type="image/jpeg"))
                usable.append(item)
            except Exception:
                continue
        if not usable:
            return None

        prompt = f"""You are the identity verifier for a factual YouTube Story Short.
Requested real person: {person}
Scene narration: {scene_narration}
You are viewing Wikimedia Commons candidate thumbnails in order.
Choose the candidate that most confidently depicts the requested real person.
Prioritize an unmistakable real-person photograph or frame of that person.
Do not select logos, statues, paintings, unrelated people, or generic images.
A historical photograph with the person clearly visible is preferred over an
atmosphere image. File names alone are not sufficient evidence.
Return ONLY JSON: {{\"best_index\": 0, \"score\": 0, \"reason\": \"short reason\"}}
Score identity confidence from 0-10. Accept 6.5+ when the person's identity
is reasonably clear. best_index is 1-based."""
        response = genai.Client(api_key=key).models.generate_content(
            model="gemini-flash-lite-latest",
            contents=[prompt, *parts],
            config=types.GenerateContentConfig(temperature=0.05, response_mime_type="application/json"),
        )
        payload = _json(getattr(response, "text", "") or "")
        index = int(payload.get("best_index", 0) or 0) - 1
        score = float(payload.get("score", 0) or 0)
        if 0 <= index < len(usable) and score >= VERIFY_THRESHOLD:
            return candidates.index(usable[index])
    except Exception as exc:
        print(f"      ⚠️ Person identity verification unavailable: {type(exc).__name__}")
    return None


def _scene_query(person: str, narration: str) -> str:
    words = re.findall(r"[a-zA-Z][a-zA-Z'-]{3,}", narration)
    stop = {"that", "this", "with", "from", "they", "their", "were", "when", "what", "then", "into", "about", "because", "after", "before", "would", "could", "there", "have", "been", "while", "just", "than", "more", "very", "story", "person", "people", "life"}
    useful = []
    person_words = set(person.lower().split())
    for word in words:
        w = word.lower()
        if w not in stop and w not in useful and w not in person_words:
            useful.append(w)
    return _clean(f"{person} {' '.join(useful[:4])}", 180)


def _rank_candidates(candidates: list[dict]) -> list[dict]:
    return sorted(candidates, key=lambda x: x.get("license_preference", 0), reverse=True)


def _download(url: str, path: str) -> bool:
    tmp = f"{path}.part"
    try:
        with requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}, stream=True, timeout=(10, TIMEOUT)) as response:
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
        print(f"      ⚠️ Person media download failed: {type(exc).__name__}")
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def _safe_filename(index: int, mime: str) -> str:
    if mime.startswith("video/"):
        ext = ".webm" if "webm" in mime else ".ogv" if "ogg" in mime else ".mp4"
    else:
        ext = ".jpg"
    return f"person_{index:02d}{ext}"


def generate_person_media(script: dict, output_dir: str, person: str) -> dict:
    person = _clean(person, 180)
    if not person:
        return {"assets": [], "credits": []}
    os.makedirs(output_dir, exist_ok=True)
    scenes = script.get("scene_plan") or []
    assets = []
    credits = []
    seen_titles = set()
    print(f"👤 REAL PERSON MEDIA — priority search for: {person}")

    for scene_no in TARGET_SCENES:
        if scene_no > len(scenes):
            continue
        narration = _clean(scenes[scene_no - 1].get("narration"), 500)
        query = _scene_query(person, narration)
        candidates = _search_commons(query)
        if not candidates:
            candidates = _search_commons(person)
        candidates = [x for x in candidates if x.get("title") not in seen_titles]
        candidates = _rank_candidates(candidates)
        if not candidates:
            print(f"   ↪️ Scene {scene_no}: no real-person candidates found")
            continue

        remaining = list(candidates)
        while remaining:
            batch = remaining[:VERIFY_CANDIDATES]
            chosen_index = _gemini_verify(person, narration, batch)
            if chosen_index is None:
                remaining = remaining[VERIFY_CANDIDATES:]
                if remaining:
                    print(f"      ↪️ Scene {scene_no}: trying next person-media candidate batch")
                    continue
                print(f"   ↪️ Scene {scene_no}: no confidently verified real-person asset")
                break
            chosen = batch.pop(chosen_index)
            remaining = remaining[VERIFY_CANDIDATES:]
            seen_titles.add(chosen["title"])
            path = os.path.join(output_dir, _safe_filename(len(assets) + 1, chosen["mime"]))
            if not _download(chosen["url"], path):
                print(f"      ↪️ Trying another verified person-media candidate for Scene {scene_no}")
                continue
            asset = {
                "scene": scene_no,
                "path": path,
                "type": "video" if chosen["mime"].startswith("video/") else "photo",
                "provider": "Wikimedia Commons",
                "creator": chosen.get("creator", ""),
                "license": chosen.get("license", "Unknown / not supplied"),
                "source_url": chosen.get("source_page", ""),
                "query": query,
                "title": chosen.get("title", ""),
                "person_visual": True,
            }
            assets.append(asset)
            credits.append(asset)
            print(f"   ✅ Scene {scene_no}: VERIFIED {asset['type'].upper()} — {asset['title']} | rights metadata: {asset['license']}")
            break

    return {"assets": assets, "credits": credits, "person": person, "priority": "real_person_first", "generated_at": int(time.time())}


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
