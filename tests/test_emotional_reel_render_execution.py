from pathlib import Path


def test_emotional_reel_audio_mix_is_executable_not_commented():
    source = Path("emotional_reel.py").read_text(encoding="utf-8")

    assert "\\n # separately creates multiple audio streams" not in source
    assert "mix='[1:a]volume=0.12" in source
    assert "run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(captioned_path)" in source
    assert "if not final.exists() or final.stat().st_size < 4096:\n  raise RuntimeError" in source
