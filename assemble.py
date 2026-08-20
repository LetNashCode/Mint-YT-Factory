"""
assemble.py
Mint-YT-Factory

Version 8.2

PURPOSE
-------
Turn the story package + 14 AI visuals + narration
into one coherent cinematic YouTube Short.

PRODUCTION CONTRACT
-------------------
- 7 scenes
- 2 visuals per scene
- 14 visuals total
- 45-second storyboard
- Portrait 9:16
- Narration-driven captions
- ONE WORD AT A TIME captions
- Scene-aware highlighted words
- Cinematic image motion
- Music support
- SFX support
- Visual continuity metadata

CAPTION SYSTEM v8.2
-------------------
- Exactly one spoken word visible at a time
- Whisper word timestamps control timing
- Main/emphasis words are yellow
- Normal words are white
- No caption background rectangle
- Black stroke + subtle shadow for readability
- Captions remain centered
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

# Maximum final Short duration.
# Stories may naturally run longer than 45 seconds when needed,
# but narration is never allowed to exceed 60 seconds.
MAX_VIDEO_DURATION = 60.0
END_HOLD_SECONDS = 0.20

DEFAULT_RESOLUTION = (
    1080,
    1920,
)

DEFAULT_FPS = 30


# ==========================================================================
# CAPTIONS
# ==========================================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

FONT = os.path.join(
    BASE_DIR,
    "assets",
    "Fonts",
    "Poppins-ExtraBold.ttf",
)

if not os.path.isfile(FONT):
    raise RuntimeError(
        f"Caption font not found: {FONT}"
    )

print(
    f"✅ Caption font found: {FONT}"
)


# --------------------------------------------------------------------------
# Caption visual design
# --------------------------------------------------------------------------

CAPTION_FONT_SIZE = 78

CAPTION_COLOR = "white"

CAPTION_HIGHLIGHT_COLOR = "#FFD54A"

CAPTION_STROKE = "#111111"

CAPTION_STROKE_WIDTH = 3

CAPTION_SHADOW_COLOR = "black"

CAPTION_SHADOW_OPACITY = 0.55

CAPTION_SHADOW_OFFSET = 4

# Vertical position as percentage of video height.
#
# 0.64 means approximately 64% down the screen.
# This keeps captions around the lower-middle area rather than
# sitting directly on the bottom YouTube UI.
CAPTION_VERTICAL_POSITION = 0.64

# Minimum caption duration.
CAPTION_MIN_DURATION = 0.05

# Maximum amount of time a single word is allowed to remain
# on screen when Whisper reports an unusually long gap.
#
# This prevents one word from hanging on screen during a pause.
CAPTION_MAX_DURATION = 1.20


# ==========================================================================
# AUDIO
# ==========================================================================

DEFAULT_MUSIC_VOLUME = 0.25
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
        value = float(value)

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
        value = int(value)

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

    result = set()

    if isinstance(
        raw,
        list,
    ):

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

    # ----------------------------------------------------------------------
    # Also respect emphasis_word.
    #
    # generate_script.py already produces this field.
    # If it is present, it should always be treated as a main word.
    # ----------------------------------------------------------------------

    emphasis_word = str(
        scene.get(
            "emphasis_word",
            "",
        )
    ).strip().lower()

    if emphasis_word:

        result.add(
            emphasis_word.strip(
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
                item.get("path")
                or item.get("image")
                or item.get("src")
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

    if scene_index >= len(
        image_paths
    ):
        return []

    paths = _normalize_paths(
        image_paths[
            scene_index
        ]
    )

    return [
        path
        for path in paths
        if os.path.exists(path)
    ]


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
            f"got {len(image_paths)}."
        )

    total = 0

    for scene_index in range(
        EXPECTED_SCENES
    ):

        paths = get_scene_image_paths(
            image_paths,
            scene_index,
        )

        count = len(paths)

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

    scale = max(
        width / clip.w,
        height / clip.h,
    )

    clip = clip.resize(
        scale
    )

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
# VISUAL SETTINGS
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
        ZOOM_STRENGTH["subtle"],
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
        MOTION_MULTIPLIERS["medium"],
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
        CAMERA_SCALE["medium"],
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

    safe_duration = max(
        duration,
        0.1,
    )

    if animation == "zoom_in":

        start_scale = camera_scale
        end_scale = camera_scale * zoom

        def scale_function(t):

            progress = min(
                max(
                    t / safe_duration,
                    0.0,
                ),
                1.0,
            )

            return (
                start_scale
                + (
                    end_scale
                    - start_scale
                )
                * progress
            )

        clip = clip.resize(
            scale_function
        )

        clip = clip.set_position(
            "center"
        )

    elif animation == "zoom_out":

        start_scale = camera_scale * zoom
        end_scale = camera_scale

        def scale_function(t):

            progress = min(
                max(
                    t / safe_duration,
                    0.0,
                ),
                1.0,
            )

            return (
                start_scale
                - (
                    start_scale
                    - end_scale
                )
                * progress
            )

        clip = clip.resize(
            scale_function
        )

        clip = clip.set_position(
            "center"
        )

    elif animation == "pan_left":

        clip = clip.resize(
            camera_scale
        )

        travel = (
            70
            * motion
        )

        def position_function(t):

            progress = min(
                max(
                    t / safe_duration,
                    0.0,
                ),
                1.0,
            )

            return (
                -travel * progress,
                "center",
            )

        clip = clip.set_position(
            position_function
        )

    elif animation == "pan_right":

        clip = clip.resize(
            camera_scale
        )

        travel = (
            70
            * motion
        )

        def position_function(t):

            progress = min(
                max(
                    t / safe_duration,
                    0.0,
                ),
                1.0,
            )

            return (
                travel * progress,
                "center",
            )

        clip = clip.set_position(
            position_function
        )

    elif animation == "rotate":

        clip = clip.resize(
            camera_scale
        )

        def angle_function(t):

            progress = min(
                max(
                    t / safe_duration,
                    0.0,
                ),
                1.0,
            )

            return (
                1.0
                * motion
                * progress
            )

        clip = clip.rotate(
            angle_function
        )

        clip = clip.set_position(
            "center"
        )

    elif animation == "parallax":

        base_scale = (
            camera_scale
            * 1.02
        )

        def scale_function(t):

            progress = min(
                max(
                    t / safe_duration,
                    0.0,
                ),
                1.0,
            )

            return (
                base_scale
                + (
                    0.025
                    * motion
                    * progress
                )
            )

        clip = clip.resize(
            scale_function
        )

        clip = clip.set_position(
            "center"
        )

    else:

        clip = clip.resize(
            camera_scale
        )

        clip = clip.set_position(
            "center"
        )

    return clip


# ==========================================================================
# VISUAL TIMELINE
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

    if len(
        scenes
    ) != EXPECTED_SCENES:

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

        if len(paths) != 2:

            raise RuntimeError(
                f"Scene "
                f"{scene_index + 1} "
                "does not have exactly 2 images."
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

        storyboard_visuals = scene.get(
            "visuals",
            [],
        )

        for visual_index in range(2):

            visual_data = {}

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
# CAPTION TEXT CLIP
# ==========================================================================

def _make_word_clip(
    word,
    color,
):

    """
    Create a single transparent text layer.

    IMPORTANT:
    method='label' is intentional.

    The previous implementation used method='caption'.
    That mode is designed for caption boxes / constrained text
    and can produce unwanted background/layout behavior.

    'label' creates only the text itself with transparency.
    """

    return TextClip(
        word,
        font=FONT,
        fontsize=CAPTION_FONT_SIZE,
        color=color,
        stroke_color=CAPTION_STROKE,
        stroke_width=CAPTION_STROKE_WIDTH,
        method="label",
    )


def _make_word_shadow(
    word,
):

    """
    Create a subtle shadow behind the word.

    This is NOT a background box.
    It is only a slightly offset duplicate of the text.
    """

    return TextClip(
        word,
        font=FONT,
        fontsize=CAPTION_FONT_SIZE,
        color=CAPTION_SHADOW_COLOR,
        stroke_color=CAPTION_SHADOW_COLOR,
        stroke_width=CAPTION_STROKE_WIDTH,
        method="label",
    )


# ==========================================================================
# CAPTION WORD NORMALIZATION
# ==========================================================================

def _normalize_caption_word(
    word,
):

    return str(
        word
    ).strip().lower().strip(
        ".,!?;:\"'()[]{}"
    )


# ==========================================================================
# NORMALIZE WHISPER WORDS
# ==========================================================================

def _normalize_whisper_words(
    words,
):

    """
    Normalize Whisper alignment output.

    Each returned item contains:

        word
        start
        end

    Invalid / empty entries are ignored.
    """

    normalized = []

    if not isinstance(
        words,
        list,
    ):

        return normalized

    for item in words:

        if not isinstance(
            item,
            dict,
        ):
            continue

        word = str(
            item.get(
                "word",
                "",
            )
        ).strip()

        if not word:
            continue

        start = _safe_float(
            item.get(
                "start",
                0,
            ),
            0,
            minimum=0,
        )

        end = _safe_float(
            item.get(
                "end",
                start + 0.1,
            ),
            start + 0.1,
            minimum=start,
        )

        if end <= start:

            end = (
                start
                + 0.1
            )

        normalized.append({
            "word": word,
            "start": start,
            "end": end,
        })

    normalized.sort(
        key=lambda item: item["start"]
    )

    return normalized


# ==========================================================================
# BUILD ONE-WORD CAPTION TIMELINE
# ==========================================================================

def _build_word_timeline(
    words,
):

    """
    Create exactly one caption event per spoken word.

    The word remains visible from its Whisper start until:

        - its Whisper end, OR
        - the next word starts

    whichever comes first.

    This guarantees that two words are never intentionally displayed
    as a group.

    A maximum duration prevents captions from hanging during pauses.
    """

    timeline = []

    count = len(words)

    for index, item in enumerate(
        words
    ):

        start = item["start"]

        end = item["end"]

        # --------------------------------------------------------------
        # Never allow this word to overlap the next word.
        # --------------------------------------------------------------

        if index + 1 < count:

            next_start = words[
                index + 1
            ]["start"]

            end = min(
                end,
                next_start,
            )

        # --------------------------------------------------------------
        # Prevent unusually long caption holds.
        # --------------------------------------------------------------

        end = min(
            end,
            start
            + CAPTION_MAX_DURATION,
        )

        duration = max(
            CAPTION_MIN_DURATION,
            end - start,
        )

        timeline.append({
            "word": item["word"],
            "start": start,
            "end": start + duration,
            "duration": duration,
        })

    return timeline


# ==========================================================================
# FIND SCENE FOR TIME
# ==========================================================================

def _get_scene_for_time(
    scenes,
    scene_ranges,
    timestamp,
):

    for item in scene_ranges:

        if (
            item["start"]
            <= timestamp
            < item["end"]
        ):

            return item["scene"]

    return scenes[-1]


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
        "📝 BUILDING ONE-WORD KINETIC CAPTIONS"
    )

    print("=" * 80)

    words = transcribe(
        narration_path
    )

    if not words:

        raise RuntimeError(
            "Whisper returned no words."
        )

    words = _normalize_whisper_words(
        words
    )

    if not words:

        raise RuntimeError(
            "Whisper returned no usable word timestamps."
        )

    print(
        f"Detected words: "
        f"{len(words)}"
    )

    scenes = script.get(
        "scene_plan",
        [],
    )

    if len(
        scenes
    ) != EXPECTED_SCENES:

        raise RuntimeError(
            "Caption generation requires "
            f"{EXPECTED_SCENES} scenes."
        )

    # ----------------------------------------------------------------------
    # Build exact scene timeline.
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
            "start": current,
            "end": current + duration,
            "scene": scene,
        })

        current += duration

    # ----------------------------------------------------------------------
    # Convert Whisper words into one-word caption events.
    # ----------------------------------------------------------------------

    word_timeline = _build_word_timeline(
        words
    )

    position = caption_position(
        frame_size
    )

    clips = []

    normal_count = 0
    highlighted_count = 0

    # ----------------------------------------------------------------------
    # ONE WORD AT A TIME
    # ----------------------------------------------------------------------

    for item in word_timeline:

        word = item["word"]

        start = item["start"]

        duration = item["duration"]

        scene = _get_scene_for_time(
            scenes,
            scene_ranges,
            start,
        )

        highlights = get_caption_highlights(
            scene
        )

        normalized = _normalize_caption_word(
            word
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

        if highlighted:
            highlighted_count += 1
        else:
            normal_count += 1

        # --------------------------------------------------------------
        # Main word layer.
        #
        # method='label' ensures transparent background.
        # --------------------------------------------------------------

        text_clip = _make_word_clip(
            word,
            color,
        )

        text_clip = (
            text_clip
            .set_start(start)
            .set_duration(duration)
            .set_position(position)
        )

        # --------------------------------------------------------------
        # Subtle shadow layer.
        #
        # This is intentionally just text — no rectangle.
        # --------------------------------------------------------------

        shadow_clip = _make_word_shadow(
            word
        )

        shadow_clip = (
            shadow_clip
            .set_start(start)
            .set_duration(duration)
            .set_position(
                (
                    "center",
                    position[1]
                    + CAPTION_SHADOW_OFFSET,
                )
            )
            .set_opacity(
                CAPTION_SHADOW_OPACITY
            )
        )

        # Shadow goes underneath text.
        clips.append(
            shadow_clip
        )

        clips.append(
            text_clip
        )

    print(
        f"Caption layers: "
        f"{len(clips)}"
    )

    print(
        f"Caption words: "
        f"{len(word_timeline)}"
    )

    print(
        f"White words: "
        f"{normal_count}"
    )

    print(
        f"Yellow highlighted words: "
        f"{highlighted_count}"
    )

    print(
        "Caption mode: ONE WORD AT A TIME"
    )

    print(
        "Caption background: NONE"
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

    tracks = []

    narration_track = (
        narration
        .set_start(0)
        .set_duration(
            min(
                narration.duration,
                total_duration,
            )
        )
    )

    tracks.append(
        narration_track
    )

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

            scene_duration = get_scene_duration(
                scene,
                scene_index,
            )

            if not (
                sfx_path
                and os.path.exists(
                    sfx_path
                )
            ):

                current_time += scene_duration
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

                remaining = (
                    total_duration
                    - start
                )

                effect = (
                    effect
                    .set_start(start)
                    .set_duration(
                        min(
                            effect.duration,
                            remaining,
                        )
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

            current_time += scene_duration

    if not tracks:

        return None

    return CompositeAudioClip(
        tracks
    ).set_duration(
        total_duration
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
        "size": (
            width,
            height,
        ),
        "fps": fps,
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

    if len(
        scenes
    ) != EXPECTED_SCENES:

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

        if not isinstance(
            visuals,
            list,
        ):

            raise RuntimeError(
                f"Scene "
                f"{index + 1} visuals "
                "must be a list."
            )

        if len(
            visuals
        ) != 2:

            raise RuntimeError(
                f"Scene "
                f"{index + 1} "
                "must contain exactly "
                "2 storyboard visuals."
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

        if subtitle != narration:

            print(
                f"⚠️ Scene "
                f"{index + 1} "
                "subtitle_text did not match narration. "
                "Using narration."
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
        "ASSEMBLY v8.2"
    )

    print("=" * 80)

    validate_storyboard(
        script
    )

    validate_image_contract(
        image_paths
    )

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

    # --------------------------------------------------------------
    # Dynamic story duration.
    #
    # The storyboard is normally 45 seconds, but a complete story may
    # naturally need more time. Allow it to expand up to 60 seconds.
    # Scale all seven scenes proportionally so the 14 visuals cover
    # the complete narration instead of ending at 45 seconds.
    # --------------------------------------------------------------
    requested_duration = min(
        MAX_VIDEO_DURATION - END_HOLD_SECONDS,
        narration_duration,
    )

    if requested_duration > TARGET_DURATION:

        scale = (
            requested_duration
            / TARGET_DURATION
        )

        scaled_durations = [
            duration * scale
            for duration in SCENE_DURATIONS
        ]

        SCENE_DURATIONS[:] = scaled_durations

        scenes = script.get(
            "scene_plan",
            [],
        )

        for scene, duration in zip(
            scenes,
            scaled_durations,
        ):
            scene["duration"] = duration

        print(
            f"⏱️ Dynamic storyboard duration: "
            f"{requested_duration:.2f}s"
        )

    print(
        f"Narration: "
        f"{narration_duration:.2f}s"
    )

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

    final_duration = min(
        MAX_VIDEO_DURATION,
        narration_duration + END_HOLD_SECONDS,
    )

    print(
        f"Final duration: "
        f"{final_duration:.2f}s"
    )

    trimmed_visuals = []

    for clip in visual_clips:

        start = (
            clip.start
            or 0
        )

        end = (
            start
            + (
                clip.duration
                or 0
            )
        )

        if start >= final_duration:
            continue

        clip_end = min(
            end,
            final_duration,
        )

        clip = clip.set_duration(
            max(
                0.01,
                clip_end - start,
            )
        )

        trimmed_visuals.append(
            clip
        )

    # ----------------------------------------------------------------------
    # NEW CAPTION ENGINE
    # ----------------------------------------------------------------------

    caption_clips = build_captions(
        narration_path,
        script,
        frame_size,
    )

    trimmed_captions = []

    for clip in caption_clips:

        start = (
            clip.start
            or 0
        )

        end = (
            start
            + (
                clip.duration
                or 0
            )
        )

        if start >= final_duration:
            continue

        clip_end = min(
            end,
            final_duration,
        )

        trimmed_captions.append(
            clip.set_duration(
                max(
                    0.01,
                    clip_end - start,
                )
            )
        )

    all_video_clips = (
        trimmed_visuals
        + trimmed_captions
    )

    final = CompositeVideoClip(
        all_video_clips,
        size=frame_size,
    )

    final = final.set_duration(
        final_duration
    )

    audio = build_audio(
        narration,
        music_path,
        sfx_paths,
        script,
        final_duration,
        config,
    )

    if audio is not None:

        final = final.set_audio(
            audio
        )

    output_dir = os.path.dirname(
        out_path
    )

    if output_dir:

        os.makedirs(
            output_dir,
            exist_ok=True
        )

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
        "ONE WORD AT A TIME"
    )

    print(
        "Normal words: "
        "WHITE"
    )

    print(
        "Main words: "
        "YELLOW"
    )

    print(
        "Caption background: "
        "NONE"
    )

    print(
        "Caption outline: "
        "BLACK"
    )

    print(
        "Visual continuity: "
        "enabled"
    )

    print(
        "Portrait 9:16: "
        "enabled"
    )

    print(
        f"Duration: "
        f"{final_duration:.2f}s"
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

    try:
        narration.close()
    except Exception:
        pass

    try:
        if audio is not None:
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