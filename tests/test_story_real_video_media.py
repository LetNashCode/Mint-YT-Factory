"""Offline regression tests plus a real FFmpeg decode/transcode integration test."""
import ast
import base64
import json
import shutil
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
import yaml
import story_real_video_media as media

GOOD = {"person_visible": True, "real_footage": True, "usable": True, "relevance": 8,
        "reason": "Subject visible in filmed interview", "usage": "biographical_illustration"}


def candidate(index=0):
    return {"id": f"source:{index}", "source_url": f"https://example.org/film/{index}",
            "url": f"https://example.org/{index}.mp4", "provider": "Wikimedia Commons",
            "title": "Nelson Mandela interview", "description": "Nelson Mandela speaking"}


def story():
    return {"story_person": "Nelson Mandela", "scene_plan": [{"narration": f"Biography moment {n}"} for n in range(7)]}


def stub_pipeline(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "offline-test-only")
    monkeypatch.setattr(media, "discover", lambda *args: [candidate(n) for n in range(3)])
    monkeypatch.setattr(media, "resolve", lambda item: (item["url"], 160))
    monkeypatch.setattr(media, "extract", lambda url, start, length, path: length)
    monkeypatch.setattr(media, "frames", lambda *args: ["a", "b", "c"])
    monkeypatch.setattr(media, "verify", lambda *args: dict(GOOD))


def test_search_query_cannot_prove_identity():
    assert not media.person_match("Nelson Mandela", {"title": "Nelson interview", "query": "Nelson Mandela"})
    assert media.person_match("Nelson Mandela", {"title": "NELSON MANDELA speaks"})
    assert media.person_match("Marie Curie", {"description": "Marie <b>Curie</b>"})
    assert not media.person_match("", {"title": "interview"})


@pytest.mark.parametrize("duration", [8, 8.1, 10, 17, 30, 80, 600, 3600])
def test_windows_are_disjoint_and_within_source(duration):
    result = media.windows(duration)
    assert result
    for start, length in result:
        assert start >= 0 and start + length <= duration + 0.01
    for (start, length), (next_start, _) in zip(result, result[1:]):
        assert start + length <= next_start


@pytest.mark.parametrize("duration", [0, 3, float("nan"), float("inf")])
def test_invalid_sources_have_no_windows(duration):
    assert media.windows(duration) == []


@pytest.mark.parametrize("change", [{"person_visible": False}, {"person_visible": "true"},
                                     {"real_footage": False}, {"usable": False},
                                     {"relevance": 5}, {"relevance": "nan"}, {"relevance": 11}])
def test_verification_fails_closed(change):
    assert not media.verification_passes({**GOOD, **change})
    assert not media.verification_passes(None)


def test_commons_search_filters_video_and_follows_continuation(monkeypatch):
    calls = []
    def fetch(url, **params):
        calls.append(params)
        page = {"pageid": len(calls), "title": "Nelson Mandela", "imageinfo": [
            {"url": "https://example.org/video.webm", "mime": "video/webm"}]}
        result = {"query": {"pages": {str(len(calls)): page}}}
        if len(calls) == 1:
            result["continue"] = {"gsroffset": 40, "continue": "gsroffset||"}
        return result
    monkeypatch.setattr(media, "get_json", fetch)
    assert len(media.search_commons("Nelson Mandela")) == 2
    assert "filetype:video" in calls[0]["gsrsearch"]
    assert calls[1]["gsroffset"] == 40


def test_provider_outage_does_not_block_other_sources(monkeypatch):
    def unavailable(person):
        raise requests.Timeout()
    monkeypatch.setattr(media, "search_commons", unavailable)
    monkeypatch.setattr(media, "search_archive", lambda person: [candidate(), candidate()])
    monkeypatch.setattr(media, "search_youtube", lambda person: [])
    audit = []
    assert len(media.discover("Nelson Mandela", audit)) == 1
    assert audit[0]["error"] == "Timeout"


def test_generate_fourteen_distinct_video_intervals(monkeypatch, tmp_path):
    stub_pipeline(monkeypatch)
    result = media.generate_media(story(), str(tmp_path), {})
    media.validate_segments(result)
    assert len(result) == len({row["asset_key"] for row in result}) == 14
    assert set(row["type"] for row in result) == {"video"}
    assert max(Counter(row["source_id"] for row in result).values()) <= 6
    assert len({row["origin_url"] for row in result}) == 3
    audit = json.loads((tmp_path / "story_video_audit.json").read_text())
    assert len(audit["selected"]) == 14
    assert media.source_credits().count("https://example.org/film/0") == 1
    result[1].update(origin_url=result[0]["origin_url"], start=result[0]["start"], end=result[0]["end"])
    with pytest.raises(RuntimeError, match="Overlapping"):
        media.validate_segments(result)


