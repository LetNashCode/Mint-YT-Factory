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
