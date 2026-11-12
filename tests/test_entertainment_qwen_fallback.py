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



def test_script_generator_switches_to_supported_model_on_model_404(monkeypatch):
    class ModelFallbackClient:
        def __init__(self):
            self.calls = []
            self.models = self

        def generate_content(self, **kwargs):
            self.calls.append(kwargs["model"])
            if len(self.calls) == 1:
                raise RuntimeError(
                    "404 NOT_FOUND: model is not found for API version v1"
                )
            return type("Response", (), {"text": "{}"})()

    client = ModelFallbackClient()
    monkeypatch.setattr(entertainment.genai, "Client", lambda **kwargs: client)
    monkeypatch.setattr(entertainment, "_api_key", lambda: "test-key")
    monkeypatch.setattr(entertainment, "_parse", lambda value: {})
    monkeypatch.setattr(entertainment, "_normalize", lambda data, topic, **kwargs: {"ok": True})
    monkeypatch.setattr(entertainment.time, "sleep", lambda *_: None)
    monkeypatch.setattr(entertainment, "MODEL_NAME", "gemini-3.5-flash-lite")
    monkeypatch.setattr(entertainment, "SECONDARY_MODEL_NAME", "gemini-3.8-flash")

    result = entertainment.generate_script("Why ice floats", {})

    assert result == {"ok": True}
    assert client.calls == ["gemini-3.5-flash-lite", "gemini-3.8-flash"]
