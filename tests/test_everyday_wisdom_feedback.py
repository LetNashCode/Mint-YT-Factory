from datetime import datetime, timedelta, timezone
import json

import everyday_wisdom_shorts as wisdom


def _fresh_checked_at():
    """Keep fixture metrics fresh regardless of when CI executes."""
    return (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()


def test_performance_guidance_uses_only_mature_retention_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    registry = tmp_path / "analytics" / "everyday_wisdom" / "videos.json"
    registry.parent.mkdir(parents=True)
    rows = []
    for index, retention in enumerate((82, 76, 68, 31, 24, 90)):
        rows.append({
            "video_id": f"video-{index}",
            "title": f"Example Short {index}",
            "topic": f"Example topic {index}",
            "published_at": "2026-01-01T00:00:00+00:00" if index < 5 else datetime.now(timezone.utc).isoformat(),
            "latest": {"views": 500 + index, "average_view_percentage": retention, "checked_at": _fresh_checked_at()},
        })
    registry.write_text(json.dumps(rows), encoding="utf-8")

    guidance = wisdom.performance_guidance()

    assert "Stronger retention examples" in guidance
    assert "Example Short 0" in guidance
    assert "Lower-retention examples to learn from" in guidance
    assert "Example Short 4" in guidance
    assert "Example Short 5" not in guidance
    assert "not assume low views alone mean a bad topic" in guidance


def test_performance_guidance_is_empty_until_enough_mature_metrics_exist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    registry = tmp_path / "analytics" / "everyday_wisdom" / "videos.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps([
        {
            "video_id": "one",
            "title": "One Short",
            "topic": "one topic",
            "published_at": "2026-01-01T00:00:00+00:00",
            "latest": {"views": 100, "average_view_percentage": 45, "checked_at": _fresh_checked_at()},
        }
    ]), encoding="utf-8")

    assert wisdom.performance_guidance() == ""



def _valid_story(topic="a fresh grandma saying", topic_key="fresh grandma saying"):
    narration = (
        "Grandma always said to never leave shoes on the table, and there may be "
        "more behind that rule than superstition. In many homes, tables were kept "
        "for food, family, and important work, while shoes carried dirt from the "
        "street and barnyard. Setting them beside a meal could spread grime where "
        "people prepared and shared food. Some families also treated the table as "
        "a place of respect, not storage. The lesson stuck because it was simple: "
        "keep outside mess away from the place everyone gathers."
    )
    return {
        "title": "Why Grandma Said Shoes Never Belong on Tables",
        "topic": topic,
        "topic_key": topic_key,
        "narration": narration,
        "search_queries": ["shoes on kitchen table", "grandmother kitchen table", "muddy shoes by door"],
        "visual_queries": [f"visual beat number {i}" for i in range(16)],
    }


class _FakeResponse:
    def __init__(self, story):
        self.text = json.dumps(story)


class _FakeModels:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def generate_content(self, **kwargs):
        self.prompts.append(kwargs["contents"])
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return _FakeResponse(result)


class _FakeClient:
    def __init__(self, responses):
        self.models = _FakeModels(responses)


def test_generation_prompt_includes_old_history_and_retries_duplicate_with_feedback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    history = [{"topic_key": f"old saying {i}", "topic": f"old saying topic {i}", "title": f"Old title {i}"} for i in range(140)]
    history.append({"topic_key": "break leg phrase origin", "topic": "The origin of break a leg", "title": "Why actors say break a leg"})
    (tmp_path / "everyday_wisdom_topic_history.json").write_text(json.dumps({"topics": history}), encoding="utf-8")

    duplicate = _valid_story("The origin of break a leg", "break leg phrase origin")
    fresh = _valid_story()
    fake = _FakeClient([duplicate, fresh])
    monkeypatch.setattr(wisdom, "client", lambda: fake)
    monkeypatch.setattr(wisdom, "performance_guidance", lambda: "")
    monkeypatch.setattr(wisdom.time, "sleep", lambda _: None)

    result = wisdom.generate_story()

    assert result["topic"] == "a fresh grandma saying"
    assert "old saying topic 0" in fake.models.prompts[0]
    assert "The origin of break a leg" in fake.models.prompts[0]
    assert "rejected as a duplicate" in fake.models.prompts[1]
    assert "different underlying saying" in fake.models.prompts[1]


def test_generation_retries_short_narration_with_targeted_word_count_feedback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "everyday_wisdom_topic_history.json").write_text('{"topics": []}', encoding="utf-8")
    short = _valid_story()
    short["narration"] = "Grandma said never waste food. It mattered."
    good = _valid_story()
    fake = _FakeClient([short, good])
    monkeypatch.setattr(wisdom, "client", lambda: fake)
    monkeypatch.setattr(wisdom, "performance_guidance", lambda: "")
    monkeypatch.setattr(wisdom.time, "sleep", lambda _: None)

    result = wisdom.generate_story()

    assert len(result["narration"].split()) >= wisdom.MIN_NARRATION_WORDS
    assert "previous narration had 7 words" in fake.models.prompts[1]
    assert "Rewrite the narration to 80-95 words" in fake.models.prompts[1]


def test_generation_backs_off_after_transient_gemini_503(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "everyday_wisdom_topic_history.json").write_text('{"topics": []}', encoding="utf-8")
    fake = _FakeClient([RuntimeError("503 UNAVAILABLE: temporary service issue"), _valid_story()])
    sleeps = []
    monkeypatch.setattr(wisdom, "client", lambda: fake)
    monkeypatch.setattr(wisdom, "performance_guidance", lambda: "")
    monkeypatch.setattr(wisdom.time, "sleep", sleeps.append)

    result = wisdom.generate_story()

    assert result["topic"] == "a fresh grandma saying"
    assert sleeps == [2]
