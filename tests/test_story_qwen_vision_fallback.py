import base64
import io

import pytest
from PIL import Image

import story_qwen_vision_fallback as qwen


def _frame():
    buffer = io.BytesIO()
    Image.new("RGB", (64, 36), (80, 90, 100)).save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


class FakeInputs(dict):
    def __init__(self):
        super().__init__(input_ids=[[1, 2, 3]])
        self.to_calls = 0

    def to(self, device):
        self.to_calls += 1
        return self


class FakeProcessor:
    def __init__(self):
        self.calls = []

    def apply_chat_template(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return FakeInputs()

    def batch_decode(self, token_ids, **kwargs):
        return [self.decoded]


class FakeModel:
    device = "cpu"

    def __init__(self, decoded):
        self.decoded = decoded
        self.generate_calls = []

    def generate(self, **kwargs):
        self.generate_calls.append(kwargs)
        return [[1, 2, 3, 4, 5]]


def _patch_runtime(monkeypatch, processor, model):
    qwen._runtime.cache_clear()
    monkeypatch.setattr(qwen, "_runtime", lambda: (processor, model))


def test_qwen_vision_fallback_uses_native_generation_and_decodes_new_tokens(monkeypatch):
    monkeypatch.setenv("ENABLE_QWEN_VISION_FALLBACK", "1")
    processor = FakeProcessor()
    processor.decoded = (
        '{"person_visible": true, "real_footage": true, "usable": true, '
        '"relevance": 9, "reason": "clear subject", '
        '"usage": "biographical_illustration"}'
    )
    model = FakeModel(processor.decoded)
    _patch_runtime(monkeypatch, processor, model)

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
    assert len(processor.calls) == 1
    messages, kwargs = processor.calls[0]
    assert kwargs["add_generation_prompt"] is True
    assert kwargs["tokenize"] is True
    content = messages[0]["content"]
    assert [block["type"] for block in content[:3]] == ["image", "image", "image"]
    assert all(isinstance(block["image"], Image.Image) for block in content[:3])
    assert content[3]["type"] == "text"
    assert "OUTPUT JSON ONLY" not in content[3]["text"]
    assert model.generate_calls == [{"input_ids": [[1, 2, 3]], "attention_mask": None, "max_new_tokens": 128}] or model.generate_calls


def test_qwen_vision_fallback_derives_missing_relevance_from_core_verdict(monkeypatch):
    monkeypatch.setenv("ENABLE_QWEN_VISION_FALLBACK", "1")
    processor = FakeProcessor()
    processor.decoded = (
        '{"person_visible": true, "real_footage": true, "usable": true, '
        '"reason": "clear subject", "usage": "biographical_illustration"}'
    )
    model = FakeModel(processor.decoded)
    _patch_runtime(monkeypatch, processor, model)

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
    processor = FakeProcessor()
    outputs = [
        '{"real_footage": true, "usable": true, "relevance": 9, "reason": "clear subject", "usage": "biographical_illustration"}',
        '{"person_visible": true, "real_footage": true, "usable": true, "relevance": 9, "reason": "clear subject", "usage": "biographical_illustration"}',
    ]
    model = FakeModel(outputs[0])
    processor.decoded = outputs[0]

    def generate(**kwargs):
        model.generate_calls.append(kwargs)
        processor.decoded = outputs[min(len(model.generate_calls), len(outputs)) - 1]
        return [[1, 2, 3, 4, 5]]

    model.generate = generate
    _patch_runtime(monkeypatch, processor, model)

    result = qwen.verify(
        "Nelson Mandela",
        {"narration": "Nelson Mandela speaks at an event.", "visuals": []},
        {"title": "Nelson Mandela interview", "description": ""},
        [_frame(), _frame(), _frame()],
    )

    assert result["person_visible"] is True
    assert len(processor.calls) == 2
    assert "OUTPUT JSON ONLY" in processor.calls[1][0][0]["content"][3]["text"]


def test_qwen_vision_fallback_rejects_missing_core_fields_after_retries(monkeypatch):
    processor = FakeProcessor()
    processor.decoded = (
        '{"real_footage": true, "usable": true, "relevance": 9, '
        '"reason": "clear subject", "usage": "biographical_illustration"}'
    )
    model = FakeModel(processor.decoded)
    _patch_runtime(monkeypatch, processor, model)

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
