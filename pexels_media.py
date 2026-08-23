"""Relevance-first story media selection using Pexels only.

Pipeline:
1) Build literal, object/action-focused Pexels queries.
2) Fetch multiple Pexels candidates.
3) Gemini visually ranks candidate thumbnails against the CURRENT spoken beat.
4) Download the winner only when it is a strong literal match.
5) If Pexels cannot provide a verified match, fail the shot instead of
   silently switching to an AI-generated image provider.
"""
from __future__ import annotations
import json, os, re, time
from pathlib import Path
from typing import Any
import requests

PEXELS_API = "https://api.pexels.com/v1"
TIMEOUT = 45
USER_AGENT = "Mint-YT-Factory/PexelsMedia/3.1"
STOP = {"this","that","with","from","your","into","about","just","they","them","their","very","have","will","what","when","where","which","because","while","then","than","like","gets","make","makes","made","thing","things","exact","physical","show","showing","scene","shot","visible","action","state","realistic","cinematic","photo","photograph","video","image","someone","something","person","people","close","camera","natural","looking","moment","also","really","tiny","microscopic","single","entire","every","time","next","remember","designed","suicide","hates","defying","entirely","actually","basically","literally"}
ACTIONS = {"cling","clinging","stick","sticking","pull","pulling","grab","grabbing","hold","holding","touch","touching","rub","rubbing","fall","falling","drop","dropping","jump","jumping","run","running","pour","pouring","spill","spilling","open","opening","close","closing","break","breaking","tear","tearing","bend","bending","shake","shaking","twist","twisting","stretch","stretching","slide","sliding","move","moving","tumble","tumbling","wash","washing","dry","drying","iron","ironing","sew","sewing","wear","wearing","remove","removing","press","pressing","boil","boiling","freeze","freezing","melt","melting","fog","fogging","steam","steaming","squeeze","squeezing","crush","crushing","bounce","bouncing","spin","spinning","plug","plugging","drip","dripping","float","floating","burst","bursting","snap","snapping","crack","cracking","lift","lifting","collapse","collapsing"}

def clean(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()[:limit]

def tokens(value: Any) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", clean(value, 1600).lower()) if len(w) >= 4 and w not in STOP}

def action_tokens(value: Any) -> set[str]:
    return tokens(value) & ACTIONS

def _visual_text(scene: dict, visual: dict) -> str:
    return " ".join(filter(None, [clean(visual.get("visual_focus"),180), clean(visual.get("visual_action"),180), clean(visual.get("must_show"),260), clean(visual.get("spoken_line") or scene.get("narration"),260)]))

def queries(scene: dict, visual: dict) -> list[str]:
    focus = clean(visual.get("visual_focus"),120); action = clean(visual.get("visual_action"),140); must = clean(visual.get("must_show"),180); spoken = clean(visual.get("spoken_line") or scene.get("narration"),220)
    result = []
    for value in (f"{focus} {action}", must, f"{focus} {must}", spoken):
        words = []
        for word in re.findall(r"[A-Za-z0-9'-]+", value):
            word = word.lower().strip("'-")
            if len(word) >= 4 and word not in STOP and word not in words: words.append(word)
        query = " ".join(words[:7])
        if query and query not in result: result.append(query)
    return result[:4] or ["everyday object close up"]

def headers():
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    return {"Authorization": key, "User-Agent": USER_AGENT} if key else None

def search(endpoint: str, query: str, params: dict | None = None) -> list[dict]:
    hdrs = headers()
    if not hdrs: return []
    request_params = {"query": query, "per_page": 20}; request_params.update(params or {})
    try:
        response = requests.get(f"{PEXELS_API}/{endpoint}", headers=hdrs, params=request_params, timeout=TIMEOUT)
        if response.status_code != 200:
            print(f"⚠️ Pexels {endpoint}: HTTP {response.status_code}"); return []
        payload = response.json()
        return payload.get("videos", []) if endpoint == "videos/search" else payload.get("photos", [])
    except Exception as exc:
        print(f"⚠️ Pexels search failed: {exc}"); return []

def _candidate_preview(item: dict, kind: str):
    if kind == "video":
        pictures = item.get("video_pictures") or []
        if pictures and isinstance(pictures[0], dict): return pictures[0].get("picture")
        return item.get("image")
    src = item.get("src") or {}
    return src.get("portrait") or src.get("large2x") or src.get("large") or src.get("medium") or src.get("original")

def _heuristic_score(item: dict, required: set[str], actions: set[str], kind: str) -> float:
    if kind == "video": text = " ".join([clean(item.get("url"),400), clean(item.get("image"),300), clean(item.get("video_pictures"),600)])
    else:
        src = item.get("src") or {}; text = " ".join([clean(item.get("alt"),500), clean(item.get("url"),300), clean(src.get("portrait"),200)])
    result_tokens = tokens(text); score = len(required & result_tokens) * 2.0
    if kind == "video":
        duration = float(item.get("duration") or 0); width = int(item.get("width") or 0); height = int(item.get("height") or 0)
        if 2 <= duration <= 20: score += 2
        if height > width: score += 2
        elif width and height: score += 0.5
        score += len(actions & result_tokens) * 2.5
    else:
        width = int(item.get("width") or 0); height = int(item.get("height") or 0)
        if height >= width and height: score += 2
    return score

def _dedupe(results: list[dict], kind: str, excluded_pages: set[str]):
    seen = set(); unique = []
    for item in results:
        page = str(item.get("url") or "")
        if page in excluded_pages or page in seen: continue
        seen.add(page)
        if _candidate_preview(item, kind): unique.append(item)
    return unique

def _download_bytes(url: str):
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30); response.raise_for_status()
        data = response.content; return data if len(data) > 1000 else None
    except Exception: return None

