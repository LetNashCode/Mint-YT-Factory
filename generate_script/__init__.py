"""Compatibility wrapper for generate_script.py.

Keeps the existing story engine intact while adding deterministic guards for
continuation-topic format, everyday-curiosity packaging, and current-topic
story identity.
"""

from __future__ import annotations

import importlib.util
import json
import os
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


# ============================================================================
# EVERYDAY-CURIOSITY CONTINUATION GATE
# ============================================================================

_BANNED_ACADEMIC = (
    "permafrost", "tundra", "tectonic", "geological", "geology",
    "quantum", "particle physics", "astrophysics", "cosmology",
    "black hole", "neutron star", "supernova", "dark matter",
    "dark energy", "subduction", "plate boundary", "ice wedge",
    "ice-wedge", "brine pocket", "crystal lattice", "electromagnetic field",
    "entropy", "thermodynamics", "microcrack", "gravitational wave",
    "neutrino", "gene expression", "chromosome", "mitochondria",
    "atmospheric circulation", "ocean current", "radiative forcing",
    "fracture mechanics", "thermal cracks", "material fatigue",
    "periglacial", "seismic", "magnetohydrodynamic", "fluid dynamics",
    "cryogenic", "crystallography", "geophysical",
    # Technical infrastructure topics are not the channel's viewer-facing
    # everyday-curiosity packaging.
    "cell tower", "cellular positioning", "tower positioning", "gps positioning",
    "radio positioning", "rf positioning", "network positioning",
    "indoor positioning", "triangulation", "trilateration",
)

_FORBIDDEN_PHRASES = (
    "the science of", "the physics of", "the biology of", "the history of",
    "the neuroscience of", "a study of", "study of", "mechanism of",
    "top 5", "top 10", "facts about", "interesting facts", "did you know",
    "benefits of", "importance of", "complete guide", "ultimate guide",
)

_EVERYDAY_SIGNALS = (
    "phone", "battery", "charger", "charging", "screen", "wifi", "wi-fi",
    "headphone", "earbuds", "voice", "recording", "speaker", "fan",
    "mirror", "shower", "toothpaste", "orange juice", "onion", "popcorn",
    "milk", "coffee", "tea", "food", "taste", "smell", "spicy", "mosquito",
    "sneeze", "hiccup", "yawn", "sleep", "alarm", "dream", "skin", "water",
    "ice", "cold", "hot", "sweat", "hair", "clothes", "static", "shock",
    "door", "window", "glass", "soap", "bubble", "bread", "egg", "rice",
    "salt", "sugar", "fridge", "freezer", "car", "traffic", "seatbelt",
    "tire", "keyboard", "computer", "laptop", "remote", "light", "shadow",
    "rain", "umbrella", "pillow", "blanket", "shoe", "paper", "pen", "bag",
    "bottle", "cup", "echo", "sound", "nose", "mouth", "teeth", "tears",
    "breath", "blink", "goosebumps", "fingers", "hands", "laundry", "oven",
    "stove", "microwave", "toaster", "candle", "towel", "sink", "tap", "socks",
)


def _clean_topic(value):
    value = str(value or "").strip()
    value = re.sub(r"```(?:text|json)?", "", value, flags=re.I)
    value = value.replace('"', "").replace("'", "")
    value = re.sub(
        r"^(topic|next topic|next_short|next short)\s*:\s*",
        "",
        value,
        flags=re.I,
    )
    value = re.sub(r"^\s*\d+[.\)\-:]\s*", "", value)
    return " ".join(value.split()).rstrip("?!.").strip()


def _is_everyday_topic(candidate):
    text = _clean_topic(candidate).lower()
    if not text:
        return False
    if any(term in text for term in _BANNED_ACADEMIC):
        return False
    if any(term in text for term in _FORBIDDEN_PHRASES):
        return False
    if not re.match(
        r"^(why does|why do|why is|why are|why can|how does|how do|how is|how are|how can)\s+.+",
        text,
        flags=re.IGNORECASE,
    ):
        return False
    words = re.findall(r"\b[\w'-]+\b", text)
    if not 6 <= len(words) <= 12:
        return False
    if any(p in text for p in (" and why ", " and how ", " or why ", " or how ")):
        return False
    if not any(term in f" {text} " for term in _EVERYDAY_SIGNALS):
        return False
    return True


_NEXT_TOPIC_CONTRACT = r"""

============================================================
NEXT SHORT TOPIC — HARD FORMAT CONTRACT
============================================================

next_short.topic is a VIEWER-FACING continuation question.
It must describe one ordinary thing a person can recognise immediately.
Science is the explanation, never the packaging.

The topic MUST begin with exactly one of these structures:
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

Never invent technical infrastructure topics such as cell-tower positioning,
GPS positioning, RF positioning, cellular triangulation, network positioning,
or similar engineering terminology.

If the proposed next topic fails the everyday gate, DO NOT keep retrying the
same idea. Replace it with a fresh everyday curiosity question.

GOOD:
Why does toothpaste make orange juice taste disgusting
Why does your phone get hot while charging
Why does a fan make you feel cooler
Why does your voice sound weird in a recording
Why does a cold glass get covered in water
Why does metal feel colder than wood
Why does a mirror seem to reverse left and right

BAD:
How does cell tower positioning work without GPS
How does indoor positioning work without GPS
How does RF fingerprinting locate a phone
The thermodynamics of freezing water
Why ice-wedge cracks propagate upward in permafrost

Return the question itself, without quotes, numbering, explanation, or labels.
"""


_original_build_system_prompt = _original.build_system_prompt
_original_build_user_prompt = _original.build_user_prompt
_original_normalize_next_short = _original._normalize_next_short
_original_validate_script = _original.validate_script


