"""Mint-YT-Factory media quality policy v14.

Narration is the sole authority for stock-media intent. Generated visual
metadata is never allowed to turn a metaphor into a literal search subject.
"""
from __future__ import annotations
import json, os, re

_RULES = [
    (("trapped air pocket", "trapped air pockets", "air pocket", "air pockets", "collapsing cavity", "collapsing cavities", "microscopic slap", "frequency shoots", "frequency higher", "pitch climbs", "rising pitch", "rising tune", "whistling", "kettle sings", "kettle singing", "singing"), ("kettle boiling close up", "kettle on stove close up", "boiling water close up", "kettle steam close up", "boiling pot close up"), "kettle on stove", "heating water; tiny bubbles forming or collapsing"),
    (("boiling water", "water boils", "water boiling", "boiling bubbles", "bubbles forming", "bubbles rise", "bubbles rising", "bubbles collapse", "collapsing bubbles", "hot water", "heated water", "rolling boil"), ("boiling water close up", "boiling water bubbles close up", "water boiling in pot close up", "boiling pot macro"), "water boiling in a pot", "bubbles rising, forming, popping or collapsing"),
    (("cooler layer", "still cool", "water is still cool", "water is still cold", "higher up", "higher up the water", "cool water", "cold water"), ("water in pot close up", "pot of water heating close up", "water surface in pot close up", "pot with water on stove"), "water in a pot", "upper water layer remaining relatively still while heating"),
    (("steam", "steaming", "escaping steam", "steam jet", "steam escaping"), ("kettle steam close up", "steam escaping kettle", "boiling kettle close up", "boiling water close up"), "kettle or pot with steam", "steam rising from heated water"),
    (("flame", "burner", "stove", "blazing hot", "very hot", "bottom of the pot"), ("pot on gas stove close up", "pot over flame close up", "boiling pot on stove", "stove flame under pot"), "pot over a stove flame", "heat reaching the bottom of the pot"),
    (("ice", "ice cube", "freezing", "frozen", "melt", "melting"), ("ice cube close up", "ice melting close up", "water freezing close up", "melting ice macro"), "ice or freezing water", "ice melting or water freezing"),
    (("bubble", "bubbles", "foam", "froth"), ("water bubbles close up", "bubbles forming in water", "bubbles popping close up", "boiling water bubbles close up"), "water bubbles", "bubbles forming, rising or popping"),
]
_UNSUPPORTED = re.compile(r"\b(?:polished\s+)?(?:copper|glass|stainless|steel|ceramic|brass|silver|gold|black|white|red|blue|green|yellow|rustic|vintage|wooden|plastic|transparent|metallic|glowing|artisan|camping|outdoor|indoor|kitchen|workshop|portable)\b", re.I)

def _clean(value, limit=700): return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]
def _narration(scene): return _clean(scene.get("narration"), 900).lower()
def _has(text, phrases): return any(p in text for p in phrases)
def _rule(scene):
    text=_narration(scene)
    for triggers, queries, focus, action in _RULES:
        if _has(text,triggers): return queries,focus,action
    return None,None,None

def _strip(value,narration):
    text=_clean(value)
    def repl(match): return match.group(0) if match.group(0).lower() in narration else ""
    return _clean(_UNSUPPORTED.sub(repl,text))

def _sanitize_visual(scene,visual):
    if not isinstance(visual,dict): return visual
    narration=_narration(scene); queries,focus,action=_rule(scene)
    # Critical fix: known physical narration replaces generated visual semantics.
    # This blocks metaphor literalization such as "tiny orchestra tuning up".
    if focus:
        visual["visual_focus"]=focus
        visual["visual_action"]=action
        visual["image_prompt"]=f"{focus}; {action}"
        visual["must_show"]=[focus]
    else:
        for key in ("visual_focus","visual_action","image_prompt"):
            visual[key]=_strip(visual.get(key),narration)
        must=visual.get("must_show")
        if isinstance(must,list): visual["must_show"]=[x for x in (_strip(v,narration) for v in must) if x][:6]
    visual["visual_contract_note"]="Narration-authoritative v14; metaphor and unsupported generated detail are ignored for stock retrieval."
    return visual

def _query_clean(value):
    stop={"this","that","with","from","your","into","about","just","they","them","their","very","have","will","what","when","where","which","because","while","then","than","like","gets","make","makes","made","thing","things","exact","physical","show","showing","scene","shot","visible","action","state","realistic","cinematic","photo","photograph","video","image","someone","something","close","camera","natural","looking","moment","also","really","tiny","microscopic","single","entire","every","time","next","remember","designed","actually","basically","literally","nobody","touched","cursed","higher","lower"}
    words=[]
    for w in re.findall(r"[a-z0-9]+",str(value).lower()):
        if len(w)>=4 and w not in stop and w not in words: words.append(w)
    return " ".join(words[:8])

