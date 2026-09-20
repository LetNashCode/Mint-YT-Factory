"""Full-frame portrait alignment for video media.

All source videos are scaled to cover the complete 9:16 canvas and centrally
cropped. This prevents landscape footage from appearing as a small contained
rectangle with black bars inside a Short.
"""
from __future__ import annotations

import math
import os

from moviepy.editor import VideoFileClip, concatenate_videoclips


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}


def _is_video(path):
    return os.path.splitext(str(path))[1].lower() in VIDEO_EXTENSIONS


def install(assemble_module):
    """Patch the live assembly module once with full-frame video cropping."""
    if getattr(assemble_module, "_mint_portrait_alignment", False):
        return

    original_make_visual_clip = assemble_module.make_visual_clip
    original_build_animated_image = assemble_module.build_animated_image

    def make_visual_clip(media_path, frame_size, duration):
        if not _is_video(media_path):
            return original_make_visual_clip(media_path, frame_size, duration)

        width, height = frame_size
        clip = VideoFileClip(media_path, audio=False)
        if not clip.duration or clip.duration <= 0:
            clip.close()
            raise RuntimeError(f"Visual video has invalid duration: {media_path}")

        original_duration = float(clip.duration)
        if original_duration < duration:
            repeats = max(1, int(math.ceil(duration / original_duration)))
            parts = [clip.subclip(0, original_duration) for _ in range(repeats)]
            clip = concatenate_videoclips(parts, method="chain").subclip(0, duration)
        else:
            clip = clip.subclip(0, min(duration, original_duration))

        # Cover the complete portrait frame; never add a black background.
        scale = max(width / float(clip.w), height / float(clip.h))
        covered = clip.resize(scale)
        crop_x = max(0, int((covered.w - width) / 2))
        crop_y = max(0, int((covered.h - height) / 2))
        aligned = covered.crop(
            x1=crop_x,
            y1=crop_y,
            x2=crop_x + width,
            y2=crop_y + height,
        ).set_duration(duration)
        print(f"   🎞️ VIDEO COVER-CROP: {os.path.basename(media_path)} | full 9:16 frame")
        return aligned

    def build_animated_image(media_path, duration, frame_size, scene, visual):
        # Keep video framing stable after the cover crop. The crop itself fills
        # the complete portrait canvas, so no containment layer can introduce bars.
        if _is_video(media_path):
            return make_visual_clip(media_path, frame_size, duration).set_position("center")
        return original_build_animated_image(media_path, duration, frame_size, scene, visual)

    assemble_module.make_visual_clip = make_visual_clip
    assemble_module.build_animated_image = build_animated_image
    assemble_module._mint_portrait_alignment = True
    print("🛡️ Portrait video alignment: ACTIVE | cover-crop/full-frame mode")
