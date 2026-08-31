"""
assemble.py
Mint-YT-Factory

Version 8.3

Assembles the 7-scene / 14-visual YouTube Short.
"""

import os
import math
import shutil as _shutil
from PIL import Image, ImageDraw, ImageFont

from whisper_align import transcribe
from moviepy.config import change_settings

_im = _shutil.which("magick") or _shutil.which("convert")
if _im:
    change_settings({"IMAGEMAGICK_BINARY": _im})

from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    TextClip,
    afx,
)

EXPECTED_SCENES = 7
VISUALS_PER_SCENE = 2
EXPECTED_TOTAL_VISUALS = 14
TARGET_DURATION = 45.0
DEFAULT_RESOLUTION = (1080, 1920)
DEFAULT_FPS = 30

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(BASE_DIR, "assets", "Fonts", "Poppins-ExtraBold.ttf")
if not os.path.isfile(FONT):
    raise RuntimeError(f"Caption font not found: {FONT}")
print(f"✅ Caption font found: {FONT}")

# Quirky, high-impact caption system.
# Captions live in the lower-centre safe area and deliberately change scale
# and colour with the story beat instead of showing tiny uniform words.
CAPTION_FONT_SIZE = 92
CAPTION_COLOR = "white"
CAPTION_HIGHLIGHT_COLOR = "#FFD54A"
CAPTION_COLORS = ("#FFFFFF", "#FFD54A", "#49D7FF", "#FF5AAE", "#8DFF63")
CAPTION_STROKE = "#111111"
CAPTION_STROKE_WIDTH = 5
CAPTION_SHADOW_COLOR = "black"
CAPTION_SHADOW_OPACITY = 0.65
CAPTION_SHADOW_OFFSET = 7
CAPTION_VERTICAL_POSITION = 0.67
CAPTION_MIN_DURATION = 0.18
CAPTION_MAX_DURATION = 1.60
CAPTION_MAX_WORDS = 1
CAPTION_MAX_CHARS = 28
CAPTION_SAFE_WIDTH = 0.88
CAPTION_SIZE_BY_SCENE = (1.38, 0.92, 1.00, 1.00, 1.08, 1.08, 1.28)
DEFAULT_MUSIC_VOLUME = 0.25
DEFAULT_SFX_VOLUME = 0.75

MOTION_MULTIPLIERS = {"low": 0.45, "medium": 1.0, "high": 1.45}
ZOOM_STRENGTH = {"subtle": 1.045, "medium": 1.085, "strong": 1.13}
CAMERA_SCALE = {
    "macro": 1.10, "close_up": 1.075, "medium": 1.045, "wide": 1.02,
    "top_down": 1.045, "side": 1.045, "aerial": 1.02, "orbit": 1.055,
}

SCENE_DURATIONS = [3.0, 5.0, 7.0, 7.0, 8.0, 8.0, 7.0]


def _safe_float(value, default=0.0, minimum=None, maximum=None):
    try:
        value = float(value)
    except Exception:
        return default
    if math.isnan(value) or math.isinf(value):
        return default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _safe_int(value, default=0, minimum=None):
    try:
        value = int(value)
    except Exception:
        return default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _safe_lower(value, default=""):
    try:
        return str(value).strip().lower()
    except Exception:
        return default


def get_scene_duration(scene, scene_index):
    expected = SCENE_DURATIONS[scene_index]
    duration = _safe_float(scene.get("duration", expected), expected, minimum=0.05)
    if abs(duration - expected) > 0.01:
        print(f"⚠️ Scene {scene_index + 1} duration changed from {duration}s to {expected}s.")
        duration = expected
    return duration


def get_caption_highlights(scene):
    result = set()
    raw = scene.get("caption_highlights", [])
    if isinstance(raw, list):
        for item in raw:
            word = item.get("word", "") if isinstance(item, dict) else item
            word = str(word).strip().lower()
            if word:
                result.add(word.strip(".,!?;:\"'()[]{}"))
    emphasis_word = str(scene.get("emphasis_word", "")).strip().lower()
    if emphasis_word:
        result.add(emphasis_word.strip(".,!?;:\"'()[]{}"))
    return result


def _normalize_paths(value):
    if value is None:
        return []
    if isinstance(value, str):
        value = value.strip()
        return [value] if value else []
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str):
            item = item.strip()
            if item:
                result.append(item)
        elif isinstance(item, dict):
            path = item.get("path") or item.get("image") or item.get("src")
            if isinstance(path, str):
                path = path.strip()
                if path:
                    result.append(path)
    return result


