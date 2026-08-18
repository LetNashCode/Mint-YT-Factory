"""
assemble.py
Mint-YT-Factory

Version 8.0

PURPOSE
-------
Turn the v9.0 story package + 14 AI visuals + narration
into one coherent cinematic YouTube Short.

PRODUCTION CONTRACT
-------------------
- 7 scenes
- 2 visuals per scene
- 14 visuals total
- 45-second storyboard
- Portrait 9:16
- Narration-driven timing
- Word-by-word captions
- Scene-aware highlighted words
- Cinematic image motion
- Music support
- SFX support
- Visual continuity metadata
- Compatible with generate_images.py v8+
- Compatible with generate_script.py v9+

IMPORTANT
---------
The generated storyboard is the creative source of truth.

The 14 images are NOT treated as random slideshow images.

Each image:
    - belongs to a specific scene
    - has a specific visual prompt
    - has its own animation
    - has its own camera treatment
    - advances the story
"""


import os
import math
import shutil as _shutil


from whisper_align import transcribe


from moviepy.config import change_settings


# ==========================================================================
# IMAGEMAGICK
# ==========================================================================

_im = (
    _shutil.which("magick")
    or _shutil.which("convert")
)

if _im:

    change_settings({
        "IMAGEMAGICK_BINARY": _im
    })


# ==========================================================================
# MOVIEPY
# ==========================================================================

from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ColorClip,
    ImageClip,
    TextClip,
    afx,
)


# ==========================================================================
# CONSTANTS
# ==========================================================================

EXPECTED_SCENES = 7

VISUALS_PER_SCENE = 2

EXPECTED_TOTAL_VISUALS = 14

TARGET_DURATION = 45.0


# ==========================================================================
# OUTPUT
# ==========================================================================

DEFAULT_RESOLUTION = (
    1080,
    1920,
)

DEFAULT_FPS = 30


# ==========================================================================
# CAPTIONS
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

CAPTION_SHADOW_OPACITY = 0.65

CAPTION_SHADOW_OFFSET = 4

CAPTION_STROKE = "#111111"

CAPTION_STROKE_WIDTH = 2


# Caption vertical position.
# 0.64 = approximately 64% down the frame.
CAPTION_VERTICAL_POSITION = 0.64


# ==========================================================================
# AUDIO
# ==========================================================================

DEFAULT_MUSIC_VOLUME = 0.10

DEFAULT_SFX_VOLUME = 0.75


# ==========================================================================
# MOTION
# ==========================================================================

MOTION_MULTIPLIERS = {

    "low": 0.45,

    "medium": 1.0,

    "high": 1.45,
}


ZOOM_STRENGTH = {

    "subtle": 1.045,

    "medium": 1.085,

    "strong": 1.13,
}


# ==========================================================================
# CAMERA
# ==========================================================================

CAMERA_SCALE = {

    "macro": 1.10,

    "close_up": 1.075,

    "medium": 1.045,

    "wide": 1.02,

    "top_down": 1.045,

    "side": 1.045,

    "aerial": 1.02,

    "orbit": 1.055,
}


# ==========================================================================
# EXACT STORYBOARD
# ==========================================================================

SCENE_DURATIONS = [

    3.0,

    5.0,

    7.0,

    7.0,

    8.0,

    8.0,

    7.0,
]


# ==========================================================================
# SAFE HELPERS
# ==========================================================================

def _safe_float(
    value,
    default=0.0,
    minimum=None,
    maximum=None,
):

    try:

        value = float(
            value
        )

    except Exception:

        return default


    if math.isnan(value):

        return default


    if math.isinf(value):

        return default


    if minimum is not None:

        value = max(
            minimum,
            value,
        )


    if maximum is not None:

        value = min(
            maximum,
            value,
        )


    return value


def _safe_int(
    value,
    default=0,
    minimum=None,
):

    try:

        value = int(
            value
        )

    except Exception:

        return default


    if minimum is not None:

        value = max(
            minimum,
            value,
        )


    return value


def _safe_lower(
    value,
    default="",
):

    try:

        return str(
            value
        ).strip().lower()

    except Exception:

        return default


# ==========================================================================
# SCENE DURATION
# ==========================================================================

