"""Production entrypoint for Mint-YT-Factory."""
from __future__ import annotations
import os
from runtime_overrides import patch_continuation,patch_tts_result,patch_visuals,patch_story_style
from quality_overrides import patch_story_quality,patch_visual_diversity
from media_quality_overrides import patch_media_selection

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

def main_entry():
    import main,generate_images
    patch_story_style(); patch_story_quality(main); patch_continuation(main); patch_tts_result(main); patch_visuals(generate_images)
    _patch_pexels_media(main,generate_images); _patch_pexels_metadata(main); _patch_pexels_video_assembly()
    print("="*80); print("🧩 MINT-YT-FACTORY PRODUCTION MEDIA + STORY QUALITY v3"); print("="*80)
    print("Pexels: relevant video → relevant photo → Pollinations FLUX")
    print("Media: portrait preference, useful duration, no duplicate Pexels assets")
    print("Story: 125-140 words / approximately 38-43 seconds")
    print("Captions: meaningful-word emphasis")
    print("Pexels API key:","AVAILABLE" if os.environ.get("PEXELS_API_KEY") else "NOT CONFIGURED — Pollinations fallback active")
    print("="*80)
    main.run(dry_run=False)

if __name__=="__main__": main_entry()
