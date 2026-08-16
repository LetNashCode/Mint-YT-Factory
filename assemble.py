"""
assemble.py
Mint-YT-Factory

Version 7.1

Production:
- 7 scenes
- 2 AI visuals per scene
- 14 visuals total
- 45-second target
- Word-by-word captions
- Scene-aware caption highlighting
- Music support
- SFX support
- Portrait 9:16 output
- Compatible with generate_images.py v7+
"""

import os
import math
import shutil as _shutil

from whisper_align import transcribe

from moviepy.config import change_settings

_im = (
    _shutil.which("convert")
    or _shutil.which("magick")
)

if _im:
    change_settings(
        {
            "IMAGEMAGICK_BINARY": _im
        }
    )

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


# ==========================================================================
# CONSTANTS
# ==========================================================================

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

DEFAULT_SCENE_DURATION = 5.0

DEFAULT_CAMERA = "medium"

DEFAULT_ANIMATION = "hold"

DEFAULT_TRANSITION = "hard_cut"

DEFAULT_ZOOM_FACTOR = 1.08

DEFAULT_MOTION_SPEED = "medium"

DEFAULT_MUSIC_VOLUME = 0.12

DEFAULT_SFX_VOLUME = 0.80


# ==========================================================================
# CAMERA
# ==========================================================================

CAMERA_SCALES = {

    "macro": 1.18,

    "close_up": 1.12,

    "medium": 1.08,

    "wide": 1.02,

    "top_down": 1.06,

    "side": 1.08,

    "aerial": 1.02,

    "orbit": 1.08,
}


# ==========================================================================
# MOTION
# ==========================================================================

MOTION_MULTIPLIERS = {

    "low": 0.5,

    "medium": 1.0,

    "high": 1.5,

    "slow": 0.5,

    "fast": 1.5,
}


# ==========================================================================
# TRANSITIONS
# ==========================================================================

TRANSITION_ALIASES = {

    "cut": "hard_cut",

    "hard_cut": "hard_cut",

    "crossfade": "crossfade",

    "fade": "fade",

    "dissolve": "dissolve",

    "none": "hard_cut",
}


TRANSITION_DURATIONS = {

    "hard_cut": 0.0,

    "crossfade": 0.20,

    "fade": 0.35,

    "dissolve": 0.30,
}


# ==========================================================================
# SAFE HELPERS
# ==========================================================================

def _safe_lower(
    value,
    default,
):

    try:

        return str(
            value
        ).strip().lower()

    except Exception:

        return default


def _safe_float(
    value,
    default,
    min_value=None,
    max_value=None,
):

    try:

        result = float(
            value
        )

    except Exception:

        return default

    if math.isnan(result):

        return default

    if math.isinf(result):

        return default

    if min_value is not None:

        result = max(
            result,
            min_value,
        )

    if max_value is not None:

        result = min(
            result,
            max_value,
        )

    return result


def _safe_int(
    value,
    default,
    min_value=None,
):

    try:

        result = int(
            value
        )

    except Exception:

        return default

    if min_value is not None:

        result = max(
            result,
            min_value,
        )

    return result


# ==========================================================================
# SCENE SETTINGS
# ==========================================================================

def get_scene_duration(
    scene,
):

    return _safe_float(

        scene.get(
            "duration",
            DEFAULT_SCENE_DURATION,
        ),

        DEFAULT_SCENE_DURATION,

        min_value=0.1,
    )


def get_pause_after(
    scene,
):

    milliseconds = _safe_float(

        scene.get(
            "pause_after_ms",
            0,
        ),

        0,

        min_value=0,
    )

    return milliseconds / 1000.0


def get_camera(
    scene,
):

    camera = _safe_lower(

        scene.get(
            "camera",
            DEFAULT_CAMERA,
        ),

        DEFAULT_CAMERA,
    )

    if camera not in CAMERA_SCALES:

        return DEFAULT_CAMERA

    return camera


def get_animation(
    visual,
    scene,
):

    animation = visual.get(
        "animation"
    )

    if not animation:

        animation = scene.get(
            "animation",
            DEFAULT_ANIMATION,
        )

    return _safe_lower(
        animation,
        DEFAULT_ANIMATION,
    )


