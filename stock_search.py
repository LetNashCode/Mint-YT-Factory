"""Stock-only visual search pipeline for Mint-YT-Factory.

Gemini is used ONLY as a search-language director and visual verifier.
Production media is ALWAYS retrieved from Pexels/Pixabay. No AI-generated
production imagery is permitted.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests

PEXELS_API = "https://api.pexels.com/v1"
PIXABAY_API = "https://pixabay.com/api"
PIXABAY_VIDEO_API = "https://pixabay.com/api/videos"
GEMINI_MODEL = "gemini-flash-lite-latest"
VERIFY_THRESHOLD = 7.5
SEARCH_PROMPTS = 8
CANDIDATES_PER_SEARCH = 6
TIMEOUT = 35
USER_AGENT = "Mint-YT-Factory/StockSearch/12.0"


def clean(v: Any, n=700):
    return " ".join(str(v or "").replace("\n", " ").split()).strip()[:n]


def _key():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required for stock visual direction.")
    return key


def _json(text):
    text = re.sub(r"^```(?:json)?", "", str(text or "").strip(), flags=re.I).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise RuntimeError("Gemini returned invalid stock-search JSON.")
        return json.loads(match.group(0))


def _is_transient_gemini_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(x in text for x in (
        "503", "unavailable", "429", "resource exhausted", "500", "502",
        "504", "high demand", "temporarily"
    ))


def _gemini(prompt: str, temperature: float):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_key())
    last_error = None
    for attempt in range(1, 4):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[prompt],
                config=types.GenerateContentConfig(temperature=temperature),
            )
            return _json(getattr(response, "text", ""))
        except Exception as exc:
            last_error = exc
            if _is_transient_gemini_error(exc) and attempt < 3:
                print(f"⚠️ {GEMINI_MODEL} temporary failure ({attempt}/3); retrying...")
                time.sleep(2.0 * attempt)
                continue
            break
    raise RuntimeError(
        f"Gemini visual/search call failed using {GEMINI_MODEL}: "
        f"{type(last_error).__name__}: {last_error}"
    ) from last_error


def direct(scene_no: int, shot_no: int, scene: dict, visual: dict):
    """Turn one spoken visual beat into an ordered vocabulary search ladder.

    The important change is that Gemini does NOT merely produce five near-
    duplicate keywords. It creates genuinely different ways to describe the
    SAME visual event. The search engine tries them in order and stops only
    after a Gemini visual check accepts an asset.
    """
    spoken = clean(visual.get("spoken_line") or scene.get("narration"), 650)
    focus = clean(visual.get("visual_focus"), 350)
    action = clean(visual.get("visual_action"), 350)
    must = [clean(x, 180) for x in visual.get("must_show", []) if clean(x)]
    avoid = [clean(x, 180) for x in visual.get("must_not_show", []) if clean(x)]

    prompt = f"""You are the VISUAL SEARCH DIRECTOR for a fast, funny, curiosity-driven YouTube Short.

The final video can ONLY use real stock media from Pexels or Pixabay.
You are NOT generating an image. You are writing search language that a stock
library can understand.

SCENE: {scene_no}
SHOT: {shot_no}
SPOKEN BEAT: {spoken}
VISUAL FOCUS: {focus}
VISUAL ACTION: {action}
MUST SHOW: {json.dumps(must, ensure_ascii=False)}
MUST NOT SHOW: {json.dumps(avoid, ensure_ascii=False)}

YOUR JOB
Create an ordered SEARCH LADDER for this exact visual beat.
Every search must still refer to the SAME real-world subject and idea.
Do not wander into a merely related object.

VOCABULARY RULE — CRITICAL
If search #1 is unavailable, search #2 MUST use noticeably different wording,
not just add/remove one word. Change the noun, verb, everyday phrasing,
physical description, viewpoint, or context while preserving the meaning.
For example, do NOT output:
  "candle flame", "candle flame closeup", "candle burning flame"
Instead think like a stock researcher:
  "wax candle burning"
  "candle wick lit"
  "flame melting candle wax"
  "burning candle close view"
  "wax dripping from candle"

SEARCH LADDER TYPES
1. LITERAL — the most obvious stock-library wording.
2. EVERYDAY — how an ordinary person would describe the same thing.
3. ACTION — emphasize what the subject is physically doing.
4. STATE/RESULT — emphasize the visible condition or immediate result.
5. ALTERNATE NOUN — use a genuine synonym or more concrete term for the subject.
6. VIEWPOINT — close-up, hands-on, overhead, side view, macro, etc., ONLY if useful.
7. CONTEXT — put the same subject in the real setting where the event happens.
8. CAUSAL — show the same subject immediately before/after the spoken event.

