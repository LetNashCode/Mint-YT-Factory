"""Mint-YT-Factory runtime quality layer.

Production-wide caption/video encoding patches plus compatibility overrides for
stock-media Gemini models live here so model migrations cannot silently break
the pipeline.
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
    # IMPORTANT: keep assemble.py as the single source of truth for captions.
    #
    # A previous runtime override replaced build_captions() with an alternate
    # renderer that randomly varied word size, alternated colours by index and
    # injected emoji overlays. That bypassed the canonical scene-aware
    # highlighting, shadow styling and timeline logic in assemble.py and made
    # captions visually inconsistent from one Short to the next.
    #
    # Do not monkey-patch build_captions here. The canonical renderer already
    # owns:
    #   - Whisper/script word timing
    #   - min/max caption durations
    #   - scene-aware semantic highlights
    #   - font, outline and shadow styling
    #   - one-word kinetic caption mode
    print("📝 Caption runtime: canonical assemble.py renderer ENABLED")

    # Video defaults remain production-quality settings; caption behaviour is
    # intentionally not overridden at runtime.
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


def _patch_stock_search(module):
    # Single-model policy: every Gemini call in Mint-YT-Factory must use
    # gemini-flash-lite-latest. Never configure or invoke a model fallback.
    module.GEMINI_MODEL = "gemini-flash-lite-latest"
    module.GEMINI_FALLBACK_MODEL = None
    print("🛡️ Stock-search Gemini: gemini-flash-lite-latest ONLY — no fallback model")


def _patch_stock_media_resilient(module):
    import stock_search

    def generate_media(script, output_dir, config, gim=None):
        print("🛡️ Stock media adapter: Gemini search direction + visual verification ENABLED")
        return stock_search.generate_media(script, output_dir, config, gim=gim)

    module.generate_media = generate_media
    module.GEMINI_MODEL = stock_search.GEMINI_MODEL


def _patch_stock_query_expander(module):
    module.GEMINI_MODEL = "gemini-flash-lite-latest"
    module.GEMINI_FALLBACK_MODEL = None


def _patch(module):
    name = getattr(module, "__name__", "")
    if name == "assemble":
        _patch_assemble(module)
        _patch_video_quality(module)
    elif name == "tts":
        module.NARRATION_SPEED = 1.0
    elif name == "stock_search":
        _patch_stock_search(module)
    elif name == "stock_media_resilient":
        _patch_stock_media_resilient(module)
    elif name == "stock_query_expander":
        _patch_stock_query_expander(module)


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
    TARGETS = {"tts", "assemble", "stock_search", "stock_media_resilient", "stock_query_expander"}

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
