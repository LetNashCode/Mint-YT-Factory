"""Pexels-only media selection policy for Mint-YT-Factory.

Pexels is the only media provider in the current production mode.
Gemini is used only to visually rank Pexels candidates.
No Pollinations/FLUX fallback is permitted.
"""
from __future__ import annotations
import os,re,json

_CUSTOM_RE=re.compile(r"\b(?:square|triangular|triangle|cubic|cube|rectangular|hexagonal|pentagonal|wire[- ]frame|soap[- ]film|film under tension|molecular|molecule|cross[- ]section|microscopic|micro[- ]scale|membrane|surface tension|physics demonstration|experiment setup|exact geometry|geometric frame)\b",re.I)

def _text(scene,visual):
    return " ".join(str(x or "") for x in (visual.get("visual_focus"),visual.get("visual_action"),visual.get("must_show"),visual.get("spoken_line") or scene.get("narration")))

def _custom(scene,visual):
    return bool(_CUSTOM_RE.search(_text(scene,visual)))

_ALIASES={
    "earbuds":["earbuds","earphones","headphones"],
    "earbud":["earbud","earphone","headphone"],
    "wired earbuds":["wired earbuds","wired earphones","earphone cable"],
    "pocket":["pocket","jeans pocket","pants pocket"],
    "cord":["cord","cable","wire"],
    "cable":["cable","wire","cord"],
    "phone":["phone","smartphone","mobile phone"],
    "ice cube":["ice cube","ice","ice cubes"],
    "ice cubes":["ice cubes","ice","ice cube"],
    "soap bubbles":["soap bubbles","bubbles","bubble"],
    "bubble":["bubble","soap bubble","bubbles"],
    "keyboard":["keyboard","computer keyboard"],
    "screen":["screen","phone screen","display"],
}

# Stock search engines respond much better to the visible state than to prose
# such as "ancient sailor knot" or "pull them out minutes later".
_STATE_ALIASES={
    "tangle":["tangled earbuds","tangled earphones","tangled headphones","earbuds tangled"],
    "tangled":["tangled earbuds","tangled earphones","tangled headphones","earbuds tangled"],
    "knot":["earbud knot","earphone knot","tangled earphones","tangled earbuds"],
    "knotted":["knotted earphones","knotted earbuds","tangled earphones","tangled earbuds"],
    "shake":["shaking cable","shaking cord","tangled cord"],
    "pull":["pulling earbuds","pulling earphones","earbuds from pocket"],
    "pocket":["earbuds pocket","earphones pocket","earbuds jeans pocket"],
}

def _expand_queries(pexels_media,scene,visual):
    """Build stock-friendly queries from the visual beat, not the whole prose."""
    focus=str(visual.get("visual_focus") or "").strip().lower()
    action=str(visual.get("visual_action") or "").strip().lower()
    must=visual.get("must_show") or []
    if isinstance(must,list): must_text=" ".join(str(x) for x in must[:6]).lower()
    else: must_text=str(must).lower()
    spoken=str(visual.get("spoken_line") or scene.get("narration") or "").strip().lower()
    raw=" ".join([focus,action,must_text,spoken])
    tokens=re.findall(r"[a-z0-9]+",raw)
    important=[]
    for word in tokens:
        if len(word)>=4 and word not in important and word not in getattr(pexels_media,"STOP",set()):
            important.append(word)
    variants=[]
    def add(q):
        q=" ".join(q.split()).strip()
        if q and q not in variants: variants.append(q)
    base_phrases=[]
    for phrase in (focus,must_text,action):
        phrase=" ".join(re.findall(r"[a-z0-9]+",phrase))
        if phrase: base_phrases.append(phrase)

    # 1. Explicit state queries first. These are the highest-value queries for
    # beats where the exact sentence describes an action that stock rarely tags.
    lowraw=raw.lower()
    for key,aliases in _STATE_ALIASES.items():
        if key in lowraw:
            for alias in aliases: add(alias)

    # 2. Normal noun aliases and focus/action combinations.
    for phrase in base_phrases:
        low=phrase.lower()
        for key,aliases in _ALIASES.items():
            if key in low:
                for alias in aliases[:3]: add(low.replace(key,alias)[:90])
        add(low[:90])

    alias_hits=[]
    for key,aliases in _ALIASES.items():
        if key in lowraw: alias_hits.extend(aliases[:3])
    actions=[]
    for a in getattr(pexels_media,"ACTIONS",set()):
        if a in lowraw: actions.append(a)
    for noun in alias_hits[:8]:
        for act in actions[:3]: add(f"{noun} {act}")
        add(noun)

    # 3. Always inject the most useful physical-state combinations when the
    # story is about loose wires/earbuds. This avoids generic pocket results.
    if any(x in lowraw for x in ("earbud","earphone","headphone")) and any(x in lowraw for x in ("tangle","tangled","knot","knotted","cord","wire")):
        for q in ("tangled earbuds","tangled earphones","earphones tangled knot","earbuds tangled cord","tangled headphone wires"):
            add(q)

    if important:
        add(" ".join(important[:5]))
        add(" ".join(important[:8]))
    # Keep explicit state queries ahead of noisy full-sentence queries.
    return variants[:8] or pexels_media.queries(scene,visual)

