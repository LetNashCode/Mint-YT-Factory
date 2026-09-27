import json
import time

import factory_content_memory as memory


def test_factory_topic_memory_rejects_near_duplicate(tmp_path, monkeypatch):
    path = tmp_path / "topic_history.json"
    monkeypatch.setattr(memory, "HISTORY", path)
    memory.claim("publish", "Why do mirrors reverse your reflection?")
    try:
        try:
            memory.claim("emotional", "Why does a mirror reverse your reflection?")
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
    memory.claim("mystery", "The abandoned ship that vanished without a trace")
    rows = json.loads(path.read_text())
    assert len(rows) == 2


def test_factory_topic_memory_expires_stale_reservation(tmp_path, monkeypatch):
    path = tmp_path / "topic_history.json"
    monkeypatch.setattr(memory, "HISTORY", path)
    old = int(time.time()) - memory.RESERVATION_TTL_SECONDS - 10
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([{
        "topic": "Old reserved topic",
        "workflow": "emotional",
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
