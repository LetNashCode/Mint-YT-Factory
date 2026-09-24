import json
from pathlib import Path

import whisper_align


def test_load_expected_words_supports_emotional_reel_scenes(tmp_path):
    audio = tmp_path / "narration.mp3"
    audio.write_bytes(b"placeholder")
    script = {
        "title": "Test",
        "scenes": [
            {"narration": "First emotional thought."},
            {"narration": "Then the story continues."},
        ],
    }
    (tmp_path / "script.json").write_text(json.dumps(script), encoding="utf-8")

    words = whisper_align._load_expected_words(str(audio))

    assert words == [
        "First",
        "emotional",
        "thought",
        "Then",
        "the",
        "story",
        "continues",
    ]
