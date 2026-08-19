"""Compatibility wrapper for generate_script.py.

Keeps the existing story engine intact while adding deterministic guards for
continuation-topic format and current-topic story identity.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re


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
_original_normalize_next_short = _original._normalize_next_short
_original_validate_script = _original.validate_script


def build_system_prompt():
    return _original_build_system_prompt().rstrip() + "\n" + _NEXT_TOPIC_CONTRACT


def build_user_prompt(topic, config, research):
    return _original_build_user_prompt(topic, config, research).rstrip() + "\n" + _NEXT_TOPIC_CONTRACT


def _normalize_next_short(script):
    _original_normalize_next_short(script)

    topic = str(
        script["next_short"]["topic"]
    ).strip()

    if not re.match(
        r"^(why does|why do|why is|why are|why can|how does|how do|how is|how are|how can)\s+.+",
        topic,
        flags=re.IGNORECASE,
    ):
        raise RuntimeError(
            "next_short.topic must be a complete observable question "
            "starting with Why does/Why do/Why is/Why are/Why can/"
            "How does/How do/How is/How are/How can."
        )

    script["next_short"]["topic"] = topic.rstrip("?!.").strip()


def _topic_terms_from_research(research):
    vocabulary = research.get(
        "research_vocabulary",
        {},
    )

    subjects = vocabulary.get(
        "subject",
        [],
    )

    phenomena = vocabulary.get(
        "phenomenon",
        [],
    )

    if not isinstance(subjects, list):
        subjects = []

    if not isinstance(phenomena, list):
        phenomena = []

    subject_phrase = ""
    for item in subjects:
        item = str(item or "").strip().lower()
        if item:
            subject_phrase = item
            break

    # The research parser's first subject entry is the concrete phrase.
    # Ignore generic adjectives when checking story identity.
    generic = {
        "fresh", "good", "right", "different", "new", "common",
        "everyday", "often", "sometimes", "cold", "hot",
    }

    subject_terms = {
        word
        for word in re.findall(r"[a-z0-9]+", subject_phrase)
        if len(word) >= 3 and word not in generic
    }

    phenomenon_terms = set()
    for item in phenomena:
        text = str(item or "").lower()
        words = set(re.findall(r"[a-z0-9]+", text))
        if "smell" in words or "odor" in words or "odour" in words or "aroma" in words:
            phenomenon_terms.update({"smell", "odor", "odour", "aroma"})
        elif "sound" in words or "noise" in words or "echo" in words:
            phenomenon_terms.update({"sound", "noise", "echo"})
        elif "feel" in words or "temperature" in words or "cold" in words:
            phenomenon_terms.update({"feel", "temperature", "cold"})
        elif "taste" in words or "flavor" in words or "flavour" in words:
            phenomenon_terms.update({"taste", "flavor", "flavour"})
        else:
            phenomenon_terms.update(
                word for word in words if len(word) >= 3
            )

    return subject_terms, phenomenon_terms


def _contains_any(text, terms):
    words = set(
        re.findall(
            r"[a-z0-9]+",
            str(text or "").lower(),
        )
    )
    return any(term in words for term in terms)


def validate_script(script, verified_research):
    result = _original_validate_script(
        script,
        verified_research,
    )

    subject_terms, phenomenon_terms = _topic_terms_from_research(
        verified_research
    )

    if not subject_terms and not phenomenon_terms:
        return result

    narration = " ".join(
        str(scene.get("narration", ""))
        for scene in script.get("scene_plan", [])
        if isinstance(scene, dict)
    )

    title = str(
        script.get("title", "")
    )

    description = str(
        script.get("description", "")
    )

    # The current story must identify its concrete subject somewhere in the
    # narration and in public metadata. This prevents a valid evidence package
    # from turning into a different story such as COVID smell loss.
    if subject_terms:
        if not _contains_any(narration, subject_terms):
            raise RuntimeError(
                "CURRENT TOPIC DRIFT: narration does not identify the "
                "concrete subject from the verified current topic."
            )

        if not _contains_any(
            f"{title} {description}",
            subject_terms,
        ):
            raise RuntimeError(
                "CURRENT TOPIC DRIFT: title/description do not identify "
                "the concrete subject from the verified current topic."
            )

    if phenomenon_terms and not _contains_any(
        narration,
        phenomenon_terms,
    ):
        raise RuntimeError(
            "CURRENT TOPIC DRIFT: narration does not identify the "
            "observable phenomenon from the verified current topic."
        )

    return result


# Patch the ORIGINAL module's globals because generate_script() and its
# validation helpers execute inside that module namespace.
_original.build_system_prompt = build_system_prompt
_original.build_user_prompt = build_user_prompt
_original._normalize_next_short = _normalize_next_short
_original.validate_script = validate_script


# Export the complete original API after patching its internal functions.
for _name, _value in vars(_original).items():
    if _name.startswith("__"):
        continue
    globals()[_name] = _value

# Explicitly export the patched callables too.
globals()["build_system_prompt"] = build_system_prompt
globals()["build_user_prompt"] = build_user_prompt
globals()["_normalize_next_short"] = _normalize_next_short
globals()["validate_script"] = validate_script
