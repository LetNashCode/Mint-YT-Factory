import os
import math
import json

from whisper_align import transcribe
from moviepy.config import change_settings
import shutil as _shutil

_im = _shutil.which("convert") or _shutil.which("magick")

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

# ============================================================
# Constants / Defaults
# ============================================================

FONT = os.path.join(
    "assets",
    "fonts",
    "Poppins-ExtraBold.ttf",
)

CAPTION_FONT_SIZE = 66
CAPTION_COLOR = "white"
CAPTION_HIGHLIGHT_COLOR = "#FFD54A"
CAPTION_STROKE = "#222222"
CAPTION_STROKE_WIDTH = 2

OVERLAY_FONT_SIZE = 88
OVERLAY_STROKE_WIDTH = 6
OVERLAY_MAX_DURATION = 2.5
OVERLAY_FADE = 0.20

DEFAULT_SCENE_DURATION = 5.0
DEFAULT_CAMERA = "medium"
DEFAULT_ANIMATION = "hold"
DEFAULT_TRANSITION = "crossfade"
DEFAULT_SUBTITLE_STYLE = "lower_third"
DEFAULT_ZOOM_FACTOR = 1.08
DEFAULT_MOTION_SPEED = "medium"

DEFAULT_MUSIC_VOLUME = 0.12
DEFAULT_SFX_VOLUME = 0.80

CAPTION_GROUP_MIN_WORDS = 2
CAPTION_GROUP_MAX_WORDS = 4
# a gap this large between words forces a new caption group even
# if we haven't hit CAPTION_GROUP_MAX_WORDS yet
CAPTION_GROUP_MAX_GAP = 0.6

CAMERA_SCALES = {
    "macro": 1.35,
    "close_up": 1.22,
    "medium": 1.10,
    "wide": 1.00,
    "top_down": 1.05,
    "side": 1.12,
    "aerial": 0.95,
}

MOTION_MULTIPLIERS = {
    "slow": 0.5,
    "medium": 1.0,
    "fast": 1.5,
}

TRANSITION_ALIASES = {
    "cut": "hard_cut",
    "hard_cut": "hard_cut",
    "crossfade": "crossfade",
    "fade": "fade",
    "flash": "flash",
    "dissolve": "dissolve",
    "zoom": "zoom",
    "whip": "whip",
}

TRANSITION_DURATIONS = {
    "hard_cut": 0.0,
    "crossfade": 0.20,
    "fade": 0.35,
    "flash": 0.08,
    "dissolve": 0.50,
    "zoom": 0.25,
    "whip": 0.12,
}


# ============================================================
# Small safe-parsing helpers
#
# Every one of these takes possibly-missing / possibly-wrong-typed
# input from the Gemini-generated storyboard and returns a safe,
# defaulted value. Nothing here raises.
# ============================================================

def _safe_lower(value, default):
    try:
        return str(value).strip().lower()
    except Exception:
        return default


def _safe_float(value, default, min_value=None, max_value=None):
    try:
        result = float(value)
    except Exception:
        return default

    if math.isnan(result) or math.isinf(result):
        return default

    if min_value is not None:
        result = max(result, min_value)

    if max_value is not None:
        result = min(result, max_value)

    return result


def _safe_int(value, default, min_value=None):
    try:
        result = int(value)
    except Exception:
        return default

    if min_value is not None:
        result = max(result, min_value)

    return result


def get_scene_duration(scene):
    return _safe_float(
        scene.get("duration", DEFAULT_SCENE_DURATION),
        DEFAULT_SCENE_DURATION,
        min_value=0.1,
    )


def get_pause_after(scene):
    ms = _safe_float(scene.get("pause_after_ms", 0), 0, min_value=0)
    return ms / 1000.0


def get_camera(scene):
    cam = _safe_lower(scene.get("camera", DEFAULT_CAMERA), DEFAULT_CAMERA)
    return cam if cam in CAMERA_SCALES else DEFAULT_CAMERA


def get_animation(scene):
    return _safe_lower(scene.get("animation", DEFAULT_ANIMATION), DEFAULT_ANIMATION)


