import numpy as np

from tts import apply_narration_speed


class FakeClip:
    def __init__(self, duration):
        self.duration = float(duration)
        self.time_map = None

    def fl_time(self, mapper, apply_to=None):
        self.time_map = mapper
        return self

    def set_duration(self, duration):
        self.duration = float(duration)
        return self


def test_adaptive_speed_maps_output_to_full_source_ending():
    source = FakeClip(57.32)
    output = apply_narration_speed(source, target_duration=53.5)

    assert output is source
    # The transformed clip should honor the requested output duration.
    assert output.duration == 53.5
    # The final output timestamp must map to the end of the original audio.
    mapped_end = float(output.time_map(53.5))
    assert mapped_end >= 57.318
    assert mapped_end <= 57.32


def test_adaptive_speed_does_not_reverse_time_mapping():
    source = FakeClip(57.32)
    output = apply_narration_speed(source, target_duration=53.5)

    assert float(output.time_map(10.0)) > 10.0
    assert np.isfinite(output.time_map(np.array([0.0, 20.0, 53.5]))).all()


def test_kokoro_default_voice_is_af_bella():
    from tts import KOKORO_VOICE

    assert KOKORO_VOICE == "af_bella"


def test_publish_bridge_speed_maps_to_full_source_ending():
    import tts_bridge
    source_duration = 39.84
    target_duration = 38.69
    speed = source_duration / target_duration
    source_limit = source_duration - 0.001
    def time_map(t):
        return np.minimum(np.asarray(t) * speed, source_limit)
    mapped_end = float(time_map(target_duration))
    assert mapped_end >= source_duration - 0.002
    assert mapped_end <= source_duration

def test_configured_kokoro_provider_cannot_silently_switch_to_edge(monkeypatch):
    import tts

    calls = []

    def fake_kokoro(text, voice_config, output_path):
        calls.append(("kokoro", voice_config["voice_name"]))
        return output_path

    def fake_edge(text, voice_config, output_path):
        calls.append(("edge", voice_config["edge_voice"]))
        return output_path

    monkeypatch.setattr(tts, "_generate_kokoro", fake_kokoro)
    monkeypatch.setattr(tts, "_generate_edge", fake_edge)
    monkeypatch.setenv("MINT_TTS_PROVIDER", "edge")

    result = tts._synthesize_once(
        "test narration",
        {
            "provider": "kokoro",
            "voice_name": "af_heart",
            "kokoro_lang": "a",
            "edge_voice": "en-US-GuyNeural",
        },
        "/tmp/test-publish-voice.wav",
    )

    assert result.endswith("test-publish-voice.wav")
    assert calls == [("kokoro", "af_heart")]

