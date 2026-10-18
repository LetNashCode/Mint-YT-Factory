import json

import youtube_analytics as analytics


def test_wisdom_profile_never_recovers_publish_publications(tmp_path, monkeypatch):
    monkeypatch.setattr(analytics, "_PROFILE", "wisdom")
    monkeypatch.setattr(analytics, "ROOT", tmp_path)
    (tmp_path / "completed_publications.json").write_text(
        json.dumps([{"video_id": "publish-only-id", "topic": "Publish topic"}]),
        encoding="utf-8",
    )

    assert analytics._read_durable_publications() == []
