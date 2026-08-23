"""Production entrypoint for Mint-YT-Factory."""
from __future__ import annotations
import inspect,json,os,glob,re
from runtime_overrides import patch_continuation,patch_tts_result,patch_visuals,patch_story_style
from quality_overrides import patch_story_quality,patch_visual_diversity
from media_quality_overrides import patch_media_selection

MIN_NARRATION_SECONDS=35.0
MAX_SHORT_TTS_REGEN=2


def _canonical_teaser(topic:str)->str:
    text=re.sub(r"\s+"," ",str(topic or "").strip()).rstrip(".!?")
    return f"Then comes an even weirder question: {text}."


def _is_bad_future_sentence(sentence:str,current_topic:str)->bool:
    norm=re.sub(r"[^a-z0-9 ]+","",sentence.lower()).strip()
    canonical=re.sub(r"[^a-z0-9 ]+","",current_topic.lower()).strip()
    if canonical and canonical in norm:
        return False
    return bool(re.search(
        r"\b(?:speaking of|on a related note|that makes you wonder|that makes you ask|"
        r"another question|one more question|one more thing|which raises|which brings up|"
        r"that brings us to|related question|why do|why does|why are|why is|"
        r"coming next|next topic|next short|next video|stay tuned)\b",
        norm,
        re.I,
    ))


def _strip_future_teasers(narration:str,current_topic:str)->str:
    sentences=[x.strip() for x in re.split(r"(?<=[.!?])\s+",str(narration or "").strip()) if x.strip()]
    kept=[x for x in sentences if not _is_bad_future_sentence(x,current_topic)]
    return " ".join(kept).strip()


def _patch_tts_duration(main):
    from moviepy.editor import AudioFileClip
    original=main.synthesize_script
    if getattr(original,"_mint_duration_guard",False):return
    def synthesize(script,config,out_dir):
        current_next=((script.get("next_short") or {}).get("topic") or "").strip()
        current_teaser=((script.get("next_short") or {}).get("teaser") or "").strip()
        topic=str(script.get("topic","")).strip()
        for attempt in range(MAX_SHORT_TTS_REGEN+1):
            audio=original(script,config,out_dir);clip=AudioFileClip(audio)
            try:duration=float(clip.duration)
            finally:clip.close()
            print(f"🎯 TTS duration gate: {duration:.2f}s")
            if duration>=MIN_NARRATION_SECONDS:return audio
            if attempt>=MAX_SHORT_TTS_REGEN:raise RuntimeError(f"Narration remained too short after {MAX_SHORT_TTS_REGEN} regeneration attempts: {duration:.2f}s")
            feedback=(
                f"The previous narration rendered at {duration:.2f} seconds. Rewrite the entire current story so natural narration is at least {MIN_NARRATION_SECONDS:.0f} seconds. "
                "Add concrete everyday details, stronger escalation and a satisfying payoff. Do not pad with scientific filler. Aim for about 115-135 words before the final teaser. "
                "IMPORTANT: the final teaser is injected by the production system. Do not invent, change, or mention any future topic in the rewritten story."
            )
            candidate=main.generate_script(topic,config,None,extra_feedback=feedback)
            candidate["topic"]=script.get("topic",candidate.get("topic",topic))
            candidate["title"]=candidate.get("title",script.get("title",topic))
            if len(candidate.get("scene_plan") or [])!=7:raise RuntimeError("Audio-length regeneration produced an invalid 7-scene script.")
            preserved_next={"topic":current_next,"teaser":current_teaser or _canonical_teaser(current_next)}
            candidate["next_short"]=preserved_next
            scenes=candidate.get("scene_plan") or []
            if scenes:
                final_scene=scenes[-1]
                base=_strip_future_teasers(final_scene.get("narration") or "",current_next)
                if not base:base="And that is the strange part."
                final_scene["narration"]=(base.rstrip(".!?")+". "+preserved_next["teaser"]).strip()
                final_scene["subtitle_text"]=final_scene["narration"]
                final_scene["pause_after_ms"]=250
                final_scene["emotional_tone"]="satisfied"
                final_scene["music_cue"]="fade_out"
            script.clear();script.update(candidate)
            try:
                workdir=os.path.dirname(os.path.dirname(os.path.abspath(out_dir)))
                with open(os.path.join(workdir,"script.json"),"w",encoding="utf-8") as h:json.dump(script,h,indent=2,ensure_ascii=False)
                if hasattr(main,"write_continuation_manifest"):main.write_continuation_manifest(topic,current_next,"locked",workdir)
            except Exception as exc:print(f"⚠️ Could not refresh regenerated script artifact: {exc}")
        return audio
    synthesize._mint_duration_guard=True;main.synthesize_script=synthesize


