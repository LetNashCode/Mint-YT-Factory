"""Compatibility wrapper for the existing topics.py engine.

The original topics.py remains the source of truth for validation and
persistence. This package strengthens continuation-topic generation and
adds durable continuation state for GitHub Actions.

GitHub-hosted runners are ephemeral. The workflow currently commits
used_topics.json after a successful publish, but next_topic.json is only a
local runner file. That meant Scene 7 could tease topic B while the next
scheduled run generated a different topic C.

We therefore persist the pending continuation topic inside used_topics.json
using a private marker. The existing workflow already commits that file.
The marker is consumed at the beginning of the next run, so the exact topic
teased by the previous Short becomes the next video's CURRENT TOPIC.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


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
        print(f"⚠️ Could not read used_topics.json for continuation state: {error}")
        return []


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
    topic = str(topic or "").strip()
    if not topic:
        return False

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
    """Return the exact topic teased by the previous successful Short."""

    pending = _consume_persisted_pending_topic()

    if pending:
        # Validate exactly as the original pending-topic path does, but do not
        # let historical duplicate protection reject the already-teased topic.
        if not _original.validate_topic_for_pipeline(
            pending,
            check_duplicate=False,
        ):
            raise RuntimeError(
                "Persisted continuation topic is invalid: "
                f"{pending}"
            )

        return pending

    return _original.get_next_topic()


def save_next_short(next_short):
    """Persist the generated next Short locally and durably across runs."""

    saved = _original.save_next_short(next_short)

    if not saved:
        return False

    _persist_pending_topic(next_short)
    return True


# Export the complete original API first, then keep the wrappers above as the
# public implementations for the three state-sensitive functions.
for _name, _value in vars(_original).items():
    if _name.startswith("__"):
        continue
    if _name in {"get_next_topic", "save_next_short"}:
        continue
    globals()[_name] = _value

# Re-bind the wrappers after exporting the original module namespace.
globals()["get_next_topic"] = get_next_topic
globals()["save_next_short"] = save_next_short
