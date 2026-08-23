"""Media-selection policy for Mint-YT-Factory.

Important production rule:
- Ordinary, literal real-world beats may use Pexels.
- Exact scientific/geometric beats must use the image generator because stock
  footage is usually a semantic near-match rather than the requested moment.
- Pexels gets ONE Gemini ranking call per shot, not one call per search query.
- If Gemini is unavailable/rate-limited, Pexels is rejected rather than falling
  back to a weak keyword/metadata match.
- We do not run another 14-image Gemini QC pass after selection; that duplicated
  calls and exhausted the free 15-requests/minute Gemini quota.
"""
from __future__ import annotations
import os,re,json

_CUSTOM_RE=re.compile(r"\b(?:square|triangular|triangle|cubic|cube|rectangular|hexagonal|pentagonal|wire[- ]frame|soap[- ]film|film under tension|molecular|molecule|cross[- ]section|microscopic|micro[- ]scale|membrane|surface tension|physics demonstration|experiment setup|exact geometry|geometric frame)\b",re.I)

def _text(scene,visual):
    return " ".join(str(x or "") for x in (visual.get("visual_focus"),visual.get("visual_action"),visual.get("must_show"),visual.get("spoken_line") or scene.get("narration")))

def _custom(scene,visual):return bool(_CUSTOM_RE.search(_text(scene,visual)))

def _install_strict_selector(pexels_media):
    if getattr(pexels_media,"_mint_selector_v4",False):return
    def select(scene,visual,excluded_pages=None):
        excluded_pages=excluded_pages or set()
        # These are the cases where the exact requested object/geometry/state is
        # the point of the shot. Do not waste Pexels/Gemini calls searching for a
        # square soap-film frame and then accept a building or basket.
        if _custom(scene,visual):
            print("   🧪 CUSTOM VISUAL: exact scientific/geometric beat → Pexels skipped")
            return None
        if not pexels_media.headers():return None
        qs=pexels_media.queries(scene,visual)
        videos=[];photos=[]
        for q in qs[:3]:
            videos.extend(pexels_media.search("videos/search",q,{"orientation":"portrait","size":"medium"}))
            photos.extend(pexels_media.search("search",q,{"orientation":"portrait","size":"large"}))
        videos=pexels_media._dedupe(videos,"video",excluded_pages);photos=pexels_media._dedupe(photos,"photo",excluded_pages)
        videos.sort(key=lambda x:pexels_media._heuristic_score(x,set(),set(),"video"),reverse=True);photos.sort(key=lambda x:pexels_media._heuristic_score(x,set(),set(),"photo"),reverse=True)
        # One visual-ranking request per shot. Never retry different Pexels queries
        # with separate Gemini calls.
        selected=pexels_media._gemini_rank_candidates(scene,visual,videos[:8],"video") if videos else []
        for item in selected:
            if item.get("_gemini_pass"):
                link=pexels_media._video_download_url(item)
                if link:return {"kind":"video","video":link,"page":item.get("url",""),"photographer":(item.get("user") or {}).get("name","") or "","score":int(item.get("_gemini_score",0)),"qc_reason":item.get("_gemini_reason","") ,"query":" | ".join(qs)}
        selected=pexels_media._gemini_rank_candidates(scene,visual,photos[:8],"photo") if photos else []
        for item in selected:
            if item.get("_gemini_pass"):
                src=item.get("src") or {};link=src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
                if link:return {"kind":"photo","photo":link,"page":item.get("url",""),"photographer":item.get("photographer","") or "","score":int(item.get("_gemini_score",0)),"qc_reason":item.get("_gemini_reason","") ,"query":" | ".join(qs)}
        # IMPORTANT: no heuristic fallback. A Gemini failure/429 means the stock
        # asset is not trusted, so generate a custom visual instead.
        return None
    pexels_media._select=select;pexels_media._mint_selector_v4=True

def _assert_complete(groups):
    if len(groups)!=7:raise RuntimeError(f"Media contract failed: expected 7 scene groups, found {len(groups)}")
    for si,paths in enumerate(groups,1):
        if len(paths)!=2:raise RuntimeError(f"Media contract failed: Scene {si} has {len(paths)} paths")
        if any(not os.path.exists(p) for p in paths):raise RuntimeError(f"Media contract failed: Scene {si} has missing assets")

def patch_media_selection(media):
    original_generate=media.generate_media
    if getattr(original_generate,"_mint_media_policy_v4",False):return
    import pexels_media
    _install_strict_selector(pexels_media)
    def generate_media(script,output_dir,config,gim):
        groups=original_generate(script,output_dir,config,gim);_assert_complete(groups)
        with open(os.path.join(output_dir,"media_manifest.json"),"w",encoding="utf-8") as handle:
            json.dump({
                "provider_order":["pexels_verified_video","pexels_verified_photo","pollinations_custom"],
                "gemini_calls":"one_per_shot_for_pexels_only",
                "post_selection_gemini_qc":False,
                "exact_scientific_visuals":"pollinations_custom",
                "heuristic_fallback":"disabled",
            },handle,ensure_ascii=False,indent=2)
        print("🧠 Media policy v4: exact visuals → FLUX | ordinary Pexels → one Gemini ranking | no weak fallback | no duplicate QC")
        return groups
    generate_media._mint_media_policy_v4=True;media.generate_media=generate_media
