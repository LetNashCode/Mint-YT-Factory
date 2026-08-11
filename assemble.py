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

CAPTION_FONT_SIZE = 74
CAPTION_COLOR = "white"
CAPTION_HIGHLIGHT_COLOR = "#FFD54A"

CAPTION_SHADOW_COLOR = "black"
CAPTION_SHADOW_OPACITY = 0.60
CAPTION_SHADOW_OFFSET = 3

CAPTION_STROKE = "#222222"
CAPTION_STROKE_WIDTH = 1

CAPTION_VERTICAL_POSITION = 0.68

CAPTION_GROUP_MIN_WORDS = 1
CAPTION_GROUP_MAX_WORDS = 1
CAPTION_GROUP_MAX_GAP = 0.6

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
# Safe Parsing Helpers
# ============================================================

def _safe_lower(value, default):
    try:
        return str(value).strip().lower()
    except Exception:
        return default


def _safe_float(
    value,
    default,
    min_value=None,
    max_value=None,
):
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


def _safe_int(
    value,
    default,
    min_value=None,
):
    try:
        result = int(value)
    except Exception:
        return default

    if min_value is not None:
        result = max(result, min_value)

    return result


def get_scene_duration(scene):
    return _safe_float(
        scene.get(
            "duration",
            DEFAULT_SCENE_DURATION,
        ),
        DEFAULT_SCENE_DURATION,
        min_value=0.1,
    )


def get_pause_after(scene):

    ms = _safe_float(
        scene.get(
            "pause_after_ms",
            0,
        ),
        0,
        min_value=0,
    )

    return ms / 1000.0


def get_camera(scene):

    cam = _safe_lower(
        scene.get(
            "camera",
            DEFAULT_CAMERA,
        ),
        DEFAULT_CAMERA,
    )

    return (
        cam
        if cam in CAMERA_SCALES
        else DEFAULT_CAMERA
    )


def get_animation(scene):

    return _safe_lower(
        scene.get(
            "animation",
            DEFAULT_ANIMATION,
        ),
        DEFAULT_ANIMATION,
    )


def get_zoom_factor(scene):

    return _safe_float(
        scene.get(
            "zoom_factor",
            DEFAULT_ZOOM_FACTOR,
        ),
        DEFAULT_ZOOM_FACTOR,
        min_value=1.0,
        max_value=1.40,
    )


def get_motion_multiplier(scene):

    speed = _safe_lower(
        scene.get(
            "motion_speed",
            DEFAULT_MOTION_SPEED,
        ),
        DEFAULT_MOTION_SPEED,
    )

    return MOTION_MULTIPLIERS.get(
        speed,
        MOTION_MULTIPLIERS[
            DEFAULT_MOTION_SPEED
        ],
    )


def get_transition(scene):

    raw = _safe_lower(
        scene.get(
            "transition",
            DEFAULT_TRANSITION,
        ),
        DEFAULT_TRANSITION,
    )

    return TRANSITION_ALIASES.get(
        raw,
        DEFAULT_TRANSITION,
    )


def get_subtitle_style(scene):

    return _safe_lower(
        scene.get(
            "subtitle_style",
            DEFAULT_SUBTITLE_STYLE,
        ),
        DEFAULT_SUBTITLE_STYLE,
    )


# ============================================================
# Caption Highlight Parsing
# ============================================================

def get_caption_highlights(scene):

    raw = scene.get(
        "caption_highlights",
        [],
    )

    if not isinstance(raw, list):
        return set()

    highlights = set()

    for item in raw:

        if isinstance(item, dict):

            word = item.get(
                "word",
                "",
            )

            if word:
                highlights.add(
                    str(word)
                    .strip()
                    .lower()
                )

        elif isinstance(item, str):

            highlights.add(
                item.strip().lower()
            )

    return highlights


# ============================================================
# Visual Path Normalization
#
# Supports BOTH:
#
# OLD:
# [
#     "scene_01.png",
#     "scene_02.png"
# ]
#
# NEW:
# [
#     ["scene_01_shot_01.png"],
#     ["scene_02_shot_01.png",
#      "scene_02_shot_02.png"]
# ]
#
# Also supports:
#
# [
#     [
#         {"path": "..."}
#     ]
# ]
# ============================================================

