from datetime import datetime, timedelta, timezone

import learning_engine as engine


def _fresh_checked_at():
    """Stable fresh analytics timestamp independent of the calendar date CI runs."""
    return (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()


def _record(score, hook="question", payoff="reveal", tease="open"):
    return {
        "video_id": f"v{score}",
        "topic": "test topic",
        "latest": {"views": int(score * 1000), "average_view_percentage": float(score)},
        "workdir": "",
        "_score": score,
        "script": {
            "hook_type": hook,
            "payoff_type": payoff,
            "tease_type": tease,
        },
    }


def test_discriminative_rank_excludes_pattern_that_is_not_better_than_weak_evidence(monkeypatch):
    monkeypatch.setattr(engine, "_creative_features", lambda record: {
        "hook_type": record["hook"],
        "payoff_type": record["payoff"],
        "tease_type": record["tease"],
    })
    monkeypatch.setattr(engine, "_performance", lambda record: record["_score"])

    winners = [
        {"_score": 80, "hook": "question", "payoff": "reveal", "tease": "open"},
        {"_score": 82, "hook": "question", "payoff": "reveal", "tease": "open"},
    ]
    losers = [
        {"_score": 90, "hook": "question", "payoff": "reveal", "tease": "open"},
        {"_score": 91, "hook": "question", "payoff": "reveal", "tease": "open"},
    ]
    result = engine._discriminative_rank(
        winners,
        losers,
        {"hook_type": "hook_type", "payoff_type": "payoff_type", "tease_type": "tease_type"},
        2,
    )
    assert result == []


def test_discriminative_rank_keeps_pattern_when_winner_evidence_is_stronger(monkeypatch):
    monkeypatch.setattr(engine, "_creative_features", lambda record: {
        "hook_type": record["hook"],
        "payoff_type": record["payoff"],
        "tease_type": record["tease"],
    })
    monkeypatch.setattr(engine, "_performance", lambda record: record["_score"])

    winners = [
        {"_score": 90, "hook": "question", "payoff": "reveal", "tease": "open"},
        {"_score": 92, "hook": "question", "payoff": "reveal", "tease": "open"},
        {"_score": 94, "hook": "question", "payoff": "reveal", "tease": "open"},
    ]
    losers = [
        {"_score": 60, "hook": "question", "payoff": "reveal", "tease": "open"},
        {"_score": 61, "hook": "question", "payoff": "reveal", "tease": "open"},
    ]
    result = engine._discriminative_rank(
        winners,
        losers,
        {"hook_type": "hook_type", "payoff_type": "payoff_type", "tease_type": "tease_type"},
        2,
    )
    assert len(result) == 1
    assert result[0]["score"] == 92
    assert result[0]["sample_size"] == 3
    assert result[0]["weak_score"] == 60.5


def test_discriminative_rank_rejects_pattern_equally_common_in_both_cohorts(monkeypatch):
    monkeypatch.setattr(engine, "_creative_features", lambda record: {
        "hook_type": record["hook"],
        "payoff_type": record["payoff"],
        "tease_type": record["tease"],
    })
    monkeypatch.setattr(engine, "_performance", lambda record: record["_score"])

    winners = [
        {"_score": 90, "hook": "question", "payoff": "reveal", "tease": "open"},
        {"_score": 92, "hook": "question", "payoff": "reveal", "tease": "open"},
    ]
    losers = [
        {"_score": 60, "hook": "question", "payoff": "reveal", "tease": "open"},
        {"_score": 61, "hook": "question", "payoff": "reveal", "tease": "open"},
    ]
    result = engine._discriminative_rank(
        winners,
        losers,
        {"hook_type": "hook_type", "payoff_type": "payoff_type", "tease_type": "tease_type"},
        2,
    )
    assert result == []


def test_build_playbook_does_not_learn_from_overlapping_small_cohorts(monkeypatch):
    monkeypatch.setattr(engine, "_performance", lambda record: record["_score"])
    monkeypatch.setattr(engine, "_creative_features", lambda record: {
        "hook_type": "same_hook",
        "story_format": "same_story",
        "payoff_position": "mid",
        "explanation_position": "mid",
        "script_length": "short",
        "narration_pace": "natural",
        "payoff_type": "reveal",
        "tease_type": "open",
        "creative_strategy": "wild",
    })
    records = [
        {
            "video_id": f"v{score}",
            "topic": f"topic {score}",
            "published_at": "2026-01-01T00:00:00+00:00",
            "_score": score,
            "latest": {
                "views": score * 100,
                "analytics_views": score * 100,
                "average_view_percentage": float(score),
                "checked_at": _fresh_checked_at(),
            },
        }
        for score in (10, 20, 30, 40, 50)
    ]

    playbook = engine.build_playbook(records)

    assert playbook["metrics_available"] is True
    assert playbook["creative_learning_version"] == "v6"
    assert playbook["comparative_learning_ready"] is False
    assert playbook["winning_patterns"] == []
    assert playbook["weak_patterns"] == []
    assert playbook["winning_topics"] == []
    assert playbook["avoid_topics"] == []


def test_new_upload_does_not_enter_learning_cohorts(monkeypatch):
    from datetime import datetime, timezone

    monkeypatch.setattr(engine, "_performance", lambda record: record["_score"])
    monkeypatch.setattr(engine, "_creative_features", lambda record: {
        "hook_type": "same_hook",
        "story_format": "same_story",
        "payoff_position": "mid",
        "explanation_position": "mid",
        "script_length": "short",
        "narration_pace": "natural",
        "payoff_type": "reveal",
        "tease_type": "open",
        "creative_strategy": "wild",
    })
    mature = [
        {
            "video_id": f"mature-{score}",
            "topic": f"mature topic {score}",
            "published_at": "2026-01-01T00:00:00+00:00",
            "_score": score,
            "latest": {
                "views": score * 100,
                "analytics_views": score * 100,
                "average_view_percentage": float(score),
                "checked_at": _fresh_checked_at(),
            },
        }
        for score in (10, 20, 30, 40, 50, 60)
    ]
    mature.append({
        "video_id": "fresh",
        "topic": "fresh upload must not be a loser or winner",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "_score": 10000,
        "latest": {
            "views": 5000,
            "analytics_views": 5000,
            "average_view_percentage": 99.0,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        },
    })

    playbook = engine.build_playbook(mature)

    assert playbook["video_count"] == 7
    assert playbook["learning_sample_size"] == 6
    assert "fresh upload must not be a loser or winner" not in playbook["winning_topics"]
    assert "fresh upload must not be a loser or winner" not in playbook["avoid_topics"]


def test_stale_analytics_snapshots_are_not_used_for_learning(monkeypatch):
    monkeypatch.setattr(engine, "_performance", lambda record: record["_score"])
    monkeypatch.setattr(engine, "_creative_features", lambda record: {
        "hook_type": "same_hook",
        "story_format": "same_story",
        "payoff_position": "mid",
        "explanation_position": "mid",
        "script_length": "short",
        "narration_pace": "natural",
        "payoff_type": "reveal",
        "tease_type": "open",
        "creative_strategy": "wild",
    })
    records = [
        {
            "video_id": f"stale-{score}",
            "topic": f"stale topic {score}",
            "published_at": "2026-01-01T00:00:00+00:00",
            "_score": score,
            "latest": {
                "views": score * 100,
                "analytics_views": score * 100,
                "average_view_percentage": float(score),
                "checked_at": "2026-10-01T00:00:00+00:00",
            },
        }
        for score in (10, 20, 30, 40, 50, 60)
    ]

    playbook = engine.build_playbook(records)

    assert playbook["video_count"] == 6
    assert playbook["learning_sample_size"] == 0
    assert playbook["comparative_learning_ready"] is False
    assert playbook["winning_patterns"] == []
    assert playbook["avoid_topics"] == []
