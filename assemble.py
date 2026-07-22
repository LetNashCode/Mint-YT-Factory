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
    afx,
    vfx,
)

FONT = "Montserrat-Black"


def _fit(clip, size):
    w, h = size

    if clip.h / clip.w < h / w:
        clip = clip.resize(height=h)
    else:
        clip = clip.resize(width=w)

    return clip.crop(
        x_center=clip.w / 2,
        y_center=clip.h / 2,
        width=w,
        height=h,
    )


def _motion(clip):
    return clip.fx(
        vfx.resize,
        lambda t: 1 + 0.05 * min(t / max(clip.duration, 0.1), 1),
    )


def _captions(audio_path, size):
    _, h = size

    words = transcribe(audio_path)

    clips = []

    for word in words:
        clips.append(
            TextClip(
                word["word"].upper(),
                font=FONT,
                fontsize=82,
                color="white",
                stroke_color="black",
                stroke_width=4,
            )
            .set_position(("center", h * 0.65))
            .set_start(word["start"])
            .set_duration(max(0.05, word["end"] - word["start"]))
        )

    return clips


def assemble_video(script, audio_paths, visual_paths, config, out_path):

    size = tuple(config["video"]["resolution"])

    narration = AudioFileClip(audio_paths[0])

    total_duration = narration.duration

    scene_total = sum(
        scene.get("duration", 1)
        for scene in script["scene_plan"]
    )

    scale = total_duration / max(scene_total, 1)

    timeline = []

    current_time = 0

    for scene, scene_clips in zip(script["scene_plan"], visual_paths):

        scene_duration = scene.get("duration", 1) * scale

        if not scene_clips:

            timeline.append(
                ColorClip(
                    size,
                    color=(15, 15, 15),
                )
                .set_start(current_time)
                .set_duration(scene_duration)
            )

            current_time += scene_duration
            continue

        clip_duration = scene_duration / len(scene_clips)

        for clip_path in scene_clips:

            if clip_path and os.path.exists(clip_path):

                clip = VideoFileClip(clip_path).without_audio()

                if clip.duration < clip_duration:
                    clip = clip.loop(duration=clip_duration)
                else:
                    clip = clip.subclip(0, clip_duration)

                clip = _fit(clip, size)
                clip = _motion(clip)

            else:

                clip = ColorClip(
                    size,
                    color=(15, 15, 15),
                ).set_duration(clip_duration)

            clip = (
                clip
                .set_start(current_time)
                .set_duration(clip_duration)                
            )

            timeline.append(clip)

            current_time += clip_duration

    captions = _captions(
        audio_paths[0],
        size,
    )

    final = CompositeVideoClip(
        timeline + captions,
        size=size,
    ).set_duration(total_duration)

    final = final.set_audio(narration)

    music = config["video"].get("background_music")

    if music and os.path.exists(music):

        bg = (
            AudioFileClip(music)
            .fx(
                afx.audio_loop,
                duration=final.duration,
            )
            .volumex(
                config["video"].get(
                    "music_volume",
                    0.08,
                )
            )
        )

        final = final.set_audio(
            CompositeAudioClip(
                [
                    final.audio,
                    bg,
                ]
            )
        )

    os.makedirs(
        os.path.dirname(out_path),
        exist_ok=True,
    )

    final.write_videofile(
        out_path,
        fps=config["video"].get("fps", 30),
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=2,
    )

    return out_path