def _unwrap_per_image_gemini_gate(generate_images_module):
    fn=getattr(generate_images_module,"generate_image",None)
    if not fn or not getattr(fn,"_mint_strict_gate",False):return
    try:
        original=inspect.getclosurevars(fn).nonlocals.get("old_generate")
        if original:
            generate_images_module.generate_image=original
            print("🧹 Removed per-image Gemini gate; quota-safe batch/policy checks remain")
    except Exception as exc:print(f"⚠️ Could not unwrap per-image Gemini gate: {exc}")


def _patch_pexels_media(main,generate_images_module):
    import pexels_media
    _unwrap_per_image_gemini_gate(generate_images_module)
    patch_media_selection(pexels_media)
    def generate(script,output_dir,config):
        return pexels_media.generate_media(script,output_dir,config,generate_images_module)
    main.generate_images=generate
    patch_visual_diversity(pexels_media)


def _patch_pexels_metadata(main):
    original=main.build_youtube_metadata
    def build(script):
        title,description=original(script)
        if script.get("_pexels_used"):
            description=(description+"\n\nVisuals provided by Pexels.")[:4500]
        return title,description
    main.build_youtube_metadata=build


def _patch_pexels_video_assembly():
    import assemble
    from moviepy.editor import VideoFileClip
    from moviepy.video.fx.all import loop
    original=assemble.build_animated_image
    if getattr(original,"_mint_pexels_video_support",False):return
    def build_animated_image(image_path,duration,frame_size,scene,visual):
        if not str(image_path).lower().endswith((".mp4",".mov",".webm")):
            return original(image_path,duration,frame_size,scene,visual)
        width,height=frame_size
        print(f"🎞️ Pexels VIDEO clip: {os.path.basename(image_path)}")
        clip=VideoFileClip(image_path,audio=False)
        try:
            clip=loop(clip,duration=duration) if clip.duration<duration else clip.subclip(0,duration)
            scale=max(width/clip.w,height/clip.h)
            clip=clip.resize(scale)
            crop_x=max(0,int((clip.w-width)/2));crop_y=max(0,int((clip.h-height)/2))
            return clip.crop(x1=crop_x,y1=crop_y,x2=crop_x+width,y2=crop_y+height).set_duration(duration).set_position("center")
        except Exception:
            clip.close();raise
    build_animated_image._mint_pexels_video_support=True
    assemble.build_animated_image=build_animated_image


def _patch_thumbnail_upload(main):
    original=main.upload_video
    if getattr(original,"_mint_thumbnail_support",False):return
    def upload(video_path,title,description,config):
        from thumbnail_builder import build_thumbnail
        workdir=os.path.dirname(video_path);script_path=os.path.join(workdir,"script.json");thumbnail_path=os.path.join(workdir,"thumbnail.jpg")
        try:
            with open(script_path,"r",encoding="utf-8") as handle:script=json.load(handle)
            media_paths=sorted(glob.glob(os.path.join(workdir,"visuals","*")))
            if not media_paths:raise RuntimeError("No visual assets found for thumbnail.")
            build_thumbnail(script,[media_paths],thumbnail_path)
            print(f"🖼️ Uploading with custom thumbnail: {thumbnail_path}")
            return original(video_path,title,description,config,thumbnail_path=thumbnail_path)
        except Exception as exc:
            print(f"⚠️ Thumbnail generation failed: {type(exc).__name__}: {exc}")
            print("ℹ️ Continuing with the video upload without a custom thumbnail.")
            return original(video_path,title,description,config)
    upload._mint_thumbnail_support=True;main.upload_video=upload


def main_entry():
    import main,generate_images
    patch_story_style();patch_story_quality(main);patch_tts_result(main);patch_visuals(generate_images)
    _patch_tts_duration(main)
    _patch_pexels_media(main,generate_images)
    _patch_pexels_metadata(main)
    _patch_pexels_video_assembly()
    _patch_thumbnail_upload(main)
    print("="*80);print("🧩 MINT-YT-FACTORY PRODUCTION MEDIA + STORY QUALITY v7.0");print("="*80)
    print("Visual provider: Pexels ONLY")
    print("Media order: Pexels verified VIDEO → Pexels verified PHOTO")
    print("AI image generation: DISABLED")
    print("Pollinations/FLUX: DISABLED")
    print("If Pexels cannot provide a relevant verified asset: production stops rather than using an unrelated fallback")
    print("Gemini: visual verification/ranking of Pexels candidates only")
    print("Thumbnail: story-specific Pexels visual asset + curiosity headline")
    print("Continuation: canonical next topic only — random future-topic mentions blocked")
    print("Pexels API key:","AVAILABLE" if os.environ.get("PEXELS_API_KEY") else "NOT CONFIGURED")
    print("Story: soft 100-145 words / TTS-authoritative 35-44 seconds")
    print("Captions: Whisper word timing → deterministic fallback if Whisper fails")
    print("TTS duration guard: ENABLED")
    print("="*80)
    main.run(dry_run=False)

if __name__=="__main__":main_entry()
