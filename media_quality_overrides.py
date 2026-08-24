"""Mint-YT-Factory media quality policy v16.

Shot-level spoken text is the authority for visual casting. Metaphorical words
such as rumble, growl, hiss, singing, opera and collapse are mapped back to the
physical subject being explained instead of becoming stock-search subjects.
"""
from __future__ import annotations
import json, os, re

KETTLE_TERMS=(
    "kettle","kettles","boiling water","water boils","water boiling",
    "deep rumble","deep growl","grumpy growl","growl","rumble",
    "high pitched hiss","high pitch","high-pitched","hiss","shriek",
    "rising tune","rising pitch","sonic shift","kettle sings","kettle singing",
    "singing","opera","orchestra","structural collapse","tiny structural collapse",
    "microscopic shockwaves","bubbles collapse","bubbles collapsing",
    "bubble collapse","bubbles shrink","bubble shrinking","bubbles implode",
    "bubbles rising","bubbles rise","bubbles forming","air bubbles",
    "micro bubbles","microscopic bubbles","millions of times a second",
    "millions times a second","steam","steaming","blazing hot","bottom of the pot",
    "water at the bottom","higher up","still chilly","still cool","cooler layer",
    "upper water layer","hot water","heated water","rolling boil","stove","burner"
)

KETTLE_QUERIES=(
    "kettle boiling close up",
    "kettle on stove close up",
    "boiling water close up",
    "boiling water bubbles macro",
    "kettle steam close up",
    "boiling pot close up",
    "water bubbles close up",
)

ICE_TERMS=("ice","ice cube","freezing","frozen","melt","melting")
ICE_QUERIES=("ice cube close up","ice melting close up","water freezing close up","melting ice macro")

BUBBLE_TERMS=("bubble","bubbles","foam","froth")
BUBBLE_QUERIES=("water bubbles close up","bubbles forming in water","bubbles popping close up","boiling water bubbles close up")

UNSUPPORTED=re.compile(r"\b(?:polished\s+)?(?:copper|glass|stainless|steel|ceramic|brass|silver|gold|black|white|red|blue|green|yellow|rustic|vintage|wooden|plastic|transparent|metallic|glowing|artisan|camping|outdoor|indoor|kitchen|workshop|portable)\b",re.I)

def _clean(value,limit=900):
    return re.sub(r"\s+"," ",str(value or "")).strip()[:limit]

def _beat(scene,visual):
    if isinstance(visual,dict):
        spoken=_clean(visual.get("spoken_line"))
        if spoken:return spoken.lower()
    return _clean(scene.get("narration")).lower()

def _has(text,terms):
    return any(term in text for term in terms)

def _rule(scene,visual=None):
    text=_beat(scene,visual or {})
    if _has(text,KETTLE_TERMS):
        # Always cast the same physical world: kettle, pot, heated water,
        # bubbles and steam. Never cast a metaphor such as opera or collapse.
        if _has(text,("higher up","still chilly","still cool","cooler layer","upper water layer")):
            return (
                ("kettle water upper layer close up","water in pot close up","pot of water heating close up","kettle on stove close up"),
                "upper layer of water in a heated pot",
                "show the upper water remaining cooler while the lower water is heated"
            )
        if _has(text,("bubbles collapse","bubbles collapsing","bubble collapse","bubbles shrink","bubble shrinking","bubbles implode","bubbles rising","bubbles rise","bubbles forming","air bubbles","micro bubbles","microscopic bubbles","millions of times a second","millions times a second")):
            return (
                ("tiny bubbles in boiling water close up","bubbles rising in water close up","boiling water bubbles macro","water bubbles close up"),
                "tiny bubbles in heated water",
                "show tiny bubbles forming, rising, shrinking, popping or collapsing in liquid"
            )
        if _has(text,("steam","steaming")):
            return (
                ("kettle steam close up","steam escaping kettle","boiling kettle close up","boiling water close up"),
                "kettle with steam",
                "show steam rising from heated water"
            )
        if _has(text,("stove","burner","blazing hot","bottom of the pot","water at the bottom")):
            return (
                ("pot on gas stove close up","pot over flame close up","boiling pot on stove","stove flame under pot"),
                "pot over a stove flame",
                "show heat reaching the bottom of the pot"
            )
        return KETTLE_QUERIES,"kettle and heated water","show the kettle heating water, with visible bubbles or steam"
    if _has(text,ICE_TERMS):
        return ICE_QUERIES,"ice or freezing water","show ice melting or water freezing"
    if _has(text,BUBBLE_TERMS):
        return BUBBLE_QUERIES,"water bubbles","show bubbles forming, rising or popping"
    return None,None,None

def _sanitize_visual(scene,visual):
    if not isinstance(visual,dict):return visual
    queries,focus,action=_rule(scene,visual)
    if focus:
        visual["visual_focus"]=focus
        visual["visual_action"]=action
        visual["image_prompt"]=f"{focus}; {action}"
        visual["must_show"]=[focus]
        visual["must_not_show"]=["metaphorical subject","unrelated object","second topic","different mystery"]
    else:
        beat=_beat(scene,visual)
        for key in ("visual_focus","visual_action","image_prompt"):
            value=str(visual.get(key) or "")
            visual[key]=_clean(UNSUPPORTED.sub(lambda m:m.group(0) if m.group(0).lower() in beat else "",value))
    visual["visual_contract_note"]="Narration-authoritative v16; shot-level physical mapping overrides metaphor and generated visual prose."
    return visual

