import learning_engine


def test_creative_profiles_have_distinct_visual_and_pacing_dimensions():
    profiles = learning_engine.CREATIVE_PROFILES
    assert len(profiles) >= 6
    assert len({p["hook"] for p in profiles}) >= 6
    assert len({p["story"] for p in profiles}) >= 6
    assert len({p["visual_style"] for p in profiles}) >= 6
    assert len({p["pacing"] for p in profiles}) >= 4


def test_selector_avoids_recently_saturated_profile(monkeypatch):
    monkeypatch.setattr(
        learning_engine,
        "get_playbook",
        lambda: {"video_count": 3, "learning_ready": False},
    )
    saturated = learning_engine.CREATIVE_PROFILES[0]
    monkeypatch.setattr(
        learning_engine,
        "_recent_creative_cooldown",
        lambda: {
            "hook": {saturated["hook"]: 4},
            "story": {saturated["story"]: 4},
            "visual": {saturated["visual_style"]: 4},
            "pacing": {saturated["pacing"]: 4},
        },
    )

    result = learning_engine.select_creative_strategy()
    assert result["profile"] != saturated["id"]
    assert result["visual_style"]
    assert result["pacing"]


def test_topic_visual_anchor_excludes_raw_narration(monkeypatch):
    import stock_search

    anchors = stock_search._anchor_terms(
        "The sponge secretly becomes a tiny ecosystem.",
        "wet kitchen sponge",
        "sits damp beside a sink",
        ["sponge", "sink", "water"],
        "close-up damp sponge beside sink",
    )

    assert "secretly" not in anchors
    assert "ecosystem" not in anchors
    assert "sponge" in anchors
    assert "sink" in anchors