def _normalize_visual_paths(raw):

    if raw is None:
        return []

    # Single path
    if isinstance(raw, str):

        raw = raw.strip()

        return [raw] if raw else []

    # Not a list
    if not isinstance(raw, list):
        return []

    normalized = []

    for item in raw:

        # Direct string
        if isinstance(item, str):

            item = item.strip()

            if item:
                normalized.append(item)

            continue

        # Dictionary
        if isinstance(item, dict):

            path = (
                item.get("path")
                or item.get("image")
                or item.get("src")
            )

            if isinstance(path, str):
                path = path.strip()

                if path:
                    normalized.append(path)

            continue

        # Nested list
        if isinstance(item, list):

            nested = _normalize_visual_paths(
                item
            )

            normalized.extend(
                nested
            )

    return normalized


def _scene_visuals_from_generated_paths(
    image_paths,
    scene_index,
):
    """
    Extract visual paths belonging to one scene.

    image_paths can be:

        [
            "scene_01.png",
            "scene_02.png"
        ]

    OR:

        [
            ["scene_01_shot_01.png"],
            ["scene_02_shot_01.png",
             "scene_02_shot_02.png"]
        ]

    Returns a flat list of valid paths for
    the requested scene.
    """

    if not isinstance(
        image_paths,
        list,
    ):
        return []

    if scene_index < 0:
        return []

    if scene_index >= len(
        image_paths
    ):
        return []

    scene_data = image_paths[
        scene_index
    ]

    paths = _normalize_visual_paths(
        scene_data
    )

    return [
        p
        for p in paths
        if p
        and isinstance(p, str)
        and os.path.exists(p)
    ]


def get_visuals(
    scene,
    fallback_image=None,
    generated_scene_paths=None,
):
    """
    Resolve visuals for a scene.

    Priority:

    1. Explicit paths inside scene["visuals"]
    2. Generated AI scene paths
    3. fallback image

    IMPORTANT:
    This function always returns a FLAT list
    of filesystem paths.

    This prevents os.path.exists()
    from receiving a list.
    """

    paths = []

    # --------------------------------------------------------
    # 1. Explicit visual paths from storyboard
    # --------------------------------------------------------

    raw = scene.get(
        "visuals"
    )

    if isinstance(
        raw,
        list,
    ) and raw:

        for item in raw:

            if isinstance(
                item,
                dict,
            ):

                p = (
                    item.get(
                        "path"
                    )
                    or item.get(
                        "image"
                    )
                    or item.get(
                        "src"
                    )
                )

            else:

                p = item

            if isinstance(
                p,
                str,
            ) and p.strip():

                paths.append(
                    p.strip()
                )

    elif isinstance(
        raw,
        str,
    ) and raw.strip():

        paths.append(
            raw.strip()
        )

    # --------------------------------------------------------
    # 2. AI generated paths
    # --------------------------------------------------------

    if not paths:

        paths.extend(
            _normalize_visual_paths(
                generated_scene_paths
            )
        )

    # --------------------------------------------------------
    # 3. Fallback
    # --------------------------------------------------------

    if (
        not paths
        and fallback_image
    ):

        paths.append(
            fallback_image
        )

    # --------------------------------------------------------
    # Only return real files
    # --------------------------------------------------------

    existing = []

    for path in paths:

        if not isinstance(
            path,
            str,
        ):
            continue

        if not path:
            continue

        if os.path.exists(path):

            existing.append(
                path
            )

    if existing:
        return existing

    return [None]


# ============================================================
# Music / SFX
# ============================================================

def get_music_cue(scene):

    cue = scene.get(
        "music_cue",
        {},
    )

    if not isinstance(
        cue,
        dict,
    ):
        return {}

    return cue


def get_sfx_cue(scene):

    cue = scene.get(
        "sfx_cue",
        {},
    )

    if not isinstance(
        cue,
        dict,
    ):
        return {}

    return cue


def get_subtitle_text(scene):

    overlay = scene.get(
        "subtitle_text"
    )

    if overlay is None:
        return None

    if isinstance(
        overlay,
        dict,
    ):

        text = overlay.get(
            "content",
            "",
        )

        style = overlay.get(
            "style",
            "center",
        )

    else:

        text = str(
            overlay
        )

        style = "center"

    text = text.strip()

    if not text:
        return None

    return {
        "text": text,
        "style": _safe_lower(
            style,
            "center",
        ),
    }


# ============================================================
# Video Config
# ============================================================

