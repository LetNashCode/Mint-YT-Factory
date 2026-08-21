"""Compatibility package for the entertainment-first script generator.

The active implementation now lives in the repository-level generate_script.py.
Research is intentionally bypassed while we tune Short generation quality.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_ORIGINAL_PATH = _ROOT / "generate_script.py"

_spec = importlib.util.spec_from_file_location("_mint_original_generate_script", _ORIGINAL_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load {_ORIGINAL_PATH}")

_original = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_original)

# Public API used by main.py and older pipeline code.
generate_script = _original.generate_script

# Keep these names available for compatibility with any other modules that
# imported them from the old package wrapper.
_build_system_prompt = getattr(_original, "_build_system_prompt", None)
_build_schema = getattr(_original, "_build_schema", None)
_normalize = getattr(_original, "_normalize", None)
_parse = getattr(_original, "_parse", None)


def build_system_prompt():
    if _build_system_prompt is None:
        raise AttributeError("build_system_prompt is unavailable")
    return _build_system_prompt()


def validate_script(script, verified_research=None):
    """Compatibility no-op validation.

    Research has deliberately been removed from the current generation stage.
    The active generator performs its own structural normalization/validation.
    """
    if not isinstance(script, dict):
        raise RuntimeError("Generated script must be a JSON object.")
    scenes = script.get("scene_plan")
    if not isinstance(scenes, list) or len(scenes) != 7:
        raise RuntimeError("Generated script must contain exactly 7 scenes.")
    return True


def _normalize_next_short(script):
    """Compatibility helper for legacy callers."""
    return script


def build_user_prompt(topic, config=None, research=None):
    """Compatibility helper; the active generator builds its own prompt."""
    return str(topic or "")


__all__ = ["generate_script", "build_system_prompt", "build_user_prompt", "validate_script"]
