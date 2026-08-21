"""Entertainment-first topic engine for Mint-YT-Factory.

Research is intentionally disabled in this development phase.
This module is self-contained so it does not depend on the legacy topics.py API.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from google import genai
from google.genai import types

_ROOT = Path(__file__).resolve().parent.parent
_USED_TOPICS_PATH = _ROOT / "used_topics.json"
_PENDING_PREFIX = "__MINT_PENDING_NEXT_TOPIC__::"
MODEL = "gemini-flash-lite-latest"

_BANNED = (
    "permafrost", "tundra", "tectonic", "geological", "geology", "quantum",
    "particle physics", "astrophysics", "cosmology", "black hole", "neutron star",
    "supernova", "dark matter", "dark energy", "subduction", "plate boundary",
    "ice wedge", "ice-wedge", "brine pocket", "crystal lattice", "electromagnetic field",
    "entropy", "thermodynamics", "microcrack", "gravitational wave", "neutrino",
    "gene expression", "chromosome", "mitochondria", "atmospheric circulation",
    "ocean current", "radiative forcing", "fracture mechanics", "thermal cracks",
    "material fatigue", "periglacial", "seismic", "magnetohydrodynamic",
    "fluid dynamics", "cryogenic", "crystallography", "geophysical", "cell tower",
    "cellular positioning", "gps positioning", "rf positioning", "network positioning",
    "triangulation", "trilateration",
)

_FORBIDDEN = (
    "the science of", "the physics of", "the biology of", "the history of",
    "the neuroscience of", "study of", "mechanism of", "top 5", "top 10",
    "facts about", "interesting facts", "did you know", "benefits of",
    "importance of", "complete guide", "ultimate guide", "what is", "what are",
)

_SIGNALS = (
    "phone", "battery", "charger", "charging", "screen", "wifi", "wi-fi", "headphone",
    "earbuds", "voice", "recording", "speaker", "fan", "mirror", "shower", "toothpaste",
    "orange juice", "onion", "popcorn", "milk", "coffee", "tea", "food", "taste", "smell",
    "spicy", "mosquito", "sneeze", "hiccup", "yawn", "sleep", "alarm", "dream", "skin",
    "water", "ice", "cold", "hot", "sweat", "hair", "clothes", "static", "shock", "door",
    "window", "glass", "soap", "bubble", "bread", "egg", "rice", "salt", "sugar", "fridge",
    "freezer", "car", "traffic", "seatbelt", "tire", "keyboard", "computer", "laptop",
    "remote", "light", "shadow", "rain", "umbrella", "pillow", "blanket", "shoe", "paper",
    "pen", "bag", "bottle", "cup", "echo", "sound", "nose", "mouth", "teeth", "tears",
    "breath", "blink", "goosebumps", "fingers", "hands", "laundry", "oven", "stove",
    "microwave", "toaster", "candle", "towel", "sink", "tap", "socks",
)

_PROMPT = """
You create topics for a highly entertaining YouTube Shorts channel.

CHANNEL PROMISE:
Things ordinary people experience all the time but almost never stop to ask why.

Choose ONE familiar, visually interesting everyday mystery. The viewer should
instantly recognise it and think: "Wait... why DOES that happen?"

Science is the explanation, NEVER the packaging.

Good areas: phones, charging, screens, headphones, voice recordings, fans,
mirrors, showers, toothpaste, food, taste, smell, cooking, onions, popcorn,
coffee, spicy food, mosquitoes, sneezing, hiccups, yawning, sleep, skin, hair,
water, ice, static, soap, bubbles, bread, eggs, cars, traffic, keyboards,
lights, shadows, rain, bottles, cups, doors, windows, sounds and echoes.

Reject academic subjects, generic facts, lists, countdowns, medical advice,
politics, conspiracy, fearbait, broad subjects, and anything difficult to show.

Return ONLY one question, 6-12 words, no quotes, no numbering, no explanation,
no question mark. Prefer Why does / Why do / Why is / Why are / Why can / How does / How do.