def get_video_config(config):

    video_cfg = (
        config.get(
            "video",
            {},
        )
        if isinstance(
            config,
            dict,
        )
        else {}
    )

    if not isinstance(
        video_cfg,
        dict,
    ):
        video_cfg = {}

    resolution = video_cfg.get(
        "resolution",
        (
            1080,
            1920,
        ),
    )

    try:

        size = (
            int(
                resolution[0]
            ),
            int(
                resolution[1]
            ),
        )

    except Exception:

        size = (
            1080,
            1920,
        )

    fps = _safe_int(
        video_cfg.get(
            "fps",
            30,
        ),
        30,
        min_value=1,
    )

    music_volume = _safe_float(
        video_cfg.get(
            "music_volume",
            DEFAULT_MUSIC_VOLUME,
        ),
        DEFAULT_MUSIC_VOLUME,
        min_value=0.0,
    )

    sfx_volume = _safe_float(
        video_cfg.get(
            "sfx_volume",
            DEFAULT_SFX_VOLUME,
        ),
        DEFAULT_SFX_VOLUME,
        min_value=0.0,
    )

    return {
        "size": size,
        "fps": fps,
        "music_volume": music_volume,
        "sfx_volume": sfx_volume,
    }


# ============================================================
# Master Timeline
# ============================================================

class SceneTiming:

    __slots__ = (
        "scene",
        "index",
        "start",
        "end",
        "duration",
        "pause_after",
    )

    def __init__(
        self,
        scene,
        index,
        start,
        end,
        duration,
        pause_after,
    ):

        self.scene = scene
        self.index = index
        self.start = start
        self.end = end
        self.duration = duration
        self.pause_after = pause_after


def build_master_timeline(
    script,
    total_duration,
):

    scene_plan = (
        script.get(
            "scene_plan",
            [],
        )
        if isinstance(
            script,
            dict,
        )
        else []
    )

    if not scene_plan:

        return [
            SceneTiming(
                scene={},
                index=0,
                start=0.0,
                end=max(
                    total_duration,
                    0.1,
                ),
                duration=max(
                    total_duration,
                    0.1,
                ),
                pause_after=0.0,
            )
        ]

    raw_durations = [
        get_scene_duration(
            s
        )
        for s in scene_plan
    ]

    raw_pauses = [
        get_pause_after(
            s
        )
        for s in scene_plan
    ]

    raw_total = (
        sum(raw_durations)
        + sum(raw_pauses)
    )

    raw_total = max(
        raw_total,
        0.1,
    )

    scale = (
        total_duration
        / raw_total
        if total_duration > 0
        else 1.0
    )

    timeline = []

    current = 0.0

    for index, scene in enumerate(
        scene_plan
    ):

        duration = (
            raw_durations[index]
            * scale
        )

        pause = (
            raw_pauses[index]
            * scale
        )

        start = current
        end = (
            start
            + duration
        )

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

        current = (
            end
            + pause
        )

    return timeline


def scene_at_time(
    timeline,
    t,
):

    for entry in timeline:

        if (
            entry.start
            <= t
            <= entry.end
        ):
            return entry

    if not timeline:
        return None

    if (
        t
        < timeline[0].start
    ):
        return timeline[0]

    return timeline[-1]


# ============================================================
# Camera
# ============================================================

def apply_camera(
    clip,
    camera_name,
):

    scale = CAMERA_SCALES.get(
        camera_name,
        CAMERA_SCALES[
            DEFAULT_CAMERA
        ],
    )

    return clip.resize(
        scale
    )


# ============================================================
# Animation
# ============================================================