def get_zoom_factor(
    visual,
):

    return _safe_float(

        visual.get(
            "zoom_factor",
            DEFAULT_ZOOM_FACTOR,
        ),

        DEFAULT_ZOOM_FACTOR,

        min_value=1.0,

        max_value=1.40,
    )


def get_motion_multiplier(
    visual,
):

    speed = _safe_lower(

        visual.get(
            "motion_intensity",
            "medium",
        ),

        "medium",
    )

    return MOTION_MULTIPLIERS.get(
        speed,
        1.0,
    )


def get_transition(
    scene,
):

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


# ==========================================================================
# CAPTION HIGHLIGHTS
# ==========================================================================

def get_caption_highlights(
    scene,
):

    raw = scene.get(
        "caption_highlights",
        [],
    )

    if not isinstance(
        raw,
        list,
    ):

        return set()

    highlights = set()

    for item in raw:

        if isinstance(
            item,
            dict,
        ):

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

        elif isinstance(
            item,
            str,
        ):

            if item.strip():

                highlights.add(
                    item.strip()
                    .lower()
                )

    return highlights


# ==========================================================================
# VISUAL PATH NORMALIZATION
# ==========================================================================

def _normalize_visual_paths(
    raw,
):

    if raw is None:

        return []

    if isinstance(
        raw,
        str,
    ):

        raw = raw.strip()

        return (
            [raw]
            if raw
            else []
        )

    if not isinstance(
        raw,
        list,
    ):

        return []

    result = []

    for item in raw:

        if isinstance(
            item,
            str,
        ):

            item = item.strip()

            if item:

                result.append(
                    item
                )

        elif isinstance(
            item,
            dict,
        ):

            path = (

                item.get(
                    "path"
                )

                or

                item.get(
                    "image"
                )

                or

                item.get(
                    "src"
                )
            )

            if isinstance(
                path,
                str,
            ):

                path = path.strip()

                if path:

                    result.append(
                        path
                    )

        elif isinstance(
            item,
            list,
        ):

            result.extend(
                _normalize_visual_paths(
                    item
                )
            )

    return result


def _scene_visuals_from_generated_paths(
    image_paths,
    scene_index,
):

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

        path

        for path in paths

        if isinstance(
            path,
            str,
        )

        and os.path.exists(
            path
        )
    ]


def get_visuals(
    scene,
    fallback_image=None,
    generated_scene_paths=None,
):

    paths = []

    # ----------------------------------------------------------------------
    # Explicit paths
    # ----------------------------------------------------------------------

    raw = scene.get(
        "visuals"
    )

    if isinstance(
        raw,
        list,
    ):

        for item in raw:

            if isinstance(
                item,
                dict,
            ):

                path = (

                    item.get(
                        "path"
                    )

                    or

                    item.get(
                        "image"
                    )

                    or

                    item.get(
                        "src"
                    )
                )

            else:

                path = item

            if isinstance(
                path,
                str,
            ):

                path = path.strip()

                if path:

                    paths.append(
                        path
                    )

    elif isinstance(
        raw,
        str,
    ):

        raw = raw.strip()

        if raw:

            paths.append(
                raw
            )

    # ----------------------------------------------------------------------
    # Generated AI images
    # ----------------------------------------------------------------------

    if not paths:

        paths.extend(
            _normalize_visual_paths(
                generated_scene_paths
            )
        )

    # ----------------------------------------------------------------------
    # Fallback
    # ----------------------------------------------------------------------

    if (
        not paths
        and fallback_image
    ):

        paths.append(
            fallback_image
        )

    # ----------------------------------------------------------------------
    # Existing files only
    # ----------------------------------------------------------------------

    existing = []

    for path in paths:

        if not isinstance(
            path,
            str,
        ):

            continue

        if os.path.exists(
            path
        ):

            existing.append(
                path
            )

    if existing:

        return existing

    return [None]


