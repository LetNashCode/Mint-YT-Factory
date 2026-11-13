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
    wisdom = (ROOT / ".github/workflows/wisdom-shorts.yml").read_text(encoding="utf-8")
    story = (ROOT / ".github/workflows/story-shorts.yml").read_text(encoding="utf-8")
    for workflow in (publish, wisdom, story):
        assert "secrets.INSTAGRAM_ACCOUNT_ID" in workflow
        assert "secrets.INSTAGRAM_ACCESS_TOKEN" in workflow
        assert "secrets.FACEBOOK_PAGE_ID" in workflow
        assert "secrets.FACEBOOK_PAGE_ACCESS_TOKEN" in workflow
        assert "vars.SOCIAL_PUBLISH_STRICT || 'true'" in workflow
    assert 'python -m py_compile everyday_wisdom_shorts.py social_publish.py youtube_analytics.py' in wisdom



def test_instagram_reel_derivative_matches_meta_audio_and_mp4_container_requirements():
    source = (ROOT / "social_publish.py").read_text(encoding="utf-8")
    assert '"-ar", "48000"' in source
    assert '"-use_editlist", "0"' in source
    assert '"-movflags", "+faststart"' in source
    assert 'int(audio.get("sample_rate") or 0) != 48000' in source
    assert 'retry_delays = (15, 45, 90)' in source
    assert "Strict social publishing failed after {MAX_SOCIAL_ATTEMPTS} attempts" in source


def test_story_pipeline_queues_youtube_upload_before_shared_meta_publisher():
    source = (ROOT / "interactive_main.py").read_text(encoding="utf-8")
    youtube_upload = source.index("result=upload_video(final,title,desc,config")
    queue_save = source.index("_save_social_queue(", youtube_upload)
    social_publish = source.index("publish_social_reels(final,title,desc,config,workdir)", queue_save)
    queue_clear = source.index("_clear_social_queue()", social_publish)
    assert youtube_upload < queue_save < social_publish < queue_clear
    assert '"status": "complete"' in source


def test_story_social_resume_uses_same_meta_publisher_and_keeps_queue_on_failure():
    source = (ROOT / "story_social_resume.py").read_text(encoding="utf-8")
    assert "from social_publish import publish_social_reels" in source
    assert "publish_social_reels(final" in source
    assert "QUEUE.unlink(missing_ok=True)" in source
    assert source.index("if failures:") < source.index("QUEUE.unlink(missing_ok=True)")