Previous topics:
{previous}
"""


def _clean_topic(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"```(?:text|json)?", "", text, flags=re.I)
    text = text.replace('"', "").replace("'", "")
    text = re.sub(r"^(topic|next topic|next_short|next short)\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*\d+[.)\-:]\s*", "", text)
    return " ".join(text.split()).rstrip(".!? ").strip()


def _key(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", _clean_topic(value).lower()).split())


def _is_everyday_topic(value: str) -> bool:
    text = _clean_topic(value).lower()
    if not text or any(x in text for x in _BANNED) or any(x in text for x in _FORBIDDEN):
        return False
    if not re.match(r"^(why does|why do|why is|why are|why can|how does|how do|how is|how are|how can)\s+.+", text):
        return False
    words = re.findall(r"\b[\w'-]+\b", text)
    if not 6 <= len(words) <= 12:
        return False
    if any(x in text for x in (" and why ", " and how ", " or why ", " or how ")):
        return False
    return any(signal in f" {text} " for signal in _SIGNALS)


def _read_used() -> list[str]:
    try:
        if not _USED_TOPICS_PATH.exists():
            return []
        data = json.loads(_USED_TOPICS_PATH.read_text(encoding="utf-8"))
        return [str(x) for x in data] if isinstance(data, list) else []
    except Exception:
        return []


def _write_used(items: list[str]) -> None:
    tmp = _USED_TOPICS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(_USED_TOPICS_PATH)


def _consume_pending() -> str:
    items = _read_used()
    pending = ""
    clean = []
    for item in items:
        if item.startswith(_PENDING_PREFIX):
            if not pending:
                pending = _clean_topic(item[len(_PENDING_PREFIX):])
        else:
            clean.append(item)
    if pending:
        _write_used(clean)
        print("=" * 80)
        print("🔗 CONTINUING FROM PREVIOUS SHORT")
        print("=" * 80)
        print(f"Next topic: {pending}")
        print("Continuation state consumed from used_topics.json.")
        print("=" * 80)
    return pending


def _generate_topic(used: list[str]) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")
    client = genai.Client(api_key=api_key)
    previous = "\n".join(used[-100:])
    prompt = _PROMPT.format(previous=previous)

    for attempt in range(1, 11):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=1.1),
            )
            candidate = _clean_topic(getattr(response, "text", ""))
            print(f"🧠 Topic attempt {attempt}/10: {candidate}")
            if not _is_everyday_topic(candidate):
                print("⚠️ Rejected: not a valid everyday curiosity.")
                continue
            key = _key(candidate)
            if any(key == _key(x) for x in used):
                print("⚠️ Rejected: duplicate topic.")
                continue
            return candidate
        except Exception as error:
            print(f"⚠️ Topic attempt failed: {error}")

    fallbacks = [
        "Why does your phone get hot while charging",
        "Why does your voice sound weird in a recording",
        "Why does a cold glass get covered in water",
        "Why does a fan make you feel cooler",
        "Why do onions make you cry",
    ]
    for candidate in fallbacks:
        if _is_everyday_topic(candidate) and not any(_key(candidate) == _key(x) for x in used):
            print(f"🔄 Using fallback topic: {candidate}")
            return candidate
    raise RuntimeError("Could not generate a valid everyday-curiosity topic.")


def get_next_topic() -> str:
    pending = _consume_pending()
    if pending and _is_everyday_topic(pending):
        return pending
    if pending:
        print(f"⚠️ Discarding stale continuation topic: {pending}")
    used = [x for x in _read_used() if not x.startswith(_PENDING_PREFIX)]
    return _generate_topic(used)


def save_next_short(next_short: str) -> bool:
    topic = _clean_topic(next_short)
    if not _is_everyday_topic(topic):
        raise RuntimeError(f"Generated next Short violates topic policy: {topic}")
    items = [x for x in _read_used() if not x.startswith(_PENDING_PREFIX)]
    items.append(_PENDING_PREFIX + topic)
    _write_used(items)
    print("💾 Durable continuation state saved in used_topics.json")
    print(f"🔗 Exact next-video topic: {topic}")
    return True


def commit_topic(topic: str) -> bool:
    topic = _clean_topic(topic)
    items = _read_used()
    key = _key(topic)
    items = [x for x in items if not x.startswith(_PENDING_PREFIX)]
    if not any(_key(x) == key for x in items):
        items.append(topic)
    _write_used(items)
    print(f"📌 Committed topic: {topic}")
    return True


def validate_topic_for_pipeline(topic: str, used=None, check_duplicate=True) -> bool:
    if not _is_everyday_topic(topic):
        return False
    if check_duplicate:
        pool = list(used) if used is not None else _read_used()
        if any(_key(topic) == _key(x) for x in pool if not x.startswith(_PENDING_PREFIX)):
            return False
    return True
