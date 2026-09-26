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
    assert "images" not in calls[0]
    content = calls[0]["text"][0]["content"]
    assert len(content) == 4
    assert [block["type"] for block in content[:3]] == ["image", "image", "image"]
    assert all(isinstance(block["image"], Image.Image) for block in content[:3])


def test_qwen_vision_fallback_derives_missing_relevance_from_core_verdict(monkeypatch):
    monkeypatch.setenv("ENABLE_QWEN_VISION_FALLBACK", "1")

    class FakePipe:
        def __call__(self, **kwargs):
            return [{
                "generated_text": '{"person_visible": true, "real_footage": true, '
                                  '"usable": true, "reason": "clear subject", '
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

    assert result["relevance"] == 10
    assert result["relevance_source"] == "derived_from_qwen_core_verdict"


def test_qwen_vision_fallback_retries_incomplete_core_verdict(monkeypatch):
    monkeypatch.setenv("ENABLE_QWEN_VISION_FALLBACK", "1")
    calls = []

    class FakePipe:
        def __call__(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return [{
                    "generated_text": '{"real_footage": true, "usable": true, '
                                      '"relevance": 9, "reason": "clear subject", '
                                      '"usage": "biographical_illustration"}'
                }]
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
    assert len(calls) == 2
    assert "OUTPUT JSON ONLY" in calls[1]["text"][0]["content"][3]["text"]


def test_qwen_vision_fallback_rejects_missing_core_fields_after_retries(monkeypatch):
    class FakePipe:
        def __call__(self, **kwargs):
            return [{
                "generated_text": '{"real_footage": true, "usable": true, '
                                  '"relevance": 9, "reason": "clear subject", '
                                  '"usage": "biographical_illustration"}'
            }]

    qwen._pipeline.cache_clear()
    monkeypatch.setattr(qwen, "_pipeline", lambda: FakePipe())
    with pytest.raises(ValueError, match="after 2 verdict attempts: .*person_visible"):
        qwen.verify(
            "Nelson Mandela",
            {"narration": "Nelson Mandela speaks at an event.", "visuals": []},
            {"title": "Nelson Mandela interview", "description": ""},
            [_frame(), _frame(), _frame()],
        )


def test_qwen_vision_fallback_rejects_missing_core_fields():
    with pytest.raises(ValueError, match="missing fields: reason"):
        qwen._normalize_result({
            "person_visible": True,
            "real_footage": True,
            "usable": True,
            "usage": "biographical_illustration",
        })


def test_qwen_vision_fallback_rejects_missing_frames():
    with pytest.raises(ValueError, match="exactly 3 frames"):
        qwen._images([_frame(), _frame()])


def test_qwen_vision_fallback_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_QWEN_VISION_FALLBACK", raising=False)
    assert qwen.enabled() is False
