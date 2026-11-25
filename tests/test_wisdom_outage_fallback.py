import re

import everyday_wisdom_shorts as wisdom


def test_curated_outage_fallback_is_complete_and_tts_compatible(monkeypatch):
    monkeypatch.setattr(wisdom, "is_duplicate_topic", lambda story, history: False)
    story = wisdom.build_outage_fallback_story([])
    words = re.findall(r"\\b[\\w'-]+\\b", story["narration"])

    assert 78 <= len(words) <= 85
    assert re.search(r"\\b(I|I'm|I've|I'd|my|me|we|our|ours)\\b", story["narration"], re.I)
    assert len(story["search_queries"]) == 3
    assert len(story["visual_queries"]) == 16
    assert story["generation_mode"] == "curated_offline_fallback"
    assert story["editorial_scores"]["fallback"] == "curated_offline_story"


def test_curated_outage_fallback_skips_used_topics(monkeypatch):
    calls = []

    def duplicate(story, history):
        calls.append(story["topic_key"])
        return story["topic_key"] != "waiting until everyone is served"

    monkeypatch.setattr(wisdom, "is_duplicate_topic", duplicate)
    story = wisdom.build_outage_fallback_story([])

    assert story["topic_key"] == "knocking before entering"
    assert calls[:2] == [
        "waiting until everyone is served",
        "knocking before entering",
    ]


def test_curated_outage_fallback_refuses_to_reuse_every_topic(monkeypatch):
    monkeypatch.setattr(wisdom, "is_duplicate_topic", lambda story, history: True)

    try:
        wisdom.build_outage_fallback_story([])
    except RuntimeError as exc:
        assert "already used" in str(exc)
    else:
        raise AssertionError("Fallback must refuse duplicate topics")
