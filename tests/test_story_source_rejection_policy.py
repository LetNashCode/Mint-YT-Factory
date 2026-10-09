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
