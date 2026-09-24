import emotional_reel


def test_emotional_reel_uses_single_mixed_audio_stream():
    source = open("emotional_reel.py", "r", encoding="utf-8").read()

    assert "[m][n]amix=inputs=2" in source
    assert "[mixout]" in source
    assert "'-map','[mixout]'" in source
    assert "'-map','[m]'" not in source
    assert "'-map','[n]'" not in source
