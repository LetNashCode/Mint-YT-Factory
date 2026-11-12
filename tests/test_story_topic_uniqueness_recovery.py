import json

import story_topic_uniqueness
import story_topic_runtime
import interactive_topics


def test_duplicate_pending_without_candidate_is_cleared(tmp_path, monkeypatch):
    history = tmp_path / "story_topic_history.json"
    pending = tmp_path / "pending_story.json"
    candidates = tmp_path / "story_candidates.json"

    history.write_text(
        json.dumps([{"person": "A.P.J. Abdul Kalam", "topic": "Journey to space"}]),
        encoding="utf-8",
    )
    pending.write_text(
        json.dumps({
            "pillar": "one_decision",
            "topic": "A.P.J. Abdul Kalam: a journey",
            "person": "A.P.J. Abdul Kalam",
            "number": 18,
            "status": "reserved",
        }),
        encoding="utf-8",
    )
    candidates.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(story_topic_uniqueness, "ROOT", tmp_path)
    monkeypatch.setattr(story_topic_uniqueness, "HISTORY", history)
    monkeypatch.setattr(story_topic_uniqueness, "PENDING", pending)

    story_topic_uniqueness.repair_pending_story()

    assert json.loads(pending.read_text(encoding="utf-8")) == {}
    # Published history and the candidate pool are left untouched.
    assert len(json.loads(history.read_text(encoding="utf-8"))) == 1
    assert json.loads(candidates.read_text(encoding="utf-8")) == []



def test_stale_reserved_alias_is_cleared_before_topic_retry(tmp_path, monkeypatch):
    history = tmp_path / "story_topic_history.json"
    pending = tmp_path / "pending_story.json"
    history.write_text(
        json.dumps([{"person": "A.P.J. Abdul Kalam", "topic": "India's space journey"}]),
        encoding="utf-8",
    )
    pending.write_text(
        json.dumps({
            "pillar": "one_decision",
            "topic": "APJ Abdul Kalam: one defining decision",
            "person": "APJ Abdul Kalam",
            "number": 19,
            "status": "reserved",
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(interactive_topics, "PENDING", pending)
    monkeypatch.setattr(interactive_topics, "get_pending_story", lambda: json.loads(pending.read_text(encoding="utf-8")))
    monkeypatch.setattr(interactive_topics, "_load_history", lambda: json.loads(history.read_text(encoding="utf-8")))
    monkeypatch.setattr(
        interactive_topics,
        "_save",
        lambda path, value: path.write_text(json.dumps(value), encoding="utf-8"),
    )
    monkeypatch.setattr(story_topic_runtime, "PENDING", pending)

    assert story_topic_runtime._reserved() is None
    assert json.loads(pending.read_text(encoding="utf-8")) == {}
