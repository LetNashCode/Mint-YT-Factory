"""Runtime guard that prevents Story Shorts from reusing the same person."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / "story_topic_history.json"
PENDING = ROOT / "pending_story.json"


def _name_key(value: str) -> str:
    """Normalize names and remove common honorifics/titles."""
    text = re.sub(r"[^a-z0-9 ]+", " ", str(value or "").lower())
    words = [w for w in text.split() if w not in {
        "mr", "mrs", "ms", "dr", "prof", "sir", "lord", "lady",
        "colonel", "col", "captain", "capt", "general", "president",
        "the", "late",
    }]
    return " ".join(words)


def _person_keys(value: str) -> set[str]:
    key = _name_key(value)
    tokens = key.split()
    keys = {key} if key else set()
    if len(tokens) >= 2:
        keys.add(" ".join(tokens[-2:]))
        keys.add(" ".join(tokens[:2]))
    return keys


def _read_json(path: Path, default):
    import json
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except Exception:
        return default


def install() -> None:
    """Patch topic selection with a durable, alias-tolerant uniqueness guard."""
    import interactive_topics

    original = interactive_topics.get_next_topic
    if getattr(original, "_mint_uniqueness_guard", False):
        return

    def guarded_get_next_topic():
        history = _read_json(HISTORY, [])
        pending = _read_json(PENDING, {})
        used = set()
        for row in history:
            if isinstance(row, dict):
                used.update(_person_keys(row.get("person", "")))
        if isinstance(pending, dict):
            used.update(_person_keys(pending.get("person", "")))

        # Remove known-used candidates before the original scorer can select one.
        candidates = _read_json(interactive_topics.CANDIDATES, [])
        filtered = [
            row for row in candidates
            if isinstance(row, dict)
            and not (_person_keys(row.get("person", "")) & used)
        ]
        interactive_topics._save(interactive_topics.CANDIDATES, filtered)

        result = original()
        person = result[2] if isinstance(result, tuple) and len(result) >= 3 else ""
        if _person_keys(person) & used:
            raise RuntimeError(
                f"Story uniqueness guard blocked previously used person: {person}"
            )
        print(f"🔒 Story uniqueness guard: approved new person — {person}")
        return result

    guarded_get_next_topic._mint_uniqueness_guard = True
    interactive_topics.get_next_topic = guarded_get_next_topic
