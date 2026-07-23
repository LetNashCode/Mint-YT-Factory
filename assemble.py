import os
import random
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
    ImageClip,
    TextClip,
    afx,
    vfx,
)

FONT = "DejaVu-Sans-Bold"


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


def _animate(clip, duration):

    mode = random.choice([
        "zoom_in",
        "zoom_out",
        "left",
        "right",
        "up",
        "down",
    ])

    if mode == "zoom_in":
        return clip.fx(
            vfx.resize,
            lambda t: 1 + 0.08 * t / max(duration, 0.1),
        )

    if mode == "zoom_out":
        return clip.fx(
            vfx.resize,
            lambda t: 1.08 - 0.08 * t / max(duration, 0.1),
        )

    if mode == "left":
        return clip.set_position(
            lambda t: (
                -40 * t / max(duration, 0.1),
                "center",
            )
        )

    if mode == "right":
        return clip.set_position(
            lambda t: (
                40 * t / max(duration, 0.1),
                "center",
            )
        )

    if mode == "up":
        return clip.set_position(
            lambda t: (
                "center",
                -40 * t / max(duration, 0.1),
            )
        )

    return clip.set_position(
        lambda t: (
            "center",
            40 * t / max(duration, 0.1),
        )
    )


def assemble_video(
    script,
    audio_paths,
    image_paths,
    music_path,
    sfx_paths,
    config,
    out_path,
):

    size = tuple(config["video"]["resolution"])

    narration = AudioFileClip(audio_paths[0])

    total_duration = narration.duration

    total_scene_time = sum(
        scene.get("duration", 1)
        for scene in script["scene_plan"]
    )

    scale = total_duration / max(total_scene_time, 1)

    timeline = []

    current = 0

    for scene, image in zip(script["scene_plan"], image_paths):

        duration = scene.get("duration", 1) * scale

        if image and os.path.exists(image):

            clip = ImageClip(image).resize(height=size[1])

            if clip.w < size[0]:
                clip = clip.resize(width=size[0])

            clip = clip.crop(
                x_center=clip.w / 2,
                y_center=clip.h / 2,
                width=size[0],
                height=size[1],
            )

            clip = _animate(clip, duration)

        else:

            clip = ColorClip(
                size,
                color=(20, 20, 20),
            )

        clip = (
            clip
            .set_start(current)
            .set_duration(duration)
            .crossfadein(0.25)
            .crossfadeout(0.25)
        )

        timeline.append(clip)

        current += duration

    captions = _captions(
        audio_paths[0],
        size,
    )

    final = CompositeVideoClip(
        timeline + captions,
        size=size,
    ).set_duration(total_duration)

    # ---------------- Audio ----------------

    audio_tracks = [narration]

    if music_path and os.path.exists(music_path):

        bg = (
            AudioFileClip(music_path)
            .fx(
                afx.audio_loop,
                duration=final.duration,
            )
            .volumex(
                config["video"].get(
                    "music_volume",
                    0.18,
                )
            )
        )

        audio_tracks.append(bg)

    current = 0

    for scene, sfx in zip(script["scene_plan"], sfx_paths):

        if not os.path.exists(sfx):
            current += scene.get("duration", 1) * scale
            continue

        effect = (
            AudioFileClip(sfx)
            .set_start(current)
            .volumex(
                config["video"].get(
                    "sfx_volume",
                    0.75,
                )
            )
        )

        audio_tracks.append(effect)

        current += scene.get("duration", 1) * scale

    final = final.set_audio(
        CompositeAudioClip(audio_tracks)
    )

    # ---------------------------------------

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
