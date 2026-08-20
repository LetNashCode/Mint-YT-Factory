"""Compatibility wrapper for the existing topics.py engine.

This package is the public topic entry point used by main.py.  The original
root topics.py remains responsible for the existing research/duplicate and
persistence rules, while this wrapper owns the channel's viewer-facing topic
policy.

HARD CHANNEL POLICY
-------------------
The channel is built around ordinary things people notice in daily life.
Science is the explanation, not the packaging.  Academic phenomena such as
permafrost, tectonic processes, fracture mechanics, particle physics, etc.
must never become the next video's current topic.

The everyday gate lives here (not only in sitecustomize.py) so it remains
active even when Python does not load the optional runtime hook.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path

from google import genai
from google.genai import types


_ROOT = Path(__file__).resolve().parent.parent
_ORIGINAL_PATH = _ROOT / "topics.py"
_USED_TOPICS_PATH = _ROOT / "used_topics.json"
_PENDING_PREFIX = "__MINT_PENDING_NEXT_TOPIC__::"

_spec = importlib.util.spec_from_file_location(
    "_mint_original_topics",
    _ORIGINAL_PATH,
)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load original topics module: {_ORIGINAL_PATH}")

_original = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_original)


# ============================================================================
# EVERYDAY-CURIOSITY HARD GATE
# ============================================================================

EVERYDAY_TOPIC_MODEL = "gemini-flash-lite-latest"
EVERYDAY_TOPIC_ATTEMPTS = 10

_BANNED_ACADEMIC = (
    "permafrost", "tundra", "tectonic", "geological", "geology",
    "quantum", "particle physics", "astrophysics", "cosmology",
    "black hole", "neutron star", "supernova", "dark matter",
    "dark energy", "subduction", "plate boundary", "ice wedge",
    "brine pocket", "crystal lattice", "electromagnetic field",
    "entropy", "thermodynamics", "microcrack", "gravitational wave",
    "neutrino", "gene expression", "chromosome", "mitochondria",
    "atmospheric circulation", "ocean current", "radiative forcing",
    "fracture mechanics", "thermal cracks", "material fatigue",
    "periglacial", "seismic", "magnetohydrodynamic", "fluid dynamics",
    "quantum mechanics", "plate tectonics", "ice-wedge", "ice wedge",
    "periglacial", "cryogenic", "crystallography", "geophysical",
)

_FORBIDDEN_TOPIC_PHRASES = (
    "the science of", "the physics of", "the biology of", "the history of",
    "the neuroscience of", "a study of", "study of", "mechanism of",
    "thermodynamics", "fracture mechanics", "academic", "research on",
    "what is", "what are", "how the universe", "why is the universe",
    "top 5", "top 10", "facts about", "interesting facts", "did you know",
    "benefits of", "importance of", "complete guide", "ultimate guide",
)

_EVERYDAY_SIGNALS = (
    "phone", "battery", "charger", "charging", "screen", "wifi", "wi-fi",
    "headphone", "earbuds", "voice", "recording", "speaker", "fan",
    "air conditioner", " ac ", "mirror", "shower", "toothpaste",
    "orange juice", "onion", "popcorn", "milk", "coffee", "tea",
    "food", "taste", "smell", "spicy", "mosquito", "itch", "sneeze",
    "hiccup", "yawn", "sleep", "alarm", "dream", "skin", "water",
    "ice", "cold", "hot", "sweat", "hair", "clothes", "static",
    "shock", "door", "window", "glass", "soap", "bubble", "bread",
    "egg", "rice", "salt", "sugar", "fridge", "freezer", "car",
    "traffic", "seatbelt", "steering", "tire", "keyboard", "computer",
    "laptop", "remote", "light", "shadow", "rain", "umbrella", "pillow",
    "blanket", "shoe", "paper", "pen", "bag", "bottle", "cup",
    "clap", "echo", "sound", "nose", "mouth", "teeth", "tears",
    "breath", "blink", "goosebumps", "fingers", "hands", "laundry",
    "clothes", "oven", "stove", "microwave", "toaster", "candle",
    "soap", "towel", "sink", "tap", "water bottle", "socks", "shoes",
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
    return " ".join(value.split()).rstrip(".!? ").strip()


def _is_everyday_topic(candidate):
    text = _clean_topic(candidate).lower()
    if not text:
        return False

    if any(term in text for term in _BANNED_ACADEMIC):
        return False

    if any(term in text for term in _FORBIDDEN_TOPIC_PHRASES):
        return False

    if not re.match(r"^(why|how|can|does|do)\b", text):
        return False

    words = re.findall(r"\b[\w'-]+\b", text)
    if not 6 <= len(words) <= 12:
        return False

    if any(p in text for p in (" and why ", " and how ", " or why ", " or how ")):
        return False

    # A topic must contain a recognisable everyday object/experience.
    if not any(term in f" {text} " for term in _EVERYDAY_SIGNALS):
        return False

    return True


_EVERYDAY_PROMPT = """
You are selecting the next episode for a highly entertaining everyday-
curiosity YouTube Shorts channel.