HARD RULES
- Keep the subject identical across the ladder.
- Do not replace the subject with a metaphor, diagram, laboratory graphic,
  generic texture, generic person, or unrelated object.
- Prefer visible physical evidence over invisible scientific explanations.
- For invisible mechanisms, search for the SAME object's visible consequence.
- Avoid words like science, concept, mystery, mechanism, educational,
  experiment, cinematic, futuristic, abstract.
- Each query must be 2-7 words and natural for Pexels/Pixabay search.
- Make every query materially different in vocabulary.
- Queries must be useful even if the previous query returned zero results.
- Keep Shot {shot_no} visually distinct from the other shot in Scene {scene_no}.

Also describe what a successful asset must visibly contain so a later visual
judge can reject attractive but irrelevant footage.

Return ONLY JSON:
{{
  "search_ladder": [
    {{"query":"...","strategy":"literal"}},
    {{"query":"...","strategy":"everyday"}},
    {{"query":"...","strategy":"action"}},
    {{"query":"...","strategy":"state-result"}},
    {{"query":"...","strategy":"alternate-noun"}},
    {{"query":"...","strategy":"viewpoint"}},
    {{"query":"...","strategy":"context"}},
    {{"query":"...","strategy":"causal"}}
  ],
  "casting_brief":"...",
  "must_match":["..."],
  "avoid":["..."]
}}"""

    data = _gemini(prompt, 0.25)
    ladder = []
    seen = set()
    for item in data.get("search_ladder", []):
        if not isinstance(item, dict):
            continue
        query = clean(item.get("query"), 100)
        strategy = clean(item.get("strategy"), 40)
        key = query.lower()
        if not query or key in seen or len(query.split()) > 8:
            continue
        seen.add(key)
        ladder.append({"query": query, "strategy": strategy or "alternate"})

    if len(ladder) < 4:
        raise RuntimeError("Gemini produced too few materially different stock-search prompts.")

    return {
        "search_ladder": ladder[:SEARCH_PROMPTS],
        "queries": [x["query"] for x in ladder[:SEARCH_PROMPTS]],
        "casting_brief": clean(data.get("casting_brief"), 600),
        "must_match": [clean(x, 180) for x in data.get("must_match", [])[:10]],
        "avoid": [clean(x, 180) for x in data.get("avoid", [])[:10]],
        "spoken_beat": spoken,
        "visual_focus": focus,
        "visual_action": action,
    }


def build_plan(script):
    scenes = script.get("scene_plan")
    if not isinstance(scenes, list) or len(scenes) != 7:
        raise RuntimeError("Stock search requires exactly 7 scenes.")

    plan = []
    print(f"🧠 STOCK SEARCH DIRECTOR — {GEMINI_MODEL} — Gemini search-language ladder")
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
    params = {"query": query, "per_page": CANDIDATES_PER_SEARCH, "orientation": "portrait"}
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
    except Exception:
        return []


def pixabay(query, video):
    key = os.getenv("PIXABAY_API_KEY", "").strip()
    if not key:
        return []
    endpoint = PIXABAY_VIDEO_API if video else PIXABAY_API
    params = {
        "key": key,
        "q": query,
        "lang": "en",
        "per_page": CANDIDATES_PER_SEARCH,
        "safesearch": "true",
        "order": "popular",
    }
    if video:
        params["video_type"] = "film"
    else:
        params.update(image_type="photo", orientation="vertical")
    try:
        r = requests.get(endpoint, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        if r.status_code != 200:
            return []
        return r.json().get("hits", [])
    except Exception:
        return []


def _preview(item, provider, video):
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
            # Prefer portrait files, then highest usable resolution.
            choices = []
            for f in item.get("video_files") or []:
                u = f.get("link")
                w = int(f.get("width") or 0)
                h = int(f.get("height") or 0)
                if u:
                    choices.append((h > w, w * h, u))
            return max(choices)[2] if choices else ""
        src = item.get("src") or {}
        return src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original") or ""
    if video:
        for key in ("large", "medium", "small", "tiny"):
            u = (item.get("videos") or {}).get(key, {}).get("url")
            if u:
                return u
        return ""
    return item.get("largeImageURL") or item.get("fullHDURL") or item.get("imageURL") or ""


def _creator(item, provider):
    if provider == "Pexels":
        return ((item.get("user") or {}).get("name", ""))
    return item.get("user", "")


def _verify_prompt(directed, query, strategy):
    return f"""You are the FINAL VISUAL MATCH JUDGE for a YouTube Short.
