"""Stock-only visual search pipeline for Mint-YT-Factory.

Gemini directs and verifies real Pexels/Pixabay candidates. It never generates
replacement imagery. The primary model is gemini-flash-lite-latest, with a
multimodal fallback only when the primary service is temporarily unavailable.
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
GEMINI_FALLBACK_MODEL = "gemini-2.5-flash-lite"
VERIFY_THRESHOLD = 7.5
CANDIDATES = 6
QUERIES = 5
TIMEOUT = 35
USER_AGENT = "Mint-YT-Factory/StockSearch/11.5"

STOP = {"this","that","with","from","your","into","about","just","they","them","their","very","have","will","what","when","where","which","because","while","then","than","like","gets","make","makes","made","thing","things","exact","physical","show","showing","scene","shot","visible","action","state","realistic","cinematic","photo","photograph","video","image","someone","something","people","person","camera","natural","looking","moment","also","really","tiny","microscopic","single","entire","every","time","next","remember","designed","actually","basically","literally","only","must","contain"}
ACTIONS = {"cling","stick","pull","grab","hold","touch","rub","fall","drop","jump","run","pour","spill","open","close","break","tear","bend","shake","twist","stretch","slide","move","tumble","wash","dry","iron","sew","wear","remove","press","boil","freeze","melt","steam","squeeze","crush","bounce","spin","plug","drip","float","burst","snap","crack","lift","collapse","tangle","cut","slice","pop","pouring","boiling","melting","cracking","popping"}


def clean(v: Any, n=700):
    return " ".join(str(v or "").replace("\n", " ").split()).strip()[:n]


def tokens(v: Any):
    return {x for x in re.findall(r"[a-z0-9]+", clean(v, 3000).lower()) if len(x) >= 3 and x not in STOP}


def action_tokens(v: Any):
    return tokens(v) & ACTIONS


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
    return any(x in text for x in ("503", "unavailable", "429", "resource exhausted", "500", "502", "504", "high demand", "temporarily"))


def _gemini(prompt: str, temperature: float):
    from google import genai
    from google.genai import types
    last_error = None
    for model_index, model in enumerate((GEMINI_MODEL, GEMINI_FALLBACK_MODEL)):
        client = genai.Client(api_key=_key())
        for attempt in range(1, 3):
            try:
                response = client.models.generate_content(model=model, contents=[prompt], config=types.GenerateContentConfig(temperature=temperature))
                if model != GEMINI_MODEL:
                    print(f"🛟 Gemini fallback used: {model}")
                return _json(getattr(response, "text", ""))
            except Exception as exc:
                last_error = exc
                if _is_transient_gemini_error(exc) and attempt < 2:
                    print(f"⚠️ {model} temporary failure ({attempt}/2); retrying...")
                    time.sleep(2.0 * attempt)
                    continue
                if model_index == 0 and _is_transient_gemini_error(exc):
                    print(f"⚠️ {model} unavailable; switching to {GEMINI_FALLBACK_MODEL}")
                break
    raise RuntimeError(f"Gemini visual/search call failed after primary+fallback: {type(last_error).__name__}: {last_error}") from last_error


def direct(scene_no: int, shot_no: int, scene: dict, visual: dict):
    spoken = clean(visual.get("spoken_line") or scene.get("narration"), 650)
    focus = clean(visual.get("visual_focus"), 300)
    action = clean(visual.get("visual_action"), 300)
    must = [clean(x, 160) for x in visual.get("must_show", []) if clean(x)]
    avoid = [clean(x, 160) for x in visual.get("must_not_show", []) if clean(x)]
    prompt = f"""You are the stock-footage SEARCH DIRECTOR for a fast, fun YouTube Short.
The production system can ONLY use real Pexels/Pixabay stock footage/photos.

SCENE {scene_no}, SHOT {shot_no}
SPOKEN BEAT: {spoken}
VISUAL FOCUS: {focus}
VISUAL ACTION: {action}
MUST SHOW: {json.dumps(must)}
MUST NOT SHOW: {json.dumps(avoid)}

Find what stock libraries can realistically contain. Do not invent an image.

