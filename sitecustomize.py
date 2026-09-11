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
        verb_words = {
            "flatten", "spin", "feel", "feels", "make", "makes", "cause", "causes", "melt",
            "freeze", "break", "breaks", "pop", "pops", "crack", "cracks", "open", "opens",
            "close", "closes", "move", "moves", "fall", "falls", "rise", "rises", "turn",
            "turns", "work", "works", "disappear", "disappears", "change", "changes", "grow",
            "grows", "stick", "sticks", "bounce", "bounces", "float", "floats", "sink", "sinks",
            "boil", "boils", "burn", "burns", "stretch", "stretches", "shrink", "shrinks",
            "squeeze", "squeezes", "compress", "compresses", "absorb", "absorbs", "reflect",
            "reflects", "reverse", "reverses", "ring", "rings", "echo", "echoes", "sound",
            "sounds", "smell", "smells", "taste", "tastes", "shine", "shines", "glow", "glows",
        }

        def topic_subject(topic):
            words = re.findall(r"[a-z][a-z-]{2,}", str(topic or "").lower())
            candidates = []
            for word in words:
                if word in ignored or word in bad_query_words:
                    continue
                if word not in candidates:
                    candidates.append(word)

            subject = []
            for word in candidates:
                if word in verb_words and subject:
                    break
                subject.append(word)
                if len(subject) >= 3:
                    break
            if not subject and candidates:
                subject = candidates[:1]
            return " ".join(subject)

        def _scene_terms(shot):
            text = " ".join([
                str(shot.get("spoken_beat", "")),
                str(shot.get("visual_focus", "")),
                str(shot.get("visual_action", "")),
                " ".join(str(x) for x in shot.get("anchor_terms", []) or []),
            ]).lower()
            ignored_local = ignored | bad_query_words | {
                "show", "showing", "visible", "camera", "shot", "scene", "people", "person",
                "ordinary", "photographer", "uploaded", "stock", "image", "video", "footage",
                "realistically", "search", "same", "primary", "physical", "subject", "related",
                "objects", "object", "state", "visible", "focus", "action", "create", "atmosphere",
                "spoken", "beat", "never", "only", "current", "answer", "required", "clue",
            }
            terms = []
            for word in re.findall(r"[a-z][a-z-]{2,}", text):
                if word in ignored_local:
                    continue
                if word not in terms:
                    terms.append(word)
            return terms[:8]

        def _query_variants(subject, shot, original_ladder):
            subject_words = set(subject.split())
            variants = []
            seen = set()

            def add(suffix_words, strategy):
                suffix = []
                for word in suffix_words:
                    word = str(word).lower().strip()
                    if not word or word in subject_words or word in bad_query_words:
                        continue
                    if word not in suffix:
                        suffix.append(word)
                    if len(suffix) >= 5:
                        break
                query = " ".join([subject, *suffix]).strip()
                query = " ".join(query.split()[:7])
                if len(query.split()) >= 2 and query not in seen:
                    seen.add(query)
                    variants.append({"query": query, "strategy": strategy})

            for entry in original_ladder or []:
                qwords = re.findall(r"[a-z0-9-]+", str(entry.get("query", "")).lower())
                add(qwords, entry.get("strategy", "topic-lock"))

            terms = _scene_terms(shot)
            for offset in range(0, len(terms), 2):
                add(terms[offset:offset + 4], "scene-variation")
                if len(variants) >= 8:
                    break

            safe_suffixes = ("close up", "bedroom", "being used", "compressed", "side view", "texture")
            for suffix in safe_suffixes:
                add(suffix.split(), "topic-lock-fallback")
                if len(variants) >= 8:
                    break
            return variants[:8]

        def normalize_plan(script):
            plan = original_build_plan(script)
            if script.get("riddle_number") or script.get("riddle_visual_mode"):
                print("🎭 RIDDLE VISUAL LOCK: preserving per-scene atmosphere queries; topic lock bypassed")
                return plan

            subject = topic_subject(script.get("topic", ""))
            if not subject:
                return plan

            for shots in plan:
                for shot in shots:
                    shot["search_ladder"] = _query_variants(subject, shot, shot.get("search_ladder", []))
                    shot["queries"] = [x["query"] for x in shot["search_ladder"]]

            print(
                f"🔒 STOCK TOPIC LOCK: subject='{subject}' | "
                "per-scene visual query variation ENABLED | max 8 queries/shot"
            )
            return plan

        normalize_plan._mint_topic_lock = True
        module.build_plan = normalize_plan

    print(
        "🛡️ Stock-search Gemini: gemini-flash-lite-latest ONLY | "
        f"media cooldown={RECENT_MEDIA_COOLDOWN} | topic lock=ON | scene variation=ON"
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