Judge ONLY what is visibly present in the supplied stock previews.

SPOKEN BEAT:
{directed['spoken_beat']}

VISUAL FOCUS:
{directed['visual_focus']}

VISUAL ACTION:
{directed['visual_action']}

SEARCH PROMPT THAT FOUND THESE ASSETS:
{query}

SEARCH STRATEGY:
{strategy}

IDEAL SHOT:
{directed['casting_brief']}

MUST MATCH:
{json.dumps(directed.get('must_match', []), ensure_ascii=False)}

MUST AVOID:
{json.dumps(directed.get('avoid', []), ensure_ascii=False)}

STRICT JUDGING RULES
1. The actual subject being spoken about must be visible.
2. The visible physical action/state should match the spoken beat whenever possible.
3. A related object is NOT good enough. Reject it.
4. Generic attractive footage is NOT good enough. Reject it.
5. Generic people, generic laboratory scenes, generic food/water, decorative
   textures, diagrams and abstract science imagery are NOT good enough.
6. If the spoken mechanism is invisible, accept only a truthful visible proxy
   involving the SAME subject: for example a cut-open object, steam, boiling,
   swelling, cracking, dripping, melting, bursting, or the immediate result.
7. A causal before/after shot is acceptable only when it uses the SAME subject
   and clearly helps explain the spoken beat.
8. Do not reward cinematic quality when the subject is wrong.
9. Prefer a simple literal stock shot over a clever but ambiguous one.

Score each candidate from 0-10 using:
- subject_match: 0-10
- action_match: 0-10
- context_match: 0-10

The overall score should heavily favor subject accuracy. A candidate must be
rejected unless the subject genuinely matches. Usable means score >= {VERIFY_THRESHOLD}
and reject=false.

