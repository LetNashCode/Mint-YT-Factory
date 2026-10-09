from pathlib import Path

import pytest


def _script(count, **metadata):
    return {
        **metadata,
        "topic": "Why do loose hairs stick to sweaters",
        "scene_plan": [{"narration": f"Scene {i}."} for i in range(1, count + 1)],
    }


def test_publish_sfx_accepts_six_active_scenes(monkeypatch, tmp_path):
    import sfx

    monkeypatch.setattr(sfx, "ensure_sfx_assets", lambda: {})
    monkeypatch.setattr(sfx, "_write_wav", lambda path, samples: Path(path).write_bytes(b"wav"))
    script = _script(6)

    paths = sfx.generate_sfx(script, str(tmp_path))

    assert len(paths) == 6
    assert len(script["sfx_plan"]) == 6
    assert all(cue["enabled"] for cue in script["sfx_plan"])
    assert script["sfx_plan"][-1]["category"] != "none"


def test_story_sfx_keeps_seventh_scene_silent(monkeypatch, tmp_path):
    import sfx

    monkeypatch.setattr(sfx, "ensure_sfx_assets", lambda: {})
    monkeypatch.setattr(sfx, "_write_wav", lambda path, samples: Path(path).write_bytes(b"wav"))
    script = _script(7, story_person="Test Person")

    paths = sfx.generate_sfx(script, str(tmp_path))

    assert len(paths) == 7
    assert script["sfx_plan"][-1]["enabled"] is False
    assert script["sfx_plan"][-1]["category"] == "none"
    assert paths[-1].endswith("scene_7_continuation_silent.wav")


def test_sfx_rejects_wrong_scene_count_for_workflow(monkeypatch, tmp_path):
    import sfx

    monkeypatch.setattr(sfx, "ensure_sfx_assets", lambda: {})
    with pytest.raises(RuntimeError, match="Publish SFX generation requires exactly 6 scenes"):
        sfx.generate_sfx(_script(7), str(tmp_path))
    with pytest.raises(RuntimeError, match="Story SFX generation requires exactly 7 scenes"):
        sfx.generate_sfx(_script(6, story_person="Test Person"), str(tmp_path))