def get_scene_duration(
    scene,
    scene_index,
):

    expected = SCENE_DURATIONS[
        scene_index
    ]


    duration = _safe_float(

        scene.get(
            "duration",
            expected,
        ),

        expected,

        minimum=0.05,
    )


    # The storyboard duration is authoritative.
    if abs(
        duration - expected
    ) > 0.01:

        print(

            f"⚠️ Scene "
            f"{scene_index + 1} "
            f"duration changed from "
            f"{duration}s to "
            f"{expected}s."
        )


        duration = expected


    return duration


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


    result = set()


    for item in raw:

        if isinstance(
            item,
            dict,
        ):

            word = item.get(
                "word",
                "",
            )

        else:

            word = item


        word = str(
            word
        ).strip().lower()


        if word:

            result.add(
                word.strip(
                    ".,!?;:\"'()[]{}"
                )
            )


    return result


# ==========================================================================
# VISUAL PATH HELPERS
# ==========================================================================

def _normalize_paths(
    value,
):

    if value is None:

        return []


    if isinstance(
        value,
        str,
    ):

        value = value.strip()

        return (
            [value]
            if value
            else []
        )


    if not isinstance(
        value,
        list,
    ):

        return []


    result = []


    for item in value:

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

                or item.get(
                    "image"
                )

                or item.get(
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


    return result


def get_scene_image_paths(
    image_paths,
    scene_index,
):

    if not isinstance(
        image_paths,
        list,
    ):

        return []


    if (
        scene_index
        >= len(image_paths)
    ):

        return []


    paths = _normalize_paths(
        image_paths[
            scene_index
        ]
    )


    existing = [

        path

        for path in paths

        if os.path.exists(
            path
        )
    ]


    return existing


# ==========================================================================
# VALIDATE IMAGE CONTRACT
# ==========================================================================

def validate_image_contract(
    image_paths,
):

    if not isinstance(
        image_paths,
        list,
    ):

        raise RuntimeError(
            "image_paths must be a list."
        )


    if len(
        image_paths
    ) != EXPECTED_SCENES:

        raise RuntimeError(

            f"Expected "
            f"{EXPECTED_SCENES} image groups, "
            f"got "
            f"{len(image_paths)}."
        )


    total = 0


    for scene_index in range(
        EXPECTED_SCENES
    ):

        paths = get_scene_image_paths(

            image_paths,

            scene_index,
        )


        count = len(
            paths
        )


        print(

            f"Scene "
            f"{scene_index + 1}: "
            f"{count}/"
            f"{VISUALS_PER_SCENE} images"
        )


        if count != VISUALS_PER_SCENE:

            raise RuntimeError(

                f"Scene "
                f"{scene_index + 1} "
                f"requires "
                f"{VISUALS_PER_SCENE} images, "
                f"found {count}."
            )


        total += count


    if total != EXPECTED_TOTAL_VISUALS:

        raise RuntimeError(

            f"Expected "
            f"{EXPECTED_TOTAL_VISUALS} total images, "
            f"found {total}."
        )


# ==========================================================================
# IMAGE FITTING
# ==========================================================================

def make_image_clip(
    image_path,
    frame_size,
):

    width, height = frame_size


    clip = ImageClip(
        image_path
    )


    # ----------------------------------------------------------------------
    # Cover the entire portrait frame.
    # ----------------------------------------------------------------------

    scale = max(

        width / clip.w,

        height / clip.h,
    )


    clip = clip.resize(
        scale
    )


    # ----------------------------------------------------------------------
    # Crop to exact portrait dimensions.
    # ----------------------------------------------------------------------

    crop_x = max(
        0,
        int(
            (clip.w - width)
            / 2
        ),
    )


    crop_y = max(
        0,
        int(
            (clip.h - height)
            / 2
        ),
    )


    clip = clip.crop(

        x1=crop_x,

        y1=crop_y,

        x2=crop_x + width,

        y2=crop_y + height,
    )


    return clip


# ==========================================================================
# VISUAL ANIMATION
# ==========================================================================

def get_visual_animation(
    visual,
):

    animation = _safe_lower(

        visual.get(
            "animation",
            "hold",
        ),

        "hold",
    )


    allowed = {

        "zoom_in",

        "zoom_out",

        "pan_left",

        "pan_right",

        "rotate",

        "parallax",

        "highlight",

        "hold",
    }


    if animation not in allowed:

        animation = "hold"


    return animation


def get_visual_zoom(
    visual,
):

    explicit = visual.get(
        "zoom_factor"
    )


    if explicit is not None:

        return _safe_float(

            explicit,

            1.06,

            minimum=1.0,

            maximum=1.15,
        )


    strength = _safe_lower(

        visual.get(
            "zoom_strength",
            "subtle",
        ),

        "subtle",
    )


    return ZOOM_STRENGTH.get(
        strength,
        ZOOM_STRENGTH[
            "subtle"
        ],
    )


def get_visual_motion(
    visual,
):

    intensity = _safe_lower(

        visual.get(
            "motion_intensity",
            "medium",
        ),

        "medium",
    )


    return MOTION_MULTIPLIERS.get(

        intensity,

        MOTION_MULTIPLIERS[
            "medium"
        ],
    )


def get_camera_scale(
    scene,
    visual,
):

    camera = _safe_lower(

        visual.get(
            "camera",
            scene.get(
                "camera",
                "medium",
            ),
        ),

        "medium",
    )


    return CAMERA_SCALE.get(

        camera,

        CAMERA_SCALE[
            "medium"
        ],
    )


# ==========================================================================
# BUILD ANIMATED IMAGE
# ==========================================================================

def build_animated_image(
    image_path,
    duration,
    frame_size,
    scene,
    visual,
):

    clip = make_image_clip(

        image_path,

        frame_size,
    )


    clip = clip.set_duration(
        duration
    )


    animation = get_visual_animation(
        visual
    )


    zoom = get_visual_zoom(
        visual
    )


    motion = get_visual_motion(
        visual
    )


    camera_scale = get_camera_scale(

        scene,

        visual,
    )


    # ----------------------------------------------------------------------
    # Combine camera treatment + storyboard animation.
    # ----------------------------------------------------------------------

    base_scale = camera_scale


    if animation in {
        "zoom_in",
        "zoom_out",
        "parallax",
    }:

        final_scale = (
            base_scale
            * zoom
        )

    else:

        final_scale = base_scale


    if final_scale > 1.0:

        clip = clip.resize(
            final_scale
        )


    safe_duration = max(
        duration,
        0.1,
    )


    # ----------------------------------------------------------------------
    # ZOOM IN
    # ----------------------------------------------------------------------

    if animation == "zoom_in":

        start_scale = base_scale


        end_scale = (
            base_scale
            * zoom
        )


        clip = clip.resize(

            lambda t:

                start_scale
                + (

                    end_scale
                    - start_scale

                ) * min(

                    max(
                        t / safe_duration,
                        0.0,
                    ),

                    1.0,
                )
        )


        clip = clip.set_position(
            "center"
        )


    # ----------------------------------------------------------------------
    # ZOOM OUT
    # ----------------------------------------------------------------------

    elif animation == "zoom_out":

        start_scale = (
            base_scale
            * zoom
        )


        end_scale = base_scale


        clip = clip.resize(

            lambda t:

                start_scale
                - (

                    start_scale
                    - end_scale

                ) * min(

                    max(
                        t / safe_duration,
                        0.0,
                    ),

                    1.0,
                )
        )


        clip = clip.set_position(
            "center"
        )


    # ----------------------------------------------------------------------
    # PAN LEFT
    # ----------------------------------------------------------------------

    elif animation == "pan_left":

        travel = (
            70
            * motion
        )


        clip = clip.set_position(

            lambda t:

                (

                    -travel
                    * min(

                        max(
                            t / safe_duration,
                            0.0,
                        ),

                        1.0,
                    ),

                    "center",
                )
        )


    # ----------------------------------------------------------------------
    # PAN RIGHT
    # ----------------------------------------------------------------------

    elif animation == "pan_right":

        travel = (
            70
            * motion
        )


        clip = clip.set_position(

            lambda t:

                (

                    travel
                    * min(

                        max(
                            t / safe_duration,
                            0.0,
                        ),

                        1.0,
                    ),

                    "center",
                )
        )


    # ----------------------------------------------------------------------
    # ROTATE
    # ----------------------------------------------------------------------

    elif animation == "rotate":

        clip = clip.rotate(

            lambda t:

                1.0
                * motion
                * min(

                    max(
                        t / safe_duration,
                        0.0,
                    ),

                    1.0,
                )
        )


        clip = clip.set_position(
            "center"
        )


    # ----------------------------------------------------------------------
    # PARALLAX
    # ----------------------------------------------------------------------

    elif animation == "parallax":

        clip = clip.resize(

            lambda t:

                base_scale
                * (

                    1.0
                    + (

                        0.025
                        * motion
                        * min(

                            max(
                                t / safe_duration,
                                0.0,
                            ),

                            1.0,
                        )
                    )
                )
        )


        clip = clip.set_position(
            "center"
        )


    # ----------------------------------------------------------------------
    # HOLD / HIGHLIGHT
    # ----------------------------------------------------------------------

    else:

        clip = clip.set_position(
            "center"
        )


    return clip


# ==========================================================================
# BUILD SCENE VISUALS
# ==========================================================================

def build_scene_visuals(
    scene,
    scene_index,
    image_paths,
    frame_size,
):

    paths = get_scene_image_paths(

        image_paths,

        scene_index,
    )


    if len(paths) != 2:

        raise RuntimeError(

            f"Scene "
            f"{scene_index + 1} "
            f"does not have exactly "
            f"2 visuals."
        )


    scene_duration = get_scene_duration(

        scene,

        scene_index,
    )


    # ----------------------------------------------------------------------
    # Split the scene into two shots.
    #
    # This is intentionally equal.
    #
    # Example:
    #
    # 7 seconds → 3.5 + 3.5
    # 8 seconds → 4.0 + 4.0
    # ----------------------------------------------------------------------

    shot_duration = (

        scene_duration
        / 2.0
    )


    clips = []


    for visual_index in range(2):

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


        print(

            f"   Scene "
            f"{scene_index + 1} "
            f"Shot "
            f"{visual_index + 1}: "
            f"{paths[visual_index]}"
        )


        clip = build_animated_image(

            paths[visual_index],

            shot_duration,

            frame_size,

            scene,

            visual_data,
        )


        clip = clip.set_start(

            (

                sum(
                    SCENE_DURATIONS[
                        :scene_index
                    ]
                )

                + (

                    visual_index
                    * shot_duration
                )
            )
        )


        clips.append(
            clip
        )


    return clips


# ==========================================================================
# BUILD COMPLETE VISUAL TIMELINE
# ==========================================================================

def build_visual_timeline(
    script,
    image_paths,
    frame_size,
):

    scenes = script.get(
        "scene_plan",
        [],
    )


    if len(scenes) != EXPECTED_SCENES:

        raise RuntimeError(

            f"Expected "
            f"{EXPECTED_SCENES} scenes."
        )


    clips = []


    current_time = 0.0


    for scene_index, scene in enumerate(
        scenes
    ):

        duration = get_scene_duration(

            scene,

            scene_index,
        )


        paths = get_scene_image_paths(

            image_paths,

            scene_index,
        )


        print(

            f"🎬 Scene "
            f"{scene_index + 1}: "
            f"{current_time:.2f}s → "
            f"{current_time + duration:.2f}s"
        )


        shot_duration = (
            duration / 2.0
        )


        for visual_index in range(2):

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


            clip = build_animated_image(

                paths[visual_index],

                shot_duration,

                frame_size,

                scene,

                visual_data,
            )


            clip = clip.set_start(

                current_time
                + (

                    visual_index
                    * shot_duration
                )
            )


            clips.append(
                clip
            )


        current_time += duration


    return clips


# ==========================================================================
# CAPTION POSITION
# ==========================================================================

def caption_position(
    frame_size,
):

    width, height = frame_size


    return (

        "center",

        int(
            height
            * CAPTION_VERTICAL_POSITION
        ),
    )


# ==========================================================================
# TEXT CLIP
# ==========================================================================

def create_caption(
    text,
    color,
    start,
    duration,
    position,
    opacity=1.0,
):

    clip = TextClip(

        text,

        font=FONT,

        fontsize=CAPTION_FONT_SIZE,

        color=color,

        stroke_color=CAPTION_STROKE,

        stroke_width=CAPTION_STROKE_WIDTH,
    )


    return (

        clip

        .set_start(
            start
        )

        .set_duration(
            duration
        )

        .set_position(
            position
        )

        .set_opacity(
            opacity
        )
    )


# ==========================================================================
# CAPTION GENERATION
# ==========================================================================

def build_captions(
    narration_path,
    script,
    frame_size,
):

    print("=" * 80)

    print(
        "📝 BUILDING WORD-BY-WORD CAPTIONS"
    )

    print("=" * 80)


    words = transcribe(
        narration_path
    )


    if not words:

        raise RuntimeError(
            "Whisper returned no words."
        )


    print(
        f"Detected words: "
        f"{len(words)}"
    )


    scenes = script.get(
        "scene_plan",
        [],
    )


    if len(scenes) != EXPECTED_SCENES:

        raise RuntimeError(
            "Caption generation requires "
            f"{EXPECTED_SCENES} scenes."
        )


    # ----------------------------------------------------------------------
    # Build exact scene boundaries.
    # ----------------------------------------------------------------------

    scene_ranges = []


    current = 0.0


    for scene_index, scene in enumerate(
        scenes
    ):

        duration = get_scene_duration(

            scene,

            scene_index,
        )


        scene_ranges.append({

            "start":
                current,

            "end":
                current + duration,

            "scene":
                scene,
        })


        current += duration


    position = caption_position(
        frame_size
    )


    clips = []


    for word_data in words:

        word = str(

            word_data.get(
                "word",
                "",
            )
        ).strip()


        if not word:

            continue


        start = _safe_float(

            word_data.get(
                "start",
                0,
            ),

            0,

            minimum=0,
        )


        end = _safe_float(

            word_data.get(
                "end",
                start + 0.1,
            ),

            start + 0.1,

            minimum=start,
        )


        duration = max(

            0.04,

            end - start,
        )


        # --------------------------------------------------------------
        # Find scene.
        # --------------------------------------------------------------

        scene = scenes[-1]


        for item in scene_ranges:

            if (

                item["start"]
                <= start
                < item["end"]

            ):

                scene = item["scene"]

                break


        highlights = get_caption_highlights(
            scene
        )


        normalized = (

            word.lower()
            .strip(
                ".,!?;:\"'()[]{}"
            )
        )


        highlighted = (

            normalized
            in highlights
        )


        color = (

            CAPTION_HIGHLIGHT_COLOR

            if highlighted

            else CAPTION_COLOR
        )


        # --------------------------------------------------------------
        # Shadow.
        # --------------------------------------------------------------

        shadow = create_caption(

            word,

            CAPTION_SHADOW_COLOR,

            start,

            duration,

            (

                position[0],

                position[1]
                + CAPTION_SHADOW_OFFSET,
            ),

            CAPTION_SHADOW_OPACITY,
        )


        # --------------------------------------------------------------
        # Main word.
        # --------------------------------------------------------------

        caption = create_caption(

            word,

            color,

            start,

            duration,

            position,
        )


        clips.append(
            shadow
        )


        clips.append(
            caption
        )


    print(

        f"Caption layers: "
        f"{len(clips)}"
    )


    return clips


# ==========================================================================
# AUDIO CONFIG
# ==========================================================================

def get_audio_config(
    config,
):

    video_config = config.get(
        "video",
        {},
    )


    if not isinstance(
        video_config,
        dict,
    ):

        video_config = {}


    music_volume = _safe_float(

        video_config.get(
            "music_volume",
            DEFAULT_MUSIC_VOLUME,
        ),

        DEFAULT_MUSIC_VOLUME,

        minimum=0,

        maximum=1,
    )


    sfx_volume = _safe_float(

        video_config.get(
            "sfx_volume",
            DEFAULT_SFX_VOLUME,
        ),

        DEFAULT_SFX_VOLUME,

        minimum=0,

        maximum=2,
    )


    return {

        "music_volume":
            music_volume,

        "sfx_volume":
            sfx_volume,
    }


# ==========================================================================
# AUDIO
# ==========================================================================

def build_audio(
    narration,
    music_path,
    sfx_paths,
    script,
    total_duration,
    config,
):

    audio_config = get_audio_config(
        config
    )


    tracks = [
        narration
    ]


    # ----------------------------------------------------------------------
    # Narration
    # ----------------------------------------------------------------------

    narration = narration.set_duration(
        total_duration
    )


    # ----------------------------------------------------------------------
    # Music
    # ----------------------------------------------------------------------

    if (

        music_path

        and os.path.exists(
            music_path
        )
    ):

        print(
            f"🎵 Music: "
            f"{music_path}"
        )


        music = AudioFileClip(
            music_path
        )


        music = music.fx(

            afx.audio_loop,

            duration=total_duration,
        )


        music = (

            music

            .volumex(
                audio_config[
                    "music_volume"
                ]
            )

            .set_duration(
                total_duration
            )
        )


        tracks.append(
            music
        )


    # ----------------------------------------------------------------------
    # SFX
    # ----------------------------------------------------------------------

    scenes = script.get(
        "scene_plan",
        [],
    )


    if isinstance(
        sfx_paths,
        list,
    ):

        current_time = 0.0


        for scene_index, scene in enumerate(
            scenes
        ):

            if scene_index >= len(
                sfx_paths
            ):

                break


            sfx_path = sfx_paths[
                scene_index
            ]


            if not (

                sfx_path

                and os.path.exists(
                    sfx_path
                )
            ):

                current_time += (
                    get_scene_duration(
                        scene,
                        scene_index,
                    )
                )

                continue


            cue = scene.get(
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

                    minimum=0,
                )

                / 1000.0
            )


            start = (
                current_time
                + offset
            )


            if start < total_duration:

                effect = AudioFileClip(
                    sfx_path
                )


                effect = (

                    effect

                    .set_start(
                        start
                    )

                    .volumex(
                        audio_config[
                            "sfx_volume"
                        ]
                    )
                )


                tracks.append(
                    effect
                )


            current_time += (
                get_scene_duration(
                    scene,
                    scene_index,
                )
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

    video = config.get(
        "video",
        {},
    )


    if not isinstance(
        video,
        dict,
    ):

        video = {}


    resolution = video.get(

        "resolution",

        DEFAULT_RESOLUTION,
    )


    try:

        width = int(
            resolution[0]
        )

        height = int(
            resolution[1]
        )

    except Exception:

        width, height = (
            DEFAULT_RESOLUTION
        )


    # Force portrait.
    if width > height:

        width, height = (
            height,
            width,
        )


    fps = _safe_int(

        video.get(
            "fps",
            DEFAULT_FPS,
        ),

        DEFAULT_FPS,

        minimum=1,
    )


    return {

        "size":
            (
                width,
                height,
            ),

        "fps":
            fps,
    }


# ==========================================================================
# STORYBOARD VALIDATION
# ==========================================================================

def validate_storyboard(
    script,
):

    scenes = script.get(
        "scene_plan",
        [],
    )


    if len(scenes) != EXPECTED_SCENES:

        raise RuntimeError(

            f"Storyboard must contain "
            f"{EXPECTED_SCENES} scenes."
        )


    total = 0.0


    for index, scene in enumerate(
        scenes
    ):

        expected = SCENE_DURATIONS[
            index
        ]


        duration = get_scene_duration(

            scene,

            index,
        )


        if abs(
            duration - expected
        ) > 0.01:

            raise RuntimeError(

                f"Scene "
                f"{index + 1} duration mismatch."
            )


        visuals = scene.get(
            "visuals",
            [],
        )


        if len(visuals) != 2:

            raise RuntimeError(

                f"Scene "
                f"{index + 1} "
                f"must contain exactly "
                f"2 storyboard visuals."
            )


        narration = str(

            scene.get(
                "narration",
                "",
            )
        ).strip()


        if not narration:

            raise RuntimeError(

                f"Scene "
                f"{index + 1} "
                "has no narration."
            )


        subtitle = str(

            scene.get(
                "subtitle_text",
                "",
            )
        ).strip()


        # ------------------------------------------------------------------
        # generate_script.py v9 guarantees this.
        # ------------------------------------------------------------------

        if subtitle != narration:

            print(

                f"⚠️ Scene "
                f"{index + 1} "
                "subtitle_text did not match narration."
            )


            scene[
                "subtitle_text"
            ] = narration


        total += duration


    if abs(
        total - TARGET_DURATION
    ) > 0.01:

        raise RuntimeError(

            f"Storyboard duration is "
            f"{total}s, expected "
            f"{TARGET_DURATION}s."
        )


# ==========================================================================
# FINAL ASSEMBLY
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

    print(
        "🎬 MINT-YT-FACTORY "
        "ASSEMBLY v8.0"
    )

    print("=" * 80)


    # ==========================================================================
    # STORYBOARD
    # ==========================================================================

    validate_storyboard(
        script
    )


    # ==========================================================================
    # IMAGE CONTRACT
    # ==========================================================================

    validate_image_contract(
        image_paths
    )


    # ==========================================================================
    # VIDEO CONFIG
    # ==========================================================================

    video_config = get_video_config(
        config
    )


    frame_size = video_config[
        "size"
    ]


    fps = video_config[
        "fps"
    ]


    print(
        f"Resolution: "
        f"{frame_size[0]}x"
        f"{frame_size[1]}"
    )


    print(
        f"FPS: "
        f"{fps}"
    )


    # ==========================================================================
    # NARRATION
    # ==========================================================================

    if not audio_paths:

        raise RuntimeError(
            "No narration audio supplied."
        )


    narration_path = audio_paths[
        0
    ]


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


    narration_duration = (
        narration.duration
    )


    print(
        f"Narration: "
        f"{narration_duration:.2f}s"
    )


    # ==========================================================================
    # VISUAL TIMELINE
    # ==========================================================================

    print("=" * 80)

    print(
        "🖼️ BUILDING 14-SHOT VISUAL TIMELINE"
    )

    print("=" * 80)


    visual_clips = build_visual_timeline(

        script,

        image_paths,

        frame_size,
    )


    print(
        f"Visual clips created: "
        f"{len(visual_clips)}"
    )


    if len(
        visual_clips
    ) != EXPECTED_TOTAL_VISUALS:

        raise RuntimeError(

            f"Expected "
            f"{EXPECTED_TOTAL_VISUALS} "
            f"visual clips, got "
            f"{len(visual_clips)}."
        )


    # ==========================================================================
    # CAPTIONS
    # ==========================================================================

    caption_clips = build_captions(

        narration_path,

        script,

        frame_size,
    )


    # ==========================================================================
    # FINAL VIDEO DURATION
    # ==========================================================================

    # The storyboard is 45 sec, but narration remains the final
    # synchronization authority.
    #
    # Never extend the video beyond narration.

    final_duration = min(

        TARGET_DURATION,

        narration_duration,
    )


    print(
        f"Final duration: "
        f"{final_duration:.2f}s"
    )


    # ==========================================================================
    # COMPOSITE
    # ==========================================================================

    all_video_clips = (

        visual_clips

        + caption_clips
    )


    final = CompositeVideoClip(

        all_video_clips,

        size=frame_size,
    )


    final = final.set_duration(
        final_duration
    )


    # ==========================================================================
    # AUDIO
    # ==========================================================================

    audio = build_audio(

        narration,

        music_path,

        sfx_paths,

        script,

        final_duration,

        config,
    )


    final = final.set_audio(
        audio
    )


    # ==========================================================================
    # OUTPUT DIRECTORY
    # ==========================================================================

    output_dir = os.path.dirname(
        out_path
    )


    if output_dir:

        os.makedirs(

            output_dir,

            exist_ok=True,
        )


    # ==========================================================================
    # RENDER
    # ==========================================================================

    print("=" * 80)

    print(
        "🎥 RENDERING FINAL SHORT"
    )

    print("=" * 80)


    print(
        f"Output: "
        f"{out_path}"
    )


    print(
        "Story structure: "
        "7 scenes / 14 shots"
    )


    print(
        "Captions: "
        "word-by-word"
    )


    print(
        "Visual continuity: "
        "enabled"
    )


    print(
        "Portrait 9:16: "
        "enabled"
    )


    final.write_videofile(

        out_path,

        fps=fps,

        codec="libx264",

        audio_codec="aac",

        preset="medium",

        threads=4,

        temp_audiofile=(
            out_path
            + ".temp_audio.m4a"
        ),

        remove_temp=True,
    )


    print("=" * 80)

    print(
        "✅ FINAL SHORT COMPLETE"
    )

    print("=" * 80)


    print(
        out_path
    )


    # ==========================================================================
    # CLEANUP
    # ==========================================================================

    try:

        narration.close()

    except Exception:

        pass


    try:

        audio.close()

    except Exception:

        pass


    try:

        final.close()

    except Exception:

        pass


    for clip in visual_clips:

        try:

            clip.close()

        except Exception:

            pass


    for clip in caption_clips:

        try:

            clip.close()

        except Exception:

            pass


    return out_path