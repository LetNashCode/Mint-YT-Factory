"""Factory-wide topic memory, reservation, and learning bridge.

Every content workflow uses this module before generation and after publication.
The shared analytics/topic history is the source of truth across formats.
"""
from __future__ import annotations

import difflib
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / "analytics" / "topic_history.json"
BOOTSTRAP_STATE = ROOT / "analytics" / "factory_memory_state.json"
RESERVATION_TTL_SECONDS = 24 * 60 * 60
DUPLICATE_THRESHOLD = 0.70
MAX_HISTORY_ROWS = 5000

STOPWORDS = {
    "why","how","what","when","where","does","do","did","is","are","the","a","an",
    "your","you","my","in","on","at","to","of","for","with","from","into","and","or",
    "this","that","these","those","about","over","under","can","will","make","makes",
}
ALIASES = {
    "cellphone":"phone","mobile":"phone","mobiles":"phone","screens":"screen",
    "onions":"onion","eyes":"eye","cubes":"cube","mirrors":"mirror",
    "windows":"window","bubbles":"bubble","bags":"bag","earbuds":"earbud",
}


def normalize_topic(value: str) -> str:
    words = re.findall(r"[a-z0-9]+", str(value or "").lower())
    return " ".join(ALIASES.get(word, word) for word in words)


def _tokens(value: str) -> set[str]:
    return {word for word in normalize_topic(value).split() if len(word) > 2 and word not in STOPWORDS}


