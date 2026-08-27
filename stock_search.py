"""Stock-only visual search pipeline for Mint-YT-Factory.

Gemini is used only for search-language direction and visual verification.
Production media comes from Pexels/Pixabay.
"""
from __future__ import annotations
import json, os, re, time
from typing import Any
import requests

PEXELS_API="https://api.pexels.com/v1"
PIXABAY_API="https://pixabay.com/api"
PIXABAY_VIDEO_API="https://pixabay.com/api/videos"
GEMINI_MODEL="gemini-flash-lite-latest"
VERIFY_THRESHOLD=7.5
SEARCH_PROMPTS=8
CANDIDATES_PER_SEARCH=6
TIMEOUT=35
USER_AGENT="Mint-YT-Factory/StockSearch/14.0"

def clean(v:Any,n=700):
    return " ".join(str(v or "").replace("\n"," ").split()).strip()[:n]

def _key():
    key=os.getenv("GEMINI_API_KEY","").strip()
    if not key: raise RuntimeError("GEMINI_API_KEY is required for stock visual direction.")
    return key

def _json(text):
    """Parse Gemini JSON robustly; never rely on greedy {..} regex."""
    text=str(text or "").strip()
    text=re.sub(r"^```(?:json)?\s*","",text,flags=re.I)
    text=re.sub(r"\s*```$","",text).strip()
    try: return json.loads(text)
    except json.JSONDecodeError as first:
        decoder=json.JSONDecoder()
        # Try every opening brace and let JSONDecoder determine the exact end.
        # This handles trailing prose and avoids selecting a malformed greedy
        # object when Gemini emits more than one JSON-looking fragment.
        for m in re.finditer(r"\{",text):
            try:
                obj,end=decoder.raw_decode(text[m.start():])
                if isinstance(obj,dict): return obj
            except json.JSONDecodeError:
                continue
        raise RuntimeError(f"Gemini returned invalid stock-search JSON: {first}") from first

def _is_transient_gemini_error(exc:Exception)->bool:
    text=str(exc).lower()
    return any(x in text for x in ("503","unavailable","429","resource exhausted","500","502","504","high demand","temporarily"))

def _gemini(prompt:str,temperature:float):
    from google import genai
    from google.genai import types
    client=genai.Client(api_key=_key())
    last=None
    for attempt in range(1,4):
        try:
            response=client.models.generate_content(
                model=GEMINI_MODEL, contents=[prompt],
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    response_mime_type="application/json",
                ),
            )
            return _json(getattr(response,"text",""))
        except Exception as exc:
            last=exc
            if _is_transient_gemini_error(exc) and attempt<3:
                print(f"⚠️ {GEMINI_MODEL} temporary failure ({attempt}/3); retrying...")
                time.sleep(2.0*attempt)
                continue
            break
    raise RuntimeError(f"Gemini visual/search call failed using {GEMINI_MODEL}: {type(last).__name__}: {last}") from last

def _normalize_ladder(data):
    ladder=[]; seen=set()
    for item in data.get("search_ladder",[]) if isinstance(data,dict) else []:
        if not isinstance(item,dict): continue
        query=clean(item.get("query"),100)
        strategy=clean(item.get("strategy"),40) or "alternate"
        key=re.sub(r"[^a-z0-9 ]+","",query.lower()).strip()
        if not query or key in seen or not 2<=len(query.split())<=7: continue
        seen.add(key); ladder.append({"query":query,"strategy":strategy})
    return ladder