def test_failed_first_source_is_skipped(monkeypatch, tmp_path):
    stub_pipeline(monkeypatch)
    monkeypatch.setattr(media, "discover", lambda *args: [candidate(n) for n in range(4)])
    def resolve(item):
        if item["id"] == "source:0":
            raise RuntimeError("unavailable")
        return item["url"], 160
    monkeypatch.setattr(media, "resolve", resolve)
    groups = media.generate_media(story(), str(tmp_path), {})
    assert all(row["source_id"] != "source:0" for row in groups)


def test_missing_footage_never_falls_back_to_photos(monkeypatch, tmp_path):
    stub_pipeline(monkeypatch)
    monkeypatch.setattr(media, "discover", lambda *args: [])
    with pytest.raises(RuntimeError, match="No real video candidates"):
        media.generate_media(story(), str(tmp_path), {})
    assert json.loads((tmp_path / "story_video_audit.json").read_text())["selected"] == []
    assert media.source_credits() == ""


def test_rejected_identity_is_never_selected(monkeypatch, tmp_path):
    stub_pipeline(monkeypatch)
    monkeypatch.setattr(media, "verify", lambda *args: {**GOOD, "person_visible": False})
    with pytest.raises(RuntimeError, match="Insufficient verified"):
        media.generate_media(story(), str(tmp_path), {})
    assert json.loads((tmp_path / "story_video_audit.json").read_text())["selected"] == []


def test_verifier_quota_stops_without_accepting_unchecked_video(monkeypatch, tmp_path):
    stub_pipeline(monkeypatch)
    def exhausted(*args):
        response = requests.Response()
        response.status_code = 429
        raise requests.HTTPError(response=response)
    monkeypatch.setattr(media, "verify", exhausted)
    with pytest.raises(RuntimeError, match="verifier HTTP 429"):
        media.generate_media(story(), str(tmp_path), {})
    assert (tmp_path / "story_video_audit.json").exists()


def test_probe_accepts_format_duration_when_stream_is_na(monkeypatch):
    data = {"streams": [{"width": 640, "height": 360, "duration": "N/A"}], "format": {"duration": "12.0"}}
    monkeypatch.setattr(media, "command", lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(data).encode()))
    assert media.probe("clip.webm") == 12


def test_story_route_is_isolated():
    root = Path(__file__).resolve().parents[1]
    runner = (root / "story_identity_runner.py").read_text(encoding="utf-8")
    ast.parse(runner)
    assert "story_real_video_media.generate_media" in runner
    assert "story_archival_media.generate_media" not in runner
    for name in ("production_entry.py", "production_entry_runner.py", "main.py",
                 "mystery_documentary.py", "mystery_documentary_runner.py", "sitecustomize.py"):
        assert "story_real_video_media" not in (root / name).read_text(encoding="utf-8")
    for name in ("publish.yml", "mystery-footage-shorts.yml"):
        workflow = (root / ".github/workflows" / name).read_text(encoding="utf-8")
        assert "story_real_video_media" not in workflow
        assert "story_identity_runner" not in workflow
        yaml.safe_load(workflow)
    yaml.safe_load((root / ".github/workflows/story-shorts.yml").read_text(encoding="utf-8"))


def test_real_ffmpeg_transcodes_and_samples_video(tmp_path):
    assert shutil.which("ffmpeg") and shutil.which("ffprobe"), "CI must install FFmpeg"
    source, target = tmp_path / "source.webm", tmp_path / "segment.mp4"
    media.command(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i",
                   "testsrc2=size=640x360:rate=30", "-t", "12", "-c:v", "libvpx", "-b:v", "500k", str(source)])
    duration = media.extract(str(source), 2, 8, target)
    assert 7.75 <= duration <= 8.25
    samples = media.frames(target, duration)
    assert len(samples) == 3 and len(set(samples)) == 3
    assert all(base64.b64decode(sample).startswith(b"\xff\xd8") for sample in samples)


def test_verification_samples_the_rendered_opening_not_later_frames(monkeypatch):
    commands = []
    def fake_command(args, timeout=90):
        commands.append(args)
        return SimpleNamespace(stdout=b"jpeg")
    monkeypatch.setattr(media, "command", fake_command)
    assert len(media.frames("clip.mp4", 8.0)) == 3
    times = [float(args[args.index("-ss") + 1]) for args in commands]
    assert times == [0.0, 0.4, 0.9]


def test_retired_verifier_model_falls_back_once_and_caches(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "offline-test-only")
    monkeypatch.setenv("STORY_VIDEO_VERIFY_MODEL", "retired-model")
    monkeypatch.setattr(media, "_VERIFIER_MODELS", {})
    calls = []
    def post(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=404 if len(calls) == 1 else 200,
            raise_for_status=lambda: None,
            json=lambda: {"candidates": [{"content": {"parts": [{"text": json.dumps(GOOD)}]}}]})
    monkeypatch.setattr(media.requests, "post", post)
    for _ in range(2):
        assert media.verification_passes(media.verify("Nelson Mandela", {}, candidate(), ["a", "b", "c"]))
    assert len(calls) == 3
    assert "retired-model" in calls[0]
    assert all("gemini-3.8-flash" in url for url in calls[1:])
