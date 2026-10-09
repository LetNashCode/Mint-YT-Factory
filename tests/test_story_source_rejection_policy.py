from story_real_video_media import source_rejection_limit


def test_source_rejection_limit_defaults_to_four(monkeypatch):
    monkeypatch.delenv("STORY_SOURCE_MAX_REJECTIONS", raising=False)
    assert source_rejection_limit() == 4


def test_source_rejection_limit_is_bounded():
    assert source_rejection_limit("2") == 2
    assert source_rejection_limit("3") == 3
    assert source_rejection_limit("4") == 4
    assert source_rejection_limit("20") == 4
    assert source_rejection_limit("invalid") == 4

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

