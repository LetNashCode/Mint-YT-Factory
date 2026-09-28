import json
from types import SimpleNamespace

import mystery_documentary_quality_gate as gate


def _run_silence_check(monkeypatch, tmp_path, scenes, silence_start, silence_end):
    monkeypatch.setattr(gate, "OUT", tmp_path)

    rendered = tmp_path / "rendered_scene_timeline.json"
    rendered.write_text(json.dumps({"scenes": scenes}), encoding="utf-8")

    def fake_run(*args, **kwargs):
        return SimpleNamespace(
            stderr=(
                f"[silencedetect] silence_start: {silence_start}\\n"
                f"[silencedetect] silence_end: {silence_end} |"
            )
        )

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    return gate._check_unexpected_silence(
        tmp_path / "mystery-documentary.mp4",
        rendered,
    )


def test_adjacent_source_audio_scenes_are_treated_as_one_evidence_span(
    monkeypatch, tmp_path
):
    gaps = _run_silence_check(
        monkeypatch,
        tmp_path,
        [
            {"start": 77.263, "end": 80.763, "audio_mode": "original"},
            {"start": 80.796, "end": 84.296, "audio_mode": "original"},
        ],
        77.019,
        84.314,
    )

    assert gaps == []


def test_distant_source_audio_scenes_do_not_hide_a_real_silence_gap(
    monkeypatch, tmp_path
):
    gaps = _run_silence_check(
        monkeypatch,
        tmp_path,
        [
            {"start": 77.263, "end": 80.763, "audio_mode": "original"},
            {"start": 82.500, "end": 86.000, "audio_mode": "original"},
        ],
        77.019,
        86.314,
    )

    assert gaps == [9.295]