def get_scene_image_paths(image_paths, scene_index):
    if not isinstance(image_paths, list) or scene_index >= len(image_paths):
        return []
    paths = _normalize_paths(image_paths[scene_index])
    return [path for path in paths if os.path.exists(path)]


# --------------------------------------------------------------------------
# IMAGE CONTRACT
# --------------------------------------------------------------------------
# publish_short supplies 14 image paths. Older callers may supply 7 groups
# of 2. Normalize the new 14-item flat contract into the internal 7x2 form.
# --------------------------------------------------------------------------

def validate_image_contract(image_paths):
    if not isinstance(image_paths, list):
        raise RuntimeError("image_paths must be a list.")

    if len(image_paths) == EXPECTED_TOTAL_VISUALS:
        image_paths[:] = [
            image_paths[
                scene_index * VISUALS_PER_SCENE:
                (scene_index + 1) * VISUALS_PER_SCENE
            ]
            for scene_index in range(EXPECTED_SCENES)
        ]

    if len(image_paths) != EXPECTED_SCENES:
        raise RuntimeError(
            f"Expected {EXPECTED_TOTAL_VISUALS} visuals "
            f"(2 per scene), or {EXPECTED_SCENES} grouped image lists, "
            f"got {len(image_paths)}."
        )

    total = 0
    for scene_index in range(EXPECTED_SCENES):
        paths = get_scene_image_paths(image_paths, scene_index)
        count = len(paths)
        print(f"Scene {scene_index + 1}: {count}/{VISUALS_PER_SCENE} images")
        if count != VISUALS_PER_SCENE:
            raise RuntimeError(
                f"Scene {scene_index + 1} requires {VISUALS_PER_SCENE} images, found {count}."
            )
        total += count

    if total != EXPECTED_TOTAL_VISUALS:
        raise RuntimeError(f"Expected {EXPECTED_TOTAL_VISUALS} total images, found {total}.")


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}

def _is_video_path(path):
    return os.path.splitext(str(path))[1].lower() in VIDEO_EXTENSIONS

def make_visual_clip(media_path, frame_size, duration):
    """Load either a still image or stock video without changing caller contracts."""
    width, height = frame_size
    if _is_video_path(media_path):
        clip = VideoFileClip(media_path, audio=False)
        if not clip.duration or clip.duration <= 0:
            clip.close()
            raise RuntimeError(f"Visual video has invalid duration: {media_path}")
        if clip.duration < duration:
            clip = clip.fx(afx.loop, duration=duration)
        else:
            clip = clip.subclip(0, min(duration, clip.duration))
        media_kind = "VIDEO"
    else:
        clip = ImageClip(media_path).set_duration(duration)
        media_kind = "IMAGE"
    if not clip.w or not clip.h:
        clip.close()
        raise RuntimeError(f"Visual media has invalid dimensions: {media_path}")
    scale = max(width / clip.w, height / clip.h)
    clip = clip.resize(scale)
    crop_x = max(0, int((clip.w - width) / 2))
    crop_y = max(0, int((clip.h - height) / 2))
    clip = clip.crop(x1=crop_x, y1=crop_y, x2=crop_x + width, y2=crop_y + height)
    print(f"   🎞️ {media_kind}: {os.path.basename(media_path)}")
    return clip.set_duration(duration)


def get_visual_animation(visual):
    animation = _safe_lower(visual.get("animation", "hold"), "hold")
    allowed = {"zoom_in", "zoom_out", "pan_left", "pan_right", "rotate", "parallax", "highlight", "hold"}
    return animation if animation in allowed else "hold"


def get_visual_zoom(visual):
    explicit = visual.get("zoom_factor")
    if explicit is not None:
        return _safe_float(explicit, 1.06, minimum=1.0, maximum=1.15)
    strength = _safe_lower(visual.get("zoom_strength", "subtle"), "subtle")
    return ZOOM_STRENGTH.get(strength, ZOOM_STRENGTH["subtle"])


def get_visual_motion(visual):
    intensity = _safe_lower(visual.get("motion_intensity", "medium"), "medium")
    return MOTION_MULTIPLIERS.get(intensity, MOTION_MULTIPLIERS["medium"])