SEARCH RULES:
1. Start from the exact physical subject.
2. Search visible actions/states, not scientific explanations.
3. Prefer ordinary real-world footage.
4. For invisible/internal mechanisms, use truthful visible evidence or the immediate physical result.
5. Never substitute a merely related object.
6. If an exact intermediate action is unlikely to exist, search a DIRECTLY CAUSAL progression using the same subject. Do not jump to generic or unrelated material.
7. Never use abstract words such as science, mystery, concept, mechanism, education, experiment, cinematic.
8. Queries should be 2-6 words and stock-search friendly.
9. Produce five materially different searches: exact subject, subject+action, subject+context, causal progression, simplified fallback.
10. Keep this shot visually distinct from the other shot in its scene.

Return ONLY JSON:
{{"queries":["..."],"casting_brief":"...","must_match":["..."],"avoid":["..."],"search_mode":"literal|action|context|visible-proxy|causal"}}"""
    data = _gemini(prompt, 0.15)
    queries=[]
    for q in data.get("queries", []):
        q=clean(q,90)
        if q and len(q.split())<=8 and q.lower() not in {x.lower() for x in queries}: queries.append(q)
    if len(queries)<3: raise RuntimeError("Gemini produced too few usable stock queries.")
    return {"queries":queries[:QUERIES],"casting_brief":clean(data.get("casting_brief"),500),"must_match":[clean(x,150) for x in data.get("must_match",[])[:8]],"avoid":[clean(x,150) for x in data.get("avoid",[])[:8]],"search_mode":clean(data.get("search_mode"),40),"spoken_beat":spoken}


def build_plan(script):
    scenes=script.get("scene_plan")
    if not isinstance(scenes,list) or len(scenes)!=7: raise RuntimeError("Stock search requires exactly 7 scenes.")
    plan=[]
    print(f"🧠 STOCK SEARCH DIRECTOR — {GEMINI_MODEL} — fallback={GEMINI_FALLBACK_MODEL}")
    for si,scene in enumerate(scenes,1):
        visuals=scene.get("visuals")
        if not isinstance(visuals,list) or len(visuals)!=2: raise RuntimeError(f"Scene {si} must contain exactly 2 visuals.")
        shots=[]
        for vi,v in enumerate(visuals,1):
            d=direct(si,vi,scene,v); d.update(scene=si,shot=vi); shots.append(d)
            print(f"   🎯 Scene {si} Shot {vi}: {' | '.join(d['queries'])}")
        plan.append(shots)
    return plan


def pexels(query, video):
    key=os.getenv("PEXELS_API_KEY","").strip()
    if not key:return []
    endpoint="videos/search" if video else "search"
    params={"query":query,"per_page":30,"orientation":"portrait"}
    if video: params["size"]="medium"
    try:
        r=requests.get(f"{PEXELS_API}/{endpoint}",headers={"Authorization":key,"User-Agent":USER_AGENT},params=params,timeout=TIMEOUT)
        return r.json().get("videos" if video else "photos",[]) if r.status_code==200 else []
    except Exception:return []


def pixabay(query, video):
    key=os.getenv("PIXABAY_API_KEY","").strip()
    if not key:return []
    endpoint=PIXABAY_VIDEO_API if video else PIXABAY_API
    params={"key":key,"q":query,"lang":"en","per_page":30,"safesearch":"true","order":"popular"}
    if video: params["video_type"]="film"
    else: params.update(image_type="photo",orientation="vertical")
    try:
        r=requests.get(endpoint,params=params,headers={"User-Agent":USER_AGENT},timeout=TIMEOUT)
        if r.status_code!=200:return []
        return r.json().get("hits",[])
    except Exception:return []


def _text(item,provider,video):
    if provider=="Pexels": return clean(item.get("url"))+" "+clean(item.get("video_pictures")) if video else clean(item.get("alt"))+" "+clean(item.get("url"))
    return clean(item.get("tags"))+" "+clean(item.get("pageURL"))


def rank(items,directed,provider,video,used):
    req=tokens(" ".join(directed.get("must_match",[]))); q=tokens(" ".join(directed.get("queries",[]))); acts=action_tokens(" ".join(directed.get("must_match",[])))
    out=[]; seen=set(used)
    for item in items:
        page=str(item.get("url") if provider=="Pexels" else item.get("pageURL") or "")
        if not page or page in seen:continue
        txt=tokens(_text(item,provider,video)); score=len(req&txt)*5+len(q&txt)*0.8+len(acts&txt)*2
        if video:
            duration=float(item.get("duration") or 0)
            if 2<=duration<=20:score+=2
            if provider=="Pexels" and int(item.get("height") or 0)>int(item.get("width") or 0):score+=2
        else:
            h=int(item.get("height") or item.get("imageHeight") or 0); w=int(item.get("width") or item.get("imageWidth") or 0)
            if h>=w and h:score+=2
        out.append((score,item,page)); seen.add(page)
    out.sort(key=lambda x:x[0],reverse=True); return out[:CANDIDATES]


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
                if u:choices.append((h>w,w*h,u))
            return max(choices)[2] if choices else ""
        src=item.get("src") or {}; return src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original") or ""
    if video:
        for k in ("large","medium","small","tiny"):
            u=(item.get("videos") or {}).get(k,{}).get("url")
            if u:return u
        return ""
    return item.get("largeImageURL") or item.get("fullHDURL") or item.get("imageURL") or ""


def _verify_prompt(directed):
    return f"""You are the strict final visual judge for a YouTube Short. Judge ONLY what is visible.
