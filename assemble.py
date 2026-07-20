"""
Assembles the final 9:16 Short: visuals + narration audio + burned-in
captions + background music, synced item by item.
"""
import os
import shutil

import numpy as np
from moviepy.config import change_settings

# MoviePy's auto-detection of ImageMagick is unreliable on some Linux setups
# (including GitHub Actions runners) — locate and point it directly at the binary.
_imagemagick_path = shutil.which("convert") or shutil.which("magick")
if _imagemagick_path:
    change_settings({"IMAGEMAGICK_BINARY": _imagemagick_path})

from moviepy.audio.AudioClip import AudioArrayClip
from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ColorClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    concatenate_audioclips,
    concatenate_videoclips,
    afx,
)

# Captions are shown in Hinglish (Roman script), so a plain Latin font works
# fine — no need to hunt for a Devanagari font anymore.
_LATIN_FONT = "DejaVu-Sans-Bold"


def _padded_audio(audio_clip, pad_seconds=0.4):
    """Appends a short block of true silence to an audio clip. This avoids a
    known MoviePy issue where reading right up to (or past) a clip's exact
    duration during concatenation throws an IOError from tiny floating-point
    rounding differences."""
    fps = audio_clip.fps or 44100
    n_samples = max(1, int(pad_seconds * fps))
    channels = 2 if getattr(audio_clip, "nchannels", 1) == 2 else 1
    silence_array = np.zeros((n_samples, channels))
    silence = AudioArrayClip(silence_array, fps=fps)
    return concatenate_audioclips([audio_clip, silence])


def _fit_portrait(clip, size):
    w, h = size
    clip = clip.resize(height=h) if clip.h / clip.w < h / w else clip.resize(width=w)
    clip = clip.crop(
        x_center=clip.w / 2, y_center=clip.h / 2, width=w, height=h
    )
    return clip


def _caption_caption_clips(caption_text: str, duration: float, config: dict, video_size):
    """
    TikTok/Shorts style captions:
    - 2 words at a time
    - Bigger font
    - Higher position
    - Fade in/out
    """

    font_size = int(config["video"]["captions"]["font_size"] * 1.25)

    w, h = video_size

    words = caption_text.upper().split()

    GROUP_SIZE = 2

    groups = [
        " ".join(words[i:i + GROUP_SIZE])
        for i in range(0, len(words), GROUP_SIZE)
    ]

    if not groups:
        return []

    segment_duration = duration / len(groups)

    clips = []

    current_time = 0

    for group in groups:

        txt = (
            TextClip(
                group,
                fontsize=font_size,
                color="white",
                font=_LATIN_FONT,
                method="caption",
                size=(int(w * 0.82), None),
                stroke_color="black",
                stroke_width=5,
                align="center",
            )
            .set_position(("center", h * 0.73))
            .set_start(current_time)
            .set_duration(segment_duration)
            .crossfadein(0.08)
            .crossfadeout(0.08)
        )

        clips.append(txt)

        current_time += segment_duration

    return clips


def _build_item_clip(visual_path, audio_path, rank, name, caption_text, config):
    video_size = tuple(config["video"]["resolution"])
    raw_audio = AudioFileClip(audio_path)
    audio = _padded_audio(raw_audio, pad_seconds=0.4)
    duration = audio.duration

    if visual_path and os.path.exists(visual_path):
        base = VideoFileClip(visual_path).without_audio()
        if base.duration < duration:
            base = base.loop(duration=duration)
        else:
            base = base.subclip(0, duration)
        base = _fit_portrait(base, video_size)
    else:
        # Fallback: solid dark background if no stock clip was found
        base = ColorClip(video_size, color=(10, 10, 15)).set_duration(duration)

    rank_label = TextClip(
        f"#{rank}",
        fontsize=110,
        color="white",
        font=_LATIN_FONT,
        stroke_color="black",
        stroke_width=4,
    ).set_position(("center", video_size[1] * 0.08)).set_duration(duration)

    caption_clips = _caption_caption_clips(caption_text, duration, config, video_size)

    composite = CompositeVideoClip([base, rank_label, *caption_clips], size=video_size)
    composite = composite.set_audio(audio.set_start(0))
    composite = composite.set_duration(duration)
    return composite


def assemble_video(script: dict, audio_paths: list, visual_paths: list, config: dict, out_path: str) -> str:
    clips = []
    for item, audio_path, visual_path in zip(script["items"], audio_paths, visual_paths):
        # Prefer the Hinglish (Roman-script) version for on-screen captions;
        # fall back to the Devanagari narration if it's ever missing.
        caption_text = item.get("narration_hinglish") or item["narration"]
        clip = _build_item_clip(
            visual_path, audio_path, item["rank"], item["name"], caption_text, config
        )
        clips.append(clip)

    final = concatenate_videoclips(clips, method="compose")

    music_path = config["video"].get("background_music")
    if music_path and os.path.exists(music_path):
        music = AudioFileClip(music_path).fx(afx.audio_loop, duration=final.duration)
        music = music.volumex(config["video"].get("music_volume", 0.12))
        mixed = CompositeAudioClip([final.audio, music])
        final = final.set_audio(mixed)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    final.write_videofile(
        out_path,
        fps=config["video"].get("fps", 30),
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
    )
    return out_path