def direct(scene_no:int,shot_no:int,scene:dict,visual:dict,failed_queries=None,round_no=1):
    spoken=clean(visual.get("spoken_line") or scene.get("narration"),650)
    focus=clean(visual.get("visual_focus"),350)
    action=clean(visual.get("visual_action"),350)
    must=[clean(x,180) for x in visual.get("must_show",[]) if clean(x)]
    avoid=[clean(x,180) for x in visual.get("must_not_show",[]) if clean(x)]
    failed=[clean(x,100) for x in (failed_queries or []) if clean(x)]
    prompt=f'''You are the STOCK SEARCH DIRECTOR for a funny, curiosity-driven YouTube Short.
Real production media comes ONLY from Pexels and Pixabay.

SCENE {scene_no}, SHOT {shot_no}
SPOKEN BEAT: {spoken}
VISUAL FOCUS: {focus}
VISUAL ACTION: {action}
MUST SHOW: {json.dumps(must,ensure_ascii=False)}
MUST NOT SHOW: {json.dumps(avoid,ensure_ascii=False)}
FAILED QUERIES: {json.dumps(failed,ensure_ascii=False)}

Create exactly 8 stock-library search queries. The SAME concrete subject must
remain visible in every query. Use common words photographers actually use,
not scientific jargon. Queries must describe things an ordinary viewer can see.
If the mechanism is invisible, search for a visible consequence involving the
SAME object.

Every query must take a materially different lexical route. Do not merely add
words such as closeup, macro, video, footage or cinematic. Change the useful
noun, verb, visible state, setting or event while keeping the same subject.
Never substitute a related object, metaphor, laboratory, diagram, texture,
generic food, generic person or abstract concept.
Never use: science, concept, mechanism, mystery, educational, experiment,
cinematic, futuristic, abstract.
Each query: 2-7 words.

Return ONLY valid JSON. No markdown and no commentary.
{{
  "search_ladder":[
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
}}'''
    data=_gemini(prompt,0.25)
    ladder=_normalize_ladder(data)
    if len(ladder)<4: raise RuntimeError("Gemini produced too few materially different stock-search prompts.")
    return {
        "search_ladder":ladder[:SEARCH_PROMPTS],
        "queries":[x["query"] for x in ladder[:SEARCH_PROMPTS]],
        "casting_brief":clean(data.get("casting_brief"),600),
        "must_match":[clean(x,180) for x in data.get("must_match",[])[:10]],
        "avoid":[clean(x,180) for x in data.get("avoid",[])[:10]],
        "spoken_beat":spoken,"visual_focus":focus,"visual_action":action,
    }

def build_plan(script):
    scenes=script.get("scene_plan")
    if not isinstance(scenes,list) or len(scenes)!=7: raise RuntimeError("Stock search requires exactly 7 scenes.")
    plan=[]
    print(f"🧠 STOCK SEARCH DIRECTOR — {GEMINI_MODEL} — Gemini search-language ladder")
    for si,scene in enumerate(scenes,1):
        visuals=scene.get("visuals")
        if not isinstance(visuals,list) or len(visuals)!=2: raise RuntimeError(f"Scene {si} must contain exactly 2 visuals.")
        shots=[]
        for vi,visual in enumerate(visuals,1):
            directed=direct(si,vi,scene,visual)
            directed.update(scene=si,shot=vi); shots.append(directed)
            print(f"   🎯 Scene {si} Shot {vi}:")
            for idx,q in enumerate(directed["search_ladder"],1): print(f"      {idx}. [{q['strategy']}] {q['query']}")
        plan.append(shots)
    return plan

def pexels(query,video):
    key=os.getenv("PEXELS_API_KEY","").strip()
    if not key:return []
    endpoint="videos/search" if video else "search"
    params={"query":query,"per_page":CANDIDATES_PER_SEARCH}
    if video: params["size"]="medium"
    try:
        r=requests.get(f"{PEXELS_API}/{endpoint}",headers={"Authorization":key,"User-Agent":USER_AGENT},params=params,timeout=TIMEOUT)
        return r.json().get("videos" if video else "photos",[]) if r.status_code==200 else []
    except Exception:return []

def pixabay(query,video):
    key=os.getenv("PIXABAY_API_KEY","").strip()
    if not key:return []
    endpoint=PIXABAY_VIDEO_API if video else PIXABAY_API
    params={"key":key,"q":query,"lang":"en","per_page":CANDIDATES_PER_SEARCH,"safesearch":"true","order":"popular"}
    if video: params["video_type"]="film"
    else: params["image_type"]="photo"
    try:
        r=requests.get(endpoint,params=params,headers={"User-Agent":USER_AGENT},timeout=TIMEOUT)
        return r.json().get("hits",[]) if r.status_code==200 else []
    except Exception:return []

def _preview(item,provider,video):
    if provider=="Pexels":
        if video:return item.get("image","")
        src=item.get("src") or {}; return src.get("medium") or src.get("large") or src.get("portrait") or src.get("original") or ""
    if video:
        pid=str(item.get("picture_id") or ""); return f"https://i.vimeocdn.com/video/{pid}_640x360.jpg" if pid else ""
    return item.get("previewURL") or item.get("largeImageURL") or ""

def _url(item,provider,video):
    if provider=="Pexels":
        if video:
            choices=[]
            for f in item.get("video_files") or []:
                u=f.get("link"); w=int(f.get("width") or 0); h=int(f.get("height") or 0)
                if u: choices.append((h>w,w*h,u))
            return max(choices)[2] if choices else ""
        src=item.get("src") or {}; return src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original") or ""
    if video:
        for key in ("large","medium","small","tiny"):
            u=(item.get("videos") or {}).get(key,{}).get("url")
            if u:return u
        return ""
    return item.get("largeImageURL") or item.get("fullHDURL") or item.get("imageURL") or ""

