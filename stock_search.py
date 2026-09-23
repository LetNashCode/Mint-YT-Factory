"""Production stock-media director for Mint-YT-Factory.

Pexels/Pixabay only. Gemini directs stock searches and verifies actual candidate
thumbnails when available. Story Shorts use video-only stock assets and never
inherit Publish topic-lock metadata.
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

PEXELS_API = "https://api.pexels.com/v1"
PIXABAY_API = "https://pixabay.com/api"
PIXABAY_VIDEO_API = "https://pixabay.com/api/videos"
GEMINI_MODEL = "gemini-flash-lite-latest"
VERIFY_THRESHOLD = 7.0
SEARCH_PROMPTS = 8
CANDIDATES_PER_SEARCH = 8
VERIFY_CANDIDATES = 6
TIMEOUT = 25
USER_AGENT = "Mint-YT-Factory/StockSearch/16.1"
MEDIA_HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media_history.json")
BAD_QUERY_WORDS = {
    "science", "concept", "mechanism", "mystery", "educational", "experiment",
    "cinematic", "futuristic", "abstract", "diagram", "illustration", "render",
    "3d", "laboratory", "microscopic", "molecular", "physics", "chemistry",
}

def clean(value: Any, maximum: int = 700) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()[:maximum]

def _key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()

def _json(text: str) -> dict:
    text = clean(text, 12000)
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        value = json.loads(text)
        if isinstance(value, dict): return value
    except json.JSONDecodeError as first:
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", text):
            try:
                value, _ = decoder.raw_decode(text[match.start():])
                if isinstance(value, dict): return value
            except json.JSONDecodeError: continue
        raise RuntimeError(f"Gemini returned invalid stock JSON: {first}") from first
    raise RuntimeError("Gemini returned non-object stock JSON.")

def _is_transient_gemini_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(x in text for x in ("503", "429", "500", "502", "504", "unavailable", "resource exhausted", "timeout", "temporarily"))

def _gemini(prompt: str, temperature: float = 0.15, parts: list[Any] | None = None) -> dict:
    from google import genai
    from google.genai import types
    key = _key()
    if not key: raise RuntimeError("Gemini unavailable: GEMINI_API_KEY not configured")
    client = genai.Client(api_key=key)
    contents: Any = [prompt] if not parts else [prompt, *parts]
    last: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = client.models.generate_content(model=GEMINI_MODEL, contents=contents, config=types.GenerateContentConfig(temperature=temperature, response_mime_type="application/json"))
            return _json(getattr(response, "text", ""))
        except Exception as exc:
            last = exc
            if _is_transient_gemini_error(exc) and attempt < 3:
                print(f"⚠️ {GEMINI_MODEL} temporary failure ({attempt}/3); retrying...")
                time.sleep(1.5 * attempt); continue
            break
    raise RuntimeError(f"Gemini stock call failed: {type(last).__name__}: {last}") from last

def _load_media_history() -> dict:
    try:
        with open(MEDIA_HISTORY_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict): return data
    except Exception: pass
    return {"assets": []}

def _save_media_history(data: dict) -> None:
    assets = data.get("assets") if isinstance(data, dict) else None
    if not isinstance(assets, list): assets = []
    tmp = MEDIA_HISTORY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump({"assets": assets}, handle, indent=2, ensure_ascii=False); handle.write("\n")
    os.replace(tmp, MEDIA_HISTORY_PATH)

def _asset_key(item: dict, provider: str, video: bool, url: str = "") -> str:
    raw_id = item.get("id") or item.get("video_id") or item.get("picture_id")
    if raw_id: return f"{provider.lower()}:{'video' if video else 'photo'}:{raw_id}"
    return f"{provider.lower()}:{'video' if video else 'photo'}:url:{url.strip()}"

def _record_media_asset(item: dict, provider: str, video: bool, url: str, scene: int, shot: int, query: str) -> None:
    key = _asset_key(item, provider, video, url); data = _load_media_history(); assets = data.setdefault("assets", [])
    if any(isinstance(x, dict) and x.get("asset_key") == key for x in assets): return
    assets.append({"asset_key": key, "provider": provider, "type": "video" if video else "photo", "source_url": url, "scene": scene, "shot": shot, "query": query, "recorded_at": int(time.time())}); _save_media_history(data)
    print(f"      📚 MEDIA HISTORY RECORDED: {key}")

def _anchor_terms(spoken: str, focus: str, action: str, must: list[str]) -> list[str]:
    text = " ".join([spoken, focus, action, *must]).lower()
    replacements = {"popcorn kernels": "popcorn kernel", "kernels": "kernel", "maize": "corn", "pericarp": "corn shell", "starch": "corn", "pericarp shell": "corn shell"}
    for old, new in replacements.items(): text = text.replace(old, new)
    stop = {"the", "and", "with", "from", "that", "this", "into", "under", "over", "when", "your", "their", "same", "visible", "showing", "shows", "because", "like", "really", "actually", "tiny", "little", "hard", "white", "yellow", "single", "physical", "object", "thing", "surface", "state", "scene", "shot", "camera"}
    ranked: list[str] = []
    for word in re.findall(r"[a-z][a-z-]{2,}", text):
        if word not in stop and word not in BAD_QUERY_WORDS and word not in ranked: ranked.append(word)
    return ranked[:10]

def _story_context(script: dict, scene_no: int) -> list[str]:
    person = clean(script.get("story_person") or "", 100); scenes = script.get("scene_plan") or []; narration = ""
    if isinstance(scenes, list) and len(scenes) >= scene_no and isinstance(scenes[scene_no - 1], dict): narration = clean(scenes[scene_no - 1].get("narration"), 600).lower()
    text = f"{person.lower()} {narration}"; terms: list[str] = []
    if person:
        lower_person = person.lower()
        if any(x in lower_person for x in ("wade", "jordan", "lebron", "kobe", "curry")): terms.append("basketball player")
        elif any(x in lower_person for x in ("bose", "einstein", "tesla", "curie", "newton", "ramanujan")): terms.append("scientist")
        else: terms.append("historical person")
    keyword_map = [(r"basketball|court|arena|game|team|nba", "basketball court"), (r"contract|signed|deal|salary|million", "sports contract"), (r"school|college|university", "college campus"), (r"coach|coached", "sports coach"), (r"injur|hurt|pain|recover", "athlete training"), (r"family|mother|father|parent", "family support"), (r"poor|broke|money|struggle|homeless", "struggling person"), (r"practice|train|workout", "athlete training"), (r"championship|trophy|win|victory", "sports trophy"), (r"draft", "basketball draft"), (r"manuscript|journal|diary|letter|paper|book|wrote|writing", "old manuscript"), (r"research|theory|equation|discovery|experiment|scientific", "researcher writing"), (r"laboratory|lab", "research laboratory"), (r"lecture|professor|student", "university lecture"), (r"war|soldier|battle|army", "historical soldier"), (r"invention|machine|workshop", "inventor workshop")]
    for pattern, phrase in keyword_map:
        if re.search(pattern, text, re.I) and phrase not in terms: terms.append(phrase)
    return (terms or ["historical person"])[:5]

def _normalize_ladder(data: dict, anchors: list[str]) -> list[dict]:
    ladder, seen = [], set(); anchor_words = set(re.findall(r"[a-z0-9]+", " ".join(anchors).lower()))
    for item in data.get("search_ladder", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict): continue
        query = clean(item.get("query"), 100).lower(); strategy = clean(item.get("strategy"), 40) or "alternate"; key = re.sub(r"[^a-z0-9 ]+", "", query).strip(); words = set(re.findall(r"[a-z0-9]+", query))
        if not query or key in seen or not 2 <= len(query.split()) <= 7 or words & BAD_QUERY_WORDS: continue
        if anchor_words and not (words & anchor_words): continue
        seen.add(key); ladder.append({"query": query, "strategy": strategy})
    return ladder

def direct(scene_no: int, shot_no: int, scene: dict, visual: dict, failed_queries=None, round_no=1, story_script: dict | None = None):
    spoken = clean(visual.get("spoken_line") or scene.get("narration"), 650); focus = clean(visual.get("visual_focus"), 350); action = clean(visual.get("visual_action"), 350)
    must = [clean(x, 180) for x in visual.get("must_show", []) if clean(x)]; avoid = [clean(x, 180) for x in visual.get("must_not_show", []) if clean(x)]; failed = [clean(x, 100) for x in (failed_queries or []) if clean(x)]
    is_story = isinstance(story_script, dict) and bool(story_script.get("story_person") or story_script.get("interactive_pillar") or story_script.get("story_visual_mode")); anchors = _story_context(story_script, scene_no) if is_story else _anchor_terms(spoken, focus, action, must); anchor_hint = ", ".join(anchors[:6])
    prompt = f'''You are the STOCK SEARCH DIRECTOR for a YouTube Short.
Real production media comes ONLY from Pexels and Pixabay.
SCENE {scene_no}, SHOT {shot_no}
SPOKEN BEAT: {spoken}
VISUAL FOCUS: {focus}
VISUAL ACTION: {action}
MUST SHOW: {json.dumps(must, ensure_ascii=False)}
MUST NOT SHOW: {json.dumps(avoid, ensure_ascii=False)}
FAILED QUERIES: {json.dumps(failed, ensure_ascii=False)}
CONCRETE ANCHOR TERMS: {anchor_hint}

Search for what a camera can realistically see. Use ordinary stock-search language,
2-7 words per query. Keep the primary physical subject stable. Do not use abstract
or scientific terminology. Never substitute a merely related object.
Return ONLY JSON with search_ladder, casting_brief, must_match and avoid.'''
    data = {}
    try: data = _gemini(prompt, 0.25)
    except Exception as exc: print(f"🛡️ Gemini stock director unavailable — local deterministic fallback: {type(exc).__name__}")
    ladder = _normalize_ladder(data, anchors) if data else []; existing = {x["query"] for x in ladder}
    if is_story:
        context = _story_context(story_script, scene_no); safe = []
        for base in context:
            for query in (base, f"{base} action", f"{base} close up", f"{base} working", f"{base} indoors"):
                query = clean(query.lower(), 80)
                if query in existing or not 1 <= len(query.split()) <= 7 or set(query.split()) & BAD_QUERY_WORDS: continue
                safe.append({"query": query, "strategy": "story-deterministic"}); existing.add(query)
        ladder = safe + ladder
    else:
        subject = " ".join(anchors[:2]); variants = [subject, f"{subject} close up", f"{subject} being used", f"{subject} action", f"{subject} outdoors", f"{subject} indoors", f"{subject} hands"] if subject else []
        for query in variants:
            query = clean(query.lower(), 80)
            if query and query not in existing and 1 <= len(query.split()) <= 7 and not (set(query.split()) & BAD_QUERY_WORDS): ladder.append({"query": query, "strategy": "deterministic"}); existing.add(query)
    if len(ladder) < 4:
        base = " ".join(anchors[:2]) or "person"
        for query in (base, f"{base} close up", f"{base} action", f"{base} outdoors", f"{base} hands"):
            query = clean(query.lower(), 80)
            if query and query not in existing and len(query.split()) <= 7: ladder.append({"query": query, "strategy": "local-fallback"}); existing.add(query)
    return {"search_ladder": ladder[:SEARCH_PROMPTS], "queries": [x["query"] for x in ladder[:SEARCH_PROMPTS]], "casting_brief": clean(data.get("casting_brief"), 600), "must_match": [clean(x, 180) for x in data.get("must_match", [])[:10]], "avoid": [clean(x, 180) for x in data.get("avoid", [])[:10]], "spoken_beat": spoken, "visual_focus": focus, "visual_action": action, "anchor_terms": anchors}

def build_plan(script):
    scenes = script.get("scene_plan")
    if not isinstance(scenes, list) or len(scenes) != 7: raise RuntimeError("Stock search requires exactly 7 scenes.")
    plan = []; is_story = isinstance(script, dict) and bool(script.get("story_person") or script.get("interactive_pillar") or script.get("story_visual_mode"))
    if is_story: print("📖 STORY VISUAL LOCK: preserving per-scene concrete video queries; photo assets disabled")
    else: print(f"🧠 STOCK SEARCH DIRECTOR — {GEMINI_MODEL} — practical search ladder")
    for si, scene in enumerate(scenes, 1):
        visuals = scene.get("visuals")
        if not isinstance(visuals, list) or len(visuals) != 2: raise RuntimeError(f"Scene {si} must contain exactly 2 visuals.")
        shots = []
        for vi, visual in enumerate(visuals, 1):
            if is_story:
                directed = direct(si, vi, scene, visual, story_script=script)
            else:
                directed = direct(si, vi, scene, visual)
            directed.update(scene=si, shot=vi); shots.append(directed)
            print(f"   🎯 Scene {si} Shot {vi}:")
            for idx, q in enumerate(directed["search_ladder"], 1): print(f"      {idx}. [{q['strategy']}] {q['query']}")
        plan.append(shots)
    return plan

def _provider_error(label: str, response: requests.Response) -> None:
    snippet = clean(response.text, 180).replace("\n", " "); print(f"      ⚠️ {label} HTTP {response.status_code}: {snippet or 'empty response'}")

def pexels(query, video):
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key: return []
    endpoint = "videos/search" if video else "search"; params = {"query": query, "per_page": CANDIDATES_PER_SEARCH}
    if video: params["size"] = "medium"
    try:
        response = requests.get(f"{PEXELS_API}/{endpoint}", headers={"Authorization": key, "User-Agent": USER_AGENT}, params=params, timeout=TIMEOUT)
        if response.status_code != 200: _provider_error(f"Pexels {'VIDEO' if video else 'PHOTO'}", response); return []
        return response.json().get("videos" if video else "photos", [])
    except Exception as exc:
        print(f"      ⚠️ Pexels {'VIDEO' if video else 'PHOTO'} request failed: {type(exc).__name__}: {exc}"); return []

def pixabay(query, video):
    key = os.getenv("PIXABAY_API_KEY", "").strip()
    if not key: return []
    endpoint = PIXABAY_VIDEO_API if video else PIXABAY_API; params = {"key": key, "q": query, "lang": "en", "per_page": CANDIDATES_PER_SEARCH, "safesearch": "true", "order": "popular"}
    if video: params["video_type"] = "film"
    else: params["image_type"] = "photo"
    try:
        response = requests.get(endpoint, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        if response.status_code != 200: _provider_error(f"Pixabay {'VIDEO' if video else 'PHOTO'}", response); return []
        return response.json().get("hits", [])
    except Exception as exc:
        print(f"      ⚠️ Pixabay {'VIDEO' if video else 'PHOTO'} request failed: {type(exc).__name__}: {exc}"); return []

def _preview_url(item, provider, video):
    if provider == "Pexels":
        if video: return item.get("image", "")
        src = item.get("src") or {}; return src.get("medium") or src.get("large") or src.get("portrait") or src.get("original") or ""
    if video:
        pid = str(item.get("picture_id") or ""); return f"https://i.vimeocdn.com/video/{pid}_640x360.jpg" if pid else ""
    return item.get("previewURL") or item.get("largeImageURL") or ""

def _url(item, provider, video):
    if provider == "Pexels":
        if video:
            choices = []
            for file in item.get("video_files") or []:
                url = file.get("link"); width = int(file.get("width") or 0); height = int(file.get("height") or 0)
                if url: choices.append((0 if height >= width else 1, abs(width * height - 720 * 1280), url))
            return sorted(choices)[0][2] if choices else ""
        src = item.get("src") or {}; return src.get("large2x") or src.get("large") or src.get("original") or src.get("portrait") or ""
    if video:
        for key in ("medium", "large", "small", "tiny"):
            url = (item.get("videos") or {}).get(key, {}).get("url")
            if url: return url
        return ""
    return item.get("largeImageURL") or item.get("fullHDURL") or item.get("imageURL") or ""

def _creator(item, provider): return (item.get("user") or {}).get("name", "") if provider == "Pexels" else item.get("user", "")
def _download_bytes(url: str) -> bytes:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT); response.raise_for_status(); return response.content

def _image_part(data: bytes):
    from google.genai import types
    image = Image.open(io.BytesIO(data)).convert("RGB"); image.thumbnail((768, 768)); output = io.BytesIO(); image.save(output, format="JPEG", quality=82, optimize=True)
    return types.Part.from_bytes(data=output.getvalue(), mime_type="image/jpeg")

def _verification_prompt(d, query, strategy, count):
    return f'''You are the strict visual-match judge for a YouTube Short.
You are looking at {count} actual stock video thumbnails attached after this prompt.
The thumbnails are previews of VIDEO assets that may be selected for production.
Judge only what is visibly present in the video preview.
SPOKEN BEAT: {d['spoken_beat']}
VISUAL FOCUS: {d['visual_focus']}
VISUAL ACTION: {d['visual_action']}
SEARCH QUERY: {query}
IDEAL SHOT: {d['casting_brief']}
MUST MATCH: {json.dumps(d.get('must_match', []), ensure_ascii=False)}
ANCHORS: {json.dumps(d.get('anchor_terms', []), ensure_ascii=False)}
Choose ONE video thumbnail or reject all. The primary subject must be visibly present.
Reject unrelated people, objects, symbols, diagrams, generic scenery, and metaphorical imagery.
Return ONLY JSON: {{"best_index": 0, "score": 0, "reason": "short reason"}}
Use 7+ only for genuinely relevant video imagery.'''

def verify_actual(d, items, provider, video, query, strategy):
    candidates, parts = [], []; historical = _historical_asset_keys()
    for item in items[:VERIFY_CANDIDATES]:
        preview = _preview_url(item, provider, video); url = _url(item, provider, video)
        if not preview or not url or _asset_key(item, provider, video, url) in historical: continue
        try: parts.append(_image_part(_download_bytes(preview))); candidates.append(item)
        except Exception: continue
    if not candidates: return None
    payload = _gemini(_verification_prompt(d, query, strategy, len(candidates)), 0.05, parts)
    try: index = int(payload.get("best_index", 0)) - 1; score = float(payload.get("score", 0) or 0)
    except Exception: return None
    if index < 0 or index >= len(candidates) or score < VERIFY_THRESHOLD: return None
    return candidates[index]

def _deterministic_score(d, item, provider, video, query):
    hay = " ".join([query, str(item.get("alt", "")), str(item.get("description", "")), str(item.get("tags", "")), str(item.get("url", ""))]).lower(); anchors = d.get("anchor_terms", []); score = min(sum(1 for term in anchors if term.lower() in hay) * 1.5, 5.0); score += min(sum(1 for word in re.findall(r"[a-z0-9]+", query.lower()) if len(word) > 2 and word in hay) * 0.5, 2.5)
    if _url(item, provider, video): score += 1.0
    return score

def _select_without_vision(d, items, provider, video, query):
    historical = _historical_asset_keys(); ranked = [item for item in items if _url(item, provider, video) and _asset_key(item, provider, video, _url(item, provider, video)) not in historical]; ranked.sort(key=lambda item: _deterministic_score(d, item, provider, video, query), reverse=True)
    if not ranked: return None
    return ranked[0] if _deterministic_score(d, ranked[0], provider, video, query) >= 2.5 else None

def _download_file(url: str, path: str) -> bool:
    temp_path = path + ".part"
    for attempt in range(1, 4):
        try:
            if os.path.exists(temp_path): os.remove(temp_path)
            with requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}, stream=True, timeout=(10, TIMEOUT)) as response:
                if response.status_code != 200: raise RuntimeError(f"HTTP {response.status_code}")
                with open(temp_path, "wb") as handle:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk: handle.write(chunk)
            if os.path.getsize(temp_path) > 0: os.replace(temp_path, path); return True
        except Exception as exc:
            print(f"      ⚠️ Asset download attempt {attempt}/3 failed: {type(exc).__name__}: {exc}")
            if attempt < 3: time.sleep(1.5 * attempt)
        finally:
            if os.path.exists(temp_path):
                try: os.remove(temp_path)
                except OSError: pass
    return False

def _download_with_candidate_recovery(d, initial, output_path, used_urls, video_only=False):
    failed_urls, queue, queued = set(), [initial], set()
    while queue:
        item, provider, video, query = queue.pop(0); url = _url(item, provider, video); key = _asset_key(item, provider, video, url) if url else ""
        if video_only and not video: continue
        if not url or url in used_urls or url in failed_urls or key in _historical_asset_keys(): continue
        queued.add(url)
        if _download_file(url, output_path): return item, provider, video, query, url
        failed_urls.add(url)
        for entry in d.get("search_ladder", []):
            query2 = entry.get("query", "")
            providers = (("Pexels", True), ("Pixabay", True)) if video_only else (("Pexels", True), ("Pixabay", True), ("Pexels", False), ("Pixabay", False))
            for provider2, video2 in providers:
                items = pexels(query2, video2) if provider2 == "Pexels" else pixabay(query2, video2)
                for candidate in sorted(items, key=lambda x: _deterministic_score(d, x, provider2, video2, query2), reverse=True):
                    if _deterministic_score(d, candidate, provider2, video2, query2) < 2.5: break
                    candidate_url = _url(candidate, provider2, video2); candidate_key = _asset_key(candidate, provider2, video2, candidate_url) if candidate_url else ""
                    if not candidate_url or candidate_url in used_urls or candidate_url in failed_urls or candidate_url in queued or candidate_key in _historical_asset_keys(): continue
                    queue.append((candidate, provider2, video2, query2)); queued.add(candidate_url)
    return None

def generate_media(script, output_dir, config, gim=None):
    os.makedirs(output_dir, exist_ok=True); plan = build_plan(script); used = set(); groups = []; vision_available = True; vision_failures = 0
    is_story = isinstance(script, dict) and bool(script.get("story_person") or script.get("interactive_pillar") or script.get("story_visual_mode"))
    video_only = is_story or os.environ.get("MINT_PUBLISH_VIDEO_ONLY", "0").strip().lower() in {"1", "true", "yes"}
    if video_only and not is_story:
        print("🛡️ PUBLISH VIDEO-ONLY LOCK: photo assets disabled; Pexels/Pixabay VIDEO endpoints only")
    print(f"📚 STOCK SEARCH {GEMINI_MODEL} | Pexels/Pixabay only | actual-thumbnail verification"); print(f"🚫 CROSS-SHORT MEDIA REUSE: BLOCKED | historical assets: {len(_historical_asset_keys())}")
    if is_story: print("🛡️ Story stock routing: VIDEO-ONLY | Pexels/Pixabay video endpoints; photo assets disabled")
    for scene_no, shots in enumerate(plan, 1):
        for shot_no, initial_directed in enumerate(shots, 1):
            # A stock search miss must trigger a NEW SEARCH, not a workflow failure.
            # Keep the topic/scene locked, but ask the director for materially
            # different, camera-visible queries while preserving the cross-Short
            # reuse guard and the video-only contract.
            directed = initial_directed
            selected = selected_provider = selected_video = selected_query = None
            attempted_queries = []
            # Give the recovery engine enough bounded rounds to traverse
            # distinct query families. Four rounds was too shallow when a topic
            # has scarce fresh VIDEO inventory in both providers.
            search_rounds = 6
            for round_no in range(1, search_rounds + 1):
                if round_no > 1:
                    print(f"   🔄 STOCK RECOVERY ROUND {round_no}/{search_rounds} — generating fresh queries for Scene {scene_no} Shot {shot_no}")
                    scene = (script.get("scene_plan") or [])[scene_no - 1]
                    visual = (scene.get("visuals") or [])[shot_no - 1]
                    directed = direct(scene_no, shot_no, scene, visual, failed_queries=attempted_queries, round_no=round_no, story_script=script if is_story else None)
                round_selected = None
                for entry in directed["search_ladder"]:
                    query = entry["query"]; strategy = entry["strategy"]
                    if query in attempted_queries:
                        continue
                    attempted_queries.append(query)
                    print(f"   🔎 Scene {scene_no} Shot {shot_no}: [{strategy}] {query}")
                    providers = (("Pexels", True), ("Pixabay", True)) if video_only else (("Pexels", True), ("Pixabay", True), ("Pexels", False), ("Pixabay", False))
                    for provider, video in providers:
                        items = pexels(query, video) if provider == "Pexels" else pixabay(query, video)
                        if not items:
                            print(f"      ↪️ {provider} {'VIDEO' if video else 'PHOTO'}: no assets")
                            continue
                        item = None
                        if vision_available:
                            try:
                                item = verify_actual(directed, items, provider, video, query, strategy)
                                if item: print("      👁️ Vision verified actual video thumbnail")
                            except Exception as exc:
                                vision_failures += 1
                                print(f"      ⚠️ Vision verification unavailable: {type(exc).__name__}: {exc}")
                                if vision_failures >= 3:
                                    vision_available = False
                                    print("      🛡️ Vision circuit breaker OPEN — deterministic fallback enabled")
                        if item is None:
                            item = _select_without_vision(directed, items, provider, video, query)
                        if item and not vision_available:
                            print("      🧮 Selected using conservative metadata fallback")
                        if item:
                            url = _url(item, provider, video)
                            key = _asset_key(item, provider, video, url) if url else ""
                            if url and url not in used and key not in _historical_asset_keys():
                                round_selected = (item, provider, video, query, url)
                                break
                    if round_selected:
                        break
                if round_selected:
                    selected, selected_provider, selected_video, selected_query, selected_url = round_selected
                    # Download is handled below through the same candidate-recovery path.
                    selected = selected
                    break
            if not selected:
                raise RuntimeError(
                    f"No new visually relevant stock {'video' if video_only else 'stock'} asset found "
                    f"for Scene {scene_no} Shot {shot_no} after {search_rounds} search rounds. "
                    f"Topic lock and cross-Short reuse guard were preserved."
                )
            if video_only and not selected_video:
                raise RuntimeError(f"Story video-only contract violated: Scene {scene_no} Shot {shot_no} selected a non-video asset.")
            extension = "mp4" if selected_video else "jpg"
            path = os.path.join(output_dir, f"scene_{scene_no}_shot_{shot_no}.{extension}")
            recovered = _download_with_candidate_recovery(
                directed, (selected, selected_provider, selected_video, selected_query),
                path, used, video_only=video_only
            )
            if not recovered: raise RuntimeError(f"No downloadable visually relevant NEW stock {'video' if is_story else 'stock'} asset found for Scene {scene_no} Shot {shot_no} after candidate recovery.")
            selected, selected_provider, selected_video, selected_query, url = recovered
            if is_story and not selected_video: raise RuntimeError(f"Story video-only recovery violated: Scene {scene_no} Shot {shot_no} recovered a non-video asset.")
            used.add(url); _record_media_asset(selected, selected_provider, selected_video, url, scene_no, shot_no, selected_query)
            groups.append({"scene": scene_no, "shot": shot_no, "path": path, "type": "video" if selected_video else "photo", "provider": selected_provider, "creator": _creator(selected, selected_provider), "query": selected_query, "asset_key": _asset_key(selected, selected_provider, selected_video, url), "score": 8.0})
            print(f"      ✅ SELECTED NEW {selected_provider} {'VIDEO' if selected_video else 'PHOTO'}: {selected_query}")
    return groups