def get_camera_scale(scene, visual):
    camera = _safe_lower(visual.get("camera", scene.get("camera", "medium")), "medium")
    return CAMERA_SCALE.get(camera, CAMERA_SCALE["medium"])


def build_animated_image(image_path, duration, frame_size, scene, visual):
    clip = make_visual_clip(image_path, frame_size, duration).set_duration(duration)
    animation = get_visual_animation(visual)
    zoom = get_visual_zoom(visual)
    motion = get_visual_motion(visual)
    camera_scale = get_camera_scale(scene, visual)
    safe_duration = max(duration, 0.1)

    if animation == "zoom_in":
        start_scale = camera_scale
        end_scale = camera_scale * zoom
        def scale_function(t):
            progress = min(max(t / safe_duration, 0.0), 1.0)
            return start_scale + (end_scale - start_scale) * progress
        clip = clip.resize(scale_function).set_position("center")
    elif animation == "zoom_out":
        start_scale = camera_scale * zoom
        end_scale = camera_scale
        def scale_function(t):
            progress = min(max(t / safe_duration, 0.0), 1.0)
            return start_scale - (start_scale - end_scale) * progress
        clip = clip.resize(scale_function).set_position("center")
    elif animation == "pan_left":
        clip = clip.resize(camera_scale)
        travel = 70 * motion
        def position_function(t):
            progress = min(max(t / safe_duration, 0.0), 1.0)
            return (-travel * progress, "center")
        clip = clip.set_position(position_function)
    elif animation == "pan_right":
        clip = clip.resize(camera_scale)
        travel = 70 * motion
        def position_function(t):
            progress = min(max(t / safe_duration, 0.0), 1.0)
            return (travel * progress, "center")
        clip = clip.set_position(position_function)
    elif animation == "rotate":
        clip = clip.resize(camera_scale)
        def angle_function(t):
            progress = min(max(t / safe_duration, 0.0), 1.0)
            return 1.0 * motion * progress
        clip = clip.rotate(angle_function).set_position("center")
    elif animation == "parallax":
        base_scale = camera_scale * 1.02
        def scale_function(t):
            progress = min(max(t / safe_duration, 0.0), 1.0)
            return base_scale + 0.025 * motion * progress
        clip = clip.resize(scale_function).set_position("center")
    else:
        clip = clip.resize(camera_scale).set_position("center")
    return clip


def build_visual_timeline(script, image_paths, frame_size):
    scenes = script.get("scene_plan", [])
    if len(scenes) != EXPECTED_SCENES:
        raise RuntimeError(f"Expected {EXPECTED_SCENES} scenes.")

    clips = []
    current_time = 0.0
    for scene_index, scene in enumerate(scenes):
        duration = get_scene_duration(scene, scene_index)
        paths = get_scene_image_paths(image_paths, scene_index)
        if len(paths) != VISUALS_PER_SCENE:
            raise RuntimeError(f"Scene {scene_index + 1} does not have exactly {VISUALS_PER_SCENE} images.")

        print(f"🎬 Scene {scene_index + 1}: {current_time:.2f}s → {current_time + duration:.2f}s")
        shot_duration = duration / VISUALS_PER_SCENE
        storyboard_visuals = scene.get("visuals", [])

        for visual_index in range(VISUALS_PER_SCENE):
            visual_data = {}
            if (
                isinstance(storyboard_visuals, list)
                and visual_index < len(storyboard_visuals)
                and isinstance(storyboard_visuals[visual_index], dict)
            ):
                visual_data = storyboard_visuals[visual_index]

            clip = build_animated_image(
                paths[visual_index], shot_duration, frame_size, scene, visual_data
            ).set_start(current_time + visual_index * shot_duration)
            clips.append(clip)
        current_time += duration
    return clips


def caption_position(frame_size):
    width, height = frame_size
    return ("center", int(height * CAPTION_VERTICAL_POSITION))


def _make_word_clip(word, color):
    return TextClip(
        word, font=FONT, fontsize=CAPTION_FONT_SIZE, color=color,
        stroke_color=CAPTION_STROKE, stroke_width=CAPTION_STROKE_WIDTH,
        method="label",
    )


def _make_word_shadow(word):
    return TextClip(
        word, font=FONT, fontsize=CAPTION_FONT_SIZE, color=CAPTION_SHADOW_COLOR,
        stroke_color=CAPTION_SHADOW_COLOR, stroke_width=CAPTION_STROKE_WIDTH,
        method="label",
    )


