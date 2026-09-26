"""Regression tests for the Emotional Text Reel assembly manifest."""
import ast
from pathlib import Path


def test_emotional_concat_manifest_uses_real_newlines():
    root = Path(__file__).resolve().parents[1]
    source = (root / "emotional_reel.py").read_text(encoding="utf-8")
    ast.parse(source)

    # The concat demuxer requires one file directive per physical line.
    assert 'manifest.write_text('\\n'.join' in source
    assert 'manifest.write_text('\\\\n'.join' not in source


def test_emotional_concat_manifest_is_absolute_and_terminated():
    root = Path(__file__).resolve().parents[1]
    source = (root / "emotional_reel.py").read_text(encoding="utf-8")
    assert "p.resolve().as_posix()" in source
    assert " + '\\n'" in source



def test_shared_caption_style_matches_publish_shorts_baseline():
    root = Path(__file__).resolve().parents[1]
    source = (root / "assemble.py").read_text(encoding="utf-8")
    config = (root / "config.yaml").read_text(encoding="utf-8")

    # Publish Shorts baseline in config.yaml: 72px, 2px stroke, 0.64 vertical.
    assert "CAPTION_FONT_SIZE = 72" in source
    assert "CAPTION_STROKE_WIDTH = 2" in source
    assert "CAPTION_VERTICAL_POSITION = 0.64" in source
    assert "CAPTION_SIZE_BY_SCENE = (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)" in source
    assert "font_size: 72" in config
    assert "stroke_width: 2" in config
    assert "vertical_position: 0.64" in config


def test_emotional_story_prompt_requires_human_emotion_and_specificity():
    root = Path(__file__).resolve().parents[1]
    source = (root / "emotional_reel.py").read_text(encoding="utf-8")

    assert "primary human emotion" in source
    assert "specific everyday human situation" in source
    assert "HOOK/RECOGNITION" in source
    assert "EMOTIONAL TURN" in source
    assert "LINGERING CLOSE" in source
    assert "SPECIFICITY RULE" in source
    assert "ANTI-CLICHE RULE" in source
    assert "STOCK-VISUAL RULE" in source


def test_emotional_reel_defaults_to_bella_voice():
    root = Path(__file__).resolve().parents[1]
    source = (root / "emotional_reel.py").read_text(encoding="utf-8")

    assert 'EMOTIONAL_REEL_KOKORO_VOICE","af_bella"' in source


def test_emotional_script_requires_story_metadata_before_acceptance():
    root = Path(__file__).resolve().parents[1]
    source = (root / "emotional_reel.py").read_text(encoding="utf-8")

    assert "required_fields=('title','description','hashtags','primary_emotion','human_situation','emotional_turn')" in source
    assert "missing emotional story metadata" in source
