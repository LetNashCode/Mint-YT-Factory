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
    print("📝 Caption runtime: canonical assemble.py renderer ENABLED")
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
    module.GEMINI_MODEL = "gemini-flash-lite-latest"
    module.GEMINI_FALLBACK_MODEL = None

    RECENT_MEDIA_COOLDOWN = 15

    original_history = getattr(module, "_historical_asset_keys", None)
    if original_history and not getattr(original_history, "_mint_cooldown", False):
        def recent_history_keys():
            try:
                data = module._load_media_history()
                assets = data.get("assets", []) if isinstance(data, dict) else []
                records = [x for x in assets if isinstance(x, dict) and x.get("asset_key")]
                records.sort(key=lambda x: float(x.get("recorded_at", 0) or 0))
                keys = {str(x["asset_key"]) for x in records[-RECENT_MEDIA_COOLDOWN:]}
                print(
                    f"📚 MEDIA COOLDOWN: blocking {len(keys)} most recent assets "
                    f"(window={RECENT_MEDIA_COOLDOWN}); older relevant assets may be reused"
                )
                return keys
            except Exception as exc:
                print(f"⚠️ Media cooldown lookup failed; preserving safety fallback: {exc}")
                return original_history()

        recent_history_keys._mint_cooldown = True
        module._historical_asset_keys = recent_history_keys
        module.MEDIA_REUSE_COOLDOWN = RECENT_MEDIA_COOLDOWN

    original_build_plan = getattr(module, "build_plan", None)
    if original_build_plan and not getattr(original_build_plan, "_mint_topic_lock", False):
        import re

        ignored = {
            "why", "how", "what", "when", "where", "who", "does", "do", "did",
            "is", "are", "can", "will", "would", "could", "should", "the", "a", "an",
            "to", "of", "for", "in", "on", "at", "with", "from", "and", "or", "so",
            "very", "really", "actually", "just", "this", "that", "these", "those",
            "fast", "quickly", "quick", "slow", "slowly", "empty", "being", "changing",
            "state", "thing", "object", "stuff", "look", "looks", "happen", "happens",
        }
        bad_query_words = {
            "empty", "random", "generic", "thing", "stuff", "being", "changing", "state",
            "concept", "mechanism", "mystery", "educational", "experiment",
        }

        def topic_subject(topic):
            words = re.findall(r"[a-z][a-z-]{2,}", str(topic or "").lower())
            subject = []
            for word in words:
                if word in ignored:
                    continue
                if word not in subject:
                    subject.append(word)
                if len(subject) >= 2:
                    break
            return " ".join(subject)

        def normalize_plan(script):
            plan = original_build_plan(script)
            # Riddles use a spoken-atmosphere visual director. The riddle itself is
            # often phrased as a question, so extracting the first two topic words
            # (e.g. "wear no") produces terrible stock queries. Preserve Gemini's
            # per-scene visual direction instead of forcing the generic topic lock.
            if script.get("riddle_number") or script.get("riddle_visual_mode"):
                print("🎭 RIDDLE VISUAL LOCK: preserving per-scene atmosphere queries; topic lock bypassed")
                return plan

            subject = topic_subject(script.get("topic", ""))
            if not subject:
                return plan
            subject_words = set(subject.split())
            generic_suffix_words = {
                "empty", "random", "generic", "being", "changing", "state", "thing", "stuff",
                "mechanism", "concept", "mystery", "educational", "experiment",
            }
            safe_suffixes = ("close up", "inside", "in motion", "entrance", "people using", "detail")

            for shots in plan:
                for shot in shots:
                    ladder = shot.get("search_ladder", [])
                    normalized = []
                    seen = set()
                    for entry in ladder:
                        query = str(entry.get("query", "")).strip().lower()
                        words = re.findall(r"[a-z0-9-]+", query)
                        suffix = [w for w in words if w not in subject_words and w not in generic_suffix_words]
                        query = " ".join([subject, *suffix[:5]])
                        query = " ".join(query.split())
                        if len(query.split()) < 2:
                            query = f"{subject} {safe_suffixes[len(normalized) % len(safe_suffixes)]}"
                        query = " ".join(query.split()[:7])
                        if query and query not in seen:
                            seen.add(query)
                            normalized.append({"query": query, "strategy": entry.get("strategy", "topic-lock")})

                    if len(normalized) < 4:
                        for suffix in safe_suffixes:
                            query = f"{subject} {suffix}"
                            if query not in seen and len(normalized) < 8:
                                seen.add(query)
                                normalized.append({"query": query, "strategy": "topic-lock-fallback"})

                    shot["search_ladder"] = normalized[:8]
                    shot["queries"] = [x["query"] for x in normalized[:8]]

            print(f"🔒 STOCK TOPIC LOCK: subject='{subject}' | queries normalized for every shot")
            return plan

        normalize_plan._mint_topic_lock = True
        module.build_plan = normalize_plan

    print(
        "🛡️ Stock-search Gemini: gemini-flash-lite-latest ONLY | "
        f"media cooldown={RECENT_MEDIA_COOLDOWN} | topic lock=ON"
    )


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


def _patch_riddle_interactive(module):
    # Riddles are narration-first. Scene lengths are deliberately flexible;
    # the episode-level 50-85 word contract is the real pacing gate.
    module.SCENE_WORD_BUDGETS = (
        (4, 18),
        (7, 20),
        (5, 16),
        (5, 16),
        (5, 12),
        (3, 8),
        (12, 26),
    )
    module.MIN_WORDS = 50
    module.MAX_WORDS = 85
    print("🧩 Riddle pacing runtime: unified natural scene bands ENABLED | total=50-85 words")


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
    elif name == "generate_script.interactive":
        _patch_riddle_interactive(module)


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
    TARGETS = {"tts", "assemble", "stock_search", "stock_media_resilient", "stock_query_expander", "generate_script.interactive"}

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
