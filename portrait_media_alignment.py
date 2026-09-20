"""Full-frame portrait alignment for Story Shorts source videos.

Landscape archive/stock videos are contained inside the 9:16 canvas instead of
being center-cropped. Video motion effects are disabled for contained videos so
important subjects remain fully visible.
"""
from __future__ import annotations

import math
import os

from moviepy.editor import VideoFileClip, ColorClip, CompositeVideoClip, concatenate_videoclips


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}


def _is_video(path):
    return os.path.splitext(str(path))[1].lower() in VIDEO_EXTENSIONS


def install(assemble_module):
    """Patch the live assembly module once."""
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

        # Contain the entire source frame. Never crop the person or the edges.
        scale = min(width / float(clip.w), height / float(clip.h))
        contained = clip.resize(scale)
        background = ColorClip(size=(width, height), color=(0, 0, 0)).set_duration(duration)
        aligned = CompositeVideoClip(
            [background, contained.set_position(("center", "center"))],
            size=(width, height),
        ).set_duration(duration)
        print(f"   🎞️ VIDEO CONTAIN: {os.path.basename(media_path)} | full frame preserved")
        return aligned

    def build_animated_image(media_path, duration, frame_size, scene, visual):
        # Contained videos must not receive zoom/pan/rotation transforms, since
        # those transforms can crop the subject after it has been aligned.
        if _is_video(media_path):
            return make_visual_clip(media_path, frame_size, duration).set_position("center")
        return original_build_animated_image(media_path, duration, frame_size, scene, visual)

    assemble_module.make_visual_clip = make_visual_clip
    assemble_module.build_animated_image = build_animated_image
    assemble_module._mint_portrait_alignment = True
    print("🛡️ Portrait video alignment: ACTIVE | contain/full-frame/no-crop mode")
