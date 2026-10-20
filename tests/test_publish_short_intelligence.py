from publish_short_intelligence import competitor_outlier_brief, score_hook


def test_hook_score_rewards_concrete_curiosity_and_returns_explanations():
    strong = score_hook("Your cold glass suddenly grows water droplets, but the glass isn't leaking. Why?")
    weak = score_hook("Today we're going to talk about the science of condensation.")

    assert strong["score"] > weak["score"]
    assert strong["max_score"] == 10
    assert strong["is_heuristic"] is True
    assert isinstance(weak["reasons"], list)


def test_hook_score_is_advisory_for_empty_input():
    result = score_hook("")

    assert result["score"] == 1.0
    assert result["word_count"] == 0
    assert result["reasons"]


def test_competitor_outliers_require_four_videos_per_channel():
    entries = [
        {"channel": "A", "title": "A1", "views": 100},
        {"channel": "A", "title": "A2", "views": 110},
        {"channel": "A", "title": "A3", "views": 120},
        {"channel": "A", "title": "A4", "views": 900},
        {"channel": "B", "title": "B1", "views": 10},
        {"channel": "B", "title": "B2", "views": 1000},
        {"channel": "B", "title": "B3", "views": 100},
    ]

    result = competitor_outlier_brief(entries, min_channel_videos=4)

    assert [row["title"] for row in result] == ["A4"]
    assert result[0]["outlier_multiple"] > 1.5


def test_competitor_outlier_multiple_uses_channel_median_not_raw_views():
    entries = [
        {"channel": "A", "title": "low", "views": 100},
        {"channel": "A", "title": "normal1", "views": 110},
        {"channel": "A", "title": "normal2", "views": 120},
        {"channel": "A", "title": "outlier", "views": 600},
    ]

    result = competitor_outlier_brief(entries)

    assert result[0]["title"] == "outlier"
    assert result[0]["channel_median_views"] == 115
    assert result[0]["outlier_multiple"] == round(600 / 115, 2)