def _parse_json(text: str):
    text = str(text or "").strip(); text = re.sub(r"^```(?:json)?", "", text, flags=re.I).strip(); text = re.sub(r"```$", "", text).strip()
    try: return json.loads(text)
    except Exception:
        match = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
        if match:
            try: return json.loads(match.group(0))
            except Exception: pass
    return None

def _gemini_rank_candidates(scene: dict, visual: dict, candidates: list[dict], kind: str) -> list[dict]:
    try:
        from google import genai
        from google.genai import types
    except Exception: return []
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key: return []
    parts = []; usable = []
    for index, item in enumerate(candidates[:6], 1):
        preview_url = _candidate_preview(item, kind)
        data = _download_bytes(preview_url) if preview_url else None
        if not data: continue
        parts.append(types.Part.from_bytes(data=data, mime_type="image/jpeg"))
        parts.append(types.Part.from_text(text=f"CANDIDATE {index} — {kind.upper()}\nPexels page: {item.get('url','')}"))
        usable.append((index, item))
    if not usable: return []
    beat = _visual_text(scene, visual)
    instruction = f'''You are the strict visual casting director for a YouTube Short.

CURRENT SPOKEN BEAT:
{clean(beat,700)}

The stock asset must literally illustrate that beat.
Prioritize: exact main object, exact physical action/state, correct context, useful vertical composition.
Reject keyword-only matches, generic objects, unrelated people/scenery, symbolic or metaphorical science imagery, abstract graphics, wrong objects, wrong action, or wrong physical state.
Do NOT reward a candidate because its Pexels title or URL sounds relevant. Judge the supplied image itself.

Return ONLY JSON:
{{"ranking":[{{"candidate":1,"score":0,"pass":false,"reason":"short reason"}}]}}
A candidate is PASS only at score 8 or higher.'''
    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(model="gemini-flash-lite-latest", contents=parts + [instruction], config=types.GenerateContentConfig(temperature=0))
        result = _parse_json(getattr(response, "text", "") or "")
        ranking = result.get("ranking", []) if isinstance(result, dict) else []
        by_id = {int(row["candidate"]): row for row in ranking if isinstance(row, dict) and str(row.get("candidate", "")).isdigit()}
        ordered = []
        for index, item in usable:
            row = by_id.get(index, {}); score = int(row.get("score",0) or 0); passed = bool(row.get("pass")) and score >= 8
            item = dict(item); item["_gemini_score"] = score; item["_gemini_pass"] = passed; item["_gemini_reason"] = clean(row.get("reason"),180); ordered.append(item)
            print(f"   👁️ Pexels {kind} candidate {index}: {'PASS' if passed else 'FAIL'} score={score} — {item['_gemini_reason']}")
        return sorted(ordered, key=lambda x: (bool(x.get("_gemini_pass")), int(x.get("_gemini_score",0))), reverse=True)
    except Exception as exc:
        print(f"⚠️ Pexels visual ranking unavailable: {exc}"); return []

def _video_download_url(item: dict):
    choices = []
    for video_file in item.get("video_files") or []:
        link = video_file.get("link"); width = int(video_file.get("width") or 0); height = int(video_file.get("height") or 0); quality = str(video_file.get("quality") or "").lower()
        if not link or not width or not height: continue
        choices.append((1 if height > width else 0, 1 if quality == "hd" else 0, width * height, link))
    return max(choices)[3] if choices else None

def pick_video(results, required, actions, scene, visual, excluded_pages=None):
    excluded_pages = excluded_pages or set(); pool = _dedupe(results,"video",excluded_pages); pool.sort(key=lambda x:_heuristic_score(x,required,actions,"video"), reverse=True); pool = pool[:8]
    ranked = _gemini_rank_candidates(scene,visual,pool,"video")
    if ranked:
        for item in ranked:
            if item.get("_gemini_pass"):
                link = _video_download_url(item)
                if link: return {"video":link,"page":item.get("url",""),"photographer":(item.get("user") or {}).get("name",""),"score":int(item.get("_gemini_score",0)),"qc_reason":item.get("_gemini_reason","")}
        return None
    return None