def build_system_prompt():
    return _original_build_system_prompt().rstrip() + "\n" + _NEXT_TOPIC_CONTRACT


def build_user_prompt(topic, config, research):
    return _original_build_user_prompt(topic, config, research).rstrip() + "\n" + _NEXT_TOPIC_CONTRACT


def _used_topics_for_fallback():
    path = _ROOT / "used_topics.json"
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, list):
            return []
        return [str(item) for item in data if isinstance(item, str)]
    except Exception:
        return []


def _fallback_everyday_topic(current_topic=""):
    """Generate a clean continuation topic instead of retrying bad Gemini output.

    This is deliberately delegated to the channel topic engine so the same
    everyday-curiosity policy and duplicate protection used by topic selection
    applies here too.
    """
    try:
        import topics as _topics

        generator = getattr(_topics, "_generate_everyday_topic", None)
        if callable(generator):
            used = _used_topics_for_fallback()
            candidate = generator(
                current_topic=current_topic,
                used=used,
            )
            candidate = _clean_topic(candidate)
            if _is_everyday_topic(candidate):
                print(f"🔄 Replaced invalid Gemini next topic with: {candidate}")
                return candidate
    except Exception as error:
        print(f"⚠️ Everyday next-topic fallback failed: {error}")

    # Last-resort deterministic fallback. It is only used if the topic engine
    # itself cannot produce a topic, so the pipeline never dies because Gemini
    # repeatedly proposes an academic continuation.
    fallbacks = [
        "Why does your phone get hot while charging",
        "Why does your voice sound weird in a recording",
        "Why does a cold glass get covered in water",
        "Why does a fan make you feel cooler",
        "Why does toothpaste make orange juice taste disgusting",
    ]

    current_key = _clean_topic(current_topic).lower()
    for candidate in fallbacks:
        if candidate.lower() != current_key and _is_everyday_topic(candidate):
            print(f"🔄 Using deterministic everyday next topic: {candidate}")
            return candidate

    return fallbacks[0]


def _normalize_next_short(script):
    _original_normalize_next_short(script)

    topic = _clean_topic(
        script["next_short"]["topic"]
    )

    if not re.match(
        r"^(why does|why do|why is|why are|why can|how does|how do|how is|how are|how can)\s+.+",
        topic,
        flags=re.IGNORECASE,
    ) or not _is_everyday_topic(topic):
        current_topic = _clean_topic(
            script.get("current_topic", script.get("topic", ""))
        )
        topic = _fallback_everyday_topic(current_topic)

    script["next_short"]["topic"] = topic


def _topic_terms_from_research(research):
    vocabulary = research.get("research_vocabulary", {})
    subjects = vocabulary.get("subject", [])
    phenomena = vocabulary.get("phenomenon", [])

    if not isinstance(subjects, list):
        subjects = []
    if not isinstance(phenomena, list):
        phenomena = []

    generic = {
        "fresh", "good", "right", "different", "new", "common",
        "everyday", "often", "sometimes", "cold", "hot",
    }

    subject_terms = {
        word
        for item in subjects
        for word in re.findall(r"[a-z0-9]+", str(item or "").lower())
        if len(word) >= 3 and word not in generic
    }

    phenomenon_terms = set()
    for item in phenomena:
        words = set(re.findall(r"[a-z0-9]+", str(item or "").lower()))
        if {"smell", "odor", "odour", "aroma"} & words:
            phenomenon_terms.update({"smell", "odor", "odour", "aroma"})
        elif {"sound", "noise", "echo"} & words:
            phenomenon_terms.update({"sound", "noise", "echo"})
        elif {"feel", "temperature", "cold"} & words:
            phenomenon_terms.update({"feel", "temperature", "cold"})
        elif {"taste", "flavor", "flavour"} & words:
            phenomenon_terms.update({"taste", "flavor", "flavour"})
        else:
            phenomenon_terms.update(word for word in words if len(word) >= 3)

    return subject_terms, phenomenon_terms


def _contains_any(text, terms):
    words = set(re.findall(r"[a-z0-9]+", str(text or "").lower()))
    return any(term in words for term in terms)


def validate_script(script, verified_research):
    result = _original_validate_script(script, verified_research)

    subject_terms, phenomenon_terms = _topic_terms_from_research(verified_research)
    if not subject_terms and not phenomenon_terms:
        return result

    narration = " ".join(
        str(scene.get("narration", ""))
        for scene in script.get("scene_plan", [])
        if isinstance(scene, dict)
    )
    title = str(script.get("title", ""))
    description = str(script.get("description", ""))

    if subject_terms and not _contains_any(narration, subject_terms):
        raise RuntimeError(
            "CURRENT TOPIC DRIFT: narration does not identify the concrete "
            "subject from the verified current topic."
        )

    if subject_terms and not _contains_any(f"{title} {description}", subject_terms):
        raise RuntimeError(
            "CURRENT TOPIC DRIFT: title/description do not identify the "
            "concrete subject from the verified current topic."
        )

    if phenomenon_terms and not _contains_any(narration, phenomenon_terms):
        raise RuntimeError(
            "CURRENT TOPIC DRIFT: narration does not identify the observable "
            "phenomenon from the verified current topic."
        )

    return result


# Patch the ORIGINAL module's globals because generate_script() and its
# validation helpers execute inside that module namespace.
_original.build_system_prompt = build_system_prompt
_original.build_user_prompt = build_user_prompt
_original._normalize_next_short = _normalize_next_short
_original.validate_script = validate_script


for _name, _value in vars(_original).items():
    if _name.startswith("__"):
        continue
    globals()[_name] = _value


globals()["build_system_prompt"] = build_system_prompt
globals()["build_user_prompt"] = build_user_prompt
globals()["_normalize_next_short"] = _normalize_next_short
globals()["validate_script"] = validate_script
