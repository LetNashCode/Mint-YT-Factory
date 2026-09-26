import base64
import io

import pytest
from PIL import Image

import story_qwen_vision_fallback as qwen


def _frame():
    buffer = io.BytesIO()
    Image.new("RGB", (64, 36), (80, 90, 100)).save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


def test_qwen_vision_fallback_parses_pipeline_json(monkeypatch):
    monkeypatch.setenv("ENABLE_QWEN_VISION_FALLBACK", "1")
    calls = []

    class FakePipe:
        def __call__(self, **kwargs):
            calls.append(kwargs)
            return [{
                "generated_text": '{"person_visible": true, "real_footage": true, '
                                  '"usable": true, "relevance": 9, "reason": "clear subject", '
                                  '"usage": "biographical_illustration"}'
            }]

    qwen._pipeline.cache_clear()
    monkeypatch.setattr(qwen, "_pipeline", lambda: FakePipe())
    result = qwen.verify(
        "Nelson Mandela",
        {"narration": "Nelson Mandela speaks at an event.", "visuals": []},
        {"title": "Nelson Mandela interview", "description": ""},
        [_frame(), _frame(), _frame()],
    )

    assert result["person_visible"] is True
    assert result["real_footage"] is True
    assert result["usable"] is True
    assert result["relevance"] == 9
    assert len(calls) == 1
    assert len(calls[0]["images"]) == 3
    assert len(calls[0]["text"][0]["content"]) == 4


def test_qwen_vision_fallback_rejects_missing_frames():
    with pytest.raises(ValueError, match="exactly 3 frames"):
        qwen._images([_frame(), _frame()])


def test_qwen_vision_fallback_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_QWEN_VISION_FALLBACK", raising=False)
    assert qwen.enabled() is False