def _creator(item,provider): return ((item.get("user") or {}).get("name","") if provider=="Pexels" else item.get("user",""))

def _verify_prompt(d,q,strategy,preview_urls):
    return f'''You are the strict final visual-match judge for a YouTube Short.
Judge ONLY visible content in these stock previews. Do not infer hidden content.

SPOKEN BEAT: {d["spoken_beat"]}
VISUAL FOCUS: {d["visual_focus"]}
VISUAL ACTION: {d["visual_action"]}
SEARCH QUERY: {q}
IDEAL SHOT: {d["casting_brief"]}
MUST MATCH: {json.dumps(d.get("must_match",[]),ensure_ascii=False)}

The SAME concrete subject must visibly appear. Reject merely related objects,
generic footage, generic food, people, labs, diagrams, textures and metaphors.
Prefer literal subject relevance over attractiveness.

PREVIEW URLS (in candidate order):
{json.dumps(preview_urls,ensure_ascii=False)}

Return ONLY valid JSON:
{{"best_index":1,"score":0,"subject_match":0,"action_match":0,"context_match":0,"reason":"..."}}'''

def verify(d,items,provider,video,q,strategy):
    previews=[_preview(x,provider,video) for x in items]
    valid=[i for i,u in enumerate(previews) if u]
    if not valid:return None
    payload=_gemini(_verify_prompt(d,q,strategy,[previews[i] for i in valid]),0.05)
    try: idx=int(payload.get("best_index",0))-1
    except Exception: return None
    try: score=float(payload.get("score",0) or 0)
    except Exception: score=0
    if idx<0 or idx>=len(valid) or score<VERIFY_THRESHOLD:return None
    return items[valid[idx]]

def _download(url,path):
    try:
        with requests.get(url,headers={"User-Agent":USER_AGENT},stream=True,timeout=TIMEOUT) as r:
            if r.status_code!=200:return False
            with open(path,"wb") as f:
                for chunk in r.iter_content(1024*1024):
                    if chunk:f.write(chunk)
        return os.path.getsize(path)>0
    except Exception:return False

def generate_media(script,output_dir,config,gim=None):
    os.makedirs(output_dir,exist_ok=True)
    plan=build_plan(script); used=set(); groups=[]
    print(f"📚 STOCK SEARCH {GEMINI_MODEL} | Pexels/Pixabay only | visual verification enabled")
    for si,shots in enumerate(plan,1):
        for vi,d in enumerate(shots,1):
            selected=selected_provider=selected_video=selected_query=None
            for entry in d["search_ladder"]:
                q=entry["query"]; strategy=entry["strategy"]
                print(f"   🔎 Scene {si} Shot {vi}: [{strategy}] {q}")
                for provider,video in (("Pexels",True),("Pixabay",True),("Pexels",False),("Pixabay",False)):
                    items=pexels(q,video) if provider=="Pexels" else pixabay(q,video)
                    if not items:
                        print(f"      ↪️ {provider} {'VIDEO' if video else 'PHOTO'}: no assets"); continue
                    try: item=verify(d,items,provider,video,q,strategy)
                    except Exception as exc:
                        print(f"      ⚠️ verification call failed: {type(exc).__name__}; trying next provider/query")
                        item=None
                    if item:
                        url=_url(item,provider,video)
                        if url and url not in used:
                            selected=item; selected_provider=provider; selected_video=video; selected_query=q; break
                    print(f"      ↪️ {provider} {'VIDEO' if video else 'PHOTO'}: no verified match")
                if selected: break
            if not selected:
                raise RuntimeError(f"No visually relevant stock asset found for Scene {si} Shot {vi}; all direct Pexels/Pixabay searches exhausted.")
            url=_url(selected,selected_provider,selected_video)
            used.add(url)
            ext="mp4" if selected_video else "jpg"
            path=os.path.join(output_dir,f"scene_{si}_shot_{vi}.{ext}")
            if not _download(url,path): raise RuntimeError(f"Failed downloading selected {selected_provider} asset for Scene {si} Shot {vi}.")
            groups.append({"scene":si,"shot":vi,"path":path,"type":"video" if selected_video else "photo","provider":selected_provider,"creator":_creator(selected,selected_provider),"query":selected_query,"score":8.0})
            print(f"      ✅ SELECTED {selected_provider} {'VIDEO' if selected_video else 'PHOTO'}: {selected_query}")
    return groups