def _normalize_caption_word(word):
    return str(word).strip().lower().strip(".,!?;:\"'()[]{}")


def _normalize_whisper_words(words):
    normalized = []
    if not isinstance(words, list):
        return normalized
    for item in words:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        if not word:
            continue
        start = _safe_float(item.get("start", 0), 0, minimum=0)
        end = _safe_float(item.get("end", start + 0.1), start + 0.1, minimum=start)
        if end <= start:
            end = start + 0.1
        normalized.append({"word": word, "start": start, "end": end})
    normalized.sort(key=lambda item: item["start"])
    return normalized


def _build_caption_phrases(words):
    """One-word-at-a-time captions using Whisper timing."""
    phrases = []
    for item in words:
        start = item["start"]
        end = item["end"]
        duration = max(CAPTION_MIN_DURATION, min(CAPTION_MAX_DURATION, end - start))
        phrases.append({"text": item["word"], "words": [item["word"]], "start": start, "duration": duration})
    return phrases

def _caption_style(scene_index, scene, phrase, phrase_index):
    """Return playful size and colour for the current story beat."""
    multiplier = CAPTION_SIZE_BY_SCENE[min(max(scene_index, 0), len(CAPTION_SIZE_BY_SCENE) - 1)]
    highlights = get_caption_highlights(scene)
    normalized = [_normalize_caption_word(word) for word in phrase["words"]]
    has_highlight = any(word in highlights for word in normalized)
    dramatic = "!" in phrase["text"] or phrase_index == 0 or scene_index in (0, 6)

    if has_highlight:
        color = CAPTION_HIGHLIGHT_COLOR
    else:
        color = CAPTION_COLORS[(scene_index + phrase_index) % len(CAPTION_COLORS)]

    if dramatic:
        multiplier *= 1.08

    return int(CAPTION_FONT_SIZE * multiplier), color


def _caption_font(fontsize):
    try:
        return ImageFont.truetype(FONT, max(1, int(fontsize)))
    except Exception as exc:
        raise RuntimeError(f"Could not load caption font: {FONT}") from exc

