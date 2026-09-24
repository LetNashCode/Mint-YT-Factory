from pathlib import Path


def test_emotional_reel_has_deterministic_script_recovery():
    source = Path("emotional_reel.py").read_text(encoding="utf-8")

    assert "deterministic last-resort compactor" in source
    assert "raw_words=raw_words[:15]" in source
    assert "fallback_words" in source
    assert "Could not generate a valid Emotional Reel narration after bounded retries, Gemini compaction, and deterministic fallback" in source
    assert "Compact narration rewrite accepted" in source
