"""Entertainment-first topic queue for Mint-YT-Factory.

Research is not part of topic selection in the current development phase.
The topic engine optimizes for recognizable, visual, curiosity-driven Shorts.
"""

from __future__ import annotations

import json
import os
import re
import tempfile

from google import genai
from google.genai import types

MODEL_NAME = "gemini-flash-lite-latest"
USED_TOPICS_PATH = "used_topics.json"
NEXT_TOPIC_PATH = "next_topic.json"
MAX_TOPIC_WORDS = 12
MAX_TOPIC_CHARACTERS = 300

SYSTEM_PROMPT = """
You are the viral topic strategist for Wonder Minute, an entertaining
YouTube Shorts channel built around strange things people notice in daily life.

Generate ONE topic with strong visual and storytelling potential.
The viewer reaction should be: "Wait, why does THAT happen?"

Prefer:
- familiar everyday experiences
- weird physical behavior
- surprising animal behavior
- strange sounds, sights, textures or reactions
- objects behaving unexpectedly
- simple mysteries that can be shown literally
- topics that can support a 35–45 second story

The topic must have ONE central mystery.

Avoid:
- academic titles
- "the science of..."
- generic facts
- lists/top 5/countdowns
- broad subjects
- medical advice
- politics
- conspiracy theories
- fearbait
- topics that are difficult to visualize

Prefer natural human wording such as:
Why does metal feel colder than wood
Why does your voice sound weird in recordings
Why does a cold glass get wet on the outside
Why does ice suddenly crack
Why do cats squeeze into tiny spaces
Why does popcorn suddenly explode

Return ONLY one question, no quotes, no numbering, no explanation.
"""


def _clean_topic(value):
    text = str(value or "").strip()
    text = re.sub(r"```(?:text|json)?", "", text, flags=re.I)
    text = text.replace('"', "").replace("'", "")
    text = re.sub(r"^(topic|next topic|next_short|next short)\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"^\s*\d+[.)\-:]\s*", "", text)
    return " ".join(text.split()).rstrip(".!? ").strip()


def _key(topic):
    return re.sub(r"[^a-z0-9]+", " ", _clean_topic(topic).lower()).strip()


def _load_json(path, fallback):
    if not os.path.exists(path):
        return fallback
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return fallback


def _atomic_write(path, data):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, temp_path = tempfile.mkstemp(prefix=".mint_topic_", suffix=".tmp", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _used():
    data = _load_json(USED_TOPICS_PATH, [])
    return data if isinstance(data, list) else []


def _pending():
    data = _load_json(NEXT_TOPIC_PATH, {})
    if isinstance(data, dict):
        return _clean_topic(data.get("topic"))
    return _clean_topic(data)


def _save_pending(topic):
    topic = _clean_topic(topic)
    if not topic or len(topic) > MAX_TOPIC_CHARACTERS:
        return False
    _atomic_write(NEXT_TOPIC_PATH, {"topic": topic})
    return _pending() == topic


def _similar(topic, used):
    current = set(_key(topic).split())
    if not current:
        return True
    for previous in used:
        other = set(_key(previous).split())
        if not other:
            continue
        overlap = len(current & other) / max(1, len(current | other))
        if overlap >= 0.72:
            return True
    return False


def _generate_new_topic():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is missing.")
    client = genai.Client(api_key=api_key)
    used = _used()
    recent = "\n".join(f"- {x}" for x in used[-80:]) or "(none)"
    prompt = f"""
Generate one highly clickable Wonder Minute Short topic.

Previously used topics:
{recent}

The new topic must be substantially different from those topics.
Maximum {MAX_TOPIC_WORDS} words.
"""
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, temperature=1.0),
    )
    topic = _clean_topic(getattr(response, "text", ""))
    if not topic:
        raise RuntimeError("Gemini returned an empty topic.")
    if len(topic.split()) > MAX_TOPIC_WORDS:
        raise RuntimeError("Generated topic is too long.")
    if _similar(topic, used):
        raise RuntimeError("Generated topic is too similar to a previous topic.")
    return topic


def get_next_topic():
    pending = _pending()
    if pending:
        print(f"🎯 QUEUED TOPIC: {pending}")
        return pending
    for attempt in range(1, 8):
        try:
            topic = _generate_new_topic()
            if _save_pending(topic):
                print(f"📌 NEW TOPIC QUEUED: {topic}")
                return topic
        except Exception as error:
            print(f"⚠️ Topic attempt {attempt}/7 failed: {error}")
    raise RuntimeError("Could not generate a strong entertainment-first topic.")


def save_next_short(next_short):
    topic = _clean_topic(next_short)
    if not topic:
        return False
    return _save_pending(topic)


def commit_topic(topic):
    topic = _clean_topic(topic)
    if not topic:
        raise RuntimeError("Cannot commit an empty topic.")
    used = _used()
    if not any(_key(item) == _key(topic) for item in used):
        used.append(topic)
        _atomic_write(USED_TOPICS_PATH, used[-300:])
    pending = _pending()
    if pending and _key(pending) == _key(topic):
        try:
            os.remove(NEXT_TOPIC_PATH)
        except OSError:
            pass
    return True


def clear_next_topic():
    try:
        os.remove(NEXT_TOPIC_PATH)
    except OSError:
        pass
    return True