CHANNEL PROMISE:
Things people experience all the time but almost never stop to ask why.

Science is the ANSWER, not the topic packaging.
The viewer should recognise the situation instantly and think:
"Wait... why DOES that happen?"

Choose exactly ONE ordinary, personally recognisable phenomenon.
It must be something people commonly see, hear, touch, taste, use or do.
The answer must have a real, researchable scientific or technical basis.
The explanation must be understandable in simple spoken English.

HIGH-VALUE AREAS:
phones, batteries, charging, screens, headphones, voice recordings, fans,
AC, mirrors, showers, toothpaste, food, taste, smell, cooking, onions,
popcorn, milk, coffee, spicy food, mosquitoes, sneezing, hiccups, yawning,
sleep, alarms, skin, hair, clothes, water, ice, static electricity,
bubbles, soap, bread, eggs, cars, traffic, keyboards, computers, lights,
shadows, rain, bottles, cups, doors, windows, sound, echoes and other
ordinary household or daily-life experiences.

TARGET EXAMPLES:
Why does toothpaste make orange juice taste disgusting
Why does your phone get hot while charging
Why does a fan make you feel cooler
Why does your voice sound weird in a recording
Why does your stomach growl when you're hungry
Why do onions make you cry
Why does boiling milk suddenly overflow
Why does your skin wrinkle in water
Why does your nose run when you eat spicy food
Why does a cold glass get covered in water
Why does metal feel colder than wood
Why does a mirror seem to reverse left and right

ABSOLUTELY REJECT:
permafrost, tundra, tectonic plates, plate boundaries, ice wedges,
fracture mechanics, thermal cracks, geological formations, quantum topics,
particle physics, astrophysics, black holes, neutron stars, atmospheric
circulation, academic titles, broad psychology/biology, generic facts,
trivia, lists, countdowns, health advice, diagnosis, treatment, fearbait,
conspiracy, politics or anything a viewer is unlikely to encounter personally.

TITLE RULES:
- 6–12 words
- preferably starts with Why or How
- simple everyday words
- exactly one phenomenon
- no jargon
- no answer revealed in the title
- no fake hype
- no question mark

PREVIOUS TOPICS:
{previous}

Return ONLY ONE topic. No explanation, quotes, numbering or emoji.
"""


def _read_used_topics_raw():
    try:
        if not _USED_TOPICS_PATH.exists():
            return []
        with _USED_TOPICS_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, list):
            return []
        return [str(item) for item in data if isinstance(item, str)]
    except Exception as error:
        print(f"⚠️ Could not read used_topics.json: {error}")
        return []


def _topic_key(value):
    text = _clean_topic(value).lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return " ".join(text.split())


def _generate_everyday_topic(current_topic="", used=None):
    used = list(used or [])
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing for everyday topic generation.")

    previous = "\n".join(used[-120:])
    prompt = _EVERYDAY_PROMPT.format(previous=previous)
    client = genai.Client(api_key=api_key)

    for attempt in range(1, EVERYDAY_TOPIC_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=EVERYDAY_TOPIC_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=1.10),
            )
            candidate = _clean_topic(getattr(response, "text", ""))
            print(f"🧠 Everyday topic attempt {attempt}/{EVERYDAY_TOPIC_ATTEMPTS}: {candidate}")

            if not _is_everyday_topic(candidate):
                print("⚠️ Rejected: topic is not an everyday curiosity.")
                continue

            key = _topic_key(candidate)
            if current_topic and key == _topic_key(current_topic):
                print("⚠️ Rejected: duplicate of current topic.")
                continue

            if any(key == _topic_key(item) for item in used):
                print("⚠️ Rejected: duplicate of a previous topic.")
                continue

            # Keep the existing research/duplicate validator as a SECOND gate.
            if not _original.validate_topic_for_pipeline(
                candidate,
                used=used,
                check_duplicate=True,
            ):
                print("⚠️ Rejected by the original topic validator.")
                continue

            return candidate
        except Exception as error:
            print(f"⚠️ Everyday topic attempt {attempt} failed: {error}")

    raise RuntimeError("Could not generate a valid everyday-curiosity topic.")


# ============================================================================
# DURABLE CONTINUATION STATE
# ============================================================================

_NEXT_TOPIC_FORMAT = r"""

