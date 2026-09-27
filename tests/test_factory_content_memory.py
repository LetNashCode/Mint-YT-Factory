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


def test_emotional_topic_gate_rejects_same_situation_with_different_wording(tmp_path, monkeypatch):
    path = tmp_path / "topic_history.json"
    monkeypatch.setattr(memory, "HISTORY", path)
    memory.claim_emotional_topic(
        "quiet heartbreak",
        "setting the dinner table for two after a breakup",
        "laying out two plates after a breakup",
    )
    try:
        try:
            memory.claim_emotional_topic(
                "nostalgia",
                "still laying out two plates because you were used to eating together",
                "two plates remain at dinner",
            )
        except RuntimeError as exc:
            assert "Emotional situation uniqueness gate rejected" in str(exc)
        else:
            raise AssertionError("semantic emotional duplicate was accepted")
    finally:
        memory.release(
            "quiet heartbreak: setting the dinner table for two after a breakup",
            "emotional",
        )


def test_emotional_topic_gate_allows_different_situation(tmp_path, monkeypatch):
    path = tmp_path / "topic_history.json"
    monkeypatch.setattr(memory, "HISTORY", path)
    memory.claim_emotional_topic(
        "quiet heartbreak",
        "setting the dinner table for two after a breakup",
        "laying out two plates after a breakup",
    )
    memory.claim_emotional_topic(
        "family love",
        "finding an old voicemail from your father while cleaning your childhood room",
        "old voicemail from father in childhood room",
    )
    rows = json.loads(path.read_text())
    assert len(rows) == 2


def test_emotional_topic_history_exposes_structured_premises(tmp_path, monkeypatch):
    path = tmp_path / "topic_history.json"
    monkeypatch.setattr(memory, "HISTORY", path)
    memory.claim_emotional_topic(
        "friendship",
        "walking past the cafe where you used to meet your best friend",
        "old cafe where best friends met",
    )
    history = memory.emotional_topic_history()
    assert history[0]["emotion"] == "friendship"
    assert history[0]["situation"].startswith("walking past the cafe")
    assert history[0]["topic_key"] == "old cafe where best friends met"
