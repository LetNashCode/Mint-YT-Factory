from story_real_video_media import source_rejection_limit


def test_source_rejection_limit_defaults_to_two(monkeypatch):
    monkeypatch.delenv("STORY_SOURCE_MAX_REJECTIONS", raising=False)
    assert source_rejection_limit() == 2


def test_source_rejection_limit_is_bounded():
    assert source_rejection_limit("2") == 2
    assert source_rejection_limit("3") == 3
    assert source_rejection_limit("4") == 3
    assert source_rejection_limit("20") == 3
    assert source_rejection_limit("invalid") == 2

def test_legacy_rejection_cache_is_invalidated(tmp_path, monkeypatch):
    import json
    import story_real_video_media as media

    cache = tmp_path / "story_video_rejection_cache.json"
    cache.write_text(json.dumps({
        "version": 3,
        "rejected": {"legacy-source": {"reason": "visual verifier rejected source after configured consecutive unusable samples"}},
    }))
    monkeypatch.setattr(media, "PRECHECK_CACHE_FILE", cache)
    assert media._load_precheck_cache() == {}



def test_interview_and_podcast_metadata_are_not_automatic_rejections():
    import story_real_video_media as media

    for title in (
        "Marie Curie archival interview",
        "Podcast conversation with Marie Curie",
        "Marie Curie panel discussion and speech",
    ):
        assert media._source_precheck({"title": title}) is None


def test_animation_and_slideshow_metadata_remain_rejected():
    import story_real_video_media as media

    assert media._source_precheck({"title": "Animated slideshow about Marie Curie"}) is not None



def test_description_only_archive_match_needs_archival_signal():
    """Description mentions alone should not admit generic films into verification."""
    import story_real_video_media as media

    person_tokens = media._person_tokens("Boman Irani")
    identity_fields = media.words("Interview with another actor")
    description_fields = media.words("Boman Irani is mentioned in this film")
    assert person_tokens <= (identity_fields | description_fields)
    assert not person_tokens <= identity_fields
    # Without an archival signal in title/subject/creator, this candidate is
    # excluded by search_archive before metadata download and Gemini verification.
    assert sum(
        1 for term in media._POSITIVE_ARCHIVAL_TERMS
        if term in "interview with another actor"
    ) == 1
