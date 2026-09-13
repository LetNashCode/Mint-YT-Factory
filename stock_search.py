"""Production stock-media director for Mint-YT-Factory.

Goals:
- Keep stock visuals tightly tied to the spoken beat.
- Search Pexels/Pixabay using practical photographer language.
- Verify the ACTUAL candidate thumbnails with Gemini Vision when available.
- Never fail an entire production merely because Gemini verification is temporarily unavailable.
- Never silently substitute an unrelated object.
- Never reuse a previously selected production asset across Publish Shorts.

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
USER_AGENT = "Mint-YT-Factory/StockSearch/15.2"
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
    return any(token in text for token in ("503", "unavailable", "429", "resource exhausted", "500", "502", "504", "high demand", "temporarily", "deadline exceeded", "timeout"))


def _gemini(prompt: str, temperature: float = 0.15, parts: list[Any] | None = None) -> dict:
    from google import genai
    from google.genai import types
    key = _key()
    if not key: raise RuntimeError("Gemini unavailable: GEMINI_API_KEY not configured")
    client = genai.Client(api_key=key); contents: Any = [prompt] if not parts else [prompt, *parts]; last: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = client.models.generate_content(model=GEMINI_MODEL, contents=contents, config=types.GenerateContentConfig(temperature=temperature, response_mime_type="application/json"))
            return _json(getattr(response, "text", ""))
        except Exception as exc:
            last = exc
            if _is_transient_gemini_error(exc) and attempt < 3:
                print(f"⚠️ {GEMINI_MODEL} temporary failure ({attempt}/3); retrying..."); time.sleep(1.5 * attempt); continue
            break
    raise RuntimeError(f"Gemini stock call failed: {type(last).__name__}: {last}") from last


def _load_media_history() -> dict:
    try:
        data = json.loads(open(MEDIA_HISTORY_PATH, encoding="utf-8").read())
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


def _historical_asset_keys() -> set[str]:
    return {str(item["asset_key"]) for item in _load_media_history().get("assets", []) if isinstance(item, dict) and item.get("asset_key")}


def _record_media_asset(item: dict, provider: str, video: bool, url: str, scene: int, shot: int, query: str) -> None:
    key = _asset_key(item, provider, video, url); data = _load_media_history(); assets = data.setdefault("assets", [])
    if any(isinstance(x, dict) and x.get("asset_key") == key for x in assets): return
    assets.append({"asset_key": key, "provider": provider, "type": "video" if video else "photo", "source_url": url, "scene": scene, "shot": shot, "query": query, "recorded_at": int(time.time())}); _save_media_history(data)
    print(f"      📚 MEDIA HISTORY RECORDED: {key}")


def _anchor_terms(spoken: str, focus: str, action: str, must: list[str]) -> list[str]:
    text = " ".join([spoken, focus, action, *must]).lower()
    replacements = {"popcorn kernels": "popcorn kernel", "kernels": "kernel", "maize": "corn", "pericarp": "corn shell", "starch": "corn", "pericarp shell": "corn shell"}
    for old, new in replacements.items(): text = text.replace(old, new)
    stop = {"the","and","with","from","that","this","into","under","over","when","your","their","same","visible","showing","shows","because","like","really","actually","tiny","little","hard","white","yellow","single","physical","object","thing","surface","state"}
    words = re.findall(r"[a-z][a-z-]{2,}", text); ranked: list[str] = []
    for word in words:
        if word in stop or word in BAD_QUERY_WORDS: continue
        if word not in ranked: ranked.append(word)
    return ranked[:10]


def _story_context(script: dict, scene_no: int) -> list[str]:
    """Build safe stock nouns for Story Shorts without trusting malformed visual metadata."""
    person = clean(script.get("story_person") or "", 100)
    text = clean((script.get("scene_plan") or [])[scene_no-1].get("narration") if isinstance(script.get("scene_plan"), list) and len(script.get("scene_plan")) >= scene_no else "", 500).lower()
    terms: list[str] = []
    if person: terms.append("basketball player" if any(x in person.lower() for x in ("wade", "jordan", "lebron", "kobe", "curry")) else "person")
    keyword_map = [
        (r"court|arena|game|team|basketball", "basketball court"),
        (r"contract|signed|deal|salary|million", "sports contract"),
        (r"school|college|university", "college basketball"),
        (r"coach|coached|coach's", "basketball coach"),
        (r"injur|hurt|pain|recover", "athlete training"),
        (r"family|mother|father|parent", "family support"),
        (r"poor|broke|money|struggle|homeless", "struggling athlete"),
        (r"practice|train|workout", "basketball training"),
        (r"championship|trophy|win|victory", "basketball trophy"),
        (r"draft|nba", "basketball draft"),
    ]
    for pattern, phrase in keyword_map:
        if re.search(pattern, text, re.I) and phrase not in terms: terms.append(phrase)
    if not terms: terms.append("basketball player")
    return terms[:4]


def direct(scene_no: int, shot_no: int, scene: dict, visual: dict, failed_queries=None, round_no=1, story_script: dict | None = None):
    spoken = clean(visual.get("spoken_line") or scene.get("narration"), 650)
    focus = clean(visual.get("visual_focus"), 350); action = clean(visual.get("visual_action"), 350)
    must = [clean(x, 180) for x in visual.get("must_show", []) if clean(x)]; avoid = [clean(x, 180) for x in visual.get("must_not_show", []) if clean(x)]
    failed = [clean(x, 100) for x in (failed_queries or []) if clean(x)]
    is_story = isinstance(story_script, dict) and bool(story_script.get("story_person") or story_script.get("interactive_pillar") or story_script.get("story_visual_mode"))
    anchors = _story_context(story_script, scene_no) if is_story else _anchor_terms(spoken, focus, action, must)
    subject_text = " ".join([focus, action, *must]).lower()
    subject_words = [w for w in re.findall(r"[a-z][a-z-]{2,}", subject_text) if w not in BAD_QUERY_WORDS and w not in {"show","showing","visible","camera","shot","scene","with","from","onto","into","table","screen"}]
    if not is_story and subject_words:
        preferred=[]
        for w in subject_words+anchors:
            if w not in preferred: preferred.append(w)
        anchors=preferred[:10]
    anchor_hint=", ".join(anchors[:6])
    prompt=f'''You are the STOCK SEARCH DIRECTOR for a YouTube Short. Real production media comes ONLY from Pexels and Pixabay.
SCENE {scene_no}, SHOT {shot_no}
SPOKEN BEAT: {spoken}
VISUAL FOCUS: {focus}
VISUAL ACTION: {action}
MUST SHOW: {json.dumps(must, ensure_ascii=False)}
MUST NOT SHOW: {json.dumps(avoid, ensure_ascii=False)}
FAILED QUERIES: {json.dumps(failed, ensure_ascii=False)}
CONCRETE ANCHOR TERMS: {anchor_hint}
Search for what a camera can realistically see. Use ordinary stock-search language, 2-7 words. Prefer concrete nouns and visible actions. Never use abstract/scientific terms. Never replace the physical subject with a merely related object. Return ONLY JSON with search_ladder, casting_brief, must_match and avoid.'''
    data={}
    try: data=_gemini(prompt,0.25)
    except Exception as exc: print(f"🛡️ Gemini stock director unavailable — local deterministic fallback: {type(exc).__name__}")
    ladder=_normalize_ladder(data, anchors) if data else []
    if is_story:
        # Gemini is advisory for Story Shorts. Never let malformed visual metadata
        # create queries such as "pile athletic" or irrelevant state-change verbs.
        context=_story_context(story_script,scene_no)
        existing={x["query"] for x in ladder}; safe=[]
        for base in context:
            for q in (base, f"{base} action", f"{base} close up", f"{base} training", f"{base} indoors"):
                q=clean(q.lower(),80)
                if q not in existing and 1 <= len(q.split()) <= 7 and not (set(q.split()) & BAD_QUERY_WORDS):
                    safe.append({"query":q,"strategy":"story-deterministic"}); existing.add(q)
        # Put safe Story queries first so a malformed Gemini ladder can never win.
        ladder=safe+ladder
    elif anchors:
        subject=" ".join(anchors[:2]); existing={x["query"] for x in ladder}
        practical=[subject,f"{subject} on table",f"{subject} being heated",f"{subject} breaking open",f"{subject} being cut",f"{subject} close up",f"{subject} in kitchen",f"{subject} changing state"] if subject else []
        for q in practical:
            q=clean(q.lower(),80)
            if q not in existing and 2 <= len(q.split()) <= 7 and not (set(q.split()) & BAD_QUERY_WORDS): ladder.append({"query":q,"strategy":"deterministic"}); existing.add(q)
    if len(ladder)<4:
        base=" ".join(anchors[:2]) or "person"
        existing={x["query"] for x in ladder}
        for q in [base,f"{base} close up",f"{base} outdoors",f"{base} action",f"{base} hands"]:
            q=clean(q.lower(),80)
            if q and q not in existing and 1 <= len(q.split()) <= 7: ladder.append({"query":q,"strategy":"local-fallback"}); existing.add(q)
    return {"search_ladder":ladder[:SEARCH_PROMPTS],"queries":[x["query"] for x in ladder[:SEARCH_PROMPTS]],"casting_brief":clean(data.get("casting_brief"),600),"must_match":[clean(x,180) for x in data.get("must_match",[])[:10]],"avoid":[clean(x,180) for x in data.get("avoid",[])[:10]],"spoken_beat":spoken,"visual_focus":focus,"visual_action":action,"anchor_terms":anchors}


def _normalize_ladder(data: dict, anchors: list[str]) -> list[dict]:
    ladder=[]; seen=set(); anchor_words=set(re.findall(r"[a-z0-9]+"," ".join(anchors).lower()))
    for item in data.get("search_ladder",[]) if isinstance(data,dict) else []:
        if not isinstance(item,dict): continue
        query=clean(item.get("query"),100).lower(); strategy=clean(item.get("strategy"),40) or "alternate"; key=re.sub(r"[^a-z0-9 ]+","",query).strip(); words=set(re.findall(r"[a-z0-9]+",query))
        if not query or key in seen or not 2 <= len(query.split()) <= 7: continue
        if words & BAD_QUERY_WORDS: continue
        if anchor_words and not (words & anchor_words): continue
        seen.add(key); ladder.append({"query":query,"strategy":strategy})
    return ladder

# The provider/search/verification implementation below is unchanged from the
# established production pipeline.

def pexels(query, video):
    key=os.getenv("PEXELS_API_KEY","").strip()
    if not key:return []
    endpoint="videos/search" if video else "search"; params={"query":query,"per_page":CANDIDATES_PER_SEARCH}
    if video:params["size"]="medium"
    try:
        r=requests.get(f"{PEXELS_API}/{endpoint}",headers={"Authorization":key,"User-Agent":USER_AGENT},params=params,timeout=TIMEOUT); r.raise_for_status(); return r.json().get("videos" if video else "photos",[])
    except Exception as exc: print(f"      ⚠️ Pexels {('VIDEO' if video else 'PHOTO')} request failed: {type(exc).__name__}"); return []

def pixabay(query, video):
    key=os.getenv("PIXABAY_API_KEY","").strip()
    if not key:return []
    endpoint=PIXABAY_VIDEO_API if video else PIXABAY_API; params={"key":key,"q":query,"per_page":CANDIDATES_PER_SEARCH,"safesearch":"true"}
    if video: params["video_type"]="film"
    try:
        r=requests.get(endpoint,headers={"User-Agent":USER_AGENT},params=params,timeout=TIMEOUT); r.raise_for_status(); data=r.json(); return data.get("hits",[])
    except Exception as exc: print(f"      ⚠️ Pixabay {('VIDEO' if video else 'PHOTO')} request failed: {type(exc).__name__}"); return []