def _install_strict_selector(pexels_media):
    if getattr(pexels_media,"_mint_selector_v6",False): return
    def select(scene,visual,excluded_pages=None):
        excluded_pages=excluded_pages or set()
        if not pexels_media.headers(): return None
        qs=_expand_queries(pexels_media,scene,visual)
        required=pexels_media.tokens(_text(scene,visual))
        actions=pexels_media.action_tokens(_text(scene,visual))
        videos=[]
        for q in qs:
            videos.extend(pexels_media.search("videos/search",q,{"orientation":"portrait","size":"medium"}))
        videos=pexels_media._dedupe(videos,"video",excluded_pages)
        videos.sort(key=lambda x:pexels_media._heuristic_score(x,required,actions,"video"),reverse=True)
        print(f"   🔎 Pexels video queries: {len(qs)} | candidates: {len(videos)}")
        selected=pexels_media._gemini_rank_candidates(scene,visual,videos[:12],"video") if videos else []
        for item in selected:
            if item.get("_gemini_pass"):
                link=pexels_media._video_download_url(item)
                if link:
                    return {"kind":"video","video":link,"page":item.get("url",""),"photographer":(item.get("user") or {}).get("name","") or "","score":int(item.get("_gemini_score",0)),"qc_reason":item.get("_gemini_reason","") ,"query":" | ".join(qs[:5])}
        photos=[]
        for q in qs:
            photos.extend(pexels_media.search("search",q,{"orientation":"portrait","size":"large"}))
        photos=pexels_media._dedupe(photos,"photo",excluded_pages)
        photos.sort(key=lambda x:pexels_media._heuristic_score(x,required,actions,"photo"),reverse=True)
        print(f"   🔎 Pexels photo candidates: {len(photos)}")
        selected=pexels_media._gemini_rank_candidates(scene,visual,photos[:12],"photo") if photos else []
        for item in selected:
            if item.get("_gemini_pass"):
                src=item.get("src") or {}
                link=src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
                if link:
                    return {"kind":"photo","photo":link,"page":item.get("url",""),"photographer":item.get("photographer","") or "","score":int(item.get("_gemini_score",0)),"qc_reason":item.get("_gemini_reason","") ,"query":" | ".join(qs[:5])}
        return None
    pexels_media._select=select
    pexels_media._mint_selector_v6=True

def _assert_complete(groups):
    if len(groups)!=7: raise RuntimeError(f"Media contract failed: expected 7 scene groups, found {len(groups)}")
    for si,paths in enumerate(groups,1):
        if len(paths)!=2: raise RuntimeError(f"Media contract failed: Scene {si} has {len(paths)} paths")
        if any(not os.path.exists(p) for p in paths): raise RuntimeError(f"Media contract failed: Scene {si} has missing assets")

def patch_media_selection(media):
    original_generate=media.generate_media
    if getattr(original_generate,"_mint_media_policy_v6",False): return
    import pexels_media
    _install_strict_selector(pexels_media)
    def generate_media(script,output_dir,config,gim):
        groups=original_generate(script,output_dir,config,gim)
        _assert_complete(groups)
        with open(os.path.join(output_dir,"media_manifest.json"),"w",encoding="utf-8") as handle:
            json.dump({
                "provider_order":["pexels_verified_video","pexels_verified_photo"],
                "gemini_calls":"one_per_shot_for_pexels_only",
                "post_selection_gemini_qc":False,
                "pollinations":"disabled",
                "exact_scientific_visuals":"pexels_only",
                "heuristic_fallback":"disabled",
                "semantic_state_queries":"enabled",
            },handle,ensure_ascii=False,indent=2)
        print("🧠 Media policy v6: Pexels VIDEO → Pexels PHOTO | state-aware semantic queries | relevance-ranked | Pollinations disabled")
        return groups
    generate_media._mint_media_policy_v6=True
    media.generate_media=generate_media
