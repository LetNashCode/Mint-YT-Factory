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
    rows.pop()
    with pytest.raises(RuntimeError, match="Expected 14"):
        upgrade.prepare("Example Person", "Other premise")
    assert upgrade._PREPARED == {}


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
            assert fake.CAPTION_COLORS == ("#FFFFFF",)
            assert fake.build_animated_image("clip_portrait.mp4", 3, (360, 640), {}, {}) == "full-frame"
            assert fake.build_animated_image("other.mp4", 3, (360, 640), {}, {}) == "original"
            raise RuntimeError("render failed")
    assert fake.build_animated_image is original
    assert fake.CAPTION_COLORS == ("pink",) and fake.CAPTION_FONT_SIZE == 92
    assert fake.CAPTION_VERTICAL_POSITION == 0.67


def test_real_ffmpeg_portrait_preserves_both_edges(tmp_path):
    source, target = tmp_path / "wide.mp4", tmp_path / "portrait.mp4"
    media.command(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
        "testsrc2=size=640x360:rate=30", "-t", "1", "-vf",
        "drawbox=x=0:y=0:w=80:h=360:color=red:t=fill,drawbox=x=560:y=0:w=80:h=360:color=blue:t=fill",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)])
    upgrade.portrait_clip(source, target, 360, 640)
    data = json.loads(media.command(["ffprobe", "-v", "error", "-show_entries",
        "stream=width,height", "-of", "json", str(target)]).stdout)
    assert (data["streams"][0]["width"], data["streams"][0]["height"]) == (360, 640)
    raw = media.command(["ffmpeg", "-nostdin", "-v", "error", "-i", str(target), "-frames:v", "1",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]).stdout
    left = raw[(320 * 360 + 10) * 3:(320 * 360 + 10) * 3 + 3]
    right = raw[(320 * 360 + 350) * 3:(320 * 360 + 350) * 3 + 3]
    assert left[0] > 180 and left[2] < 80
    assert right[2] > 180 and right[0] < 80


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
