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
                f"[silencedetect] silence_start: {silence_start}\n"
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


def test_mystery_captions_group_words_in_fives():
    import mystery_documentary_captions as captions
    words = [{"text": f"word{i}", "start": float(i), "end": float(i) + 0.8} for i in range(7)]
    groups = captions.group_words(words, 5)
    assert [len(group) for group in groups] == [5, 2]


def test_mystery_captions_highlight_current_word_only():
    import mystery_documentary_captions as captions
    group = [{"text": word, "start": i * 0.5, "end": i * 0.5 + 0.4}
             for i, word in enumerate(["the", "camera", "moves", "toward", "him"])]
    text = captions.styled_group(group, 2)
    assert "\\fs62" in text
    assert captions.YELLOW in text
    assert "\\fs50" in text
    assert captions.WHITE in text


def test_mystery_source_key_ignores_tracking_query():
    import mystery_documentary_runner as runner
    assert runner._source_key("https://archive.org/details/example?utm_source=test#section") == "https://archive.org/details/example"