def get_zoom_factor(scene):
    return _safe_float(
        scene.get("zoom_factor", DEFAULT_ZOOM_FACTOR),
        DEFAULT_ZOOM_FACTOR,
        min_value=1.0,
        max_value=1.40,
    )


def get_motion_multiplier(scene):
    speed = _safe_lower(scene.get("motion_speed", DEFAULT_MOTION_SPEED), DEFAULT_MOTION_SPEED)
    return MOTION_MULTIPLIERS.get(speed, MOTION_MULTIPLIERS[DEFAULT_MOTION_SPEED])


def get_transition(scene):
    raw = _safe_lower(scene.get("transition", DEFAULT_TRANSITION), DEFAULT_TRANSITION)
    return TRANSITION_ALIASES.get(raw, DEFAULT_TRANSITION)


def get_subtitle_style(scene):
    return _safe_lower(scene.get("subtitle_style", DEFAULT_SUBTITLE_STYLE), DEFAULT_SUBTITLE_STYLE)


def get_caption_highlights(scene):
    raw = scene.get("caption_highlights", [])
    if not isinstance(raw, list):
        return set()
    out = set()
    for item in raw:
        try:
            out.add(str(item).strip().lower())
        except Exception:
            continue
    return out


def get_visuals(scene, fallback_image):
    """
    Returns a list of image paths for this scene.
    Prefers scene['visuals'] (list of paths/dicts), falls back to the
    single positional image_paths[i] passed into assemble_video, and
    finally to None (renderer will use a solid-color placeholder clip).
    """
    raw = scene.get("visuals")

    paths = []

    if isinstance(raw, list) and raw:
        for item in raw:
            if isinstance(item, dict):
                p = item.get("path") or item.get("image") or item.get("src")
            else:
                p = item
            if p:
                paths.append(str(p))
    elif isinstance(raw, str) and raw.strip():
        paths.append(raw.strip())

    if not paths and fallback_image:
        paths.append(fallback_image)

    # Filter to files that actually exist; keep at least one slot so
    # a placeholder clip still gets generated downstream.
    existing = [p for p in paths if p and os.path.exists(p)]

    if existing:
        return existing

    return [None]


def get_music_cue(scene):
    cue = scene.get("music_cue", {})
    if not isinstance(cue, dict):
        return {}
    return cue


def get_sfx_cue(scene):
    cue = scene.get("sfx_cue", {})
    if not isinstance(cue, dict):
        return {}
    return cue


def get_subtitle_text(scene):
    overlay = scene.get("subtitle_text")
    if overlay is None:
        return None

    if isinstance(overlay, dict):
        text = overlay.get("content", "")
        style = overlay.get("style", "center")
    else:
        text = str(overlay)
        style = "center"

    text = text.strip()
    if not text:
        return None

    return {"text": text, "style": _safe_lower(style, "center")}


def get_video_config(config):
    video_cfg = config.get("video", {}) if isinstance(config, dict) else {}
    if not isinstance(video_cfg, dict):
        video_cfg = {}

    resolution = video_cfg.get("resolution", (1080, 1920))
    try:
        size = (int(resolution[0]), int(resolution[1]))
    except Exception:
        size = (1080, 1920)

    fps = _safe_int(video_cfg.get("fps", 30), 30, min_value=1)
    music_volume = _safe_float(video_cfg.get("music_volume", DEFAULT_MUSIC_VOLUME), DEFAULT_MUSIC_VOLUME, min_value=0.0)
    sfx_volume = _safe_float(video_cfg.get("sfx_volume", DEFAULT_SFX_VOLUME), DEFAULT_SFX_VOLUME, min_value=0.0)

    return {
        "size": size,
        "fps": fps,
        "music_volume": music_volume,
        "sfx_volume": sfx_volume,
    }


# ============================================================
# Master Timeline
#
# One structure describing where every scene sits in time.
# Visuals, captions, overlays, and SFX all read from this instead
# of recomputing their own offsets.
# ============================================================

