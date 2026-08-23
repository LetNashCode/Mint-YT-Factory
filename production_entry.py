"""Production entrypoint for Mint-YT-Factory."""
from __future__ import annotations
import json
import os
from runtime_overrides import patch_continuation,patch_tts_result,patch_visuals,patch_story_style
from quality_overrides import patch_story_quality,patch_visual_diversity
from media_quality_overrides import patch_media_selection

MIN_NARRATION_SECONDS=35.0
MAX_SHORT_TTS_REGEN=2

def _patch_tts_duration(main):
    """Make real TTS duration authoritative without making main.py brittle.

    The story word count is only a soft hint. If the generated audio is shorter
    than the production target, regenerate the story before visuals are created.
    The already-locked continuation topic is preserved so spoken and queued
    continuation state cannot drift.
    """
    from moviepy.editor import AudioFileClip
    original=main.synthesize_script
    if getattr(original,"_mint_duration_guard",False): return

    def synthesize(script,config,out_dir):
        current_next=((script.get("next_short") or {}).get("topic") or "").strip()
        topic=str(script.get("topic","")).strip()
        last_duration=0.0
        for attempt in range(MAX_SHORT_TTS_REGEN+1):
            audio=original(script,config,out_dir)
            clip=AudioFileClip(audio)
            try: last_duration=float(clip.duration)
            finally: clip.close()
            print(f"🎯 TTS duration gate: {last_duration:.2f}s")
            if last_duration>=MIN_NARRATION_SECONDS:
                return audio
            if attempt>=MAX_SHORT_TTS_REGEN:
                raise RuntimeError(f"Narration remained too short after {MAX_SHORT_TTS_REGEN} regeneration attempts: {last_duration:.2f}s")
            print(f"⚠️ Narration too short ({last_duration:.2f}s). Regenerating story before visual generation.")
            feedback=(
                f"The previous narration rendered at {last_duration:.2f} seconds. "
                f"Rewrite the entire current story so natural narration is at least {MIN_NARRATION_SECONDS:.0f} seconds. "
                "Add concrete everyday details, a stronger escalation and a satisfying payoff. "
                "Do not pad with scientific filler. Aim for about 115-135 words before the final teaser."
            )
            candidate=main.generate_script(topic,config,None,extra_feedback=feedback)
            # Preserve the already locked continuation exactly. Only the current
            # story body is allowed to change during an audio-length retry.
            candidate["next_short"]=script.get("next_short",{})
            candidate["topic"]=script.get("topic",candidate.get("topic",topic))
            candidate["title"]=candidate.get("title",script.get("title",topic))
            scenes=candidate.get("scene_plan") or []
            if not isinstance(scenes,list) or len(scenes)!=7:
                raise RuntimeError("Audio-length regeneration produced an invalid 7-scene script.")
            script.clear(); script.update(candidate)
            script["next_short"]["topic"]=current_next
            # Keep the saved artifact synchronized with the regenerated story.
            try:
                workdir=os.path.dirname(os.path.dirname(os.path.abspath(out_dir)))
                with open(os.path.join(workdir,"script.json"),"w",encoding="utf-8") as handle:
                    json.dump(script,handle,indent=2,ensure_ascii=False)
                if hasattr(main,"write_continuation_manifest"):
                    main.write_continuation_manifest(topic,current_next,"locked",workdir)
            except Exception as save_error:
                print(f"⚠️ Could not refresh regenerated script artifact: {save_error}")
        return audio

    synthesize._mint_duration_guard=True
    main.synthesize_script=synthesize

def _patch_pexels_media(main,generate_images_module):
    import pexels_media
    patch_media_selection(pexels_media)
    def generate(script,output_dir,config): return pexels_media.generate_media(script,output_dir,config,generate_images_module)
    main.generate_images=generate
    patch_visual_diversity(pexels_media)

def _patch_pexels_metadata(main):
    original=main.build_youtube_metadata
    def build(script):
        title,description=original(script)
        if script.get("_pexels_used"):
            description=(description+"\n\nVisuals provided by Pexels: https://www.pexels.com")[:4500]
        return title,description
    main.build_youtube_metadata=build

def _patch_pexels_video_assembly():
    import os,assemble
    from moviepy.editor import VideoFileClip
    from moviepy.video.fx.all import loop
    original=assemble.build_animated_image
    if getattr(original,"_mint_pexels_video_support",False): return
    def build_animated_image(image_path,duration,frame_size,scene,visual):
        if not str(image_path).lower().endswith((".mp4",".mov",".webm")): return original(image_path,duration,frame_size,scene,visual)
        width,height=frame_size; print(f"🎞️ Pexels VIDEO clip: {os.path.basename(image_path)}")
        clip=VideoFileClip(image_path,audio=False)
        clip=loop(clip,duration=duration) if clip.duration<duration else clip.subclip(0,duration)
        scale=max(width/clip.w,height/clip.h); clip=clip.resize(scale)
        crop_x=max(0,int((clip.w-width)/2)); crop_y=max(0,int((clip.h-height)/2))
        return clip.crop(x1=crop_x,y1=crop_y,x2=crop_x+width,y2=crop_y+height).set_duration(duration).set_position("center")
    build_animated_image._mint_pexels_video_support=True
    assemble.build_animated_image=build_animated_image

def _patch_pexels_metadata(main):
    original=main.build_youtube_metadata
    def build(script):
        title,description=original(script)
        if script.get("_pexels_used"):
            description=(description+"\n\nVisuals provided by Pexels: https://www.pexels.com")[:4500]
        return title,description
    main.build_youtube_metadata=build

def main_entry():
    import main,generate_images
    patch_story_style(); patch_story_quality(main); patch_continuation(main); patch_tts_result(main); patch_visuals(generate_images)
    _patch_tts_duration(main)
    _patch_pexels_media(main,generate_images); _patch_pexels_metadata(main); _patch_pexels_video_assembly()
    print("="*80); print("🧩 MINT-YT-FACTORY PRODUCTION MEDIA + STORY QUALITY v3"); print("="*80)
    print("Pexels: relevant video → relevant photo → Pollinations FLUX")
    print("Media: portrait preference, useful duration, no duplicate Pexels assets")
    print("Story: soft 100-145 words / TTS-authoritative 35-44 seconds")
    print("Captions: meaningful-word emphasis")
    print("TTS duration guard: ENABLED")
    print("Pexels API key:","AVAILABLE" if os.environ.get("PEXELS_API_KEY") else "NOT CONFIGURED — Pollinations fallback active")
    print("="*80)
    main.run(dry_run=False)

if __name__=="__main__": main_entry()