Return ONLY JSON:
{{"results":[{{"candidate":1,"score":0,"subject_match":0,"action_match":0,"context_match":0,"reject":true,"reason":"..."}}]}}"""


def verify(candidates, directed, query, strategy):
    """Let Gemini choose from the assets returned by ONE search prompt.

    There is intentionally NO metadata candidate ranking here. Stock APIs are
    search providers, not relevance judges. Gemini sees the actual previews and
    decides whether any asset really matches the spoken beat.
    """
    if not candidates:
        return None

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_key())
    usable = []
    parts = []

    for candidate in candidates[:CANDIDATES_PER_SEARCH]:
        try:
            r = requests.get(candidate["preview"], headers={"User-Agent": USER_AGENT}, timeout=20)
            r.raise_for_status()
            mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
            if not mime.startswith("image/"):
                mime = "image/jpeg"
            idx = len(usable) + 1
            parts.append(types.Part.from_bytes(data=r.content, mime_type=mime))
            parts.append(types.Part.from_text(text=f"CANDIDATE {idx}"))
            usable.append(candidate)
        except Exception:
            continue

    if not usable:
        return None

    prompt = _verify_prompt(directed, query, strategy)
    last_error = None
    data = None

    for attempt in range(1, 4):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=parts + [types.Part.from_text(text=prompt)],
                config=types.GenerateContentConfig(temperature=0),
            )
            data = _json(getattr(response, "text", "") or "")
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            if _is_transient_gemini_error(exc) and attempt < 3:
                print(f"⚠️ Visual verification {GEMINI_MODEL} temporary failure ({attempt}/3); retrying...")
                time.sleep(2.0 * attempt)
                continue
            break

    if last_error is not None:
        raise RuntimeError(
            f"Visual verification failed using {GEMINI_MODEL}: "
            f"{type(last_error).__name__}: {last_error}"
        ) from last_error

    accepted = []
    for result in data.get("results", []):
        try:
            i = int(result.get("candidate", 0)) - 1
            score = float(result.get("score", 0) or 0)
            if 0 <= i < len(usable) and not bool(result.get("reject", True)) and score >= VERIFY_THRESHOLD:
                selected = dict(usable[i])
                selected.update(
                    visual_score=score,
                    visual_subject_match=float(result.get("subject_match", 0) or 0),
                    visual_action_match=float(result.get("action_match", 0) or 0),
                    visual_context_match=float(result.get("context_match", 0) or 0),
                    visual_reason=clean(result.get("reason"), 500),
                    search_query=query,
                    search_strategy=strategy,
                )
                accepted.append(selected)
        except (TypeError, ValueError):
            continue

    # Gemini has already judged the assets. If it accepts multiple, use the
    # first accepted candidate in the order Gemini returned them; no metadata
    # score/ranking is applied.
    return accepted[0] if accepted else None


def _download(url, path, provider):
    for attempt in range(1, 4):
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120, stream=True)
            r.raise_for_status()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                for chunk in r.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk)
            if os.path.getsize(path) <= 10000:
                raise RuntimeError("download too small")
            return True
        except Exception as exc:
            print(f"⚠️ {provider} download {attempt}/3 failed: {type(exc).__name__}: {exc}")
            if attempt < 3:
                time.sleep(1.5 * attempt)
    return False


def _credit(path, selected, directed):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "provider": selected["provider"],
            "type": selected["kind"],
            "page": selected["page"],
            "creator": selected.get("creator", ""),
            "search_query": selected.get("search_query", ""),
            "search_strategy": selected.get("search_strategy", ""),
            "search_ladder": directed.get("queries", []),
            "gemini_visual_score": selected["visual_score"],
            "visual_subject_match": selected.get("visual_subject_match", 0),
            "visual_action_match": selected.get("visual_action_match", 0),
            "visual_context_match": selected.get("visual_context_match", 0),
            "visual_reason": selected["visual_reason"],
        }, f, ensure_ascii=False, indent=2)


def _fetch_for_query(query, provider, video, used_pages):
    raw = pexels(query, video) if provider == "Pexels" else pixabay(query, video)
    candidates = []
    for item in raw[:CANDIDATES_PER_SEARCH]:
        page = str(item.get("url") if provider == "Pexels" else item.get("pageURL") or "")
        if not page or page in used_pages:
            continue
        preview = _preview(item, provider, video)
        url = _url(item, provider, video)
        if not preview or not url:
            continue
        candidates.append({
            "provider": provider,
            "kind": "video" if video else "photo",
            "url": url,
            "page": page,
            "creator": _creator(item, provider),
            "preview": preview,
        })
    return candidates


def generate_media(script, output_dir, config, gim=None):
    if not os.getenv("PEXELS_API_KEY", "").strip() and not os.getenv("PIXABAY_API_KEY", "").strip():
        raise RuntimeError("PEXELS_API_KEY or PIXABAY_API_KEY is required.")

    os.makedirs(output_dir, exist_ok=True)
    plan = build_plan(script)
    used_pages = set()
    groups = []

    print(f"📚 STOCK SEARCH {GEMINI_MODEL} | Pexels/Pixabay only | NO metadata ranking")

    for si, shots in enumerate(plan, 1):
        paths = []
        for vi, directed in enumerate(shots, 1):
            selected = None

            # Each search prompt is tried independently. We do not pool or
            # rank candidates from different prompts. A failed vocabulary
            # variant simply advances to the next materially different one.
            for ladder_item in directed["search_ladder"]:
                query = ladder_item["query"]
                strategy = ladder_item["strategy"]
                print(f"   🔎 Scene {si} Shot {vi}: [{strategy}] {query}")

                provider_modes = []
                if os.getenv("PEXELS_API_KEY", "").strip():
                    provider_modes.extend([("Pexels", True), ("Pexels", False)])
                if os.getenv("PIXABAY_API_KEY", "").strip():
                    provider_modes.extend([("Pixabay", True), ("Pixabay", False)])

                for provider, video in provider_modes:
                    candidates = _fetch_for_query(query, provider, video, used_pages)
                    if not candidates:
                        print(f"      ↪️ {provider} {'VIDEO' if video else 'PHOTO'}: no assets")
                        continue

                    chosen = verify(candidates, directed, query, strategy)
                    if chosen:
                        selected = chosen
                        print(
                            f"      ✅ {provider} {chosen['kind']} VERIFIED "
                            f"{chosen['visual_score']:.1f}/10 "
                            f"({chosen['search_strategy']}: {chosen['search_query']})"
                        )
                        break

                    print(f"      ↪️ {provider} {'VIDEO' if video else 'PHOTO'}: Gemini rejected all previews")

                if selected:
                    break

            if not selected:
                raise RuntimeError(
                    f"No visually relevant stock asset found for Scene {si} Shot {vi} "
                    f"after {len(directed['search_ladder'])} different Gemini-directed search vocabularies; "
                    "unrelated fallback is disabled."
                )

            used_pages.add(selected["page"])
            ext = "mp4" if selected["kind"] == "video" else "jpg"
            path = os.path.join(output_dir, f"scene_{si:02d}_shot_{vi:02d}.{ext}")
            if not _download(selected["url"], path, selected["provider"]):
                raise RuntimeError(f"Stock asset download failed for Scene {si} Shot {vi}.")
            _credit(path + ".credit.json", selected, directed)
            paths.append(path)

        groups.append(paths)

    return groups