class SceneTiming:
    __slots__ = ("scene", "index", "start", "end", "duration", "pause_after")

    def __init__(self, scene, index, start, end, duration, pause_after):
        self.scene = scene
        self.index = index
        self.start = start
        self.end = end
        self.duration = duration
        self.pause_after = pause_after


def build_master_timeline(script, total_duration):
    """
    Computes one authoritative list of SceneTiming entries.

    Scene durations from the storyboard are scaled so the sum of all
    scene durations (plus pauses) matches total_duration, which comes
    from the narration track — the true source of truth for length.
    """
    scene_plan = script.get("scene_plan", []) if isinstance(script, dict) else []

    if not scene_plan:
        # No scenes at all: single placeholder scene spanning the
        # whole narration so nothing downstream divides by zero.
        return [
            SceneTiming(
                scene={},
                index=0,
                start=0.0,
                end=max(total_duration, 0.1),
                duration=max(total_duration, 0.1),
                pause_after=0.0,
            )
        ]

    raw_durations = [get_scene_duration(s) for s in scene_plan]
    raw_pauses = [get_pause_after(s) for s in scene_plan]

    raw_total = sum(raw_durations) + sum(raw_pauses)
    raw_total = max(raw_total, 0.1)

    scale = total_duration / raw_total if total_duration > 0 else 1.0

    timeline = []
    current = 0.0

    for index, scene in enumerate(scene_plan):
        duration = raw_durations[index] * scale
        pause = raw_pauses[index] * scale

        start = current
        end = start + duration

        timeline.append(
            SceneTiming(
                scene=scene,
                index=index,
                start=start,
                end=end,
                duration=duration,
                pause_after=pause,
            )
        )

        current = end + pause

    return timeline


def scene_at_time(timeline, t):
    """Finds the SceneTiming entry covering time t; falls back to the
    nearest scene if t falls in a pause gap or past the end."""
    for entry in timeline:
        if entry.start <= t <= entry.end:
            return entry

    if not timeline:
        return None

    if t < timeline[0].start:
        return timeline[0]

    return timeline[-1]


# ============================================================
# Camera
# ============================================================

def apply_camera(clip, camera_name):
    scale = CAMERA_SCALES.get(camera_name, CAMERA_SCALES[DEFAULT_CAMERA])
    return clip.resize(scale)


# ============================================================
# Animation
# ============================================================

def apply_animation(clip, scene, duration):
    animation = get_animation(scene)
    zoom = get_zoom_factor(scene)
    speed = get_motion_multiplier(scene)

    safe_duration = max(duration, 0.1)

    if animation == "hold":
        return clip

    if animation == "zoom_in":
        return clip.fx(
            vfx.resize,
            lambda t: 1 + (zoom - 1) * (t / safe_duration),
        )

    if animation == "zoom_out":
        return clip.fx(
            vfx.resize,
            lambda t: zoom - (zoom - 1) * (t / safe_duration),
        )

    if animation == "pan_left":
        return clip.set_position(
            lambda t: (-80 * speed * (t / safe_duration), "center")
        )

    if animation == "pan_right":
        return clip.set_position(
            lambda t: (80 * speed * (t / safe_duration), "center")
        )

    if animation == "pan_up":
        return clip.set_position(
            lambda t: ("center", -80 * speed * (t / safe_duration))
        )

    if animation == "pan_down":
        return clip.set_position(
            lambda t: ("center", 80 * speed * (t / safe_duration))
        )

    if animation == "rotate":
        return clip.rotate(lambda t: 3 * speed * (t / safe_duration))

    if animation == "kenburns":
        clip = clip.fx(
            vfx.resize,
            lambda t: 1 + (0.05 * speed * (t / safe_duration)),
        )
        clip = clip.set_position(
            lambda t: (
                -30 * speed * (t / safe_duration),
                -20 * speed * (t / safe_duration),
            )
        )
        return clip

    # Unknown animation name from Gemini: fail safe to a static hold
    # rather than crash the render.
    return clip


# ============================================================
# Transitions
# ============================================================

