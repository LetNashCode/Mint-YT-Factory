from story_youtube_metadata import build_story_metadata


def test_story_metadata_is_topic_specific():
    title, description, tags = build_story_metadata(
        {
            "story_person": "Tenzing Norgay",
            "topic": "Tenzing Norgay and the climb that changed mountaineering",
            "interactive_pillar": "impossible_odds",
            "engagement": {"comment": "Would you have kept climbing?"},
        }
    )

    assert title
    assert "Tenzing" in title
    assert "Tenzing Norgay" in description
    assert "Would you have kept climbing?" in description
    assert "tenzing norgay" in tags
    assert "story shorts" in tags
    assert all("#" not in tag for tag in tags)
    assert sum(len(tag) for tag in tags) + max(0, len(tags) - 1) <= 450


def test_story_metadata_does_not_use_publish_branding():
    _, description, tags = build_story_metadata(
        {
            "story_person": "Alexander Fleming",
            "topic": "Alexander Fleming's accidental discovery",
        }
    )

    combined = (description + " " + " ".join(tags)).lower()
    assert "wonder minute" not in combined
