"""Production entrypoint for Mint-YT-Factory.

ACTIVE MEDIA ARCHITECTURE
--------------------------
Gemini Visual/Search Director -> Pexels VIDEO -> Pixabay VIDEO fallback ->
Pexels PHOTO -> Pixabay PHOTO -> Gemini candidate visual verification -> assembly.
"""
from __future__ import annotations

import json
import os
import re

from runtime_overrides import patch_continuation, patch_tts_result
from quality_overrides import patch_story_quality
from story_quality_gate import patch_story_generation

MIN_NARRATION_SECONDS = 35.0
MAX_NARRATION_SECONDS = 43.90
MAX_SHORT_TTS_REGEN = 2


def _patch_visual_search_plan():
    import pexels_media
    original = pexels_media.build_search_plan
    if getattr(original, "_mint_diverse_queries", False):
        return
    REMOVE_WORDS = {"single", "one", "macro", "close", "closeup", "close-up", "extreme", "cinematic", "glossy", "isolated", "dark", "moody", "dramatic", "beautiful", "photography", "photograph", "photo", "slow", "motion", "detailed", "detail", "realistic", "natural", "background", "slate", "surface", "shiny", "polished", "high", "quality", "professional", "shot", "footage"}
    def simplify(value: str) -> str:
        words = re.findall(r"[A-Za-z0-9'-]+", str(value or "").lower())
        return " ".join(w for w in words if w not in REMOVE_WORDS)[:160].strip()
    def build(script):
        plan = original(script)
        for scene_plan in plan:
            for directed in scene_plan:
                original_queries = [str(q).strip() for q in directed.get("queries", []) if str(q).strip()]
                focus = str(directed.get("visual_focus") or directed.get("casting_brief") or "").strip()
                action = str(directed.get("visual_action") or "").strip()
                must = [str(x).strip() for x in directed.get("must_match", []) if str(x).strip()]
                candidates = original_queries[:2]
                if focus and action: candidates.append(f"{simplify(focus)} {simplify(action)}".strip())
                elif focus: candidates.append(simplify(focus))
                elif must: candidates.append(simplify(must[0]))
                if must: candidates.append(simplify(must[0]))
                if len(must) > 1: candidates.append(simplify(" ".join(must[:2])))
                final=[]; seen=set()
                for query in candidates + original_queries[2:]:
                    query=re.sub(r"\s+", " ", query).strip()
                    if len(query.split()) < 2: continue
                    key=query.lower()
                    if key not in seen:
                        seen.add(key); final.append(query)
                    if len(final)>=4: break
                if len(final)<2: raise RuntimeError(f"Visual search plan became too narrow for Scene {directed.get('scene')} Shot {directed.get('shot')}.")
                directed["queries"]=final[:4]
                print(f"   🔎 Diversified stock queries Scene {directed.get('scene')} Shot {directed.get('shot')}: " + " | ".join(directed["queries"]))
        return plan
    build._mint_diverse_queries=True
    pexels_media.build_search_plan=build


def _patch_tts_duration(main):
    from moviepy.editor import AudioFileClip
    original=main.synthesize_script
    if getattr(original,"_mint_duration_guard",False): return
    def synthesize(script,config,out_dir):
        current_next=((script.get("next_short") or {}).get("topic") or "").strip(); topic=str(script.get("topic","")).strip()
        for attempt in range(MAX_SHORT_TTS_REGEN+1):
            audio=original(script,config,out_dir); clip=AudioFileClip(audio)
            try: duration=float(clip.duration)
            finally: clip.close()
            print(f"🎯 TTS duration gate: {duration:.2f}s")
            if MIN_NARRATION_SECONDS<=duration<=MAX_NARRATION_SECONDS: return audio
            if attempt>=MAX_SHORT_TTS_REGEN: raise RuntimeError(f"Narration duration remained outside production range after {MAX_SHORT_TTS_REGEN} regeneration attempts: {duration:.2f}s (allowed {MIN_NARRATION_SECONDS:.2f}-{MAX_NARRATION_SECONDS:.2f}s).")
            direction=(f"The previous narration rendered at {duration:.2f} seconds and is TOO LONG. Rewrite it shorter. Target 90-100 words before the locked continuation. Remove filler, repeated explanations and extra setup while keeping the hook, escalation and payoff." if duration>MAX_NARRATION_SECONDS else f"The previous narration rendered at {duration:.2f} seconds and is TOO SHORT. Target 100-110 words before the locked continuation. Add concrete everyday details and escalation, not scientific filler.")
            feedback=f"{direction} IMPORTANT: current topic is {topic!r}. Do not introduce another mystery. Scene 7 must contain only the payoff for {topic!r}, followed by the exact locked continuation topic {current_next!r}. Do not invent a different teaser."
            candidate=main.generate_script(topic,config,None,extra_feedback=feedback); candidate["topic"]=topic; candidate["next_short"]=dict(candidate.get("next_short") or {}); candidate["next_short"]["topic"]=current_next
            candidate,locked_next=main.lock_next_topic(candidate,topic)
            if locked_next!=current_next: raise RuntimeError(f"TTS regeneration changed locked next topic: {locked_next!r} != {current_next!r}")
            script.clear(); script.update(candidate)
            workdir=os.path.dirname(os.path.dirname(os.path.abspath(out_dir)))
            try:
                with open(os.path.join(workdir,"script.json"),"w",encoding="utf-8") as handle: json.dump(script,handle,indent=2,ensure_ascii=False)
                if hasattr(main,"write_continuation_manifest"): main.write_continuation_manifest(topic,current_next,"locked",workdir)
            except Exception as exc: print(f"⚠️ Could not refresh regenerated script artifact: {exc}")
        return audio
    synthesize._mint_duration_guard=True; main.synthesize_script=synthesize