# ==========================================================================
# TIMELINE
# ==========================================================================

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

    scene_plan = script.get(
        "scene_plan",
        [],
    )

    if not scene_plan:

        return [

            SceneTiming(

                {},

                0,

                0.0,

                total_duration,

                total_duration,

                0.0,
            )
        ]

    durations = [

        get_scene_duration(
            scene
        )

        for scene in scene_plan
    ]

    pauses = [

        get_pause_after(
            scene
        )

        for scene in scene_plan
    ]

    raw_total = (

        sum(durations)

        + sum(pauses)
    )

    if raw_total <= 0:

        raw_total = total_duration

    scale = (

        total_duration
        / raw_total
    )

    timeline = []

    current = 0.0

    for index, scene in enumerate(
        scene_plan
    ):

        duration = (
            durations[index]
            * scale
        )

        pause = (
            pauses[index]
            * scale
        )

        start = current

        end = (
            start
            + duration
        )

        timeline.append(

            SceneTiming(

                scene,

                index,

                start,

                end,

                duration,

                pause,
            )
        )

        current = (
            end
            + pause
        )

    return timeline


def scene_at_time(
    timeline,
    timestamp,
):

    for entry in timeline:

        if (

            entry.start
            <= timestamp
            < entry.end

        ):

            return entry

    if not timeline:

        return None

    return timeline[-1]


# ==========================================================================
# VISUAL FIT
# ==========================================================================

def build_visual_clip_for_image(
    image_path,
    duration,
    size,
    scene,
    visual,
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

        # --------------------------------------------------------------
        # Fill the 9:16 frame.
        # --------------------------------------------------------------

        scale = max(

            size[0] / clip.w,

            size[1] / clip.h,
        )

        clip = clip.resize(
            scale
        )

        # --------------------------------------------------------------
        # Center crop.
        # --------------------------------------------------------------

        clip = CompositeVideoClip(

            [

                clip.set_position(
                    "center"
                )

            ],

            size=size,
        )

        clip = clip.set_duration(
            duration
        )

    else:

        clip = ColorClip(

            size=size,

            color=(
                18,
                18,
                18,
            ),
        ).set_duration(
            duration
        )

    # ----------------------------------------------------------------------
    # Camera
    # ----------------------------------------------------------------------

    camera = get_camera(
        scene
    )

    camera_scale = CAMERA_SCALES.get(
        camera,
        CAMERA_SCALES[
            DEFAULT_CAMERA
        ],
    )

    if camera_scale != 1.0:

        clip = clip.resize(
            camera_scale
        )

    # ----------------------------------------------------------------------
    # Animation
    # ----------------------------------------------------------------------

    animation = get_animation(
        visual,
        scene,
    )

    zoom_factor = get_zoom_factor(
        visual
    )

    motion = get_motion_multiplier(
        visual
    )

    safe_duration = max(
        duration,
        0.1,
    )

    if animation == "zoom_in":

        clip = clip.fx(

            vfx.resize,

            lambda t:

                1.0
                + (
                    zoom_factor
                    - 1.0
                )
                * (
                    t
                    / safe_duration
                ),
        )

    elif animation == "zoom_out":

        clip = clip.fx(

            vfx.resize,

            lambda t:

                zoom_factor
                - (
                    zoom_factor
                    - 1.0
                )
                * (
                    t
                    / safe_duration
                ),
        )

    elif animation == "pan_left":

        clip = clip.set_position(

            lambda t:

                (

                    -50
                    * motion
                    * (
                        t
                        / safe_duration
                    ),

                    "center",
                )
        )

    elif animation == "pan_right":

        clip = clip.set_position(

            lambda t:

                (

                    50
                    * motion
                    * (
                        t
                        / safe_duration
                    ),

                    "center",
                )
        )

    elif animation == "rotate":

        clip = clip.rotate(

            lambda t:

                2.0
                * motion
                * (
                    t
                    / safe_duration
                )
        )

    elif animation == "parallax":

        clip = clip.fx(

            vfx.resize,

            lambda t:

                1.0
                + (
                    0.04
                    * motion
                    * (
                        t
                        / safe_duration
                    )
                ),
        )

    # "hold" = no animation

    return clip


# ==========================================================================
# SCENE VISUALS
# ==========================================================================

def build_scene_visual_clips(
    entry,
    image_paths,
    size,
):

    scene = entry.scene

    generated_paths = (
        _scene_visuals_from_generated_paths(

            image_paths,

            entry.index,
        )
    )

    fallback_image = None

    # Legacy flat list support.

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

        generated_paths,
    )

    print(
        f"🎬 Scene {entry.index + 1}: "
        f"{len(visuals)} visual(s)"
    )

    for i, path in enumerate(
        visuals,
        start=1,
    ):

        print(
            f"   Visual {i}: {path}"
        )

    count = max(
        len(visuals),
        1,
    )

    visual_duration = (

        entry.duration
        / count
    )

    clips = []

    for visual_index, image_path in enumerate(
        visuals
    ):

        start = (

            entry.start

            + (

                visual_index
                * visual_duration
            )
        )

        visual_data = {}

        storyboard_visuals = scene.get(
            "visuals",
            [],
        )

        if (

            isinstance(
                storyboard_visuals,
                list,
            )

            and visual_index
            < len(
                storyboard_visuals
            )

            and isinstance(
                storyboard_visuals[
                    visual_index
                ],
                dict,
            )
        ):

            visual_data = storyboard_visuals[
                visual_index
            ]

        clip = build_visual_clip_for_image(

            image_path,

            visual_duration,

            size,

            scene,

            visual_data,
        )

        transition = get_transition(
            scene
        )

        if transition != "hard_cut":

            fade_duration = (
                TRANSITION_DURATIONS.get(
                    transition,
                    0.0,
                )
            )

            if fade_duration > 0:

                clip = clip.crossfadein(
                    min(
                        fade_duration,
                        visual_duration / 2,
                    )
                )

        clip = (

            clip

            .set_start(
                start
            )

            .set_duration(
                visual_duration
            )
        )

        clips.append(
            clip
        )

    return clips


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


