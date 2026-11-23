import generate_script.entertainment as entertainment


class _FakeModels:
    def __init__(self, failures_before_success):
        self.failures_before_success = failures_before_success
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append(model)
        if len(self.calls) <= self.failures_before_success:
            raise RuntimeError("503 UNAVAILABLE: model is experiencing high demand")
        return type("Response", (), {"text": "{}"})()


class _FakeClient:
    def __init__(self, models):
        self.models = models


def test_publish_script_rotates_models_and_retries_transient_503(monkeypatch):
    models = _FakeModels(failures_before_success=4)
    monkeypatch.setattr(entertainment, "MODEL_CHAIN", ("primary", "fallback", "tertiary"))
    monkeypatch.setattr(entertainment, "MODEL_NAME", "primary")
    monkeypatch.setattr(entertainment, "_api_key", lambda: "test-key")
    monkeypatch.setattr(entertainment.genai, "Client", lambda api_key: _FakeClient(models))
    monkeypatch.setattr(entertainment.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(entertainment, "_normalize", lambda data, topic, enforce_word_contract=False: {"topic": topic})

    result = entertainment.generate_script("Why do cats purr?", {})

    assert result == {"topic": "Why do cats purr?"}
    assert models.calls == ["primary", "fallback", "tertiary", "primary", "fallback"]
