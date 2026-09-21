from story_media_quality_gate import score_candidate, validate_groups


def test_candidate_score_requires_person_and_context():
    score, overlap = score_candidate(
        "Marie Curie",
        "laboratory research",
        {"title": "Marie Curie in laboratory", "description": "Research photograph", "artist": ""},
    )
    assert score >= 2
    assert "laboratory" in overlap or "marie" in overlap


def test_groups_require_unique_sources():
    groups = [{"source_url": f"https://example.test/{i}", "asset_key": str(i)} for i in range(14)]
    validate_groups(groups)


def test_groups_reject_duplicates():
    groups = [{"source_url": "https://example.test/same", "asset_key": str(i)} for i in range(14)]
    try:
        validate_groups(groups)
    except RuntimeError as exc:
        assert "reused" in str(exc)
    else:
        raise AssertionError("duplicate sources should fail")
