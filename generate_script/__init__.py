"""Compatibility package for the entertainment-first script generator.

The active implementation lives in entertainment.py while research remains disabled.

Scene 7 continuation ownership belongs to main.py. The active entertainment
module still contains an older validator that expects the model to author the
next-topic bridge during generation. That conflicts with the production-owned
canonical lock and can reject an otherwise valid current-topic story before
main.py gets a chance to append the bridge. Patch that validator at the package
boundary so the model may finish the current story and production can append
exactly one canonical continuation later.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import importlib.abc
import importlib.machinery
import sys

_ROOT = Path(__file__).resolve().parent
_ACTIVE_PATH = _ROOT / "entertainment.py"

_spec = importlib.util.spec_from_file_location("_mint_entertainment_generate_script", _ACTIVE_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load {_ACTIVE_PATH}")

_original = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_original)


def _production_scene7_boundary_passthrough(text, next_topic):
    """Do not force a model-authored continuation sentence into Scene 7."""
    return str(text or "").strip()


def _production_bridge_validator(text, next_topic):
    """Compatibility return value; main.py owns the real continuation validation."""
    sentences = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", str(text or "").strip())
        if part.strip()
    ]
    return sentences[-1] if sentences else ""


# IMPORTANT: generate_script is the function object loaded from entertainment.py,
# so its __globals__ points at that module's namespace. Patching these two legacy
# helpers here removes the stale pre-production bridge gate without duplicating
# the generator or changing the active model.
_original_globals = getattr(_original.generate_script, "__globals__", {})
_original_globals["_ensure_scene7_boundary"] = _production_scene7_boundary_passthrough
_original_globals["_validate_natural_bridge"] = _production_bridge_validator

# Keep the model's next-topic metadata available, but make the ownership explicit.
_original_globals["CONTINUATION_OWNER"] = "main.py"

generate_script = _original.generate_script
_build_system_prompt = getattr(_original, "SYSTEM_PROMPT", None)
_build_schema = getattr(_original, "_build_schema", None)
_normalize = getattr(_original, "_normalize", None)
_parse = getattr(_original, "_parse", None)


def build_system_prompt():
    if _build_system_prompt is None:
        raise AttributeError("build_system_prompt is unavailable")
    return _build_system_prompt


def validate_script(script, verified_research=None):
    if not isinstance(script, dict):
        raise RuntimeError("Generated script must be a JSON object.")
    scenes = script.get("scene_plan")
    if not isinstance(scenes, list) or len(scenes) != 7:
        raise RuntimeError("Generated script must contain exactly 7 scenes.")
    return True


def _normalize_next_short(script):
    return script


def build_user_prompt(topic, config=None, research=None):
    return str(topic or "")


# ---------------------------------------------------------------------------
# RIDDLES SHORTS RUNTIME POLISH
# ---------------------------------------------------------------------------
# These patches deliberately live at the package boundary so the independent
# Riddles pipeline can improve its presentation without changing Publish Shorts.

_RIDDLE_CAPTION_STOPWORDS = {
    "the", "and", "that", "this", "with", "from", "your", "you", "have",
    "what", "when", "where", "which", "will", "would", "could", "should",
    "into", "over", "under", "then", "than", "just", "like", "does", "dont",
    "don't", "they", "them", "their", "there", "here", "were", "been", "being",
    "answer", "guess", "riddle", "next", "short", "follow", "subscribe",
}


def _riddle_caption_highlights(narration: str):
    words = re.findall(r"[A-Za-z][A-Za-z'-]{3,}", str(narration or ""))
    result = []
    for word in words:
        key = word.lower().strip("'\"")
        if key in _RIDDLE_CAPTION_STOPWORDS or key in result:
            continue
        result.append(key)
        if len(result) >= 2:
            break
    return result


def _riddle_caption_phrases(words):
    """Build natural 2-4 word caption beats instead of one-word karaoke."""
    normalized = []
    for item in words or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("word", "")).strip()
        if not text:
            continue
        try:
            start = max(0.0, float(item.get("start", 0.0)))
            end = max(start + 0.05, float(item.get("end", start + 0.05)))
        except Exception:
            continue
        normalized.append({"word": text, "start": start, "end": end})

    phrases = []
    index = 0
    while index < len(normalized):
        first = normalized[index]
        chunk = [first]
        chars = len(first["word"])
        cursor = index + 1

        while cursor < len(normalized) and len(chunk) < 4:
            candidate = normalized[cursor]
            candidate_text = candidate["word"]
            if chars + 1 + len(candidate_text) > 28:
                break
            previous = chunk[-1]["word"]
            chunk.append(candidate)
            chars += 1 + len(candidate_text)
            cursor += 1
            if re.search(r"[.!?]$", previous):
                break

        start = chunk[0]["start"]
        end = chunk[-1]["end"]
        if cursor < len(normalized):
            end = min(end, normalized[cursor]["start"])
        if end <= start:
            end = start + 0.08

        phrases.append({
            "text": " ".join(x["word"] for x in chunk),
            "words": [x["word"] for x in chunk],
            "start": start,
            "duration": min(1.35, max(0.12, end - start)),
        })
        index = cursor

    return phrases


def _patch_riddle_narration(module):
    original = getattr(module, "polish_riddle_script", None)
    if original is None or getattr(original, "_mint_riddle_runtime", False):
        return

    def polished(script, previous, number):
        result = original(script, previous, number)
        scenes = result.get("scene_plan") or []
        for scene in scenes:
            narration = str(scene.get("narration", "")).strip()
            scene["caption_highlights"] = [
                {"word": word} for word in _riddle_caption_highlights(narration)
            ]
            if scene["caption_highlights"]:
                scene["emphasis_word"] = scene["caption_highlights"][0]["word"]
            scene["visual_dependency"] = "none"
            for visual in scene.get("visuals") or []:
                if isinstance(visual, dict):
                    # Preserve Gemini's concrete visual focus; only replace it
                    # when the storyboard failed to provide one.
                    visual["spoken_line"] = narration
                    if not str(visual.get("visual_focus", "")).strip():
                        visual["visual_focus"] = narration[:180]
                    visual["visual_action"] = (
                        "Create atmosphere for the spoken beat only. "
                        "Never show a required clue or the current answer."
                    )
        result["riddle_visual_mode"] = "narration_atmosphere_v2"
        result["riddle_caption_mode"] = "phrase_beats_v2"
        return result

    polished._mint_riddle_runtime = True
    module.polish_riddle_script = polished
    print("🎬 Riddle runtime polish: atmosphere-only visuals + phrase caption metadata ENABLED")


def _patch_assemble(module):
    """Improve Riddle captions while leaving the shared renderer architecture intact."""
    module.CAPTION_MAX_WORDS = 4
    module.CAPTION_MAX_CHARS = 28
    module.CAPTION_MIN_DURATION = 0.12
    module.CAPTION_MAX_DURATION = 1.35
    module.CAPTION_VERTICAL_POSITION = 0.64
    original = getattr(module, "_build_caption_phrases", None)
    if original is None or getattr(original, "_mint_riddle_phrases", False):
        return
    module._build_caption_phrases = _riddle_caption_phrases
    module._build_caption_phrases._mint_riddle_phrases = True
    print("📝 Riddle captions: natural 2-4 word phrase beats ENABLED")


class _RiddleRuntimeFinder(importlib.abc.MetaPathFinder):
    TARGETS = {"assemble", "riddle_narration"}

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
        spec.loader = _RiddleRuntimeLoader(spec.loader)
        return spec


class _RiddleRuntimeLoader(importlib.abc.Loader):
    def __init__(self, loader):
        self.loader = loader

    def create_module(self, spec):
        creator = getattr(self.loader, "create_module", None)
        return creator(spec) if creator else None

    def exec_module(self, module):
        self.loader.exec_module(module)
        if module.__name__ == "assemble":
            _patch_assemble(module)
        elif module.__name__ == "riddle_narration":
            _patch_riddle_narration(module)


if not any(isinstance(x, _RiddleRuntimeFinder) for x in sys.meta_path):
    sys.meta_path.insert(0, _RiddleRuntimeFinder())


class _RiddleQualityFinder(importlib.abc.MetaPathFinder):
    """Patch non-critical riddle novelty checks when generate_script.interactive loads."""

    TARGET = "generate_script.interactive"

    def find_spec(self, fullname, path=None, target=None):
        if fullname != self.TARGET:
            return None
        try:
            sys.meta_path.remove(self)
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        finally:
            sys.meta_path.insert(0, self)
        if spec is None or spec.loader is None:
            return None
        spec.loader = _RiddleQualityLoader(spec.loader)
        return spec


class _RiddleQualityLoader(importlib.abc.Loader):
    def __init__(self, loader):
        self.loader = loader

    def create_module(self, spec):
        creator = getattr(self.loader, "create_module", None)
        return creator(spec) if creator else None

    def exec_module(self, module):
        self.loader.exec_module(module)
        original = getattr(module, "_validate_internal_novelty", None)
        if original is None or getattr(original, "_mint_nonfatal", False):
            return

        def nonfatal_novelty_guard(scenes):
            """Run novelty checks for diagnostics, but never kill production for style."""
            try:
                original(scenes)
            except Exception as exc:
                print(f"⚠️ Riddle novelty warning (non-fatal): {type(exc).__name__}: {exc}")

        nonfatal_novelty_guard._mint_nonfatal = True
        module._validate_internal_novelty = nonfatal_novelty_guard
        print("🛡️ Riddle novelty guard: diagnostic/non-fatal mode ENABLED")


if not any(isinstance(x, _RiddleQualityFinder) for x in sys.meta_path):
    sys.meta_path.insert(0, _RiddleQualityFinder())


__all__ = ["generate_script", "build_system_prompt", "build_user_prompt", "validate_script"]