def apply_animation(
    clip,
    scene,
    duration,
):

    animation = get_animation(
        scene
    )

    zoom = get_zoom_factor(
        scene
    )

    speed = get_motion_multiplier(
        scene
    )

    safe_duration = max(
        duration,
        0.1,
    )

    if animation == "hold":

        return clip

    if animation == "zoom_in":

        return clip.fx(
            vfx.resize,
            lambda t:
                1
                + (
                    zoom - 1
                )
                * (
                    t
                    / safe_duration
                ),
        )

    if animation == "zoom_out":

        return clip.fx(
            vfx.resize,
            lambda t:
                zoom
                - (
                    zoom - 1
                )
                * (
                    t
                    / safe_duration
                ),
        )

    if animation == "pan_left":

        return clip.set_position(
            lambda t:
                (
                    -80
                    * speed
                    * (
                        t
                        / safe_duration
                    ),
                    "center",
                )
        )

    if animation == "pan_right":

        return clip.set_position(
            lambda t:
                (
                    80
                    * speed
                    * (
                        t
                        / safe_duration
                    ),
                    "center",
                )
        )

    if animation == "pan_up":

        return clip.set_position(
            lambda t:
                (
                    "center",
                    -80
                    * speed
                    * (
                        t
                        / safe_duration
                    ),
                )
        )

    if animation == "pan_down":

        return clip.set_position(
            lambda t:
                (
                    "center",
                    80
                    * speed
                    * (
                        t
                        / safe_duration
                    ),
                )
        )

    if animation == "rotate":

        return clip.rotate(
            lambda t:
                3
                * speed
                * (
                    t
                    / safe_duration
                )
        )

    if animation == "kenburns":

        clip = clip.fx(
            vfx.resize,
            lambda t:
                1
                + (
                    0.05
                    * speed
                    * (
                        t
                        / safe_duration
                    )
                ),
        )

        clip = clip.set_position(
            lambda t:
                (
                    -30
                    * speed
                    * (
                        t
                        / safe_duration
                    ),
                    -20
                    * speed
                    * (
                        t
                        / safe_duration
                    ),
                )
        )

        return clip

    return clip


# ============================================================
# Transitions
# ============================================================

def apply_transition(
    clip,
    transition_name,
):

    fade_time = (
        TRANSITION_DURATIONS.get(
            transition_name,
            TRANSITION_DURATIONS[
                DEFAULT_TRANSITION
            ],
        )
    )

    if fade_time <= 0:
        return clip

    return clip.crossfadein(
        fade_time
    ).crossfadeout(
        fade_time
    )


# ============================================================
# Visual Clip
# ============================================================

def build_visual_clip_for_image(
    image_path,
    sub_duration,
    size,
    scene,
):

    if (
        image_path
        and os.path.exists(
            image_path
        )
    ):

        clip = ImageClip(
            image_path
        )

        image_scale = max(
            size[0] / clip.w,
            size[1] / clip.h,
        )

        clip = clip.resize(
            image_scale
        )

        clip = CompositeVideoClip(
            [
                clip.set_position(
                    "center"
                )
            ],
            size=size,
        ).set_duration(
            sub_duration
        )

    else:

        clip = ColorClip(
            size=size,
            color=(
                20,
                20,
                20,
            ),
        ).set_duration(
            sub_duration
        )

    clip = apply_camera(
        clip,
        get_camera(scene),
    )

    clip = apply_animation(
        clip,
        scene,
        sub_duration,
    )

    return clip


# ============================================================
# Scene Visual Clips
# ============================================================

def build_scene_visual_clips(
    entry,
    image_paths,
    size,
):

    scene = entry.scene

    # --------------------------------------------------------
    # IMPORTANT FIX
    #
    # image_paths may be:
    #
    # [
    #   ["scene_01.png"],
    #   ["scene_02.png"]
    # ]
    #
    # instead of:
    #
    # [
    #   "scene_01.png",
    #   "scene_02.png"
    # ]
    #
    # Extract ONLY this scene's paths.
    # --------------------------------------------------------

    generated_scene_paths = (
        _scene_visuals_from_generated_paths(
            image_paths,
            entry.index,
        )
    )

    fallback_image = None

    # --------------------------------------------------------
    # Legacy flat-list support
    # --------------------------------------------------------

    if (
        entry.index
        < len(image_paths)
        and isinstance(
            image_paths[
                entry.index
            ],
            str,
        )
    ):

        fallback_image = image_paths[
            entry.index
        ]

    visuals = get_visuals(
        scene,
        fallback_image,
        generated_scene_paths,
    )

    # --------------------------------------------------------
    # Debug
    # --------------------------------------------------------

    print(
        f"🎬 Scene {entry.index + 1}: "
        f"{len(visuals)} visual(s)"
    )

    for visual_index, visual in enumerate(
        visuals,
        start=1,
    ):

        print(
            f"   Visual {visual_index}: "
            f"{visual}"
        )

    count = max(
        len(visuals),
        1,
    )

    sub_duration = (
        entry.duration
        / count
    )

    clips = []

    for sub_index, image_path in enumerate(
        visuals
    ):

        sub_start = (
            entry.start
            + (
                sub_index
                * sub_duration
            )
        )

        clip = build_visual_clip_for_image(
            image_path,
            sub_duration,
            size,
            scene,
        )

        clip = apply_transition(
            clip,
            get_transition(
                scene
            ),
        )

        clip = (
            clip
            .set_start(
                sub_start
            )
            .set_duration(
                sub_duration
            )
        )

        clips.append(
            clip
        )

    return clips


