from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_publish_shorts_saves_youtube_state_then_publishes_meta():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    state_write = source.index("save_json(publish_state, publish_state_path)")
    social_call = source.index("publish_social_reels(final_video, title, description, config, workdir)")
    next_topic_commit = source.index("queued_topic = save_next_short(next_topic)")
    assert state_write < social_call < next_topic_commit
    assert '"uploaded": True' in source
    assert '"status": "published"' in source


def test_everyday_wisdom_publishes_meta_after_youtube_upload():
    source = (ROOT / "everyday_wisdom_shorts.py").read_text(encoding="utf-8")
    youtube_upload = source.index("video_id = upload(video, story)")
    social_call = source.index("publish_social_reels(str(video), title, description, {}, str(RUN_ROOT))")
    assert youtube_upload < social_call
    assert '"publish_state.json"' in source
    assert '"instagram"' in (ROOT / "social_publish.py").read_text(encoding="utf-8")
    assert '"facebook"' in (ROOT / "social_publish.py").read_text(encoding="utf-8")


def test_both_workflows_pass_meta_credentials_and_default_to_strict():
    publish = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    wisdom = (ROOT / ".github/workflows/everyday-wisdom-shorts.yml").read_text(encoding="utf-8")
    for workflow in (publish, wisdom):
        assert "secrets.INSTAGRAM_ACCOUNT_ID" in workflow
        assert "secrets.INSTAGRAM_ACCESS_TOKEN" in workflow
        assert "secrets.FACEBOOK_PAGE_ID" in workflow
        assert "secrets.FACEBOOK_PAGE_ACCESS_TOKEN" in workflow
        assert "vars.SOCIAL_PUBLISH_STRICT || 'true'" in workflow
    assert 'python -m py_compile everyday_wisdom_shorts.py social_publish.py youtube_analytics.py' in wisdom
