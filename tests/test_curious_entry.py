import curious_entry

def test_topic_contract():
    assert "United States" in curious_entry.TOPIC_PROMPT
    assert "India" in curious_entry.TOPIC_PROMPT

def test_script_contract():
    assert "entertaining" in curious_entry.SCRIPT_PROMPT.lower()
    assert "second topic" in curious_entry.SCRIPT_PROMPT.lower()

def test_requires_seven_scenes():
    try:
        curious_entry.validate({"scene_plan":[{"narration":"x"}]*6})
    except RuntimeError as exc:
        assert "7 scenes" in str(exc)
    else:
        raise AssertionError("Expected seven-scene failure")

def test_rejects_future_video_ending():
    scenes=[{"narration":"You have seen this familiar thing forever and probably never stopped to ask why it works this way."}]*6
    scenes.append({"narration":"Follow us in the next video for more."})
    try:
        curious_entry.validate({"scene_plan":scenes})
    except RuntimeError as exc:
        assert "Future-video teaser" in str(exc)
    else:
        raise AssertionError("Expected future-video failure")