# ============================================================
# Timeline Visuals
# ============================================================

def build_timeline_visuals(
    timeline,
    image_paths,
    size,
):

    clips = []

    for entry in timeline:

        clips.extend(
            build_scene_visual_clips(
                entry,
                image_paths,
                size,
            )
        )

    return clips


# ============================================================
# Captions
# ============================================================

def get_caption_position(
    style,
    h,
):

    if style == "top":

        return (
            "center",
            h * 0.18,
        )

    if style == "center":

        return (
            "center",
            h * 0.50,
        )

    if style == "bottom":

        return (
            "center",
            h * CAPTION_VERTICAL_POSITION,
        )

    return (
        "center",
        h * CAPTION_VERTICAL_POSITION,
    )


def group_words_into_phrases(
    words
):

    phrases = []

    for word in words:

        text = str(
            word.get(
                "word",
                "",
            )
        ).strip()

        if not text:
            continue

        start = _safe_float(
            word.get(
                "start",
                0,
            ),
            0,
            min_value=0,
        )

        end = _safe_float(
            word.get(
                "end",
                start + 0.1,
            ),
            start + 0.1,
            min_value=start,
        )

        phrases.append(
            {
                "text": text,
                "start": start,
                "end": end,
                "words": [
                    {
                        "word": text,
                        "start": start,
                        "end": end,
                    }
                ],
            }
        )

    return phrases


def build_captions(
    audio_path,
    script,
    timeline,
    size,
):

    _, h = size

    print("=" * 80)
    print("📝 GENERATING CAPTIONS")
    print("=" * 80)

    try:

        words = transcribe(
            audio_path
        )

        print(
            f"Whisper detected "
            f"{len(words)} words."
        )

    except Exception as e:

        print("=" * 80)
        print(
            "❌ CAPTION TRANSCRIPTION FAILED"
        )
        print("=" * 80)
        print(e)
        print("=" * 80)

        raise

    if not words:

        print(
            "⚠️ Whisper returned no words."
        )

        return []

    phrases = group_words_into_phrases(
        words
    )

    print(
        f"Creating "
        f"{len(phrases)} caption clips."
    )

    clips = []

    for phrase in phrases:

        mid_time = (
            phrase["start"]
            + phrase["end"]
        ) / 2.0

        entry = scene_at_time(
            timeline,
            mid_time,
        )

        scene = (
            entry.scene
            if entry
            else {}
        )

        style = get_subtitle_style(
            scene
        )

        position = get_caption_position(
            style,
            h,
        )

        highlights = (
            get_caption_highlights(
                scene
            )
        )

        word = phrase[
            "text"
        ]

        is_highlighted = (
            word.strip()
            .lower()
            in highlights
        )

        color = (
            CAPTION_HIGHLIGHT_COLOR
            if is_highlighted
            else CAPTION_COLOR
        )

        duration = max(
            0.05,
            phrase["end"]
            - phrase["start"],
        )

        shadow = (
            TextClip(
                word,
                font=FONT,
                fontsize=CAPTION_FONT_SIZE,
                color=CAPTION_SHADOW_COLOR,
            )
            .set_start(
                phrase["start"]
            )
            .set_duration(
                duration
            )
            .set_position(
                (
                    position[0],
                    position[1]
                    + CAPTION_SHADOW_OFFSET,
                )
            )
            .set_opacity(
                CAPTION_SHADOW_OPACITY
            )
        )

        text = (
            TextClip(
                word,
                font=FONT,
                fontsize=CAPTION_FONT_SIZE,
                color=color,
                stroke_color=CAPTION_STROKE,
                stroke_width=CAPTION_STROKE_WIDTH,
            )
            .set_start(
                phrase["start"]
            )
            .set_duration(
                duration
            )
            .set_position(
                position
            )
        )

        clips.append(
            shadow
        )

        clips.append(
            text
        )

    print(
        f"✅ Caption clips created: "
        f"{len(clips)}"
    )

    return clips


