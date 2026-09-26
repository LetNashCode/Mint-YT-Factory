"""Offline Story-only catalog/planning tests and a real portrait render smoke test."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import story_real_video_media as media
import story_visual_upgrade as upgrade

GOOD = {"person_visible": True, "real_footage": True, "usable": True,
        "relevance": 8, "usage": "biographical_illustration", "reason": "test review"}


def candidate(index=0):
    return {"id": f"commons:{index}", "provider": "Wikimedia Commons",
            "url": f"https://upload.wikimedia.org/test{index}.mp4",
            "source_url": f"https://commons.wikimedia.org/wiki/File:Test{index}.mp4",
            "title": "Example Person filmed interview", "description": "Example Person"}


def reviewed_groups(root):
    rows = []
    for index in range(14):
        item = candidate(index % 2)
        path = root / f"raw{index}.mp4"
        path.write_bytes(b"test-fixture")
        start = index * 10.0
        rows.append({"path": str(path), "scene": index // 2 + 1, "shot": index % 2 + 1,
                     "type": "video", "provider": item["provider"], "source_id": item["id"],
                     "origin_url": item["source_url"], "source_url": item["source_url"],
                     "start": start, "end": start + 8, "asset_key": f"clip:{index}",
                     "query": item["title"], "score": 8 if index else 9,
                     "verification": dict(GOOD)})
    return rows


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(upgrade, "CATALOG_PATH", tmp_path / "catalog.json")
    monkeypatch.setattr(upgrade, "_PREPARED", {})
    monkeypatch.setattr(upgrade, "_LAST_GROUPS", [])


def test_cache_reuses_only_identical_review_and_rechecks_changed_samples(monkeypatch, tmp_path):
    calls = []
    def review(*args):
        calls.append(args)
        return dict(GOOD)
    monkeypatch.setattr(media, "verify", review)
    catalog = upgrade.FootageCatalog()
    scene = {"narration": "Example Person's biography"}
    for _ in range(2):
        assert catalog.verify("Example Person", scene, candidate(), ["a", "b", "c"], 10, 8) == GOOD
    assert len(calls) == 1 and catalog.cache_hits == 1
    loaded = upgrade.FootageCatalog()
    assert loaded.candidates("Example Person") == [candidate()]
    assert loaded.intervals("Example Person", candidate(), 30) == [(10.0, 8.0)]
    assert loaded.intervals("Another Person", candidate(), 30) == []
    loaded.verify("Example Person", scene, candidate(), ["changed", "b", "c"], 10, 8)
    assert len(calls) == 2
    loaded.verify("Example Person", {"narration": "Different event"}, candidate(), ["changed", "b", "c"], 10, 8)
    assert len(calls) == 3
    monkeypatch.setenv("STORY_VIDEO_VERIFY_MODEL", "changed-model")
    loaded.verify("Example Person", scene, candidate(), ["changed", "b", "c"], 10, 8)
    assert len(calls) == 4


@pytest.mark.parametrize("change", [{"person_visible": False}, {"real_footage": False}, {"usable": False}])
def test_rejected_clips_are_never_cached(monkeypatch, change):
    monkeypatch.setattr(media, "verify", lambda *args: {**GOOD, **change})
    catalog = upgrade.FootageCatalog()
    catalog.verify("Example Person", {}, candidate(), ["a"], 0, 8)
    assert catalog.rows == [] and not catalog.path.exists()


def test_catalog_rejects_youtube_and_untrusted_sources():
    for url in ("https://youtube.com/watch?v=1", "https://upload.wikimedia.org.evil.test/a.mp4",
                "file:///etc/passwd", "http://upload.wikimedia.org/a.mp4"):
        assert not upgrade._source_allowed({**candidate(), "url": url})


def test_corrupt_catalog_is_treated_as_empty(tmp_path):
    upgrade.CATALOG_PATH.write_text("{broken")
    assert upgrade.FootageCatalog().rows == []
    upgrade.CATALOG_PATH.write_text(json.dumps({"schema_version": 1, "segments": [None, {}, {"person": "x"}]}))
    assert upgrade.FootageCatalog().rows == []


def test_prepare_happens_before_context_and_requires_all_clips(monkeypatch, tmp_path):
    with pytest.raises(RuntimeError, match="before writing narration"):
        upgrade.script_context()
    rows = reviewed_groups(tmp_path)
    seen = []
    def generate(script, output_dir, config, catalog=None):
        seen.append(script)
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        return rows
    monkeypatch.setattr(media, "generate_media", generate)
    upgrade.prepare("Example Person", "A documented turning point")
    assert len(seen[0]["scene_plan"]) == 7
    assert "untrusted catalog data" in upgrade.script_context()
    assert "Example Person" in upgrade.script_context()
    assert "ONE specific" in upgrade.script_context()
    assert "No fabricated danger" in upgrade.script_context()
    rows.pop()
    with pytest.raises(RuntimeError, match="Expected 14"):
        upgrade.prepare("Example Person", "Other premise")
    assert upgrade._PREPARED == {}


def test_prepare_reuses_identical_existing_plan_without_second_media_generation(monkeypatch, tmp_path):
    rows = reviewed_groups(tmp_path)
    calls = []
    monkeypatch.setattr(media, "generate_media", lambda *args, **kwargs: calls.append(1) or rows)
    first = upgrade.prepare("Example Person", "Same premise")
    second = upgrade.prepare("Example Person", "Same premise")
    assert len(calls) == 1
    assert first == second


def test_render_reuses_prepared_video_and_preserves_source_intervals(monkeypatch, tmp_path):
    rows = reviewed_groups(tmp_path)
    upgrade._PREPARED = {"person": "Example Person", "groups": rows}
    def portrait(source, target):
        target.write_bytes(source.read_bytes())
    monkeypatch.setattr(upgrade, "portrait_clip", portrait)
    monkeypatch.setattr(media, "discover", lambda *a: pytest.fail("No second discovery"))
    result = upgrade.generate_media({"story_person": "Example Person"}, str(tmp_path / "render"), {})
    assert len(result) == 14
    assert result[0]["score"] == 9
    assert all(Path(row["path"]).name.endswith("_portrait.mp4") for row in result)
    assert all(a["source_id"] != b["source_id"] for a, b in zip(result, result[1:]))
    assert {row["asset_key"] for row in result} == {row["asset_key"] for row in rows}
    assert "not necessarily the narrated event" in upgrade.source_credits()
    media.validate_segments(result)
    with pytest.raises(RuntimeError, match="does not match"):
        upgrade.generate_media({"story_person": "Someone Else"}, str(tmp_path / "render"), {})


def test_renderer_style_restores_shared_state_even_on_failure():
    original = lambda *args: "original"
    fake = SimpleNamespace(CAPTION_COLORS=("pink",), CAPTION_FONT_SIZE=92,
        CAPTION_SIZE_BY_SCENE=(1,), CAPTION_VERTICAL_POSITION=0.67,
        build_animated_image=original, make_visual_clip=lambda *args: "full-frame")
    with pytest.raises(RuntimeError, match="render failed"):
        with upgrade.renderer_style(fake):
            assert fake.CAPTION_COLORS == ("pink",)
            assert fake.CAPTION_FONT_SIZE == 92
            assert fake.CAPTION_SIZE_BY_SCENE == (1,)
            assert fake.CAPTION_VERTICAL_POSITION == 0.67
            assert fake.build_animated_image("clip_portrait.mp4", 3, (360, 640), {}, {}) == "full-frame"
            assert fake.build_animated_image("other.mp4", 3, (360, 640), {}, {}) == "original"
            raise RuntimeError("render failed")
    assert fake.build_animated_image is original
    assert fake.CAPTION_COLORS == ("pink",) and fake.CAPTION_FONT_SIZE == 92
    assert fake.CAPTION_VERTICAL_POSITION == 0.67


def _pixels(path):
    import numpy as np
    raw = media.command(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-frames:v", "1",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(640, 360, 3)


def test_real_ffmpeg_portrait_fills_canvas_and_removes_embedded_borders(tmp_path):
    source, target = tmp_path / "wide.mp4", tmp_path / "portrait.mp4"
    media.command(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
        "color=c=lime:size=640x360:rate=30", "-t", "1", "-vf", "pad=704:440:32:40:black",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)])
    active, focus = upgrade._framing(source)
    assert active == (640, 360, 32, 40)
    assert focus == (0.5, 0.5)
    upgrade.portrait_clip(source, target, 360, 640)
    data = json.loads(media.command(["ffprobe", "-v", "error", "-show_entries",
        "stream=width,height", "-of", "json", str(target)]).stdout)
    assert (data["streams"][0]["width"], data["streams"][0]["height"]) == (360, 640)
    frame = _pixels(target)
    for x, y in ((3, 3), (356, 3), (3, 636), (356, 636), (180, 320)):
        assert frame[y, x, 1] > 180 and frame[y, x, 0] < 60 and frame[y, x, 2] < 60


def test_off_center_subject_is_centered_without_added_borders(monkeypatch, tmp_path):
    import cv2
    class Detector:
        def empty(self): return False
        def detectMultiScale(self, *args, **kwargs): return [(100, 100, 60, 60)]
    monkeypatch.setattr(cv2, "CascadeClassifier", lambda *args: Detector())
    source, target = tmp_path / "subject.mp4", tmp_path / "portrait.mp4"
    media.command(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
        "color=c=lime:size=640x360:rate=30", "-t", "1", "-vf",
        "drawbox=x=100:y=100:w=60:h=60:color=white:t=fill",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)])
    upgrade.portrait_clip(source, target, 360, 640)
    frame = _pixels(target)
    assert all(int(value) > 220 for value in frame[230, 180])
    assert frame[3, 3, 1] > 180 and frame[636, 356, 1] > 180


@pytest.mark.parametrize("focus", [(float("nan"), 0.5), (-0.1, 0.5), (1.1, 0.5)])
def test_invalid_framing_is_rejected(focus):
    with pytest.raises(ValueError):
        upgrade.portrait_filter(focus=focus)


def test_quality_gate_runs_before_upload_on_exact_path(monkeypatch):
    import sys
    import story_identity_runner as runner
    import final_video_quality_gate as gate
    calls = []
    def upload(path, *args, **kwargs):
        calls.append(("upload", path))
        return "already-published-id"
    fake = SimpleNamespace(upload_video=upload)
    monkeypatch.setitem(sys.modules, "upload_youtube", fake)
    monkeypatch.setattr(gate, "validate", lambda path: calls.append(("validate", path)))
    runner._patch_story_titles()
    runner._patch_story_titles()  # Idempotent: do not upload or validate twice.
    assert fake.upload_video("exact/current/final.mp4", "Before Fame: Test Person", "", {}) == "already-published-id"
    assert calls == [("validate", "exact/current/final.mp4"), ("upload", "exact/current/final.mp4")]


def test_failed_quality_gate_prevents_upload(monkeypatch):
    import sys
    import story_identity_runner as runner
    import final_video_quality_gate as gate
    def invalid(path): raise RuntimeError("invalid render")
    fake = SimpleNamespace(upload_video=lambda *a, **k: pytest.fail("Must not upload invalid render"))
    monkeypatch.setitem(sys.modules, "upload_youtube", fake)
    monkeypatch.setattr(gate, "validate", invalid)
    runner._patch_story_titles()
    with pytest.raises(RuntimeError, match="invalid render"):
        fake.upload_video("exact/current/final.mp4", "Title", "", {})


def test_no_post_publication_quality_scan():
    import inspect
    import story_identity_runner as runner
    assert "_validate_final_videos" not in inspect.getsource(runner)
    assert "from final_video_quality_gate import validate_video" not in inspect.getsource(runner)


def test_only_story_workflow_enables_upgrade():
    root = Path(__file__).resolve().parents[1]
    for name in ("publish.yml", "mystery-footage-shorts.yml", "emotional-reel.yml"):
        source = (root / ".github/workflows" / name).read_text()
        assert "story_visual_upgrade" not in source
        assert "story_identity_runner" not in source
        yaml.safe_load(source)
    workflow = yaml.safe_load((root / ".github/workflows/story-shorts.yml").read_text())
    assert workflow["jobs"]["story-shorts"]["needs"] == "quality-checks"
    assert "test_only" in workflow["jobs"]["story-shorts"]["if"]
    assert not (root / ".github/workflows/story-video-tests.yml").exists()
