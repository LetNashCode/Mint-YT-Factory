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
    assert output.duration == 53.5 / (57.32 / 53.5)
    # The final output timestamp must map to the end of the original audio.
    mapped_end = float(output.time_map(53.5))
    assert mapped_end >= 57.318
    assert mapped_end <= 57.32


def test_adaptive_speed_does_not_reverse_time_mapping():
    source = FakeClip(57.32)
    output = apply_narration_speed(source, target_duration=53.5)

    assert float(output.time_map(10.0)) > 10.0
    assert np.isfinite(output.time_map(np.array([0.0, 20.0, 53.5]))).all()