SPOKEN BEAT: {directed['spoken_beat']}
IDEAL STOCK SHOT: {directed['casting_brief']}
MUST MATCH: {json.dumps(directed.get('must_match',[]))}
AVOID: {json.dumps(directed.get('avoid',[]))}

Reject merely related objects, decorative textures, generic food/water, generic people, abstract science imagery, or attractive footage that does not explain the beat. The visible subject must be the actual subject spoken about. The visible action/state should match when reasonably available. For hard-to-film intermediate states, a directly causal progression with the SAME subject is acceptable. For invisible mechanisms, accept only truthful visible proxies such as cut-open objects, steam, boiling, swelling, cracking, bursting, or the immediate result. Cinematic quality never compensates for mismatch.

Return ONLY JSON: {{"results":[{{"candidate":1,"score":0,"subject_match":0,"action_match":0,"context_match":0,"reject":true,"reason":"..."}}]}}. Score 0-10; usable requires score >= {VERIFY_THRESHOLD} and reject=false."""


def verify(candidates,directed):
    if not candidates:return None
    from google import genai
    from google.genai import types
    usable=[];parts=[]
    for c in candidates[:CANDIDATES]:
        try:
            r=requests.get(c["preview"],headers={"User-Agent":USER_AGENT},timeout=20); r.raise_for_status()
            parts += [types.Part.from_bytes(data=r.content,mime_type="image/jpeg"),types.Part.from_text(text=f"CANDIDATE {len(usable)+1}")]
            usable.append(c)
        except Exception:continue
    if not usable:return None
    prompt=_verify_prompt(directed)
    last_error=None; data=None
    for model in (GEMINI_MODEL,GEMINI_FALLBACK_MODEL):
        client=genai.Client(api_key=_key())
        for attempt in range(1,3):
            try:
                response=client.models.generate_content(model=model,contents=parts+[types.Part.from_text(text=prompt)],config=types.GenerateContentConfig(temperature=0))
                if model != GEMINI_MODEL: print(f"🛟 Visual verification fallback used: {model}")
                data=_json(getattr(response,"text","") or "")
                last_error=None; break
            except Exception as exc:
                last_error=exc
                if _is_transient_gemini_error(exc) and attempt<2:
                    print(f"⚠️ Visual verification {model} temporary failure ({attempt}/2); retrying...")
                    time.sleep(2.0*attempt); continue
                if model==GEMINI_MODEL and _is_transient_gemini_error(exc): print(f"⚠️ Visual verification switching to {GEMINI_FALLBACK_MODEL}")
                break
        if last_error is None: break
    if last_error is not None: raise RuntimeError(f"Visual verification failed after primary+fallback: {type(last_error).__name__}: {last_error}") from last_error
    results=[]
    for x in data.get("results",[]):
        try:
            i=int(x.get("candidate",0))-1; score=float(x.get("score",0) or 0)
            if 0<=i<len(usable) and not bool(x.get("reject",True)) and score>=VERIFY_THRESHOLD:
                z=dict(usable[i]); z.update(visual_score=score,visual_subject_match=float(x.get("subject_match",0)),visual_action_match=float(x.get("action_match",0)),visual_context_match=float(x.get("context_match",0)),visual_reason=clean(x.get("reason"),400)); results.append(z)
        except (TypeError,ValueError):continue
    return sorted(results,key=lambda x:x["visual_score"],reverse=True)[0] if results else None


def _download(url,path,provider):
    for attempt in range(1,4):
        try:
            r=requests.get(url,headers={"User-Agent":USER_AGENT},timeout=120,stream=True); r.raise_for_status(); os.makedirs(os.path.dirname(path),exist_ok=True)
            with open(path,"wb") as f:
                for chunk in r.iter_content(1024*1024):
                    if chunk:f.write(chunk)
            if os.path.getsize(path)<=10000:raise RuntimeError("download too small")
            return True
        except Exception as exc:
            print(f"⚠️ {provider} download {attempt}/3 failed: {type(exc).__name__}: {exc}")
            if attempt<3:time.sleep(1.5*attempt)
    return False


def _credit(path,c,d):
    with open(path,"w",encoding="utf-8") as f:
        json.dump({"provider":c["provider"],"type":c["kind"],"page":c["page"],"creator":c.get("creator",""),"search_queries":d["queries"],"search_mode":d.get("search_mode",""),"metadata_score":c["metadata_score"],"gemini_visual_score":c["visual_score"],"visual_reason":c["visual_reason"]},f,ensure_ascii=False,indent=2)


def generate_media(script,output_dir,config,gim=None):
    if not os.getenv("PEXELS_API_KEY","").strip() and not os.getenv("PIXABAY_API_KEY","").strip():raise RuntimeError("PEXELS_API_KEY or PIXABAY_API_KEY is required.")
    os.makedirs(output_dir,exist_ok=True); plan=build_plan(script); used=set(); groups=[]
    print(f"📚 STOCK SEARCH {GEMINI_MODEL} | fallback {GEMINI_FALLBACK_MODEL} | Pexels/Pixabay only")
    for si,shots in enumerate(plan,1):
        paths=[]
        for vi,d in enumerate(shots,1):
            selected=None
            for provider,video in (("Pexels",True),("Pixabay",True),("Pexels",False),("Pixabay",False)):
                if provider=="Pexels" and not os.getenv("PEXELS_API_KEY",""):continue
                if provider=="Pixabay" and not os.getenv("PIXABAY_API_KEY",""):continue
                raw=[]
                for q in d["queries"]:raw += pexels(q,video) if provider=="Pexels" else pixabay(q,video)
                candidates=[]
                for score,item,page in rank(raw,d,provider,video,used):
                    preview=_preview(item,provider,video); url=_url(item,provider,video)
                    if preview and url:candidates.append({"provider":provider,"kind":"video" if video else "photo","url":url,"page":page,"creator":((item.get("user") or {}).get("name","") if provider=="Pexels" else item.get("user","")),"metadata_score":score,"preview":preview})
                chosen=verify(candidates,d)
                if chosen:
                    selected=chosen; print(f"   ✅ Scene {si} Shot {vi}: {provider} {chosen['kind']} VERIFIED {chosen['visual_score']:.1f}/10"); break
                print(f"   ↪️ Scene {si} Shot {vi}: {provider} {'VIDEO' if video else 'PHOTO'} produced no verified match")
            if not selected:raise RuntimeError(f"No visually relevant stock asset found for Scene {si} Shot {vi}; unrelated fallback is disabled.")
            used.add(selected["page"]); ext="mp4" if selected["kind"]=="video" else "jpg"; path=os.path.join(output_dir,f"scene_{si:02d}_shot_{vi:02d}.{ext}")
            if not _download(selected["url"],path,selected["provider"]):raise RuntimeError(f"Stock asset download failed for Scene {si} Shot {vi}.")
            _credit(path+".credit.json",selected,d); paths.append(path)
        groups.append(paths)
    return groups
