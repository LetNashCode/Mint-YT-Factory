# assemble.py (Whisper version)
import os
import shutil

from whisper_align import transcribe
from moviepy.config import change_settings

_im = shutil.which("convert") or shutil.which("magick")
if _im:
    change_settings({"IMAGEMAGICK_BINARY": _im})

from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ColorClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
    afx,
)

FONT = "DejaVu-Sans-Bold"


def _fit(c, size):
    w, h = size
    c = c.resize(height=h) if c.h / c.w < h / w else c.resize(width=w)
    return c.crop(x_center=c.w / 2, y_center=c.h / 2, width=w, height=h)


def _caption(audio_path, size):
    w, h = size
    words = transcribe(audio_path)
    clips = []

    for item in words:
        clips.append(
            TextClip(
                item["word"].upper(),
                font=FONT,
                fontsize=82,
                color="white",
                stroke_color="black",
                stroke_width=4,
            )
            .set_position(("center", h * 0.65))
            .set_start(item["start"])
            .set_duration(max(0.05, item["end"] - item["start"]))
        )

    return clips


def assemble_video(script, audio_paths, visual_paths, config, out_path):
    size = tuple(config["video"]["resolution"])

    narration = AudioFileClip(audio_paths[0])
    total = narration.duration

    seg = total / max(1, len(visual_paths))
    video_clips = []

    for i, vp in enumerate(visual_paths):
        start = i * seg

        if vp and os.path.exists(vp):
            base = VideoFileClip(vp).without_audio()
            if base.duration < seg:
                base = base.loop(duration=seg)
            else:
                base = base.subclip(0, seg)
            base = _fit(base, size)
        else:
            base = ColorClip(size, color=(15, 15, 15)).set_duration(seg)

        base = base.set_start(start).set_duration(seg)
        video_clips.append(base)

    captions = _caption(audio_paths[0], size)

    final = CompositeVideoClip(
        video_clips + captions,
        size=size
    ).set_duration(total).set_audio(narration)

    music = config["video"].get("background_music")
    if music and os.path.exists(music):
        bg = AudioFileClip(music).fx(
            afx.audio_loop,
            duration=final.duration
        ).volumex(0.08)

        final = final.set_audio(
            CompositeAudioClip([final.audio, bg])
        )

    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    final.write_videofile(
        out_path,
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
    )