def _caption_bitmap(text, fontsize, color, frame_size, shadow=False):
    """Render captions with Pillow; avoids ImageMagick security-policy failures."""
    max_width = max(1, int(frame_size[0] * CAPTION_SAFE_WIDTH))
    font = _caption_font(fontsize)
    probe = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=CAPTION_STROKE_WIDTH)
    text_w = max(1, bbox[2] - bbox[0])
    text_h = max(1, bbox[3] - bbox[1])
    if text_w > max_width:
        font = _caption_font(max(1, int(fontsize * max_width / float(text_w))))
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=CAPTION_STROKE_WIDTH)
        text_w = max(1, bbox[2] - bbox[0])
        text_h = max(1, bbox[3] - bbox[1])
    pad = CAPTION_STROKE_WIDTH + 8
    image = Image.new("RGBA", (text_w + pad * 2, text_h + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    fill = CAPTION_SHADOW_COLOR if shadow else color
    stroke_fill = CAPTION_SHADOW_COLOR if shadow else CAPTION_STROKE
    draw.text((pad - bbox[0], pad - bbox[1]), text, font=font, fill=fill,
              stroke_width=CAPTION_STROKE_WIDTH, stroke_fill=stroke_fill)
    return image

def _make_caption_clip(text, fontsize, color, frame_size):
    return ImageClip(_caption_bitmap(text, fontsize, color, frame_size, shadow=False))

def _make_caption_shadow(text, fontsize, frame_size):
    return ImageClip(_caption_bitmap(text, fontsize, CAPTION_SHADOW_COLOR, frame_size, shadow=True))

def _get_scene_index_for_time(scene_ranges, timestamp):
    for index, item in enumerate(scene_ranges):
        if item["start"] <= timestamp < item["end"]:
            return index
    return len(scene_ranges) - 1


def build_captions(narration_path, script, frame_size):
    print("=" * 80)
    print("🌈 BUILDING QUIRKY COLOURFUL ONE-WORD CAPTIONS")
    print("=" * 80)
    words = _normalize_whisper_words(transcribe(narration_path))
    if not words:
        raise RuntimeError("Whisper returned no usable word timestamps.")
    print(f"Detected words: {len(words)}")

    scenes = script.get("scene_plan", [])
    if len(scenes) != EXPECTED_SCENES:
        raise RuntimeError(f"Caption generation requires {EXPECTED_SCENES} scenes.")

    scene_ranges = []
    current = 0.0
    for scene_index, scene in enumerate(scenes):
        duration = get_scene_duration(scene, scene_index)
        scene_ranges.append({"start": current, "end": current + duration, "scene": scene})
        current += duration

    position = caption_position(frame_size)
    clips = []
    phrases = _build_caption_phrases(words)

    for phrase_index, phrase in enumerate(phrases):
        scene_index = _get_scene_index_for_time(scene_ranges, phrase["start"])
        scene = scene_ranges[scene_index]["scene"]
        fontsize, color = _caption_style(scene_index, scene, phrase, phrase_index)

        text_clip = _make_caption_clip(
            phrase["text"], fontsize, color, frame_size
        ).set_start(phrase["start"]).set_duration(phrase["duration"]).set_position(position)

        shadow_clip = _make_caption_shadow(
            phrase["text"], fontsize, frame_size
        ).set_start(phrase["start"]).set_duration(phrase["duration"]).set_position(
            ("center", position[1] + CAPTION_SHADOW_OFFSET)
        ).set_opacity(CAPTION_SHADOW_OPACITY)

        clips.extend([shadow_clip, text_clip])

    print(f"Caption layers: {len(clips)}")
    print(f"Caption beats: {len(phrases)}")
    print("Caption mode: ONE WORD AT A TIME")
    print("Caption style: BIG HOOKS + MEDIUM EXPLAINS + BIG PAYOFFS")
    print("Caption colours: WHITE / YELLOW / CYAN / PINK / GREEN")
    print("Caption placement: LOWER CENTER SAFE AREA")
    return clips


def get_audio_config(config):
    video_config = config.get("video", {})
    if not isinstance(video_config, dict):
        video_config = {}
    return {
        "music_volume": _safe_float(video_config.get("music_volume", DEFAULT_MUSIC_VOLUME), DEFAULT_MUSIC_VOLUME, minimum=0, maximum=1),
        "sfx_volume": _safe_float(video_config.get("sfx_volume", DEFAULT_SFX_VOLUME), DEFAULT_SFX_VOLUME, minimum=0, maximum=2),
    }


def build_audio(narration, music_path, sfx_paths, script, total_duration, config):
    audio_config = get_audio_config(config)
    tracks = [narration.set_start(0).set_duration(min(narration.duration, total_duration))]

    if music_path and os.path.exists(music_path):
        print(f"🎵 Music: {music_path}")
        music = AudioFileClip(music_path).fx(afx.audio_loop, duration=total_duration)
        tracks.append(music.volumex(audio_config["music_volume"]).set_duration(total_duration))

    scenes = script.get("scene_plan", [])
    if isinstance(sfx_paths, list):
        current_time = 0.0
        for scene_index, scene in enumerate(scenes):
            if scene_index >= len(sfx_paths):
                break
            sfx_path = sfx_paths[scene_index]
            scene_duration = get_scene_duration(scene, scene_index)
            if not (sfx_path and os.path.exists(sfx_path)):
                current_time += scene_duration
                continue
            cue = scene.get("sfx_cue", {})
            if not isinstance(cue, dict):
                cue = {}
            offset = _safe_float(cue.get("at_ms", 0), 0, minimum=0) / 1000.0
            start = current_time + offset
            if start < total_duration:
                effect = AudioFileClip(sfx_path)
                effect = (
                    effect.set_start(start)
                    .set_duration(min(effect.duration, total_duration - start))
                    .volumex(audio_config["sfx_volume"])
                )
                tracks.append(effect)
            current_time += scene_duration

    return CompositeAudioClip(tracks).set_duration(total_duration) if tracks else None


def get_video_config(config):
    video = config.get("video", {})
    if not isinstance(video, dict):
        video = {}
    resolution = video.get("resolution", DEFAULT_RESOLUTION)
    try:
        width, height = int(resolution[0]), int(resolution[1])
    except Exception:
        width, height = DEFAULT_RESOLUTION
    if width > height:
        width, height = height, width
    return {"size": (width, height), "fps": _safe_int(video.get("fps", DEFAULT_FPS), DEFAULT_FPS, minimum=1)}


def validate_storyboard(script):
    scenes = script.get("scene_plan", [])
    if len(scenes) != EXPECTED_SCENES:
        raise RuntimeError(f"Storyboard must contain {EXPECTED_SCENES} scenes.")

    total = 0.0
    for index, scene in enumerate(scenes):
        duration = get_scene_duration(scene, index)
        if abs(duration - SCENE_DURATIONS[index]) > 0.01:
            raise RuntimeError(f"Scene {index + 1} duration mismatch.")
        visuals = scene.get("visuals", [])
        if not isinstance(visuals, list) or len(visuals) != VISUALS_PER_SCENE:
            raise RuntimeError(f"Scene {index + 1} must contain exactly {VISUALS_PER_SCENE} storyboard visuals.")
        narration = str(scene.get("narration", "")).strip()
        if not narration:
            raise RuntimeError(f"Scene {index + 1} has no narration.")
        subtitle = str(scene.get("subtitle_text", "")).strip()
        if subtitle != narration:
            print(f"⚠️ Scene {index + 1} subtitle_text did not match narration. Using narration.")
            scene["subtitle_text"] = narration
        total += duration

    if abs(total - TARGET_DURATION) > 0.01:
        raise RuntimeError(f"Storyboard duration is {total}s, expected {TARGET_DURATION}s.")


def assemble_video(script, audio_paths, image_paths, music_path, sfx_paths, config, out_path):
    print("=" * 80)
    print("🎬 MINT-YT-FACTORY ASSEMBLY v8.3")
    print("=" * 80)

    validate_storyboard(script)
    validate_image_contract(image_paths)

    video_config = get_video_config(config)
    frame_size = video_config["size"]
    fps = video_config["fps"]
    print(f"Resolution: {frame_size[0]}x{frame_size[1]}")
    print(f"FPS: {fps}")

    if not audio_paths:
        raise RuntimeError("No narration audio supplied.")
    narration_path = audio_paths[0]
    if not os.path.exists(narration_path):
        raise RuntimeError(f"Narration file not found: {narration_path}")

    narration = AudioFileClip(narration_path)
    narration_duration = narration.duration
    print(f"Narration: {narration_duration:.2f}s")

    print("=" * 80)
    print("🖼️ BUILDING 14-SHOT VISUAL TIMELINE")
    print("=" * 80)
    visual_clips = build_visual_timeline(script, image_paths, frame_size)
    print(f"Visual clips created: {len(visual_clips)}")
    if len(visual_clips) != EXPECTED_TOTAL_VISUALS:
        raise RuntimeError(f"Expected {EXPECTED_TOTAL_VISUALS} visual clips, got {len(visual_clips)}.")

    final_duration = min(TARGET_DURATION, narration_duration)
    print(f"Final duration: {final_duration:.2f}s")

    trimmed_visuals = []
    for clip in visual_clips:
        start = clip.start or 0
        end = start + (clip.duration or 0)
        if start >= final_duration:
            continue
        trimmed_visuals.append(clip.set_duration(max(0.01, min(end, final_duration) - start)))

    caption_clips = build_captions(narration_path, script, frame_size)
    trimmed_captions = []
    for clip in caption_clips:
        start = clip.start or 0
        end = start + (clip.duration or 0)
        if start >= final_duration:
            continue
        trimmed_captions.append(clip.set_duration(max(0.01, min(end, final_duration) - start)))

    final = CompositeVideoClip(trimmed_visuals + trimmed_captions, size=frame_size).set_duration(final_duration)
    audio = build_audio(narration, music_path, sfx_paths, script, final_duration, config)
    if audio is not None:
        final = final.set_audio(audio)

    output_dir = os.path.dirname(out_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    print("=" * 80)
    print("🎥 RENDERING FINAL SHORT")
    print("=" * 80)
    print(f"Output: {out_path}")
    print("Story structure: 7 scenes / 14 shots")
    print("Captions: QUIRKY ONE-WORD-AT-A-TIME")
    print("Caption sizes: DYNAMIC SMALL / MEDIUM / BIG EMPHASIS")
    print("Caption colours: WHITE / YELLOW / CYAN / PINK / GREEN")
    print("Caption placement: LOWER CENTER")
    print("Caption outline: THICK BLACK + SHADOW")
    print("Visual continuity: enabled")
    print("Portrait 9:16: enabled")
    print(f"Duration: {final_duration:.2f}s")

    final.write_videofile(
        out_path,
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
        temp_audiofile=out_path + ".temp_audio.m4a",
        remove_temp=True,
    )

    print("=" * 80)
    print("✅ FINAL SHORT COMPLETE")
    print("=" * 80)
    print(out_path)

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