def apply_transition(clip, transition_name):
    fade_time = TRANSITION_DURATIONS.get(transition_name, TRANSITION_DURATIONS[DEFAULT_TRANSITION])

    if fade_time <= 0:
        return clip

    return clip.crossfadein(fade_time).crossfadeout(fade_time)


# ============================================================
# Visual clip building (supports multiple visuals per scene)
# ============================================================

def build_visual_clip_for_image(image_path, sub_duration, size, scene):
    if image_path and os.path.exists(image_path):
        clip = ImageClip(image_path)

        image_scale = min(size[0] / clip.w, size[1] / clip.h)
        clip = clip.resize(image_scale)

        clip = CompositeVideoClip(
            [clip.set_position("center")],
            size=size,
        ).set_duration(sub_duration)
    else:
        clip = ColorClip(size=size, color=(20, 20, 20)).set_duration(sub_duration)

    clip = apply_camera(clip, get_camera(scene))
    clip = apply_animation(clip, scene, sub_duration)

    return clip


def build_scene_visual_clips(entry, image_paths, size):
    """
    Builds the visual clip(s) for one scene, positioned at their
    absolute start time on the master timeline. Supports multiple
    visuals per scene by splitting the scene's duration evenly and
    animating each visual independently.
    """
    scene = entry.scene

    fallback_image = None
    if entry.index < len(image_paths):
        fallback_image = image_paths[entry.index]

    visuals = get_visuals(scene, fallback_image)

    count = len(visuals)
    sub_duration = entry.duration / count if count else entry.duration

    clips = []

    for sub_index, image_path in enumerate(visuals):
        sub_start = entry.start + sub_index * sub_duration

        clip = build_visual_clip_for_image(image_path, sub_duration, size, scene)
        clip = apply_transition(clip, get_transition(scene))

        clip = clip.set_start(sub_start).set_duration(sub_duration)

        clips.append(clip)

    return clips


def build_timeline_visuals(timeline, image_paths, size):
    clips = []
    for entry in timeline:
        clips.extend(build_scene_visual_clips(entry, image_paths, size))
    return clips


# ============================================================
# Captions (phrase-grouped, not per-word)
# ============================================================

def get_caption_position(style, h):
    if style == "top":
        return ("center", h * 0.18)
    if style == "center":
        return ("center", h * 0.50)
    if style == "bottom":
        return ("center", h * 0.82)
    # default / lower_third
    return ("center", h * 0.72)


def group_words_into_phrases(words):
    """
    Groups Whisper word-level timestamps into small readable phrases
    of CAPTION_GROUP_MIN_WORDS-CAPTION_GROUP_MAX_WORDS words, breaking
    early on a long pause between words so captions don't straddle
    unrelated speech.

    Returns a list of dicts: {text, start, end, word_list}
    where word_list preserves each raw word for highlight matching.
    """
    groups = []
    current_words = []

    for word in words:
        if not current_words:
            current_words.append(word)
            continue

        gap = word["start"] - current_words[-1]["end"]

        if gap > CAPTION_GROUP_MAX_GAP or len(current_words) >= CAPTION_GROUP_MAX_WORDS:
            groups.append(current_words)
            current_words = [word]
        else:
            current_words.append(word)

    if current_words:
        groups.append(current_words)

    phrases = []
    for group in groups:
        text = " ".join(w["word"] for w in group)
        phrases.append(
            {
                "text": text,
                "start": group[0]["start"],
                "end": group[-1]["end"],
                "words": group,
            }
        )

    return phrases