# ==========================================================================
# CAPTIONS
# ==========================================================================

def get_caption_position(
    size,
):

    width, height = size

    return (

        "center",

        int(
            height
            * CAPTION_VERTICAL_POSITION
        ),
    )


def build_captions(
    audio_path,
    script,
    timeline,
    size,
):

    print("=" * 80)
    print("📝 GENERATING CAPTIONS")
    print("=" * 80)

    try:

        words = transcribe(
            audio_path
        )

    except Exception as error:

        print(
            "❌ Caption transcription failed:"
        )

        print(
            error
        )

        raise

    if not words:

        print(
            "⚠️ No words detected."
        )

        return []

    print(
        f"Whisper detected "
        f"{len(words)} words."
    )

    clips = []

    position = get_caption_position(
        size
    )

    for word_data in words:

        text = str(

            word_data.get(
                "word",
                "",
            )
        ).strip()

        if not text:

            continue

        start = _safe_float(

            word_data.get(
                "start",
                0,
            ),

            0,

            min_value=0,
        )

        end = _safe_float(

            word_data.get(
                "end",
                start + 0.1,
            ),

            start + 0.1,

            min_value=start,
        )

        duration = max(

            0.05,

            end - start,
        )

        entry = scene_at_time(

            timeline,

            (
                start
                + end
            ) / 2.0,
        )

        scene = (

            entry.scene

            if entry

            else {}
        )

        highlights = (
            get_caption_highlights(
                scene
            )
        )

        highlighted = (

            text.lower()
            in highlights
        )

        text_color = (

            CAPTION_HIGHLIGHT_COLOR

            if highlighted

            else CAPTION_COLOR
        )

        # --------------------------------------------------------------
        # Shadow
        # --------------------------------------------------------------

        shadow = (

            TextClip(

                text,

                font=FONT,

                fontsize=CAPTION_FONT_SIZE,

                color=CAPTION_SHADOW_COLOR,
            )

            .set_start(
                start
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

        # --------------------------------------------------------------
        # Main caption
        # --------------------------------------------------------------

        caption = (

            TextClip(

                text,

                font=FONT,

                fontsize=CAPTION_FONT_SIZE,

                color=text_color,

                stroke_color=CAPTION_STROKE,

                stroke_width=CAPTION_STROKE_WIDTH,
            )

            .set_start(
                start
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
            caption
        )

    print(
        f"✅ Caption layers: "
        f"{len(clips)}"
    )

    return clips


# ==========================================================================
# AUDIO
# ==========================================================================

def build_audio(
    narration,
    music_path,
    sfx_paths,
    timeline,
    total_duration,
    video_cfg,
):

    tracks = [
        narration
    ]

    # ----------------------------------------------------------------------
    # Music
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # SFX
    # ----------------------------------------------------------------------

    if isinstance(
        sfx_paths,
        list,
    ):

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

            cue = entry.scene.get(
                "sfx_cue",
                {},
            )

            if not isinstance(
                cue,
                dict,
            ):

                cue = {}

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


# ==========================================================================
# VIDEO CONFIG
# ==========================================================================

def get_video_config(
    config,
):

    video_cfg = config.get(
        "video",
        {},
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

        "music_volume":
            music_volume,

        "sfx_volume":
            sfx_volume,
    }


# ==========================================================================
# MAIN ASSEMBLER
# ==========================================================================

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

    # ----------------------------------------------------------------------
    # Narration
    # ----------------------------------------------------------------------

    if not audio_paths:

        raise RuntimeError(
            "No narration audio was provided."
        )

    narration_path = audio_paths[0]

    if not os.path.exists(
        narration_path
    ):

        raise RuntimeError(
            f"Narration file not found: "
            f"{narration_path}"
        )

    narration = AudioFileClip(
        narration_path
    )

    total_duration = (
        narration.duration
    )

    print(
        f"Narration duration: "
        f"{total_duration:.2f}s"
    )

    # ----------------------------------------------------------------------
    # Timeline
    # ----------------------------------------------------------------------

    timeline = build_master_timeline(

        script,

        total_duration,
    )

    print(
        f"Scenes: "
        f"{len(timeline)}"
    )

    for entry in timeline:

        print(

            f"Scene {entry.index + 1}: "

            f"{entry.start:.2f}s → "

            f"{entry.end:.2f}s "

            f"({entry.duration:.2f}s)"
        )

    # ----------------------------------------------------------------------
    # Visuals
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🖼️ BUILDING VISUAL TIMELINE")
    print("=" * 80)

    visual_clips = build_timeline_visuals(

        timeline,

        image_paths,

        size,
    )

    print(
        f"Visual clips: "
        f"{len(visual_clips)}"
    )

    # ----------------------------------------------------------------------
    # Captions
    # ----------------------------------------------------------------------

    caption_clips = build_captions(

        narration_path,

        script,

        timeline,

        size,
    )

    # ----------------------------------------------------------------------
    # Composite
    # ----------------------------------------------------------------------

    all_video_clips = (

        visual_clips

        + caption_clips
    )

    final = CompositeVideoClip(

        all_video_clips,

        size=size,
    ).set_duration(

        total_duration
    )

    # ----------------------------------------------------------------------
    # Audio
    # ----------------------------------------------------------------------

    audio = build_audio(

        narration,

        music_path,

        sfx_paths,

        timeline,

        total_duration,

        video_cfg,
    )

    final = final.set_audio(
        audio
    )

    # ----------------------------------------------------------------------
    # Output directory
    # ----------------------------------------------------------------------

    output_dir = os.path.dirname(
        out_path
    )

    if output_dir:

        os.makedirs(
            output_dir,
            exist_ok=True,
        )

    # ----------------------------------------------------------------------
    # Render
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🎥 RENDERING FINAL VIDEO")
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
        f"✅ VIDEO COMPLETE:"
    )

    print(
        out_path
    )

    print("=" * 80)

    # ----------------------------------------------------------------------
    # Cleanup
    # ----------------------------------------------------------------------

    try:

        narration.close()

    except Exception:

        pass

    try:

        final.close()

    except Exception:

        pass

    return out_path