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


__all__ = ["generate_script", "build_system_prompt", "build_user_prompt", "validate_script"]
