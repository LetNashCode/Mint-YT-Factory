"""Production entrypoint for Mint-YT-Factory.

Loads the existing runtime quality fixes, then adds the requested media cascade:
Pexels VIDEO -> Pexels PHOTO -> Pollinations FLUX.

Pexels videos are used as real moving clips in the final Short when a relevant
clip exists. Pexels photos are used when no relevant video exists. Pollinations
is the fallback when Pexels has no suitable media or the API is unavailable.
"""

from __future__ import annotations

import os

from runtime_overrides import (
    patch_continuation,
    patch_tts_result,
    patch_visuals,
    patch_story_style,
)


def _patch_pexels_media(main, generate_images_module):
    from pexels_media import generate_media

    def generate(script, output_dir, config):
        return generate_media(script, output_dir, config, generate_images_module)

    main.generate_images = generate


def _patch_pexels_metadata(main):
    original = main.build_youtube_metadata

    def build(script):
        title, description = original(script)
        if script.get("_pexels_used"):
            credit = "\n\nVisuals provided by Pexels: https://www.pexels.com"
            description = (description + credit)[:4500]
        return title, description

    main.build_youtube_metadata = build


def _patch_pexels_video_assembly():
    """Allow the existing 14-shot assembler to consume Pexels MP4 clips."""
    import os
    import assemble
    from moviepy.editor import VideoFileClip
    from moviepy.video.fx.all import loop

    original = assemble.build_animated_image
    if getattr(original, "_mint_pexels_video_support", False):
        return

    def build_animated_image(image_path, duration, frame_size, scene, visual):
        if not str(image_path).lower().endswith((".mp4", ".mov", ".webm")):
            return original(image_path, duration, frame_size, scene, visual)

        width, height = frame_size
        print(f"🎞️ Pexels VIDEO clip: {os.path.basename(image_path)}")
        clip = VideoFileClip(image_path, audio=False)

        if clip.duration < duration:
            clip = loop(clip, duration=duration)
        else:
            clip = clip.subclip(0, duration)

        scale = max(width / clip.w, height / clip.h)
        clip = clip.resize(scale)

        crop_x = max(0, int((clip.w - width) / 2))
        crop_y = max(0, int((clip.h - height) / 2))
        clip = clip.crop(
            x1=crop_x,
            y1=crop_y,
            x2=crop_x + width,
            y2=crop_y + height,
        )

        # Keep the natural motion of the stock clip. Applying artificial image
        # zoom/pan to a real video often looks worse and can expose crop edges.
        return clip.set_duration(duration).set_position("center")

    build_animated_image._mint_pexels_video_support = True
    assemble.build_animated_image = build_animated_image


def main_entry():
    import main
    import generate_images

    patch_story_style()
    patch_continuation(main)
    patch_tts_result(main)
    patch_visuals(generate_images)
    _patch_pexels_media(main, generate_images)
    _patch_pexels_metadata(main)
    _patch_pexels_video_assembly()

    print("=" * 80)
    print("🧩 MINT-YT-FACTORY PRODUCTION MEDIA CASCADE")
    print("=" * 80)
    print("1. Pexels video — preferred when a relevant clip exists")
    print("2. Pexels photo — used when no relevant video exists")
    print("3. Pollinations FLUX — fallback when Pexels has no suitable media")
    print("Pexels API key:", "AVAILABLE" if os.environ.get("PEXELS_API_KEY") else "NOT CONFIGURED — Pollinations fallback active")
    print("=" * 80)

    main.run(dry_run=False)


if __name__ == "__main__":
    main_entry()
