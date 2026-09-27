import learning_engine as engine


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
    assert result[0]["score"] == 91
    assert result[0]["weak_score"] == 60.5
