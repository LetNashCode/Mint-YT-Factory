from datetime import datetime, timedelta, timezone

from retention_learning import build_retention_guidance, _mature_rows


def _record(index, apv, hours_old=48, views=200):
    now = datetime.now(timezone.utc)
    return {
        "video_id": f"video-{index}",
        "title": f"Example {index}",
        "topic": f"Topic {index}",
        "published_at": (now - timedelta(hours=hours_old)).isoformat(),
        "latest": {
            "views": views,
            "analytics_views": views,
            "average_view_percentage": apv,
            "average_view_duration": 25,
            "checked_at": (now - timedelta(hours=2)).isoformat(),
        },
        "hook_type": "mystery",
        "creative_strategy": "reveal",
    }


def test_retention_guidance_waits_for_enough_mature_data():
    guidance = build_retention_guidance("publish", [_record(1, 81), _record(2, 45)])
    assert "warming up" in guidance
    assert "do not infer winners" in guidance


def test_retention_guidance_compares_high_and_low_retention_cohorts():
    records = [_record(i, apv) for i, apv in enumerate([84, 82, 78, 49, 45, 41])]
    guidance = build_retention_guidance("story", records)
    assert "STORY WORKFLOW ONLY" in guidance
    assert "HIGHER-RETENTION EXAMPLES" in guidance
    assert "LOWER-RETENTION EXAMPLES" in guidance
    assert "Do not copy" in guidance


def test_immature_and_low_view_videos_are_excluded():
    records = [
        _record(1, 85, hours_old=12),
        _record(2, 80, views=10),
        _record(3, 76),
    ]
    assert len(_mature_rows(records)) == 1


def test_workflow_paths_do_not_mix_data():
    records = [_record(i, apv) for i, apv in enumerate([83, 80, 78, 50, 45])]
    guidance = build_retention_guidance("wisdom", records)
    assert "WISDOM WORKFLOW ONLY" in guidance
