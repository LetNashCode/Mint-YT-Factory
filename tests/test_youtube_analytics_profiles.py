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


def test_failed_refresh_does_not_make_stale_summary_look_fresh(tmp_path, monkeypatch):
    analytics_dir = tmp_path / "analytics"
    analytics_dir.mkdir()
    summary_path = analytics_dir / "summary.json"
    old_timestamp = "2026-01-01T00:00:00+00:00"
    summary_path.write_text(
        json.dumps({"generated_at": old_timestamp, "video_count": 1}),
        encoding="utf-8",
    )
    monkeypatch.setattr(analytics, "ANALYTICS_DIR", analytics_dir)
    monkeypatch.setattr(analytics, "REGISTRY_PATH", analytics_dir / "videos.json")
    monkeypatch.setattr(analytics, "SUMMARY_PATH", summary_path)
    monkeypatch.setattr(analytics, "_materialize_records", lambda: [
        {
            "video_id": "existing-video",
            "latest": {"views": 100, "likes": 2, "average_view_percentage": 45},
            "snapshots": [],
        }
    ])

    def unavailable(_video_ids):
        raise RuntimeError("simulated API outage")

    monkeypatch.setattr(analytics, "fetch_video_stats", unavailable)

    summary = analytics.refresh_registry()

    assert summary["generated_at"] == old_timestamp
    assert summary["refresh_status"] == "failed"
    assert summary["refresh_attempted_at"] != old_timestamp
    assert "last successful refresh" in summary["reason"]
