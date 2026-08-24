"""Narration-authoritative Pexels media selection. No Gemini visual verification."""
from __future__ import annotations
import json, os, re

RULES=[
(("boiling water","water boils","water boiling","hot water","heated water"),("boiling water close up","water boiling in pot close up","boiling pot macro"),"water boiling in a pot","bubbles rising, forming, popping or collapsing"),
(("steam","steaming","escaping steam"),("kettle steam close up","steam escaping kettle","boiling kettle close up"),"kettle or pot with steam","steam rising from heated water"),
(("ice","ice cube","freezing","frozen","melt","melting"),("ice cube close up","ice melting close up","water freezing close up"),"ice or freezing water","ice melting or water freezing"),
(("bubble","bubbles","foam","froth"),("water bubbles close up","bubbles forming in water","bubbles popping close up"),"water bubbles","bubbles forming, rising or popping"),
]

def clean(v,limit=700): return re.sub(r"\s+"," ",str(v or "")).strip()[:limit]
def beat(scene,visual): return clean((visual or {}).get("spoken_line") or scene.get("narration"),900).lower()
def rule(scene,visual):
    text=beat(scene,visual)
    for triggers,qs,focus,action in RULES:
        if any(x in text for x in triggers): return qs,focus,action
    return None,None,None

def sanitize(scene,visual):
    v=dict(visual or {}); qs,focus,action=rule(scene,v)
    if focus:
        v["visual_focus"]=focus; v["visual_action"]=action; v["image_prompt"]=f"{focus}; {action}"; v["must_show"]=[focus]
    return v

def query_clean(v):
    stop={"this","that","with","from","your","into","about","just","they","them","their","very","have","will","what","when","where","which","because","while","then","than","like","gets","make","makes","made","thing","things","exact","physical","show","showing","scene","shot","visible","action","state","realistic","cinematic","photo","photograph","video","image","someone","something","close","camera","natural","looking","moment","also","really","tiny","microscopic","single","entire","every","time","next","remember","designed","actually","basically","literally","nobody","touched","cursed"}
    words=[]
    for w in re.findall(r"[a-z0-9]+",str(v).lower()):
        if len(w)>=4 and w not in stop and w not in words: words.append(w)
    return " ".join(words[:8])

def expand_queries(pm,scene,visual):
    v=sanitize(scene,visual); qs,_,_=rule(scene,v); values=list(qs or [])+[beat(scene,v),f"{v.get('visual_focus','')} {v.get('visual_action','')}"]; out=[]
    for value in values:
        q=query_clean(value)
        if q and q not in out: out.append(q)
    return out[:8] or ["everyday object close up"]

def _select(pm,scene,visual,excluded_pages=None):
    excluded_pages=excluded_pages or set()
    if not pm.headers(): return None
    v=sanitize(scene,visual); qs=expand_queries(pm,scene,v)
    required=pm.tokens(beat(scene,v)+" "+clean(v.get("visual_focus"),300)); actions=pm.action_tokens(clean(v.get("visual_action"),300)+" "+beat(scene,v))
    videos=[]
    for q in qs: videos.extend(pm.search("videos/search",q,{"orientation":"portrait","size":"medium"}))
    videos=pm._dedupe(videos,"video",excluded_pages); videos.sort(key=lambda x:pm._heuristic_score(x,required,actions,"video"),reverse=True)
    for item in videos[:12]:
        link=pm._video_download_url(item)
        if link: return {"kind":"video","video":link,"page":item.get("url",""),"photographer":(item.get("user") or {}).get("name","") or "","score":int(pm._heuristic_score(item,required,actions,"video")),"qc_reason":"Local narration relevance ranking","query":" | ".join(qs[:6])}
    photos=[]
    for q in qs: photos.extend(pm.search("search",q,{"orientation":"portrait","size":"large"}))
    photos=pm._dedupe(photos,"photo",excluded_pages); photos.sort(key=lambda x:pm._heuristic_score(x,required,actions,"photo"),reverse=True)
    for item in photos[:12]:
        src=item.get("src") or {}; link=src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
        if link: return {"kind":"photo","photo":link,"page":item.get("url",""),"photographer":item.get("photographer","") or "","score":int(pm._heuristic_score(item,required,actions,"photo")),"qc_reason":"Local narration relevance ranking","query":" | ".join(qs[:6])}
    return None

def assert_complete(groups):
    if len(groups)!=7: raise RuntimeError(f"Media contract failed: expected 7 scene groups, found {len(groups)}")
    for si,paths in enumerate(groups,1):
        if len(paths)!=2: raise RuntimeError(f"Media contract failed: Scene {si} has {len(paths)} paths")
        if any(not os.path.exists(p) for p in paths): raise RuntimeError(f"Media contract failed: Scene {si} has missing assets")

def patch_media_selection(media):
    original=media.generate_media
    if getattr(original,"_mint_media_policy_local",False): return
    import pexels_media
    pexels_media._select=lambda scene,visual,excluded_pages=None:_select(pexels_media,scene,visual,excluded_pages)
    def generate_media(script,output_dir,config,gim):
        groups=original(script,output_dir,config,gim); assert_complete(groups)
        manifest={"provider_order":["pexels_video","pexels_photo"],"gemini_calls":0,"visual_verification":"disabled","ranking":"local narration relevance"}
        with open(os.path.join(output_dir,"media_manifest.json"),"w",encoding="utf-8") as h: json.dump(manifest,h,ensure_ascii=False,indent=2)
        print("🧠 Media policy: local relevance ranking — Gemini visual verification DISABLED")
        return groups
    generate_media._mint_media_policy_local=True; media.generate_media=generate_media
