"""Compatibility wrapper for the existing topics.py engine.

The original topics.py remains the source of truth for validation and
persistence. This package only strengthens the Gemini generation instruction
so generated continuation topics conform to the validator already enforced
by save_next_short().
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


_ROOT = Path(__file__).resolve().parent.parent
_ORIGINAL_PATH = _ROOT / "topics.py"

_spec = importlib.util.spec_from_file_location(
    "_mint_original_topics",
    _ORIGINAL_PATH,
)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load original topics module: {_ORIGINAL_PATH}")

_original = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_original)


_NEXT_TOPIC_FORMAT = r"""

============================================================
NEXT TOPIC FORMAT — HARD REQUIREMENT
============================================================

Any topic generated for the continuation queue MUST already be a valid
observable question accepted by the existing topic validator.

It MUST begin with one of these exact question structures:

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

The question must contain a concrete observable phenomenon after the
question words. Do NOT output a bare "how" followed directly by a noun.

GOOD:

Why does fresh laundry odor boost retail spending in second-hand stores
Why does ice sometimes crack loudly
Why do wet clothes feel colder in moving air
Why does fresh bread smell so good right after slicing
How does a mirror seem to reverse left and right

BAD:

how fresh laundry odor boosts retail spending in second-hand stores
fresh laundry odor and retail spending
how ice sometimes cracks loudly
fresh bread smell after slicing
The effect of fresh laundry odor on retail spending

Return the question itself, without a question mark, quotation marks,
numbering, explanation, or terminal punctuation.

This is a HARD output constraint. If your first candidate does not match
one of the required structures, rewrite it before returning it.
"""

_original.SYSTEM_PROMPT = (
    _original.SYSTEM_PROMPT.rstrip()
    + "\n"
    + _NEXT_TOPIC_FORMAT
)


# Export the complete original API. The original validator remains intact;
# only the generation instruction is strengthened.
for _name, _value in vars(_original).items():
    if _name.startswith("__"):
        continue
    globals()[_name] = _value