def similarity(a: str, b: str) -> float:
    na, nb = normalize_topic(a), normalize_topic(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = _tokens(a), _tokens(b)
    jaccard = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    sequence = difflib.SequenceMatcher(None, na, nb).ratio()
    containment = 1.0 if ta and (ta <= tb or tb <= ta) else 0.0
    return max(jaccard, sequence, containment)


def _load() -> list[dict]:
    try:
        value = json.loads(HISTORY.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except Exception:
        return []


def _save(rows: list[dict]) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    tmp = HISTORY.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows[-MAX_HISTORY_ROWS:], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(HISTORY)


def _sanitize_internal_rows(rows: list[dict]) -> list[dict]:
    """Remove internal bookkeeping markers that are not real published topics."""
    clean = []
    removed = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        topic = str(row.get("topic") or "").strip()
        if topic.startswith("__MINT_PENDING_NEXT_TOPIC__::") or topic.startswith("__MINT_ANALYTICS__::"):
            removed += 1
            continue
        clean.append(row)
    if removed:
        print(f"🧹 Factory topic memory: removed {removed} internal bookkeeping topic marker(s)")
    return clean


def _is_internal_topic(topic: str) -> bool:
    value = str(topic or "").strip()
    return value.startswith("__MINT_PENDING_NEXT_TOPIC__::") or value.startswith("__MINT_ANALYTICS__::")


def _bootstrap_legacy(rows: list[dict]) -> list[dict]:
    """Migrate prior workflow-specific histories into the shared memory once."""
    original_count = len(rows)
    rows = _sanitize_internal_rows(rows)
    sanitized_changed = len(rows) != original_count
    try:
        state = json.loads(BOOTSTRAP_STATE.read_text(encoding="utf-8"))
        version = int(state.get("version", 0) or 0)
        if version >= 2:
            if sanitized_changed:
                _save(rows)
            return rows
        if version >= 1:
            rows = _sanitize_internal_rows(rows)
            _save(rows)
            BOOTSTRAP_STATE.parent.mkdir(parents=True, exist_ok=True)
            BOOTSTRAP_STATE.write_text(
                json.dumps({
                    "version": 2,
                    "migrated_topics": int(state.get("migrated_topics", 0) or 0),
                    "completed_at": int(time.time()),
                    "sanitized_internal_markers": True,
                }, indent=2) + "\n",
                encoding="utf-8",
            )
            return rows
    except Exception:
        pass

    legacy_topics: list[tuple[str, str]] = []

    def add_json_topics(path: Path, workflow: str, topic_keys: tuple[str, ...]) -> None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        values = value if isinstance(value, list) else []
        if isinstance(value, dict):
            values = value.get("entries") or value.get("items") or []
        for item in values:
            if isinstance(item, str):
                if not _is_internal_topic(item):
                    legacy_topics.append((workflow, item))
                continue
            if not isinstance(item, dict):
                continue
            for key in topic_keys:
                topic = str(item.get(key) or "").strip()
                if topic and not _is_internal_topic(topic):
                    legacy_topics.append((workflow, topic))
                    break

    add_json_topics(ROOT / "story_topic_history.json", "story_legacy", ("topic",))
    add_json_topics(ROOT / "used_topics.json", "publish_legacy", ("topic",))
    add_json_topics(ROOT / "analytics" / "videos.json", "analytics_legacy", ("topic", "title"))

    existing = _sanitize_internal_rows(list(rows))
    added = 0
    for workflow, topic in legacy_topics:
        clean = " ".join(str(topic).split()).strip()
        if not clean or _is_internal_topic(clean) or duplicate(clean, existing):
            continue
        now = int(time.time())
        existing.append({
            "topic": clean,
            "normalized": normalize_topic(clean),
            "workflow": workflow,
            "status": "published",
            "recorded_at": now,
            "metadata": {"source": "legacy_bootstrap_v1"},
        })
        added += 1

    existing = _sanitize_internal_rows(existing)
    _save(existing)
    BOOTSTRAP_STATE.parent.mkdir(parents=True, exist_ok=True)
    BOOTSTRAP_STATE.write_text(
        json.dumps({"version": 2, "migrated_topics": added, "completed_at": int(time.time()), "sanitized_internal_markers": True}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"🧬 Factory topic memory bootstrap: migrated {added} legacy topics")
    return existing


def _purge_stale(rows: list[dict]) -> list[dict]:
    now = int(time.time())
    fresh = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("status", "published")).lower() == "reserved":
            age = now - int(row.get("reserved_at", row.get("recorded_at", now)) or now)
            if age > RESERVATION_TTL_SECONDS:
                print(f"🧹 Factory topic memory: expired stale reservation | {row.get('topic','')}")
                continue
        fresh.append(row)
    return fresh


def _all_topics(rows: list[dict]) -> list[str]:
    return [str(row.get("topic", "")).strip() for row in rows if isinstance(row, dict) and row.get("topic")]


def duplicate(topic: str, rows: list[dict] | None = None) -> dict | None:
    clean = " ".join(str(topic or "").split()).strip()
    if not clean:
        return {"topic": "", "score": 1.0, "reason": "empty_topic"}
    rows = _purge_stale(rows if rows is not None else _load())
    for old in _all_topics(rows):
        score = similarity(clean, old)
        if score >= DUPLICATE_THRESHOLD:
            return {"topic": old, "score": round(score, 3), "reason": "near_duplicate"}
    return None


def claim(workflow: str, topic: str, metadata: dict | None = None) -> str:
    """Reserve a topic before expensive generation. Raises on global duplicates."""
    clean = " ".join(str(topic or "").split()).strip()
    if not clean:
        raise RuntimeError(f"{workflow}: cannot reserve an empty topic")
    rows = _bootstrap_legacy(_purge_stale(_load()))
    rows = _sanitize_internal_rows(rows)
    normalized = normalize_topic(clean)
    for row in rows:
        if (
            isinstance(row, dict)
            and str(row.get("status", "")).lower() == "reserved"
            and normalize_topic(row.get("topic", "")) == normalized
            and str(row.get("workflow", "")) == str(workflow)
        ):
            print(f"🔁 FACTORY TOPIC RESERVATION REUSED | workflow={workflow} | topic={clean}")
            return clean

    existing = duplicate(clean, rows)
    if existing:
        raise RuntimeError(
            f"Factory topic uniqueness gate rejected {workflow} topic: "
            f"{clean!r} duplicates {existing['topic']!r} "
            f"(similarity={existing['score']:.3f})"
        )
    now = int(time.time())
    rows.append({
        "topic": clean,
        "normalized": normalize_topic(clean),
        "workflow": str(workflow),
        "status": "reserved",
        "reserved_at": now,
        "recorded_at": now,
        "metadata": metadata if isinstance(metadata, dict) else {},
    })
    rows = _sanitize_internal_rows(rows)
    _save(rows)
    print(f"🔐 FACTORY TOPIC RESERVED | workflow={workflow} | topic={clean}")
    return clean


def release(topic: str, workflow: str = "") -> bool:
    clean = " ".join(str(topic or "").split()).strip()
    rows = _purge_stale(_load())
    before = len(rows)
    rows = [
        row for row in rows
        if not (
            isinstance(row, dict)
            and str(row.get("status", "")).lower() == "reserved"
            and normalize_topic(row.get("topic", "")) == normalize_topic(clean)
            and (not workflow or str(row.get("workflow", "")) == workflow)
        )
    ]
    if len(rows) != before:
        _save(rows)
        print(f"↩️ FACTORY TOPIC RELEASED | workflow={workflow or 'unknown'} | topic={clean}")
        return True
    return False


def publish(topic: str, workflow: str, title: str = "", video_id: str = "",
            workdir: str = "", metadata: dict | None = None) -> bool:
    """Convert a reservation into a durable published learning record."""
    clean = " ".join(str(topic or "").split()).strip()
    if not clean:
        return False
    rows = _purge_stale(_load())
    now = int(time.time())
    found = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        if normalize_topic(row.get("topic", "")) == normalize_topic(clean):
            if str(row.get("status", "")).lower() == "published":
                found = True
                break
            row.update({
                "status": "published",
                "workflow": str(workflow),
                "title": str(title or ""),
                "video_id": str(video_id or ""),
                "workdir": str(workdir or ""),
                "published_at": now,
                "metadata": metadata if isinstance(metadata, dict) else row.get("metadata", {}),
            })
            found = True
            break
    if not found:
        rows.append({
            "topic": clean,
            "normalized": normalize_topic(clean),
            "workflow": str(workflow),
            "status": "published",
            "title": str(title or ""),
            "video_id": str(video_id or ""),
            "workdir": str(workdir or ""),
            "published_at": now,
            "metadata": metadata if isinstance(metadata, dict) else {},
        })
    _save(rows)
    print(f"📚 FACTORY LEARNING MEMORY: publication recorded | workflow={workflow} | topic={clean}")
    return True


def is_reserved_or_used(topic: str) -> bool:
    return duplicate(topic) is not None


def refresh_learning() -> dict:
    """Refresh the shared YouTube analytics + creative playbook."""
    try:
        from youtube_analytics import refresh_registry
        summary = refresh_registry()
    except Exception as exc:
        print(f"⚠️ Factory learning analytics refresh unavailable: {type(exc).__name__}: {exc}")
        summary = {}
    try:
        from learning_engine import refresh_playbook
        playbook = refresh_playbook()
    except Exception as exc:
        print(f"⚠️ Factory learning playbook refresh unavailable: {type(exc).__name__}: {exc}")
        playbook = {}
    return {"analytics": summary, "playbook": playbook}


def learning_context(max_chars: int = 6000) -> str:
    try:
        from learning_context import load_learning_context
        return load_learning_context(max_chars=max_chars)
    except Exception:
        return "No shared learning context is available yet. Prefer originality and measurable experiments."


def select_strategy() -> dict:
    try:
        from learning_engine import select_creative_strategy
        return select_creative_strategy()
    except Exception:
        return {
            "strategy": "wild",
            "experiment_id": "factory_fallback",
            "selected_pattern": "",
            "guidance": "Try a genuinely new creative approach.",
        }
