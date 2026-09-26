import pytest

from generate_script import entertainment


class FakeGeminiClient:
    def __init__(self, error):
        self.error = error
        self.calls = 0
        self.models = self

    def generate_content(self, **kwargs):
        self.calls += 1
        raise self.error


def test_qwen_fallback_activates_immediately_on_gemini_quota(monkeypatch):
    client = FakeGeminiClient(RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded"))
    monkeypatch.setattr(entertainment.genai, "Client", lambda **kwargs: client)
    monkeypatch.setattr(entertainment, "_api_key", lambda: "test-key")
    monkeypatch.setattr(entertainment, "ENABLE_CPU_QWEN_FALLBACK", True)

    expected = {"scene_plan": [{"scene": 1}]}
    calls = []

    def qwen(prompt, topic, last_error=None):
        calls.append((topic, last_error))
        return expected

    monkeypatch.setattr(entertainment, "_generate_with_qwen", qwen)

    result = entertainment.generate_script("Why ice floats", {})

    assert result is expected
    assert client.calls == 1
    assert len(calls) == 1
    assert "quota" in calls[0][1].lower()


def test_qwen_fallback_does_not_mask_validation_errors(monkeypatch):
    client = FakeGeminiClient(RuntimeError("invalid structured output"))
    monkeypatch.setattr(entertainment.genai, "Client", lambda **kwargs: client)
    monkeypatch.setattr(entertainment, "_api_key", lambda: "test-key")
    monkeypatch.setattr(entertainment, "ENABLE_CPU_QWEN_FALLBACK", True)

    qwen_calls = []

    def qwen(*args, **kwargs):
        qwen_calls.append(1)
        return {"unexpected": True}

    monkeypatch.setattr(entertainment, "_generate_with_qwen", qwen)

    with pytest.raises(RuntimeError, match="SCRIPT GENERATION FAILED"):
        entertainment.generate_script("Why ice floats", {})

    assert client.calls == entertainment.MAX_ATTEMPTS
    assert qwen_calls == []