def pick_photo(results, required, actions, scene, visual, excluded_pages=None):
    excluded_pages = excluded_pages or set(); pool = _dedupe(results,"photo",excluded_pages); pool.sort(key=lambda x:_heuristic_score(x,required,actions,"photo"), reverse=True); pool = pool[:8]
    ranked = _gemini_rank_candidates(scene,visual,pool,"photo")
    if ranked:
        for item in ranked:
            if item.get("_gemini_pass"):
                src = item.get("src") or {}; link = src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
                if link: return {"photo":link,"page":item.get("url",""),"photographer":item.get("photographer","") or "","score":int(item.get("_gemini_score",0)),"qc_reason":item.get("_gemini_reason","")}
        return None
    return None

def download(url: str, path: str) -> bool:
    try:
        response = requests.get(url, headers={"User-Agent":USER_AGENT}, timeout=120, stream=True); response.raise_for_status(); Path(path).parent.mkdir(parents=True,exist_ok=True)
        with open(path,"wb") as handle:
            for chunk in response.iter_content(1024*1024):
                if chunk: handle.write(chunk)
        return os.path.getsize(path) > 10000
    except Exception as exc:
        print(f"⚠️ Pexels download failed: {exc}")
        try: os.remove(path)
        except OSError: pass
        return False

def credit(path: str, kind: str, page: str, photographer: str):
    with open(path,"w",encoding="utf-8") as handle: json.dump({"type":kind,"page":page,"photographer":photographer,"provider":"Pexels"},handle,ensure_ascii=False,indent=2)

def _select(scene, visual, excluded_pages=None):
    if not headers(): return None
    excluded_pages = excluded_pages or set(); required = tokens(_visual_text(scene,visual)); actions = action_tokens(f"{clean(visual.get('visual_action'))} {clean(visual.get('spoken_line') or scene.get('narration'))}")
    for query in queries(scene,visual):
        selected = pick_video(search("videos/search",query,{"orientation":"portrait","size":"medium"}),required,actions,scene,visual,excluded_pages)
        if selected: selected["kind"]="video"; selected["query"]=query; return selected
    for query in queries(scene,visual):
        selected = pick_photo(search("search",query,{"orientation":"portrait","size":"large"}),required,actions,scene,visual,excluded_pages)
        if selected: selected["kind"]="photo"; selected["query"]=query; return selected
    return None

def generate_media(script, output_dir, config, gim):
    scenes = script.get("scene_plan") or []; cfg = config.get("image",{}) if isinstance(config,dict) else {}; os.makedirs(output_dir,exist_ok=True); available = bool(headers()); used=False; groups=[]; credits=[]; used_pages=set()
    print("="*80); print("📚 RELEVANCE-FIRST STORY MEDIA v3.1 — PEXELS ONLY"); print(f"Pexels API: {'AVAILABLE' if available else 'NOT CONFIGURED'}"); print("Rule: Gemini must visually verify Pexels before selection"); print("Provider: Pexels verified VIDEO → Pexels verified PHOTO"); print("Pollinations/FLUX: DISABLED"); print("No-provider-fallback: a missing verified Pexels match fails the shot"); print("="*80)
    for si,scene in enumerate(scenes,1):
        paths=[]; visuals=scene.get("visuals") or []
        for vi,visual in enumerate(visuals[:2],1):
            spoken=clean(visual.get("spoken_line") or scene.get("narration"),280); stem=f"scene_{si:02d}_shot_{vi:02d}"; print(f"🎬 Scene {si}/{len(scenes)} Shot {vi}/2 | {spoken}"); selected=_select(scene,visual,used_pages) if available else None
            if selected:
                extension = ".mp4" if selected["kind"] == "video" else ".jpg"; path=os.path.join(output_dir,stem+extension); source=selected["video"] if selected["kind"] == "video" else selected["photo"]
                if download(source,path):
                    credit(os.path.join(output_dir,stem+".credit.json"),selected["kind"],selected["page"],selected["photographer"]); used_pages.add(selected["page"]); credits.append({**selected,"scene":si,"shot":vi}); paths.append(path); used=True; label="VIDEO" if selected["kind"]=="video" else "PHOTO"; print(f"🎞️ Pexels {label} VERIFIED + selected | Gemini score={selected['score']}/10 | query={selected['query']}"); print(f"   └─ {selected.get('qc_reason','')}"); continue
            raise RuntimeError(f"Scene {si} Shot {vi}: Pexels could not provide a Gemini-verified literal match for the spoken beat. Pollinations/FLUX is disabled. Revise the visual query or narration instead of using an unrelated/generated fallback.")
        if len(paths)!=2: raise RuntimeError(f"Scene {si} did not produce exactly 2 Pexels media assets.")
        groups.append(paths)
    script["_pexels_used"]=used; script["_pexels_credits"]=credits; script["_media_provider_order"]=["pexels_verified_video","pexels_verified_photo"]
    with open(os.path.join(output_dir,"media_manifest.json"),"w",encoding="utf-8") as handle: json.dump({"provider_order":["pexels_verified_video","pexels_verified_photo"],"pexels_used":used,"credits":credits},handle,ensure_ascii=False,indent=2)
    print(f"✅ Media complete: {sum(map(len,groups))} assets | Pexels verified used: {used}"); return groups