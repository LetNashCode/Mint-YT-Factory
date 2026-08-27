"""Mint-YT-Factory runtime quality layer.

Only production-wide caption and video-encoding patches live here.
Media selection is owned by pexels_media.py and is installed explicitly by
production_entry.py. No image generation, candidate-image inspection, OCR
visual gate, or alternate media provider is patched here.
"""
from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys


def _clean_words(words):
    result = []
    if not isinstance(words, list):
        return result
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
        result.append({"word": word, "start": start, "end": end})
    return sorted(result, key=lambda x: x["start"])


def _word_size(word, index, frame_size):
    width, _ = frame_size
    base = max(62, min(172, int(round(150.0 * width / 2160.0))))
    seed = sum(ord(ch) for ch in str(word)) + index * 17
    return int(base * (0.86, 1.0, 1.16)[seed % 3])


def _emoji_for_word(word):
    mapping = {
        "fire": "🔥", "hot": "🔥", "burn": "🔥", "burning": "🔥",
        "cold": "🥶", "ice": "🧊", "freeze": "🥶", "frozen": "🥶",
        "water": "💧", "rain": "🌧️", "cloud": "☁️", "sun": "☀️",
        "moon": "🌙", "star": "⭐", "stars": "⭐", "earth": "🌍",
        "space": "🚀", "heart": "❤️", "love": "❤️", "happy": "😊",
        "smile": "😊", "sad": "😢", "cry": "😭", "laugh": "😂",
        "funny": "😂", "shock": "😱", "shocked": "😱", "surprise": "😲",
        "surprised": "😲", "idea": "💡", "think": "🤔", "thinking": "🤔",
        "brain": "🧠", "danger": "⚠️", "warning": "⚠️", "money": "💰",
        "cash": "💵", "food": "🍔", "eat": "🍴", "coffee": "☕",
        "drink": "🥤", "dog": "🐶", "cat": "🐱", "bird": "🐦",
        "fish": "🐟", "tree": "🌳", "leaf": "🍃", "flower": "🌸",
        "plant": "🌱", "light": "💡", "dark": "🌑", "night": "🌙",
        "day": "☀️", "fast": "⚡", "speed": "⚡", "electric": "⚡",
        "power": "⚡", "magic": "✨", "secret": "🤫", "hidden": "🕵️",
        "look": "👀", "watch": "👀", "see": "👀", "eyes": "👀",
        "hand": "✋", "stop": "🛑", "go": "🚀", "up": "⬆️", "down": "⬇️",
        "science": "🔬", "experiment": "🧪", "question": "❓", "why": "❓",
        "answer": "💡", "true": "✅", "wrong": "❌", "yes": "✅", "no": "❌",
        "win": "🏆", "winner": "🏆",
    }
    token = str(word or "").strip().lower().strip(".,!?;:'\"()[]{}")
    if token in mapping:
        return mapping[token]
    for suffix in ("ing", "ed", "s"):
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            root = token[:-len(suffix)]
            if root in mapping:
                return mapping[root]
    return None


def _patch_assemble(module):
    old_transcribe = getattr(module, "transcribe", None)
    if old_transcribe is not None:
        module._mint_raw_transcribe = old_transcribe

    def build(narration_path, script, frame_size):
        raw = getattr(module, "_mint_raw_transcribe", None)
        if raw is None:
            raise RuntimeError("Raw Whisper transcriber unavailable.")
        words = _clean_words(raw(narration_path))
        if not words:
            raise RuntimeError("Whisper returned no usable word timestamps.")

        from moviepy.editor import TextClip
        width, height = frame_size
        safe_left = width * 0.06
        safe_right = width * 0.80
        safe_center = (safe_left + safe_right) / 2.0
        center_y = height * 0.60
        max_word_width = safe_right - safe_left
        clips = []

        for index, item in enumerate(words):
            word = item["word"]
            start = item["start"]
            duration = min(max(0.05, item["end"] - start), 1.20)
            size = _word_size(word, index, frame_size)
            color = "#FFD54A" if index % 4 != 2 else "#FFFFFF"
            old_size = getattr(module, "CAPTION_FONT_SIZE", 78)
            module.CAPTION_FONT_SIZE = size
            try:
                clip = module._make_word_clip(word, color)
            finally:
                module.CAPTION_FONT_SIZE = old_size

            if clip.w > max_word_width:
                size = max(50, int(size * max_word_width / float(clip.w) * 0.94))
                module.CAPTION_FONT_SIZE = size
                try:
                    clip = module._make_word_clip(word, color)
                finally:
                    module.CAPTION_FONT_SIZE = old_size

            x = max(safe_left, min(safe_center - clip.w / 2.0, safe_right - clip.w))
            y = center_y - clip.h / 2.0
            clips.append(clip.set_start(start).set_duration(duration).set_position((x, y)))

            emoji = _emoji_for_word(word)
            if emoji:
                try:
                    esize = max(36, int(size * 0.58))
                    eclip = TextClip(
                        emoji, fontsize=esize, font="DejaVu-Sans", color="white",
                        stroke_color="black", stroke_width=max(1, int(esize * 0.035)),
                        method="label",
                    )
                    ex = safe_center - eclip.w / 2.0
                    ey = y - eclip.h - max(10, int(size * 0.16))
                    clips.append(eclip.set_start(start).set_duration(duration).set_position((ex, ey)))
                except Exception:
                    pass

        print(f"🎬 Captions: {len(words)} timed words / safe lane 6%-80% / center 60%")
        return clips

    module.build_captions = build
    module.CAPTION_VERTICAL_POSITION = 0.60
    module.DEFAULT_RESOLUTION = (2160, 3840)
    module.DEFAULT_FPS = 60


def _patch_video_quality(module):
    try:
        cls = getattr(module, "CompositeVideoClip", None)
        original = getattr(cls, "write_videofile", None) if cls else None
        if not original or getattr(original, "_mint_quality", False):
            return

        def write(self, filename, *args, **kwargs):
            kwargs.setdefault("bitrate", "100M")
            kwargs.setdefault("audio_bitrate", "384k")
            kwargs.setdefault("codec", "libx264")
            kwargs.setdefault("audio_codec", "aac")
            kwargs.setdefault("preset", "medium")
            kwargs.setdefault("threads", 4)
            params = kwargs.setdefault("ffmpeg_params", [])
            for flag, value in (
                ("-pix_fmt", "yuv420p"),
                ("-movflags", "+faststart"),
                ("-profile:v", "high"),
                ("-level:v", "5.2"),
                ("-color_primaries", "bt709"),
                ("-color_trc", "bt709"),
                ("-colorspace", "bt709"),
            ):
                if flag not in params:
                    params.extend([flag, value])
            print("🎥 Production encoding: H.264 / 100 Mbps / 384 kbps AAC")
            return original(self, filename, *args, **kwargs)

        write._mint_quality = True
        cls.write_videofile = write
    except Exception as exc:
        print(f"⚠️ Video quality patch skipped: {exc}")


def _patch(module):
    name = getattr(module, "__name__", "")
    if name == "assemble":
        _patch_assemble(module)
        _patch_video_quality(module)
    elif name == "tts":
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
    TARGETS = {"tts", "assemble"}

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in self.TARGETS:
            return None
        try:
            sys.meta_path.remove(self)
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        finally:
            sys.meta_path.insert(0, self)
        if spec is None or spec.loader is None:
            return None
        spec.loader = _Loader(spec.loader)
        return spec


if not any(isinstance(x, _Finder) for x in sys.meta_path):
    sys.meta_path.insert(0, _Finder())
