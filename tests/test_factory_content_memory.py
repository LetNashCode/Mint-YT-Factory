import json
import time

import factory_content_memory as memory


def test_factory_topic_memory_rejects_near_duplicate(tmp_path, monkeypatch):
    path = tmp_path / "topic_history.json"
    monkeypatch.setattr(memory, "HISTORY", path)
    memory.claim("publish", "Why do mirrors reverse your reflection?")
    try:
        try:
            memory.claim("story", "Why does a mirror reverse your reflection?")
        except RuntimeError as exc:
            assert "uniqueness gate rejected" in str(exc)
        else:
            raise AssertionError("duplicate topic was accepted")
    finally:
        memory.release("Why do mirrors reverse your reflection?", "publish")


def test_factory_topic_memory_allows_distinct_topic(tmp_path, monkeypatch):
    path = tmp_path / "topic_history.json"
    monkeypatch.setattr(memory, "HISTORY", path)
    memory.claim("story", "How a failed inventor rebuilt his laboratory")
    memory.claim("story", "The abandoned ship that vanished without a trace")
    rows = json.loads(path.read_text())
    assert len(rows) == 2


def test_factory_topic_memory_expires_stale_reservation(tmp_path, monkeypatch):
    path = tmp_path / "topic_history.json"
    monkeypatch.setattr(memory, "HISTORY", path)
    old = int(time.time()) - memory.RESERVATION_TTL_SECONDS - 10
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([{
        "topic": "Old reserved topic",
        "workflow": "story",
        "status": "reserved",
        "reserved_at": old,
    }]))
    memory.claim("story", "Old reserved topic")
    rows = json.loads(path.read_text())
    assert len(rows) == 1
    assert rows[0]["workflow"] == "story"
    assert rows[0]["status"] == "reserved"


def test_factory_topic_memory_publishes_reservation(tmp_path, monkeypatch):
    path = tmp_path / "topic_history.json"
    monkeypatch.setattr(memory, "HISTORY", path)
    memory.claim("mystery", "The case of the vanished expedition")
    memory.publish(
        "The case of the vanished expedition",
        "mystery",
        title="Vanished Expedition",
        video_id="abc123",
    )
    rows = json.loads(path.read_text())
    assert rows[0]["status"] == "published"
    assert rows[0]["video_id"] == "abc123"


def test_factory_topic_memory_reuses_same_workflow_reservation(tmp_path, monkeypatch):
    path = tmp_path / "topic_history.json"
    monkeypatch.setattr(memory, "HISTORY", path)
    first = memory.claim("story", "The inventor who rebuilt after failure")
    second = memory.claim("story", "The inventor who rebuilt after failure")
    assert first == second
    rows = json.loads(path.read_text())
    assert len(rows) == 1


def test_factory_bootstrap_sanitizes_internal_pending_topic_marker(tmp_path, monkeypatch):
    history = tmp_path / "topic_history.json"
    state = tmp_path / "factory_memory_state.json"
    monkeypatch.setattr(memory, "HISTORY", history)
    monkeypatch.setattr(memory, "BOOTSTRAP_STATE", state)
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(json.dumps([
        {
            "topic": "__MINT_PENDING_NEXT_TOPIC__::Why do keys jingle",
            "workflow": "publish_legacy",
            "status": "published",
        },
        {
            "topic": "Why do mirrors reverse your reflection?",
            "workflow": "publish_legacy",
            "status": "published",
        },
    ]))
    # This test targets marker sanitization, not the one-time import of the
    # repository's real legacy histories. Mark bootstrap complete so those
    # unrelated files cannot pollute the isolated temporary history.
    state.write_text(json.dumps({"version": 2, "migrated_topics": 0}))
    memory.claim("publish", "Why do keys jingle")
    rows = json.loads(history.read_text())
    assert all(not str(row["topic"]).startswith("__MINT_PENDING_NEXT_TOPIC__::") for row in rows)
    assert any(row["topic"] == "Why do keys jingle" and row["status"] == "reserved" for row in rows)
    assert json.loads(state.read_text())["version"] == 2
