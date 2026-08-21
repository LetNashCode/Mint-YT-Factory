"""Compatibility package for the entertainment-first script generator.

The active implementation lives in entertainment.py while research remains disabled.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_ACTIVE_PATH = _ROOT / "entertainment.py"

_spec = importlib.util.spec_from_file_location("_mint_entertainment_generate_script", _ACTIVE_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load {_ACTIVE_PATH}")

_original = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_original)

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
