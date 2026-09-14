"""Story-only durable topic de-duplication and reservation layer."""
from __future__ import annotations
import re
import interactive_topics

HISTORY = interactive_topics.HISTORY
PENDING = interactive_topics.PENDING


def _norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _tokens(value):
    return {w for w in _norm(value).split() if len(w) > 2}


def _history_rows():
    try:
        return interactive_topics._load_history()
    except Exception:
        return []


def _used_people(rows):
    return {_norm(row.get("person")) for row in rows if isinstance(row, dict) and row.get("person")}


def _topic_duplicate(person, topic, rows):
    person_key = _norm(person)
    topic_tokens = _tokens(topic)
    for row in rows:
        if not isinstance(row, dict):
            continue
        old_person = _norm(row.get("person"))
        if person_key and old_person and person_key == old_person:
            return True
        old_topic = _tokens(row.get("topic"))
        if topic_tokens and old_topic:
            overlap = len(topic_tokens & old_topic) / max(1, len(topic_tokens | old_topic))
            if overlap >= 0.52:
                return True
    return False


def _reserved():
    pending = interactive_topics.get_pending_story()
    if not isinstance(pending, dict):
        return None
    if str(pending.get("status", "published")).lower() != "reserved":
        return None
    if not pending.get("person") or not pending.get("topic"):
        return None
    rows = _history_rows()
    if _topic_duplicate(pending["person"], pending["topic"], rows):
        return None
    return pending

_original_get_next_topic = interactive_topics.get_next_topic
_original_save_pending = interactive_topics.save_pending_story


def get_next_topic():
    reserved = _reserved()
    if reserved:
        print(f"🔒 STORY TOPIC RESERVATION: retrying reserved topic | {reserved['person']}")
        return reserved["pillar"], reserved["topic"], reserved["person"]

    rows = _history_rows()
    for attempt in range(1, 31):
        fmt, topic, person = _original_get_next_topic()
        if not _topic_duplicate(person, topic, rows):
            interactive_topics._save(PENDING, {
                "pillar": fmt,
                "topic": topic,
                "person": person,
                "number": 0,
                "status": "reserved",
            })
            print(f"🔒 STORY TOPIC RESERVED: {person} | duplicate protection active")
            return fmt, topic, person
        print(f"🚫 STORY TOPIC DUPLICATE REJECTED ({attempt}/30): {person}")
    raise RuntimeError("Story topic generator could not produce a globally unused topic after 30 attempts.")


def release_reservation(pillar=None, topic=None, person=None):
    """Clear a failed script reservation without marking the topic as published/used."""
    pending = interactive_topics.get_pending_story()
    if not isinstance(pending, dict) or str(pending.get("status", "")).lower() != "reserved":
        return False
    if person and _norm(pending.get("person")) != _norm(person):
        return False
    if topic and _norm(pending.get("topic")) != _norm(topic):
        return False
    interactive_topics._save(PENDING, {
        "pillar": pending.get("pillar") or pillar or "",
        "topic": pending.get("topic") or topic or "",
        "person": pending.get("person") or person or "",
        "number": 0,
        "status": "released",
    })
    print(f"↩️ STORY TOPIC RESERVATION RELEASED: {pending.get('person')} | script generation failed")
    return True


def save_pending_story(pillar, topic, person, number):
    interactive_topics._save(PENDING, {
        "pillar": pillar,
        "topic": topic,
        "person": person,
        "number": number,
        "status": "published",
    })


interactive_topics.get_next_topic = get_next_topic
interactive_topics.save_pending_story = save_pending_story
print("🛡️ Story topic runtime: global person/topic de-duplication + durable reservation ENABLED")
