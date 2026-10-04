import topics


def test_topic_candidate_score_exposes_pre_script_signals(monkeypatch):
    monkeypatch.setattr(topics, "published_topics", lambda: [])
    monkeypatch.setattr(
        topics,
        "_topic_similarity_score",
        lambda a, b: 0.0,
    )

    result = topics._topic_candidate_score(
        "Why does ketchup resist pouring",
        [],
    )

    assert result["topic"] == "Why does ketchup resist pouring"
    assert 0 <= result["score"] <= 100
    assert result["curiosity"] > 0
    assert result["familiarity"] > 0
    assert result["visual_feasibility"] > 0
    assert result["novelty"] == 10


def test_generate_topic_selects_highest_ranked_candidate(monkeypatch):
    monkeypatch.setattr(
        topics,
        "_generate_topic_candidates",
        lambda used, exclude_topics=None, target_count=20: [
            "Why does the ceiling fan wobble",
            "Why do shoelaces come undone",
        ],
    )
    monkeypatch.setattr(topics, "_candidate_is_new", lambda *args, **kwargs: True)

    def fake_score(candidate, used):
        scores = {
            "Why does the ceiling fan wobble": {
                "topic": "Why does the ceiling fan wobble",
                "score": 61.0,
            },
            "Why do shoelaces come undone": {
                "topic": "Why do shoelaces come undone",
                "score": 91.0,
            },
        }
        return scores[candidate]

    monkeypatch.setattr(topics, "_topic_candidate_score", fake_score)

    assert topics._generate_topic([]) == "Why do shoelaces come undone"


def test_generate_topic_falls_back_when_batch_has_no_valid_candidates(monkeypatch):
    monkeypatch.setattr(
        topics,
        "_generate_topic_candidates",
        lambda used, exclude_topics=None, target_count=20: [],
    )
    monkeypatch.setattr(
        topics,
        "_deterministic_fallback",
        lambda used, exclude_topics=None: "Why does toast pop up",
    )

    assert topics._generate_topic([]) == "Why does toast pop up"