def _patch_assemble_video_media():
    import assemble
    from moviepy.editor import VideoFileClip,vfx
    original=assemble.make_image_clip
    if getattr(original,"_mint_media_v3",False): return
    video_ext={".mp4",".mov",".m4v",".webm",".avi",".mkv"}
    def make_media_clip(path,frame_size):
        if os.path.splitext(str(path))[1].lower() not in video_ext: return original(path,frame_size)
        width,height=frame_size; print(f"🎞️ Assembler: stock VIDEO asset → VideoFileClip: {os.path.basename(str(path))}")
        clip=VideoFileClip(path,audio=False); scale=max(width/clip.w,height/clip.h); clip=clip.resize(scale); crop_x=max(0,int((clip.w-width)/2)); crop_y=max(0,int((clip.h-height)/2)); clip=clip.crop(x1=crop_x,y1=crop_y,x2=crop_x+width,y2=crop_y+height)
        return clip.fx(vfx.loop,duration=10.0)
    make_media_clip._mint_media_v3=True; assemble.make_image_clip=make_media_clip; print("🛡️ Assembly media compatibility: stock MP4 → VideoFileClip + safe loop")


def _install_media_pipeline(main):
    import stock_media
    import stock_media_overrides
    stock_media_overrides.install()
    main.generate_images=stock_media.generate_media
    print("🎯 Media pipeline: Gemini Visual/Search Director → Pexels → Pixabay stock fallback")
    print("🛡️ Gemini visual verification: ENABLED")
    print("🛡️ Candidate media sent to Gemini: ENABLED")
    print("🚫 AI image generation: DISABLED")
    print("🚫 Pollinations/FLUX: REMOVED")
    print("🔎 Stock search strategy: literal + object + action/context + simplified queries")


def main_entry():
    import main
    patch_continuation(main); patch_tts_result(main); patch_story_quality(main); patch_story_generation(main); _patch_visual_search_plan(); _patch_tts_duration(main); _patch_assemble_video_media(); _install_media_pipeline(main)
    print("="*80); print("🚀 MINT-YT-FACTORY STARTED"); print("="*80)
    print("Script: entertainment-first + hard coherence gate + low-jargon contract")
    print("Visual/Search Director: Gemini")
    print("Media priority: Pexels VIDEO → Pixabay VIDEO → Pexels PHOTO → Pixabay PHOTO")
    print("Visual verification: ENABLED — Gemini inspects top stock candidates")
    print("Visual verification threshold: 7.5/10")
    print("Visual verification candidate pool: up to 6 per provider/shot")
    print("Stock search: diversified retrieval; exact cinematic phrasing is not required")
    print("AI image generation: DISABLED"); print("Pollinations/FLUX: REMOVED"); print("Fallback: stock provider fallback only; no unrelated or AI visual fallback")
    print("Continuation: one locked next topic, final sentence only")
    print("Pexels API key:","AVAILABLE" if os.environ.get("PEXELS_API_KEY") else "NOT CONFIGURED")
    print("Pixabay API key:","AVAILABLE" if os.environ.get("PIXABAY_API_KEY") else "NOT CONFIGURED")
    print("Gemini API key:","AVAILABLE" if os.environ.get("GEMINI_API_KEY") else "NOT CONFIGURED")
    print("Story: TTS-authoritative 35-43.9 seconds"); print("Captions: Whisper word timing → deterministic fallback if Whisper fails"); print("TTS duration guard: ENABLED"); print("="*80)
    main.run(dry_run=False)

if __name__=="__main__": main_entry()
