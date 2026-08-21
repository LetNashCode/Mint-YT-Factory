"""Mint-YT-Factory runtime quality layer.

Entertainment-first development mode.
Research and claim verification remain disabled.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys

VIRAL_SCRIPT_RULES = r'''

============================================================
ENTERTAINMENT-FIRST STORY ENGINE
============================================================

Write like a clever friend showing the viewer something weird.
- Hook immediately with a concrete curiosity or surprising statement.
- Use conversational, slightly quirky spoken English.
- Keep sentences punchy and varied.
- Never sound like a textbook, lecture, encyclopedia or newsreader.
- Avoid generic intros and filler.
- Do not force jokes. Entertainment comes from the situation and payoff.
- Build one clear curiosity from beginning to payoff.
- Finish the current story before the continuation hook.

ACTION-FIRST STORYBOARD:
- Every scene must advance the story.
- Every visual prompt must describe a concrete visible moment.
- Prefer action, interaction, reaction, transformation, comparison or consequence.
- If a person is relevant, show the person physically doing the narrated action.
- If an object is relevant, show it being handled, used, changed or compared.
- Shot 1 establishes the action. Shot 2 reveals a new action, consequence or state.
- Never create two pretty variations of the same still.

CHARACTER CONTINUITY:
- If the same person appears in multiple shots, keep the same approximate age,
  hair, clothing and physical appearance.
- Do not introduce a different person merely to make another image attractive.

VISUAL STORY QUALITY:
- The viewer should understand the basic visual idea with sound OFF.
- Use recognizable real-world environments and physical objects.
- Prefer hands interacting with objects, close physical actions, reactions,
  before/after states and visible cause-and-effect.
- Avoid abstract explanations, diagrams and decorative imagery.
'''

VIRAL_IMAGE_RULES = r'''

============================================================
ACTION-FIRST IMAGE GENERATION — HARD OVERRIDE
============================================================

The generated image is a STORY FRAME, not a decorative illustration.
Show the exact physical action or visible consequence described by the main prompt.
Show WHO/WHAT is present, WHAT they are doing, WHERE it happens, and the visible result.
Prefer recognizable real-world environments and believable physical interaction.
Maintain character appearance when the same person appears again.
Do not add decorative particles, arrows, energy fields, equations, charts, diagrams,
glowing effects or scientific equipment unless genuinely required by the narration.
Do not render captions, subtitles, labels, logos, watermarks or readable text.
Prefer medium action shots, over-the-shoulder views, useful close-ups and consequence shots.
'''


def _patch_video_quality(module):
    try:
        video_class = getattr(module, "CompositeVideoClip", None)
        if video_class is None:
            return
        original = getattr(video_class, "write_videofile", None)
        if original is None or getattr(original, "_mint_quality", False):
            return

        def production_write(self, filename, *args, **kwargs):
            kwargs.setdefault("bitrate", "68M")
            kwargs.setdefault("audio_bitrate", "384k")
            kwargs.setdefault("codec", "libx264")
            kwargs.setdefault("audio_codec", "aac")
            kwargs.setdefault("preset", "medium")
            kwargs.setdefault("threads", 4)
            kwargs.setdefault("ffmpeg_params", [
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-profile:v", "high",
                "-level:v", "5.2",
                "-color_primaries", "bt709",
                "-color_trc", "bt709",
                "-colorspace", "bt709",
            ])
            print("🎥 Production encoding: H.264 High / 68 Mbps / 384 kbps AAC")
            print("🎥 Production pixel format: yuv420p / BT.709 / Fast Start")
            return original(self, filename, *args, **kwargs)

        production_write._mint_quality = True
        video_class.write_videofile = production_write
    except Exception as error:
        print(f"⚠️ Production video quality patch skipped: {error}")


def _clean_caption_words(words):
    clean = []
    if not isinstance(words, list):
        return clean
    for item in words:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        if not word:
            continue
        try:
            start = max(0.0, float(item.get("start", 0.0)))
            end = max(start + 0.05, float(item.get("end", start + 0.05)))
        except Exception:
            continue
        clean.append({"word": word, "start": start, "end": end})
    clean.sort(key=lambda x: x["start"])
    return clean


# Only add an emoji when the spoken word has a clear visual match.
_EMOJI_KEYWORDS = {
    "fire":"🔥", "hot":"🔥", "burn":"🔥", "burning":"🔥",
    "cold":"🥶", "ice":"🧊", "freeze":"🥶", "frozen":"🥶",
    "water":"💧", "rain":"🌧️", "cloud":"☁️", "sun":"☀️", "sunlight":"☀️",
    "moon":"🌙", "star":"⭐", "stars":"⭐", "earth":"🌍", "world":"🌍",
    "space":"🚀", "rocket":"🚀", "heart":"❤️", "love":"❤️", "happy":"😊",
    "smile":"😊", "sad":"😢", "cry":"😭", "laugh":"😂", "funny":"😂",
    "shock":"😱", "shocked":"😱", "surprise":"😲", "surprised":"😲",
    "idea":"💡", "think":"🤔", "thinking":"🤔", "brain":"🧠",
    "danger":"⚠️", "warning":"⚠️", "dangerous":"⚠️", "money":"💰",
    "rich":"💰", "cash":"💵", "buy":"🛒", "food":"🍔", "eat":"🍴",
    "coffee":"☕", "drink":"🥤", "dog":"🐶", "cat":"🐱", "bird":"🐦",
    "fish":"🐟", "tree":"🌳", "leaf":"🍃", "flower":"🌸", "plant":"🌱",
    "light":"💡", "dark":"🌑", "night":"🌙", "day":"☀️", "fast":"⚡",
    "speed":"⚡", "electric":"⚡", "power":"⚡", "magic":"✨", "secret":"🤫",
    "hidden":"🕵️", "look":"👀", "watch":"👀", "see":"👀", "eyes":"👀",
    "hand":"✋", "stop":"🛑", "go":"🚀", "up":"⬆️", "down":"⬇️",
    "science":"🔬", "experiment":"🧪", "question":"❓", "why":"❓", "answer":"💡",
    "true":"✅", "wrong":"❌", "yes":"✅", "no":"❌", "win":"🏆", "winner":"🏆",
}


def _emoji_for_word(word):
    token = str(word or "").strip().lower().strip(".,!?;:'\"()[]{}")
    if token in _EMOJI_KEYWORDS:
        return _EMOJI_KEYWORDS[token]
    for suffix in ("ing", "ed", "s"):
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            root = token[:-len(suffix)]
            if root in _EMOJI_KEYWORDS:
                return _EMOJI_KEYWORDS[root]
    return None


def _word_size_for_index(word, index, frame_size):
    width, _ = frame_size
    base = max(62, min(172, int(round(150.0 * width / 2160.0))))
    seed = sum(ord(ch) for ch in str(word)) + index * 17
    return int(base * (0.86, 1.0, 1.16)[seed % 3])


def _caption_color_for_word(word, index):
    # Yellow is the primary active-word color. Small variations keep the
    # sequence lively without turning the captions into a rainbow.
    colors = ("#FFD54A", "#FFD54A", "#FFFFFF", "#FFD54A")
    return colors[(sum(ord(ch) for ch in str(word)) + index) % len(colors)]


def _make_funky_word_clip(module, word, color, font_size):
    old_size = getattr(module, "CAPTION_FONT_SIZE", 78)
    module.CAPTION_FONT_SIZE = font_size
    try:
        return module._make_word_clip(word, color)
    finally:
        module.CAPTION_FONT_SIZE = old_size


def _make_funky_emoji_clip(emoji, font_size):
    try:
        from moviepy.editor import TextClip
        size = max(36, int(font_size * 0.58))
        return TextClip(
            emoji,
            fontsize=size,
            font="DejaVu-Sans",
            color="white",
            stroke_color="black",
            stroke_width=max(1, int(size * 0.035)),
            method="label",
        )
    except Exception:
        return None


def _build_funky_captions(module, narration_path, script, frame_size):
    """One spoken word at a time with safe positioning and optional emoji."""
    raw_transcribe = getattr(module, "_mint_raw_transcribe", None)
    if raw_transcribe is None:
        raise RuntimeError("Raw Whisper transcriber is unavailable.")

    words = _clean_caption_words(raw_transcribe(narration_path))
    if not words:
        raise RuntimeError("Whisper returned no usable word timestamps.")

    width, height = frame_size

    # The marked Shorts-safe area is deliberately below the visual focal
    # point and above the channel/title/share UI. The word itself is centered
    # in that area, not at the center of the whole 9:16 frame.
    center_y = int(height * 0.60)

    # Leave the right-side engagement controls clear. This creates a stable
    # caption lane similar to the user's reference image.
    safe_left = width * 0.06
    safe_right = width * 0.80
    safe_center = (safe_left + safe_right) / 2.0
    max_word_width = safe_right - safe_left

    clips = []

    for index, item in enumerate(words):
        word = item["word"]
        start = item["start"]
        duration = min(
            max(getattr(module, "CAPTION_MIN_DURATION", 0.05), item["end"] - start),
            getattr(module, "CAPTION_MAX_DURATION", 1.20),
        )

        font_size = _word_size_for_index(word, index, frame_size)
        color = _caption_color_for_word(word, index)
        word_clip = _make_funky_word_clip(module, word, color, font_size)

        # Never allow a word to touch the right-side Shorts controls or leave
        # the frame. Long words are scaled down until they fit the safe lane.
        if word_clip.w > max_word_width:
            ratio = max_word_width / float(word_clip.w)
            font_size = max(50, int(font_size * ratio * 0.94))
            word_clip = _make_funky_word_clip(module, word, color, font_size)

        x = safe_center - word_clip.w / 2.0
        x = max(safe_left, min(x, safe_right - word_clip.w))
        word_y = center_y - word_clip.h / 2.0

        # IMPORTANT: no duplicate/shadow text layer.
        # The previous shadow produced a ghost word behind the real caption.
        # The black stroke on the actual word already provides separation.
        clips.append(
            word_clip
            .set_start(start)
            .set_duration(duration)
            .set_position((x, word_y))
        )

        # Matching emoji appears ABOVE the active spoken word.
        emoji = _emoji_for_word(word)
        if emoji:
            emoji_clip = _make_funky_emoji_clip(emoji, font_size)
            if emoji_clip is not None:
                emoji_x = safe_center - emoji_clip.w / 2.0
                emoji_y = word_y - emoji_clip.h - max(10, int(font_size * 0.16))
                clips.append(
                    emoji_clip
                    .set_start(start)
                    .set_duration(duration)
                    .set_position((emoji_x, emoji_y))
                )

    print(f"🎬 Funky captions: {len(words)} words")
    print("🎬 Caption mode: ONE WORD AT A TIME")
    print("🎬 Caption colors: yellow-first / white accent")
    print("🎬 Caption sizing: deterministic small / normal / big")
    print("🎬 Matching emoji: ABOVE active word")
    print("🎬 Caption safe area: 6% → 80% width")
    print("🎬 Caption position: 60% height / centered safe lane")
    print("🎬 Caption shadow: DISABLED — no ghost text")

    return clips


def _patch_assemble(module):
    old_transcribe = getattr(module, "transcribe", None)
    if old_transcribe is not None:
        module._mint_raw_transcribe = old_transcribe

    module.build_captions = lambda narration_path, script, frame_size: _build_funky_captions(
        module, narration_path, script, frame_size
    )
    module.CAPTION_VERTICAL_POSITION = 0.60
    _patch_video_quality(module)


def _patch(module):
    name = getattr(module, "__name__", "")

    if name == "generate_script":
        old_builder = getattr(module, "_build_system_prompt", None) or getattr(module, "build_system_prompt", None)
        if old_builder and not getattr(old_builder, "_mint_entertainment", False):
            def wrapped():
                return old_builder() + VIRAL_SCRIPT_RULES
            wrapped._mint_entertainment = True
            if hasattr(module, "_build_system_prompt"):
                module._build_system_prompt = wrapped
            else:
                module.build_system_prompt = wrapped
        return

    if name == "generate_images":
        old_builder = getattr(module, "build_prompt", None)
        if old_builder and not getattr(old_builder, "_mint_action_visuals", False):
            def wrapped(*args, **kwargs):
                prompt = old_builder(*args, **kwargs)
                if not isinstance(prompt, str):
                    prompt = str(prompt or "")
                replacements = (
                    ("scientific illustration and realistic 3d render", "cinematic photograph / realistic 3D render"),
                    ("scientific illustration", "cinematic photograph"),
                    ("science textbook aesthetic", "entertaining documentary aesthetic"),
                    ("scientific diagram", "literal real-world scene"),
                    ("textbook diagram", "literal real-world scene"),
                )
                for old, new in replacements:
                    prompt = prompt.replace(old, new)
                return prompt + " " + VIRAL_IMAGE_RULES
            wrapped._mint_action_visuals = True
            module.build_prompt = wrapped
        return

    if name == "assemble":
        _patch_assemble(module)
        return

    if name == "tts":
        module.NARRATION_SPEED = 1.0


class _Loader(importlib.abc.Loader):
    def __init__(self, loader):
        self.loader = loader

    def create_module(self, spec):
        creator = getattr(self.loader, "create_module", None)
        return creator(spec) if creator else None

    def exec_module(self, module):
        self.loader.exec_module(module)
        _patch(module)


class _Finder(importlib.abc.MetaPathFinder):
    TARGETS = {"generate_script", "generate_images", "tts", "assemble"}

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in self.TARGETS:
            return None
        try:
            sys.meta_path.remove(self)
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        finally:
            if self not in sys.meta_path:
                sys.meta_path.insert(0, self)
        if spec is not None and spec.loader is not None:
            spec.loader = _Loader(spec.loader)
        return spec


if not any(isinstance(item, _Finder) for item in sys.meta_path):
    sys.meta_path.insert(0, _Finder())