def _expand_queries(pm,scene,visual):
    visual=_sanitize_visual(scene,visual); narration=_narration(scene); rule_queries,_,_=_rule(scene); variants=[]
    def add(q):
        q=_query_clean(q)
        if q and q not in variants: variants.append(q)
    if rule_queries:
        for q in rule_queries: add(q)
    else:
        add(narration); add(f"{visual.get('visual_focus','')} {visual.get('visual_action','')}")
    # Spoken narration is allowed as a fallback, generated visual prose is not.
    return variants[:8] or ["everyday object close up"]

def _text(scene,visual): return _clean(scene.get("narration") or visual.get("spoken_line"),900)

def _install_selector(pm):
    if getattr(pm,"_mint_selector_v14",False): return
    def select(scene,visual,excluded_pages=None):
        excluded_pages=excluded_pages or set()
        if not pm.headers(): return None
        visual=_sanitize_visual(scene,visual); qs=_expand_queries(pm,scene,visual)
        required=pm.tokens(_text(scene,visual)); actions=pm.action_tokens(_text(scene,visual)); contextual=bool(_rule(scene)); minimum=6 if contextual else 8
        print(f"   🧭 Semantic visual search: {'NARRATION-DRIVEN PHYSICAL PROXY' if contextual else 'NARRATION-DRIVEN LITERAL'} | queries={len(qs)}")
        print(f"   🔎 Search queries: {' | '.join(qs[:6])}")
        videos=[]
        for q in qs: videos.extend(pm.search("videos/search",q,{"orientation":"portrait","size":"medium"}))
        videos=pm._dedupe(videos,"video",excluded_pages); videos.sort(key=lambda x:pm._heuristic_score(x,required,actions,"video"),reverse=True)
        print(f"   🔎 Pexels video candidates: {len(videos)}")
        ranked=pm._gemini_rank_candidates(scene,visual,videos[:12],"video") if videos else []
        for item in ranked:
            score=int(item.get("_gemini_score",0) or 0); link=pm._video_download_url(item)
            if score>=minimum and link: return {"kind":"video","video":link,"page":item.get("url",""),"photographer":(item.get("user") or {}).get("name","") or "","score":score,"qc_reason":item.get("_gemini_reason",""),"query":" | ".join(qs[:6])}
        photos=[]
        for q in qs: photos.extend(pm.search("search",q,{"orientation":"portrait","size":"large"}))
        photos=pm._dedupe(photos,"photo",excluded_pages); photos.sort(key=lambda x:pm._heuristic_score(x,required,actions,"photo"),reverse=True)
        print(f"   🔎 Pexels photo candidates: {len(photos)}")
        ranked=pm._gemini_rank_candidates(scene,visual,photos[:12],"photo") if photos else []
        for item in ranked:
            score=int(item.get("_gemini_score",0) or 0); src=item.get("src") or {}; link=src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
            if score>=minimum and link: return {"kind":"photo","photo":link,"page":item.get("url",""),"photographer":item.get("photographer","") or "","score":score,"qc_reason":item.get("_gemini_reason","") ,"query":" | ".join(qs[:6])}
        print(f"   ❌ No Pexels asset passed the {minimum}/10 narration relevance threshold"); return None
    pm._select=select; pm._mint_selector_v14=True

def _assert_complete(groups):
    if len(groups)!=7: raise RuntimeError(f"Media contract failed: expected 7 scene groups, found {len(groups)}")
    for si,paths in enumerate(groups,1):
        if len(paths)!=2: raise RuntimeError(f"Media contract failed: Scene {si} has {len(paths)} paths")
        if any(not os.path.exists(p) for p in paths): raise RuntimeError(f"Media contract failed: Scene {si} has missing assets")

def patch_media_selection(media):
    original_generate=media.generate_media
    if getattr(original_generate,"_mint_media_policy_v14",False): return
    import pexels_media; _install_selector(pexels_media)
    def generate_media(script,output_dir,config,gim):
        groups=original_generate(script,output_dir,config,gim); _assert_complete(groups)
        with open(os.path.join(output_dir,"media_manifest.json"),"w",encoding="utf-8") as h:
            json.dump({"provider_order":["pexels_verified_video","pexels_verified_photo"],"gemini_calls":"one_per_shot_for_pexels_only","pollinations":"disabled","semantic_stock_query_translation":"narration_authoritative_v14","generated_visual_metadata":"ignored_when_physical_rule_matches","metaphor_literalization":"disabled","contextual_minimum":6,"ordinary_minimum":8},h,ensure_ascii=False,indent=2)
        print("🧠 Media policy v14: physical narration mapping + metaphor contamination blocked"); return groups
    generate_media._mint_media_policy_v14=True; media.generate_media=generate_media
