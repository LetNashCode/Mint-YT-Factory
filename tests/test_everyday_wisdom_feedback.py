from datetime import datetime, timezone
import json

import everyday_wisdom_shorts as wisdom


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
            "latest": {"views": 500 + index, "average_view_percentage": retention, "checked_at": "2026-10-18T00:00:00+00:00"},
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
            "latest": {"views": 100, "average_view_percentage": 45, "checked_at": "2026-10-18T00:00:00+00:00"},
        }
    ]), encoding="utf-8")

    assert wisdom.performance_guidance() == ""
