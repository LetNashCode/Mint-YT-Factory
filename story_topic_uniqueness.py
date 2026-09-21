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


def _write_json(path: Path, value) -> None:
    import json
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _history_people() -> set[str]:
    used = set()
    for row in _read_json(HISTORY, []):
        if isinstance(row, dict):
            used.update(_person_keys(row.get("person", "")))
    return used


def _is_used(person: str, used: set[str]) -> bool:
    return bool(_person_keys(person) & used)


def _replacement_from_candidates(used: set[str]):
    """Return the first unused candidate, or None when no candidate is available."""
    candidates_path = ROOT / "story_candidates.json"
    candidates = _read_json(candidates_path, [])
    for item in candidates:
        if not isinstance(item, dict):
            continue
        person = str(item.get("person", "")).strip()
        premise = str(item.get("premise", "")).strip()
        if not person or not premise or _is_used(person, used):
            continue
        return item
    return None


def repair_pending_story() -> None:
    """Replace a stale pending story when its person already exists in history."""
    pending = _read_json(PENDING, {})
    if not isinstance(pending, dict) or not pending:
        return

    used = _history_people()
    pending_person = str(pending.get("person", "")).strip()
    if not pending_person or not _is_used(pending_person, used):
        return

    replacement = _replacement_from_candidates(used)
    if replacement is None:
        raise RuntimeError(
            f"Pending story is a duplicate ({pending_person}), and no unused replacement is available."
        )

    replacement_person = str(replacement["person"]).strip()
    replacement_format = str(
        replacement.get("format") or pending.get("pillar") or "strange_turning_point"
    ).strip().lower()
    replacement_premise = str(replacement.get("premise", "")).strip()
    number = pending.get("number")

    repaired = {
        "pillar": replacement_format,
        "topic": f"{replacement_person}: {replacement_premise}",
        "person": replacement_person,
        "number": number,
    }
    _write_json(PENDING, repaired)

    candidates_path = ROOT / "story_candidates.json"
    candidates = _read_json(candidates_path, [])
    _write_json(
        candidates_path,
        [
            item for item in candidates
            if not isinstance(item, dict)
            or not _person_keys(item.get("person", "")) & _person_keys(replacement_person)
        ],
    )
    print(
        f"🔧 Story uniqueness repair: replaced duplicate pending person "
        f"'{pending_person}' with '{replacement_person}'"
    )


def _remove_person_from_pool(person: str, candidates_path: Path) -> int:
    """Remove every candidate matching a rejected person and return removals."""
    candidates = _read_json(candidates_path, [])
    person_keys = _person_keys(person)
    filtered = [
        item for item in candidates
        if not isinstance(item, dict) or not (_person_keys(item.get("person", "")) & person_keys)
    ]
    removed = len(candidates) - len(filtered)
    if removed:
        _write_json(candidates_path, filtered)
    return removed


def install() -> None:
    """Patch topic selection with a durable, alias-tolerant uniqueness guard."""
    import interactive_topics

    repair_pending_story()

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

        candidates_path = Path(interactive_topics.CANDIDATES)
        max_attempts = 12
        rejected = []

        for attempt in range(1, max_attempts + 1):
            candidates = _read_json(candidates_path, [])
            filtered = [
                row for row in candidates
                if isinstance(row, dict) and not (_person_keys(row.get("person", "")) & used)
            ]
            _write_json(candidates_path, filtered)

            result = original()
            person = result[2] if isinstance(result, tuple) and len(result) >= 3 else ""
            if not (_person_keys(person) & used):
                print(f"🔒 Story uniqueness guard: approved new person — {person}")
                if rejected:
                    print(f"🔁 Story uniqueness guard: skipped duplicates — {', '.join(rejected)}")
                return result

            rejected.append(str(person))
            removed = _remove_person_from_pool(str(person), candidates_path)
            print(
                f"⚠️ Story uniqueness guard: rejected previously used person "
                f"'{person}' (attempt {attempt}/{max_attempts}); removed {removed} candidate(s), retrying"
            )

        raise RuntimeError(
            "Story uniqueness guard could not find an unused person after "
            f"{max_attempts} attempts. Rejected: {', '.join(rejected) or 'none'}"
        )

    guarded_get_next_topic._mint_uniqueness_guard = True
    interactive_topics.get_next_topic = guarded_get_next_topic