# ============================================================
# Text Overlays
# ============================================================

def build_overlays(
    timeline,
    size,
):

    return []


# ============================================================
# Audio
# ============================================================

def build_audio(
    timeline,
    narration,
    music_path,
    sfx_paths,
    total_duration,
    video_cfg,
):

    tracks = [
        narration
    ]

    # --------------------------------------------------------
    # Background Music
    # --------------------------------------------------------

    if (
        music_path
        and os.path.exists(
            music_path
        )
    ):

        music = (
            AudioFileClip(
                music_path
            )
            .fx(
                afx.audio_loop,
                duration=total_duration,
            )
            .volumex(
                video_cfg[
                    "music_volume"
                ]
            )
        )

        tracks.append(
            music
        )

    # --------------------------------------------------------
    # SFX
    # --------------------------------------------------------

    for entry in timeline:

        if entry.index >= len(
            sfx_paths
        ):
            continue

        sfx_path = sfx_paths[
            entry.index
        ]

        if not (
            sfx_path
            and os.path.exists(
                sfx_path
            )
        ):
            continue

        cue = get_sfx_cue(
            entry.scene
        )

        offset = (
            _safe_float(
                cue.get(
                    "at_ms",
                    0,
                ),
                0,
                min_value=0,
            )
            / 1000.0
        )

        effect = (
            AudioFileClip(
                sfx_path
            )
            .set_start(
                entry.start
                + offset
            )
            .volumex(
                video_cfg[
                    "sfx_volume"
                ]
            )
        )

        tracks.append(
            effect
        )

    return CompositeAudioClip(
        tracks
    )


# ============================================================
# Assemble Video
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

    print("=" * 80)
    print("🎬 ASSEMBLING VIDEO")
    print("=" * 80)

    video_cfg = get_video_config(
        config
    )

    size = video_cfg[
        "size"
    ]

    print(
        f"Resolution: "
        f"{size[0]}x{size[1]}"
    )

    narration = AudioFileClip(
        audio_paths[0]
    )

    total_duration = (
        narration.duration
    )

    print(
        f"Narration duration: "
        f"{total_duration:.2f}s"
    )

    # --------------------------------------------------------
    # Build timeline
    # --------------------------------------------------------

    timeline = build_master_timeline(
        script,
        total_duration,
    )

    print(
        f"Scenes: {len(timeline)}"
    )

    # --------------------------------------------------------
    # Visuals
    # --------------------------------------------------------

    print("=" * 80)
    print("🖼️ BUILDING VISUAL TIMELINE")
    print("=" * 80)

    visual_clips = (
        build_timeline_visuals(
            timeline,
            image_paths,
            size,
        )
    )

    print(
        f"Visual clips: "
        f"{len(visual_clips)}"
    )

    # --------------------------------------------------------
    # Captions
    # --------------------------------------------------------

    caption_clips = build_captions(
        audio_paths[0],
        script,
        timeline,
        size,
    )

    # --------------------------------------------------------
    # No separate overlays
    # --------------------------------------------------------

    overlay_clips = []

    # --------------------------------------------------------
    # Composite video
    # --------------------------------------------------------

    final = CompositeVideoClip(
        visual_clips
        + caption_clips
        + overlay_clips,
        size=size,
    ).set_duration(
        total_duration
    )

    # --------------------------------------------------------
    # Audio
    # --------------------------------------------------------

    audio = build_audio(
        timeline,
        narration,
        music_path,
        sfx_paths,
        total_duration,
        video_cfg,
    )

    final = final.set_audio(
        audio
    )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    output_dir = os.path.dirname(
        out_path
    )

    if output_dir:

        os.makedirs(
            output_dir,
            exist_ok=True,
        )

    print("=" * 80)
    print(
        f"🎥 WRITING VIDEO"
    )
    print("=" * 80)

    final.write_videofile(
        out_path,
        fps=video_cfg[
            "fps"
        ],
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
    )

    print("=" * 80)
    print(
        f"✅ VIDEO COMPLETE: "
        f"{out_path}"
    )
    print("=" * 80)

    # --------------------------------------------------------
    # Cleanup
    # --------------------------------------------------------

    try:
        narration.close()
    except Exception:
        pass

    try:
        final.close()
    except Exception:
        pass

    return out_path