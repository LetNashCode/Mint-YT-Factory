"""Compatibility wrapper for generate_script.py.

Keeps the existing story engine intact while adding a deterministic prompt
constraint for next_short.topic so the continuation topic is generated in
the same question structure already enforced by topics.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


_ROOT = Path(__file__).resolve().parent.parent
_ORIGINAL_PATH = _ROOT / "generate_script.py"

_spec = importlib.util.spec_from_file_location(
    "_mint_original_generate_script",
    _ORIGINAL_PATH,
)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load original generate_script module: {_ORIGINAL_PATH}")

_original = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_original)


_NEXT_TOPIC_CONTRACT = r"""

============================================================
NEXT SHORT TOPIC — HARD FORMAT CONTRACT
============================================================

next_short.topic is consumed by the existing topics.py persistence validator.
It MUST already be a complete observable curiosity question before you return
JSON. Do not rely on downstream repair or validation to rewrite it.

The topic MUST begin with exactly one of these question structures:

Why does ...
Why do ...
Why is ...
Why are ...
Why can ...
How does ...
How do ...
How is ...
How are ...
How can ...

The words "why" or "how" alone are NOT sufficient.

GOOD:
Why does fresh laundry odor boost retail spending in second-hand stores
Why does ice sometimes crack loudly
Why do wet clothes feel colder in moving air
How does a mirror seem to reverse left and right

BAD:
how fresh laundry odor boosts retail spending in second-hand stores
fresh laundry odor and retail spending
how ice sometimes cracks loudly
The effect of fresh laundry odor on retail spending

The topic must:
- describe ONE observable phenomenon
- be specific and researchable
- naturally follow the CURRENT story
- be different from the CURRENT topic
- fit the existing 12-word topic limit
- contain no question mark or terminal punctuation

Return the question itself, without quotes, numbering, explanation, or labels.
If a draft does not satisfy the required structure, rewrite it internally before
returning the final JSON.
"""


_original_build_system_prompt = _original.build_system_prompt
_original_build_user_prompt = _original.build_user_prompt


def build_system_prompt():
    return _original_build_system_prompt().rstrip() + "\n" + _NEXT_TOPIC_CONTRACT


def build_user_prompt(topic, config, research):
    return _original_build_user_prompt(topic, config, research).rstrip() + "\n" + _NEXT_TOPIC_CONTRACT


_original.build_system_prompt = build_system_prompt
_original.build_user_prompt = build_user_prompt


# Export the complete original API after patching its internal prompt builders.
for _name, _value in vars(_original).items():
    if _name.startswith("__"):
        continue
    globals()[_name] = _value

# Explicitly export the patched builders too.
globals()["build_system_prompt"] = build_system_prompt
globals()["build_user_prompt"] = build_user_prompt
