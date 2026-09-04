"""Production stock-media director for Mint-YT-Factory.

Goals:
- Keep stock visuals tightly tied to the spoken beat.
- Search Pexels/Pixabay using practical photographer language.
- Verify the ACTUAL candidate thumbnails with Gemini Vision when available.
- Never fail an entire production merely because Gemini verification is temporarily unavailable.
- Never silently substitute an unrelated object.

Production media remains Pexels/Pixabay only.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import time
from typing import Any

import requests
from PIL import Image

PEXELS_API = "https://api.pexels.com/v1"
PIXABAY_API = "https://pixabay.com/api"
PIXABAY_VIDEO_API = "https://pixabay.com/api/videos"
GEMINI_MODEL = "gemini-flash-lite-latest"
VERIFY_THRESHOLD = 7.0
SEARCH_PROMPTS = 8
CANDIDATES_PER_SEARCH = 8
VERIFY_CANDIDATES = 6
TIMEOUT = 25
USER_AGENT = "Mint-YT-Factory/StockSearch/15.0"

# Words that tend to produce beautiful but useless stock results.
BAD_QUERY_WORDS = {
    "science", "concept", "mechanism", "mystery", "educational", "experiment",
    "cinematic", "futuristic", "abstract", "diagram", "illustration", "render",
    "3d", "laboratory", "microscopic", "molecular", "physics", "chemistry",
}


def clean(value: Any, maximum: int = 700) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()[:maximum]


def _key() -> str:
    # Gemini is optional for stock search. Local fallback keeps production running.
    return os.getenv("GEMINI_API_KEY", "").strip()


def _json(text: str) -> dict:
    text = clean(text, 12000)
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError as first:
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", text):
            try:
                value, _ = decoder.raw_decode(text[match.start():])
                if isinstance(value, dict):
                    return value
            except json.JSONDecodeError:
                continue
        raise RuntimeError(f"Gemini returned invalid stock JSON: {first}") from first
    raise RuntimeError("Gemini returned non-object stock JSON.")


def _is_transient_gemini_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(token in text for token in (
        "503", "unavailable", "429", "resource exhausted", "500", "502", "504",
        "high demand", "temporarily", "deadline exceeded", "timeout",
    ))


def _gemini(prompt: str, temperature: float = 0.15, parts: list[Any] | None = None) -> dict:
    """Call Gemini with bounded retries. `parts` may contain image Parts."""
    from google import genai
    from google.genai import types

    key = _key()
    if not key:
        raise RuntimeError("Gemini unavailable: GEMINI_API_KEY not configured")
    client = genai.Client(api_key=key)
    contents: Any = [prompt] if not parts else [prompt, *parts]
    last: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    response_mime_type="application/json",
                ),
            )
            return _json(getattr(response, "text", ""))
        except Exception as exc:
            last = exc
            if _is_transient_gemini_error(exc) and attempt < 3:
                print(f"⚠️ {GEMINI_MODEL} temporary failure ({attempt}/3); retrying...")
                time.sleep(1.5 * attempt)
                continue
            break
    raise RuntimeError(f"Gemini stock call failed: {type(last).__name__}: {last}") from last


def _normalize_ladder(data: dict, anchors: list[str]) -> list[dict]:
    ladder: list[dict] = []
    seen: set[str] = set()
    anchor_words = set(re.findall(r"[a-z0-9]+", " ".join(anchors).lower()))
    for item in data.get("search_ladder", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        query = clean(item.get("query"), 100).lower()
        strategy = clean(item.get("strategy"), 40) or "alternate"
        key = re.sub(r"[^a-z0-9 ]+", "", query).strip()
        words = set(re.findall(r"[a-z0-9]+", query))
        if not query or key in seen or not 2 <= len(query.split()) <= 7:
            continue
        if words & BAD_QUERY_WORDS:
            continue
        # A stock query must retain at least one concrete anchor from the visual brief.
        if anchor_words and not (words & anchor_words):
            continue
        seen.add(key)
        ladder.append({"query": query, "strategy": strategy})
    return ladder


def _anchor_terms(spoken: str, focus: str, action: str, must: list[str]) -> list[str]:
    """Extract concrete nouns likely to be useful in stock search."""
    text = " ".join([spoken, focus, action, *must]).lower()
    replacements = {
        "popcorn kernels": "popcorn kernel", "kernels": "kernel", "maize": "corn",
        "pericarp": "corn shell", "starch": "corn", "pericarp shell": "corn shell",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    stop = {
        "the", "and", "with", "from", "that", "this", "into", "under", "inside",
        "over", "when", "your", "their", "same", "visible", "showing", "shows",
        "because", "like", "really", "actually", "tiny", "little", "hard", "white",
        "yellow", "single", "physical", "object", "thing", "surface", "state",
    }
    words = re.findall(r"[a-z][a-z-]{2,}", text)
    ranked: list[str] = []
    for word in words:
        if word in stop or word in BAD_QUERY_WORDS:
            continue
        if word not in ranked:
            ranked.append(word)
    return ranked[:10]


def direct(scene_no: int, shot_no: int, scene: dict, visual: dict, failed_queries=None, round_no=1):
    spoken = clean(visual.get("spoken_line") or scene.get("narration"), 650)
    focus = clean(visual.get("visual_focus"), 350)
    action = clean(visual.get("visual_action"), 350)
    must = [clean(x, 180) for x in visual.get("must_show", []) if clean(x)]
    avoid = [clean(x, 180) for x in visual.get("must_not_show", []) if clean(x)]
    failed = [clean(x, 100) for x in (failed_queries or []) if clean(x)]
    anchors = _anchor_terms(spoken, focus, action, must)
    # Prefer explicit visual brief nouns over fragmented narration words. This
    # prevents queries like "thief never" when the narration itself is abstract.
    subject_text = " ".join([focus, action, *must]).lower()
    subject_words = [
        w for w in re.findall(r"[a-z][a-z-]{2,}", subject_text)
        if w not in BAD_QUERY_WORDS and w not in {"show", "showing", "visible", "camera", "shot", "scene", "with", "from", "onto", "into", "table", "screen"}
    ]
    if subject_words:
        preferred = []
        for w in subject_words + anchors:
            if w not in preferred:
                preferred.append(w)
        anchors = preferred[:10]
    anchor_hint = ", ".join(anchors[:6])

    prompt = f'''You are the STOCK SEARCH DIRECTOR for a funny, curiosity-driven YouTube Short.
Real production media comes ONLY from Pexels and Pixabay.

SCENE {scene_no}, SHOT {shot_no}
SPOKEN BEAT: {spoken}
VISUAL FOCUS: {focus}
VISUAL ACTION: {action}
MUST SHOW: {json.dumps(must, ensure_ascii=False)}
MUST NOT SHOW: {json.dumps(avoid, ensure_ascii=False)}
FAILED QUERIES: {json.dumps(failed, ensure_ascii=False)}
CONCRETE ANCHOR TERMS: {anchor_hint}

Your job is to find stock footage that an ordinary photographer could realistically
have uploaded. Search for what the CAMERA can see, not for the invisible explanation.

RULES:
- Keep the primary physical subject identical across all queries.
- Use ordinary stock-search language, 2-7 words per query.
- Prefer concrete nouns and visible actions: cutting, cracking, boiling, pouring,
  popping, steaming, frying, falling, opening, stretching, spilling, etc.
- If the exact microscopic/invisible mechanism cannot be filmed, search for the
  closest visible state change of the SAME physical subject.
- Never replace the subject with a related object. A popcorn story needs popcorn,
  kernels, a popcorn pan, or popped popcorn—not a random kitchen, generic food,
  generic science footage, a laboratory, or a diagram.
- Never use the words science, concept, mechanism, mystery, educational, experiment,
  cinematic, futuristic, abstract, laboratory, microscopic, molecular, physics, chemistry.
- Do not merely add camera words such as closeup, macro, cinematic, footage.
- Do not invent visual metaphors.
- Queries should become progressively more practical if earlier searches fail.

Return ONLY JSON:
{{
  "search_ladder": [
    {{"query":"exact concrete subject","strategy":"literal"}},
    {{"query":"common stock phrase","strategy":"everyday"}},
    {{"query":"visible action","strategy":"action"}},
    {{"query":"visible state change","strategy":"state-result"}},
    {{"query":"alternate common noun","strategy":"alternate-noun"}},
    {{"query":"useful viewpoint phrase","strategy":"viewpoint"}},
    {{"query":"real-world setting","strategy":"context"}},
    {{"query":"visible consequence","strategy":"causal"}}
  ],
  "casting_brief":"one sentence describing the ideal literal shot",
  "must_match":["concrete visible requirements"],
  "avoid":["likely wrong results"]
}}'''

    # Gemini improves query phrasing, but must never be a production dependency.
    data = {}
    try:
        data = _gemini(prompt, 0.25)
    except Exception as exc:
        print(f"🛡️ Gemini stock director unavailable — local deterministic fallback: {type(exc).__name__}")
    ladder = _normalize_ladder(data, anchors) if data else []

    # Deterministic practical queries guarantee that a poor Gemini answer cannot
    # turn the whole search into exotic/non-searchable language.
    if anchors:
        # Use a meaningful concrete subject phrase only. Never manufacture a
        # search query from arbitrary narration fragments.
        subject = " ".join(anchors[:2])
        if len(subject.split()) < 1 or subject in {"never", "cannot", "unless", "being", "onto"}:
            subject = ""
        practical = ([
            subject,
            f"{subject} on table",
            f"{subject} being heated",
            f"{subject} breaking open",
            f"{subject} being cut",
            f"{subject} close up",
            f"{subject} in kitchen",
            f"{subject} changing state",
        ] if subject else [])
        existing = {x["query"] for x in ladder}
        for q in practical:
            q = clean(q.lower(), 80)
            if q not in existing and 2 <= len(q.split()) <= 7 and not (set(q.split()) & BAD_QUERY_WORDS):
                ladder.append({"query": q, "strategy": "deterministic"})
                existing.add(q)

    if len(ladder) < 4:
        # Never fail production merely because Gemini is unavailable.
        base = subject if 'subject' in locals() and subject else (" ".join(anchors[:2]) or "person thinking")
        existing = {x["query"] for x in ladder}
        for q in [base, f"{base} close up", f"{base} indoors", f"{base} reaction", f"{base} hands"]:
            q = clean(q.lower(), 80)
            if q and q not in existing and 1 <= len(q.split()) <= 7:
                ladder.append({"query": q, "strategy": "local-fallback"})
                existing.add(q)

    return {
        "search_ladder": ladder[:SEARCH_PROMPTS],
        "queries": [x["query"] for x in ladder[:SEARCH_PROMPTS]],
        "casting_brief": clean(data.get("casting_brief"), 600),
        "must_match": [clean(x, 180) for x in data.get("must_match", [])[:10]],
        "avoid": [clean(x, 180) for x in data.get("avoid", [])[:10]],
        "spoken_beat": spoken,
        "visual_focus": focus,
        "visual_action": action,
        "anchor_terms": anchors,
    }


def build_plan(script):
    scenes = script.get("scene_plan")
    if not isinstance(scenes, list) or len(scenes) != 7:
        raise RuntimeError("Stock search requires exactly 7 scenes.")
    plan = []
    print(f"🧠 STOCK SEARCH DIRECTOR — {GEMINI_MODEL} — practical search ladder")
    for si, scene in enumerate(scenes, 1):
        visuals = scene.get("visuals")
        if not isinstance(visuals, list) or len(visuals) != 2:
            raise RuntimeError(f"Scene {si} must contain exactly 2 visuals.")
        shots = []
        for vi, visual in enumerate(visuals, 1):
            directed = direct(si, vi, scene, visual)
            directed.update(scene=si, shot=vi)
            shots.append(directed)
            print(f"   🎯 Scene {si} Shot {vi}:")
            for idx, q in enumerate(directed["search_ladder"], 1):
                print(f"      {idx}. [{q['strategy']}] {q['query']}")
        plan.append(shots)
    return plan


def pexels(query, video):
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        return []
    endpoint = "videos/search" if video else "search"
    params = {"query": query, "per_page": CANDIDATES_PER_SEARCH}
    if video:
        params["size"] = "medium"
    try:
        r = requests.get(
            f"{PEXELS_API}/{endpoint}",
            headers={"Authorization": key, "User-Agent": USER_AGENT},
            params=params,
            timeout=TIMEOUT,
        )
        return r.json().get("videos" if video else "photos", []) if r.status_code == 200 else []
    except Exception as exc:
        print(f"      ⚠️ Pexels request failed: {type(exc).__name__}")
        return []


def pixabay(query, video):
    key = os.getenv("PIXABAY_API_KEY", "").strip()
    if not key:
        return []
    endpoint = PIXABAY_VIDEO_API if video else PIXABAY_API
    params = {
        "key": key, "q": query, "lang": "en", "per_page": CANDIDATES_PER_SEARCH,
        "safesearch": "true", "order": "popular",
    }
    if video:
        params["video_type"] = "film"
    else:
        params["image_type"] = "photo"
    try:
        r = requests.get(endpoint, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        return r.json().get("hits", []) if r.status_code == 200 else []
    except Exception as exc:
        print(f"      ⚠️ Pixabay request failed: {type(exc).__name__}")
        return []


def _preview_url(item, provider, video):
    if provider == "Pexels":
        if video:
            return item.get("image", "")
        src = item.get("src") or {}
        return src.get("medium") or src.get("large") or src.get("portrait") or src.get("original") or ""
    if video:
        pid = str(item.get("picture_id") or "")
        return f"https://i.vimeocdn.com/video/{pid}_640x360.jpg" if pid else ""
    return item.get("previewURL") or item.get("largeImageURL") or ""


def _url(item, provider, video):
    if provider == "Pexels":
        if video:
            choices = []
            for f in item.get("video_files") or []:
                u = f.get("link")
                w = int(f.get("width") or 0)
                h = int(f.get("height") or 0)
                if u:
                    # Prefer landscape 720-ish sources. Portrait is also valid.
                    portrait_penalty = 0 if h >= w else 1
                    choices.append((portrait_penalty, abs(w * h - 720 * 1280), u))
            return sorted(choices)[0][2] if choices else ""
        src = item.get("src") or {}
        return src.get("large2x") or src.get("large") or src.get("original") or src.get("portrait") or ""
    if video:
        for key in ("medium", "large", "small", "tiny"):
            u = (item.get("videos") or {}).get(key, {}).get("url")
            if u:
                return u
        return ""
    return item.get("largeImageURL") or item.get("fullHDURL") or item.get("imageURL") or ""


def _creator(item, provider):
    return ((item.get("user") or {}).get("name", "") if provider == "Pexels" else item.get("user", ""))


def _download_bytes(url: str) -> bytes:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content


def _image_part(data: bytes):
    """Create a Gemini image Part from arbitrary JPEG/PNG thumbnail bytes."""
    from google.genai import types
    # Normalize to small JPEG to keep verification cheap and reliable.
    image = Image.open(io.BytesIO(data)).convert("RGB")
    image.thumbnail((768, 768))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=82, optimize=True)
    return types.Part.from_bytes(data=out.getvalue(), mime_type="image/jpeg")


def _verification_prompt(d, query, strategy, count):
    return f'''You are the STRICT visual-match judge for a YouTube Short.
You are looking at {count} actual stock-image thumbnails attached after this prompt.
Judge what is visibly present. Do not infer invisible science.

SPOKEN BEAT: {d["spoken_beat"]}
VISUAL FOCUS: {d["visual_focus"]}
VISUAL ACTION: {d["visual_action"]}
SEARCH QUERY: {query}
IDEAL SHOT: {d["casting_brief"]}
MUST MATCH: {json.dumps(d.get("must_match", []), ensure_ascii=False)}
ANCHORS: {json.dumps(d.get("anchor_terms", []), ensure_ascii=False)}

Choose ONE thumbnail or reject all.
A strong match requires the primary physical subject to be visibly present.
Action/state should support the spoken beat when possible. Related objects are NOT enough.
Reject generic kitchens, generic food, random people, laboratories, diagrams, symbols,
textures, or metaphorical imagery.
If the requested invisible mechanism is impossible to show, reward a truthful visible
state/consequence involving the same subject.

Return ONLY JSON:
{{
  "best_index": 0,
  "score": 0,
  "subject_match": 0,
  "action_match": 0,
  "context_match": 0,
  "reason": "short reason"
}}
Score 0-10. Use 7+ only for genuinely relevant imagery. Use 0 when none match.'''


def verify_actual(d, items, provider, video, query, strategy):
    """Verify actual thumbnails, not URLs-as-text. Returns item or None.

    If Gemini is unavailable, return None so deterministic scoring can decide.
    """
    candidates = []
    parts = []
    for item in items[:VERIFY_CANDIDATES]:
        preview = _preview_url(item, provider, video)
        if not preview:
            continue
        try:
            raw = _download_bytes(preview)
            parts.append(_image_part(raw))
            candidates.append(item)
        except Exception:
            continue
    if not candidates:
        return None
    payload = _gemini(_verification_prompt(d, query, strategy, len(candidates)), 0.05, parts)
    try:
        index = int(payload.get("best_index", 0)) - 1
        score = float(payload.get("score", 0) or 0)
    except Exception:
        return None
    if index < 0 or index >= len(candidates) or score < VERIFY_THRESHOLD:
        return None
    return candidates[index]


def _deterministic_score(d, item, provider, video, query):
    """Safe outage fallback. It ranks metadata/query alignment but never claims Vision."""
    hay = " ".join([
        query,
        str(item.get("alt", "")),
        str(item.get("description", "")),
        str(item.get("tags", "")),
        str(item.get("url", "")),
    ]).lower()
    anchors = d.get("anchor_terms", [])
    score = 0.0
    hits = 0
    for term in anchors:
        if term and term.lower() in hay:
            hits += 1
    score += min(hits * 1.5, 5.0)
    # Exact query terms are useful metadata evidence.
    qwords = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
    score += min(sum(1 for w in qwords if w in hay) * 0.5, 2.5)
    # A candidate with a preview/downloadable media URL is preferable.
    if _url(item, provider, video):
        score += 1.0
    return score


def _select_without_vision(d, items, provider, video, query):
    ranked = sorted(
        items,
        key=lambda x: _deterministic_score(d, x, provider, video, query),
        reverse=True,
    )
    if not ranked:
        return None
    score = _deterministic_score(d, ranked[0], provider, video, query)
    # Conservative: only accept a metadata-backed match. This is a resilience
    # path, not permission to select random media.
    return ranked[0] if score >= 2.5 else None


def generate_media(script, output_dir, config, gim=None):
    os.makedirs(output_dir, exist_ok=True)
    plan = build_plan(script)
    used: set[str] = set()
    groups = []
    vision_available = True
    print(f"📚 STOCK SEARCH {GEMINI_MODEL} | Pexels/Pixabay only | actual-thumbnail verification")

    for si, shots in enumerate(plan, 1):
        for vi, d in enumerate(shots, 1):
            selected = None
            selected_provider = None
            selected_video = None
            selected_query = None
            vision_failures = 0

            for entry in d["search_ladder"]:
                q = entry["query"]
                strategy = entry["strategy"]
                print(f"   🔎 Scene {si} Shot {vi}: [{strategy}] {q}")

                for provider, video in (("Pexels", True), ("Pixabay", True), ("Pexels", False), ("Pixabay", False)):
                    items = pexels(q, video) if provider == "Pexels" else pixabay(q, video)
                    if not items:
                        print(f"      ↪️ {provider} {'VIDEO' if video else 'PHOTO'}: no assets")
                        continue

                    item = None
                    if vision_available:
                        try:
                            item = verify_actual(d, items, provider, video, q, strategy)
                            if item:
                                print(f"      👁️ Vision verified actual thumbnail")
                        except Exception as exc:
                            vision_failures += 1
                            print(f"      ⚠️ Vision verification unavailable: {type(exc).__name__}")
                            # Don't hammer a failing Gemini endpoint for every provider.
                            if vision_failures >= 3:
                                vision_available = False
                                print("      🛡️ Vision circuit breaker OPEN — deterministic fallback enabled")

                    if item is None:
                        item = _select_without_vision(d, items, provider, video, q)
                        if item:
                            print("      🧮 Selected using conservative metadata fallback")

                    if item:
                        url = _url(item, provider, video)
                        if url and url not in used:
                            selected = item
                            selected_provider = provider
                            selected_video = video
                            selected_query = q
                            break
                    print(f"      ↪️ {provider} {'VIDEO' if video else 'PHOTO'}: no acceptable match")

                if selected:
                    break

            if not selected:
                # One final deterministic pass over all practical queries, with a
                # lower bar only when the candidate has explicit subject metadata.
                for entry in d["search_ladder"]:
                    q = entry["query"]
                    for provider, video in (("Pexels", False), ("Pixabay", False), ("Pexels", True), ("Pixabay", True)):
                        items = pexels(q, video) if provider == "Pexels" else pixabay(q, video)
                        item = _select_without_vision(d, items, provider, video, q) if items else None
                        if item:
                            url = _url(item, provider, video)
                            if url and url not in used:
                                selected = item
                                selected_provider = provider
                                selected_video = video
                                selected_query = q
                                print(f"      🛟 Final resilience selection: {provider} {'VIDEO' if video else 'PHOTO'}")
                                break
                    if selected:
                        break

            if not selected:
                raise RuntimeError(
                    f"No visually relevant stock asset found for Scene {si} Shot {vi}. "
                    "Pexels/Pixabay returned no candidate with sufficient subject evidence."
                )

            ext = "mp4" if selected_video else "jpg"
            path = os.path.join(output_dir, f"scene_{si}_shot_{vi}.{ext}")

            recovered = _download_with_candidate_recovery(
                d=d,
                initial=(selected, selected_provider, selected_video, selected_query),
                output_path=path,
                used_urls=used,
            )
            if not recovered:
                raise RuntimeError(
                    f"No downloadable visually relevant stock asset found for Scene {si} Shot {vi} "
                    f"after retrying the selected asset and fallback candidates."
                )

            selected, selected_provider, selected_video, selected_query, url = recovered
            used.add(url)
            groups.append({
                "scene": si,
                "shot": vi,
                "path": path,
                "type": "video" if selected_video else "photo",
                "provider": selected_provider,
                "creator": _creator(selected, selected_provider),
                "query": selected_query,
                "score": 8.0,
            })
            print(f"      ✅ SELECTED {selected_provider} {'VIDEO' if selected_video else 'PHOTO'}: {selected_query}")

    return groups


def _download_with_candidate_recovery(d, initial, output_path: str, used_urls: set[str]):
    """Download a selected asset, then recover using other relevant candidates.

    A stock API can return a valid-looking candidate whose CDN URL is stale,
    temporarily unavailable, or blocked in GitHub Actions. Download failure must
    therefore not kill the entire Short after selection succeeds.
    """
    failed_urls: set[str] = set()
    queue = [initial]
    queued_urls: set[str] = set()

    while queue:
        item, provider, video, query = queue.pop(0)
        url = _url(item, provider, video)
        if not url or url in used_urls or url in failed_urls:
            continue
        queued_urls.add(url)

        if _download_file(url, output_path):
            return item, provider, video, query, url

        failed_urls.add(url)
        print(
            f"      ⚠️ Download failed for selected {provider} "
            f"{'VIDEO' if video else 'PHOTO'}; trying another relevant candidate..."
        )

        # Search the complete practical ladder and rank every candidate by the
        # existing conservative relevance score. This keeps fallback media tied
        # to the spoken beat instead of substituting unrelated footage.
        for entry in d.get("search_ladder", []):
            q = entry.get("query", "")
            if not q:
                continue
            for next_provider, next_video in (
                ("Pexels", True), ("Pixabay", True),
                ("Pexels", False), ("Pixabay", False),
            ):
                items = (
                    pexels(q, next_video)
                    if next_provider == "Pexels"
                    else pixabay(q, next_video)
                )
                ranked = sorted(
                    items,
                    key=lambda x: _deterministic_score(
                        d, x, next_provider, next_video, q
                    ),
                    reverse=True,
                )
                for candidate in ranked:
                    score = _deterministic_score(
                        d, candidate, next_provider, next_video, q
                    )
                    if score < 2.5:
                        break
                    candidate_url = _url(candidate, next_provider, next_video)
                    if (
                        not candidate_url
                        or candidate_url in used_urls
                        or candidate_url in failed_urls
                        or candidate_url in queued_urls
                    ):
                        continue
                    queue.append((candidate, next_provider, next_video, q))
                    queued_urls.add(candidate_url)

    return None


def _download_file(url: str, path: str) -> bool:
    """Download with retries and atomic replacement of the target file."""
    temp_path = path + ".part"
    for attempt in range(1, 4):
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            with requests.get(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "*/*",
                },
                stream=True,
                timeout=(10, TIMEOUT),
            ) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"HTTP {r.status_code}")
                with open(temp_path, "wb") as f:
                    for chunk in r.iter_content(1024 * 1024):
                        if chunk:
                            f.write(chunk)

            if os.path.getsize(temp_path) > 0:
                os.replace(temp_path, path)
                return True
        except Exception as exc:
            print(
                f"      ⚠️ Asset download attempt {attempt}/3 failed: "
                f"{type(exc).__name__}: {exc}"
            )
            if attempt < 3:
                time.sleep(1.5 * attempt)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
    return False