def build_captions(audio_path, script, timeline, size):
    _, h = size

    try:
        words = transcribe(audio_path)
    except Exception:
        words = []

    if not words:
        return []

    phrases = group_words_into_phrases(words)

    clips = []

    for phrase in phrases:
        mid_time = (phrase["start"] + phrase["end"]) / 2.0
        entry = scene_at_time(timeline, mid_time)
        scene = entry.scene if entry else {}

        style = get_subtitle_style(scene)
        position = get_caption_position(style, h)
        highlights = get_caption_highlights(scene)

        # Build the phrase text with per-word highlight coloring.
        # TextClip doesn't support mixed-color runs in one call, so
        # when any word in the phrase is highlighted we color the
        # whole phrase clip using the highlight color; this keeps
        # clip count low (one TextClip per phrase, not per word)
        # while still surfacing emphasis.
        any_highlighted = any(
            w["word"].strip().lower() in highlights for w in phrase["words"]
        )
        color = CAPTION_HIGHLIGHT_COLOR if any_highlighted else CAPTION_COLOR

        duration = max(0.05, phrase["end"] - phrase["start"])

        clip = (
            TextClip(
                phrase["text"].upper(),
                font=FONT,
                fontsize=CAPTION_FONT_SIZE,
                color=color,
                stroke_color=CAPTION_STROKE,
                stroke_width=CAPTION_STROKE_WIDTH,
            )
            .set_start(phrase["start"])
            .set_duration(duration)
            .set_position(position)
        )

        clips.append(clip)

    return clips


# ============================================================
# Text Overlays (subtitle_text — separate from spoken captions)
# ============================================================

def build_overlays(timeline, size):
    w, h = size

    overlays = []

    for entry in timeline:
        overlay = get_subtitle_text(entry.scene)

        if not overlay:
            continue

        y = h * 0.20
        if overlay["style"] == "lower_third":
            y = h * 0.72
        elif overlay["style"] == "top":
            y = h * 0.18

        duration = min(entry.duration, OVERLAY_MAX_DURATION)

        clip = (
            TextClip(
                overlay["text"].upper(),
                font=FONT,
                fontsize=OVERLAY_FONT_SIZE,
                color="white",
                stroke_color="black",
                stroke_width=OVERLAY_STROKE_WIDTH,
                method="caption",
                size=(int(w * 0.88), None),
            )
            .set_position(("center", y))
            .set_start(entry.start)
            .set_duration(duration)
            .crossfadein(OVERLAY_FADE)
            .crossfadeout(OVERLAY_FADE)
        )

        overlays.append(clip)

    return overlays


# ============================================================
# Audio (narration + music + SFX, all keyed off the master timeline)
# ============================================================

def build_audio(timeline, narration, music_path, sfx_paths, total_duration, video_cfg):
    tracks = [narration]

    if music_path and os.path.exists(music_path):
        music = (
            AudioFileClip(music_path)
            .fx(afx.audio_loop, duration=total_duration)
            .volumex(video_cfg["music_volume"])
        )
        tracks.append(music)

    for entry in timeline:
        if entry.index >= len(sfx_paths):
            continue

        sfx_path = sfx_paths[entry.index]

        if not (sfx_path and os.path.exists(sfx_path)):
            continue

        cue = get_sfx_cue(entry.scene)
        offset = _safe_float(cue.get("at_ms", 0), 0, min_value=0) / 1000.0

        effect = (
            AudioFileClip(sfx_path)
            .set_start(entry.start + offset)
            .volumex(video_cfg["sfx_volume"])
        )

        tracks.append(effect)

    return CompositeAudioClip(tracks)


# ============================================================
# Assemble Video (public API — signature unchanged)
# ============================================================

def assemble_video(
    script,
    audio_paths,
    image_paths,
    music_path,
    sfx_paths,
    config,
    out_path,
):
    video_cfg = get_video_config(config)
    size = video_cfg["size"]

    narration = AudioFileClip(audio_paths[0])
    total_duration = narration.duration

    timeline = build_master_timeline(script, total_duration)

    visual_clips = build_timeline_visuals(timeline, image_paths, size)
    caption_clips = build_captions(audio_paths[0], script, timeline, size)
    overlay_clips = build_overlays(timeline, size)

    final = CompositeVideoClip(
        visual_clips + caption_clips + overlay_clips,
        size=size,
    ).set_duration(total_duration)

    audio = build_audio(
        timeline,
        narration,
        music_path,
        sfx_paths,
        total_duration,
        video_cfg,
    )

    final = final.set_audio(audio)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    final.write_videofile(
        out_path,
        fps=video_cfg["fps"],
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
    )

    return out_path