def _query_clean(value):
    stop={"this","that","with","from","your","into","about","just","they","them","their","very","have","will","what","when","where","which","because","while","then","than","like","gets","make","makes","made","thing","things","exact","physical","show","showing","scene","shot","visible","action","state","realistic","cinematic","photo","photograph","video","image","someone","something","close","camera","natural","looking","moment","also","really","tiny","microscopic","single","entire","every","time","next","remember","designed","actually","basically","literally","nobody","touched","cursed","higher","lower","still","same","current","polished","copper","stainless","steel","blue","dark"}
    words=[]
    for w in re.findall(r"[a-z0-9]+",str(value).lower()):
        if len(w)>=4 and w not in stop and w not in words:words.append(w)
    return " ".join(words[:8])

def _expand_queries(pm,scene,visual):
    visual=_sanitize_visual(scene,visual)
    rule_queries,_,_=_rule(scene,visual)
    variants=[]
    def add(q):
        q=_query_clean(q)
        if q and q not in variants:variants.append(q)
    if rule_queries:
        for q in rule_queries:add(q)
    else:
        add(_beat(scene,visual))
    return variants[:8] or ["everyday object close up"]

def _text(scene,visual):return _beat(scene,visual)

def _install_selector(pm):
    if getattr(pm,"_mint_selector_v16",False):return
    def select(scene,visual,excluded_pages=None):
        excluded_pages=excluded_pages or set()
        if not pm.headers():return None
        visual=_sanitize_visual(scene,visual)
        qs=_expand_queries(pm,scene,visual)
        required=pm.tokens(_text(scene,visual)); actions=pm.action_tokens(_text(scene,visual))
        contextual=bool(_rule(scene,visual)); minimum=6 if contextual else 8
        print(f"   🧭 Semantic visual search: {'NARRATION-DRIVEN PHYSICAL PROXY' if contextual else 'NARRATION-DRIVEN LITERAL'} | queries={len(qs)}")
        print(f"   🔎 Search queries: {' | '.join(qs[:6])}")
        videos=[]
        for q in qs:videos.extend(pm.search("videos/search",q,{"orientation":"portrait","size":"medium"}))
        videos=pm._dedupe(videos,"video",excluded_pages);videos.sort(key=lambda x:pm._heuristic_score(x,required,actions,"video"),reverse=True)
        print(f"   🔎 Pexels video candidates: {len(videos)}")
        ranked=pm._gemini_rank_candidates(scene,visual,videos[:12],"video") if videos else []
        for item in ranked:
            score=int(item.get("_gemini_score",0) or 0);link=pm._video_download_url(item)
            if score>=minimum and link:return {"kind":"video","video":link,"page":item.get("url",""),"photographer":(item.get("user") or {}).get("name","") or "","score":score,"qc_reason":item.get("_gemini_reason","") ,"query":" | ".join(qs[:6])}
        photos=[]
        for q in qs:photos.extend(pm.search("search",q,{"orientation":"portrait","size":"large"}))
        photos=pm._dedupe(photos,"photo",excluded_pages);photos.sort(key=lambda x:pm._heuristic_score(x,required,actions,"photo"),reverse=True)
        print(f"   🔎 Pexels photo candidates: {len(photos)}")
        ranked=pm._gemini_rank_candidates(scene,visual,photos[:12],"photo") if photos else []
        for item in ranked:
            score=int(item.get("_gemini_score",0) or 0);src=item.get("src") or {};link=src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
            if score>=minimum and link:return {"kind":"photo","photo":link,"page":item.get("url",""),"photographer":item.get("photographer","") or "","score":score,"qc_reason":item.get("_gemini_reason","") ,"query":" | ".join(qs[:6])}
        print(f"   ❌ No Pexels asset passed the {minimum}/10 narration relevance threshold");return None
    pm._select=select;pm._mint_selector_v16=True

def _assert_complete(groups):
    if len(groups)!=7:raise RuntimeError(f"Media contract failed: expected 7 scene groups, found {len(groups)}")
    for si,paths in enumerate(groups,1):
        if len(paths)!=2:raise RuntimeError(f"Media contract failed: Scene {si} has {len(paths)} paths")
        if any(not os.path.exists(p) for p in paths):raise RuntimeError(f"Media contract failed: Scene {si} has missing assets")

def patch_media_selection(media):
    original_generate=media.generate_media
    if getattr(original_generate,"_mint_media_policy_v16",False):return
    import pexels_media
    _install_selector(pexels_media)
    def generate_media(script,output_dir,config,gim):
        groups=original_generate(script,output_dir,config,gim);_assert_complete(groups)
        with open(os.path.join(output_dir,"media_manifest.json"),"w",encoding="utf-8") as h:
            json.dump({"provider_order":["pexels_verified_video","pexels_verified_photo"],"gemini_calls":"one_per_shot_for_pexels_only","pollinations":"disabled","semantic_stock_query_translation":"narration_authoritative_v16_shot_level","generated_visual_metadata":"ignored_when_physical_rule_matches","metaphor_literalization":"disabled","shot_level_beats":"authoritative","contextual_minimum":6,"ordinary_minimum":8},h,ensure_ascii=False,indent=2)
        print("🧠 Media policy v16: kettle sound/metaphor mapping + shot-level casting active");return groups
    generate_media._mint_media_policy_v16=True;media.generate_media=generate_media