============================================================
NEXT TOPIC FORMAT — HARD REQUIREMENT
============================================================

Any topic generated for the continuation queue MUST already be a valid
observable everyday question accepted by the channel's everyday validator.

It MUST begin with one of these exact structures:

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

Return the question itself, without a question mark, quotation marks,
numbering, explanation, or terminal punctuation.
"""

_original.SYSTEM_PROMPT = (
    _original.SYSTEM_PROMPT.rstrip()
    + "\n"
    + _NEXT_TOPIC_FORMAT
)


def _write_used_topics_raw(topics):
    temp_path = _USED_TOPICS_PATH.with_suffix(".tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(topics, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
        temp_path.replace(_USED_TOPICS_PATH)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass


def _pending_from_used_topics():
    for item in reversed(_read_used_topics_raw()):
        if item.startswith(_PENDING_PREFIX):
            topic = item[len(_PENDING_PREFIX):].strip()
            if topic:
                return topic
    return ""


def _consume_persisted_pending_topic():
    topics = _read_used_topics_raw()
    pending = ""
    cleaned = []

    for item in topics:
        if item.startswith(_PENDING_PREFIX):
            if not pending:
                candidate = item[len(_PENDING_PREFIX):].strip()
                if candidate:
                    pending = candidate
            continue
        cleaned.append(item)

    if pending:
        _write_used_topics_raw(cleaned)
        print("=" * 80)
        print("🔗 CONTINUING FROM PREVIOUS SHORT")
        print("=" * 80)
        print(f"Next topic: {pending}")
        print("Continuation state consumed from used_topics.json.")
        print("=" * 80)

    return pending


def _persist_pending_topic(topic):
    topic = _clean_topic(topic)
    if not topic:
        return False

    if not _is_everyday_topic(topic):
        raise RuntimeError(
            "Refusing to persist a non-everyday continuation topic: " + topic
        )

    topics = _read_used_topics_raw()
    topics = [item for item in topics if not item.startswith(_PENDING_PREFIX)]
    topics.append(_PENDING_PREFIX + topic)
    _write_used_topics_raw(topics)

    persisted = _pending_from_used_topics()
    if persisted.strip().lower() != topic.strip().lower():
        raise RuntimeError(
            "Continuation topic was written to used_topics.json but could not "
            "be verified after persistence."
        )

    print("💾 Durable continuation state saved in used_topics.json")
    print(f"🔗 Exact next-video topic: {topic}")
    return True


def get_next_topic():
    """Return the exact queued topic, otherwise generate a new everyday topic."""
    pending = _consume_persisted_pending_topic()

    if pending:
        if not _is_everyday_topic(pending):
            raise RuntimeError(
                "Persisted continuation topic violates everyday-curiosity policy: "
                + pending
            )

        if not _original.validate_topic_for_pipeline(
            pending,
            check_duplicate=False,
        ):
            raise RuntimeError(
                "Persisted continuation topic is invalid: " + pending
            )

        return pending

    used = _read_used_topics_raw()
    # Remove the private persistence marker from the duplicate context.
    used = [item for item in used if not item.startswith(_PENDING_PREFIX)]
    return _generate_everyday_topic(used=used)


def save_next_short(next_short):
    """Persist the generated next Short locally and durably across runs."""
    next_short = _clean_topic(next_short)

    if not _is_everyday_topic(next_short):
        raise RuntimeError(
            "Generated next Short violates everyday-curiosity policy: "
            + next_short
        )

    saved = _original.save_next_short(next_short)
    if not saved:
        return False

    _persist_pending_topic(next_short)
    return True


def validate_topic_for_pipeline(topic, used=None, check_duplicate=True):
    """Public validator: everyday policy first, original safety rules second."""
    if not _is_everyday_topic(topic):
        print(f"⚠️ Topic rejected by everyday-curiosity hard gate: {_clean_topic(topic)}")
        return False
    return _original.validate_topic_for_pipeline(
        topic,
        used=used,
        check_duplicate=check_duplicate,
    )


# Export the complete original API first, then restore the wrappers above.
for _name, _value in vars(_original).items():
    if _name.startswith("__"):
        continue
    if _name in {"get_next_topic", "save_next_short", "validate_topic_for_pipeline"}:
        continue
    globals()[_name] = _value

globals()["get_next_topic"] = get_next_topic
globals()["save_next_short"] = save_next_short
globals()["validate_topic_for_pipeline"] = validate_topic_for_pipeline
