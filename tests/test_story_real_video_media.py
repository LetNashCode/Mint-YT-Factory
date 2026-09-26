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


@pytest.fixture(autouse=True)
def reset_verifier_budget():
    media._reset_verifier_budget()
    yield
    media._reset_verifier_budget()


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
    seen_queries = {}
    def fetch(url, **params):
        calls.append(params)
        if params.get("generator") == "categorymembers":
            return {"query": {"pages": {}}}
        query = params["gsrsearch"]
        page_number = seen_queries.get(query, 0) + 1
        seen_queries[query] = page_number
        page = {"pageid": len(calls), "title": "Nelson Mandela", "imageinfo": [
            {"url": "https://example.org/video.webm", "mime": "video/webm"}]}
        result = {"query": {"pages": {str(len(calls)): page}}}
        # Every discovery query has its own continuation token.
        if page_number == 1:
            result["continue"] = {"gsroffset": 40, "continue": "gsroffset||"}
        return result
    monkeypatch.setattr(media, "get_json", fetch)
    results = media.search_commons("Nelson Mandela")
    # Four precise text searches are used; each must follow its own Commons
    # continuation. Category traversal is also attempted independently.
    assert len(results) == 8
    assert all(item["provider"] == "Wikimedia Commons" for item in results)
    assert all(item["url"].endswith("video.webm") for item in results)
    assert len(seen_queries) == 4
    assert all(count == 2 for count in seen_queries.values())
    assert "filetype:video" in calls[0]["gsrsearch"]
    assert calls[1]["gsroffset"] == 40
    assert calls[3]["gsroffset"] == 40



def test_archive_search_excludes_youtube_imports_and_prefers_subject_records(monkeypatch):
    calls = []
    def fetch(url, **params):
        calls.append((url, params))
        if "advancedsearch.php" in url:
            return {"response": {"docs": [
                {"identifier": "youtube-bad", "title": "Nelson Mandela interview"},
                {"identifier": "real-person", "title": "Nelson Mandela speaking",
                 "description": "Archival interview with Nelson Mandela", "subject": ["Nelson Mandela"]},
                {"identifier": "unrelated", "title": "Nelson Mandela mentioned",
                 "description": "A presenter discusses the topic", "subject": ["Nelson Mandela"]},
            ]}}
        return {"files": [{"name": "real.mp4", "size": "1000000"}]}
    monkeypatch.setattr(media, "get_json", fetch)
    results = media.search_archive("Nelson Mandela")
    assert [row["id"] for row in results] == ["archive:real-person", "archive:unrelated"]
    assert all("youtube-bad" not in row["id"] for row in results)
    assert all("NOT identifier:youtube-*" in params["q"] for url, params in calls if "advancedsearch.php" in url)


def test_identity_score_does_not_trust_query_field():
    item = {"title": "Nelson Mandela interview", "description": "", "query": "Nelson Mandela"}
    assert media.person_match("Nelson Mandela", item)
    assert not media.person_match("Marie Curie", item)


def test_provider_outage_does_not_block_other_sources(monkeypatch):
    def unavailable(person):
        raise requests.Timeout()
    monkeypatch.setattr(media, "search_commons", unavailable)
    monkeypatch.setattr(media, "search_archive", lambda person: [candidate(), candidate()])
    audit = []
    assert len(media.discover("Nelson Mandela", audit)) == 1
    assert audit[0]["error"] == "Timeout"


def test_generate_fourteen_distinct_video_intervals(monkeypatch, tmp_path):
    stub_pipeline(monkeypatch)
    result = media.generate_media(story(), str(tmp_path), {})
    media.validate_segments(result)
    assert len(result) == len({row["asset_key"] for row in result}) == 14
    assert set(row["type"] for row in result) == {"video"}
    assert max(Counter(row["source_id"] for row in result).values()) < 14
    assert len({row["origin_url"] for row in result}) == 2
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
    assert "story_visual_upgrade.generate_media" in runner
    assert "story_real_video_media.generate_media" not in runner
    assert "story_archival_media.generate_media" not in runner
    for name in ("production_entry.py", "production_entry_runner.py", "main.py",
                 "mystery_documentary.py", "mystery_documentary_runner.py", "sitecustomize.py"):
        assert "story_visual_upgrade" not in (root / name).read_text(encoding="utf-8")
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
    assert times == [0.0, 3.6, 7.2]


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

@pytest.mark.parametrize("url", ["https://www.youtube.com/watch?v=abc", "https://youtu.be/abc",
    "https://www.youtube-nocookie.com/embed/abc", "https://rr1.googlevideo.com/videoplayback"])
def test_youtube_urls_rejected_before_media_commands(monkeypatch, tmp_path, url):
    monkeypatch.setattr(media, "command", lambda *a, **k: pytest.fail("No command may run for YouTube"))
    for action in (lambda: media.resolve({"provider": "Wikimedia Commons", "url": url}),
                   lambda: media.probe(url), lambda: media.extract(url, 0, 8, tmp_path / "clip.mp4")):
        with pytest.raises(RuntimeError, match="YouTube downloads are disabled"):
            action()


def test_discovery_has_no_youtube_provider(monkeypatch):
    def search_commons(person):
        return []
    def search_archive(person):
        return []
    monkeypatch.setattr(media, "search_commons", search_commons)
    monkeypatch.setattr(media, "search_archive", search_archive)
    assert not hasattr(media, "search_youtube")
    audit = []
    assert media.discover("Nelson Mandela", audit) == []
    assert [entry["provider"] for entry in audit] == ["search_commons", "search_archive"]


def test_youtube_provider_rejected_even_with_other_url(monkeypatch):
    monkeypatch.setattr(media, "command", lambda *a, **k: pytest.fail("No command may run for YouTube"))
    with pytest.raises(RuntimeError, match="YouTube downloads are disabled"):
        media.resolve({"provider": "YouTube", "url": "https://example.org/video.mp4"})

@pytest.mark.parametrize("outage", [False, True])
def test_topic_preflight_skips_empty_subject_but_preserves_provider_outage(monkeypatch, outage):
    import sys
    import story_identity_runner as runner
    topics = iter([("one_decision", "No film", "First Person"), ("one_decision", "Filmed life", "Second Person")])
    released = []
    monkeypatch.setattr(runner.interactive_topics, "get_next_topic", lambda: next(topics))
    monkeypatch.setitem(sys.modules, "story_topic_runtime", SimpleNamespace(release_reservation=lambda *args: released.append(args)))
    def prepare(person, topic):
        if outage:
            raise RuntimeError("Story video providers unavailable; reserved topic preserved for retry")
        if person == "First Person":
            raise RuntimeError("Insufficient verified real footage")
        return {"person": person}
    monkeypatch.setattr(runner.story_visual_upgrade, "prepare", prepare)
    runner._patch_story_video_topics()
    if outage:
        with pytest.raises(RuntimeError, match="providers unavailable"):
            runner.interactive_topics.get_next_topic()
        assert released == []
    else:
        assert runner.interactive_topics.get_next_topic()[2] == "Second Person"
        assert released == [("one_decision", "No film", "First Person")]


def test_one_long_verified_source_can_supply_distinct_story_segments(monkeypatch, tmp_path):
    stub_pipeline(monkeypatch)
    monkeypatch.setattr(media, "discover", lambda *args: [candidate()])
    groups = media.generate_media(story(), str(tmp_path), {})
    assert len(groups) == 14
    assert len({row["source_id"] for row in groups}) == 1
    media.validate_segments(groups)


@pytest.mark.parametrize("status,allowed", [("reserved", True), ("released", True), ("published", False)])
def test_reserved_person_is_not_treated_as_published_duplicate(monkeypatch, status, allowed):
    import interactive_topics
    import story_topic_uniqueness as guard
    monkeypatch.setattr(guard, "repair_pending_story", lambda: None)
    def read(path, default):
        return {"person": "Neil Armstrong", "status": status} if path == guard.PENDING else []
    monkeypatch.setattr(guard, "_read_json", read)
    monkeypatch.setattr(guard, "_write_json", lambda *args: None)
    monkeypatch.setattr(interactive_topics, "get_next_topic", lambda: ("one_decision", "Moon mission", "Neil Armstrong"))
    guard.install()
    if allowed:
        assert interactive_topics.get_next_topic()[2] == "Neil Armstrong"
    else:
        with pytest.raises(RuntimeError, match="unused person"):
            interactive_topics.get_next_topic()


@pytest.mark.parametrize("person,topic,duplicate", [("Nelson Mandela", "Prison to president", False), ("Nelson Mandela", "Prison to president", True), ("Nelson Mandela", "", False)])
def test_manual_story_subject_keeps_history_protection(monkeypatch, person, topic, duplicate):
    import story_identity_runner as runner
    monkeypatch.setenv("STORY_PERSON", person)
    monkeypatch.setenv("STORY_TOPIC", topic)
    monkeypatch.setattr(runner.interactive_topics, "_load_history", lambda: [{"person": person}] if duplicate else [])
    writes = []
    monkeypatch.setattr(runner.interactive_topics, "_save", lambda path, data: writes.append(data))
    if duplicate or not topic:
        with pytest.raises(RuntimeError):
            runner._apply_requested_story()
        assert writes == []
    else:
        runner._apply_requested_story()
        assert writes[0]["person"] == person and writes[0]["status"] == "reserved"


def test_unrelated_source_stops_after_four_identity_rejections(monkeypatch, tmp_path):
    stub_pipeline(monkeypatch)
    monkeypatch.setattr(media, "discover", lambda *args: [candidate()])
    calls = []
    def reject(*args):
        calls.append(1)
        return {**GOOD, "person_visible": False}
    monkeypatch.setattr(media, "verify", reject)
    with pytest.raises(RuntimeError, match="Insufficient verified"):
        media.generate_media(story(), str(tmp_path), {})
    assert len(calls) == 4


def test_repeated_extraction_failure_is_bounded(monkeypatch, tmp_path):
    stub_pipeline(monkeypatch)
    monkeypatch.setattr(media, "discover", lambda *args: [candidate()])
    calls = []
    def fail(*args):
        calls.append(1)
        raise RuntimeError("ffmpeg unavailable source")
    monkeypatch.setattr(media, "extract", fail)
    with pytest.raises(RuntimeError, match="Insufficient verified"):
        media.generate_media(story(), str(tmp_path), {})
    assert len(calls) == 3


def test_runtime_verifier_quota_is_not_swallowed(monkeypatch, tmp_path):
    stub_pipeline(monkeypatch)
    calls = []
    def fail(*args):
        calls.append(1)
        raise RuntimeError("Story visual verifier HTTP 429")
    monkeypatch.setattr(media, "verify", fail)
    with pytest.raises(RuntimeError, match="verifier HTTP 429"):
        media.generate_media(story(), str(tmp_path), {})
    assert len(calls) == 1


def test_verified_sources_are_reused_before_unseen_sources(monkeypatch, tmp_path):
    stub_pipeline(monkeypatch)
    seen = []
    def resolve(item):
        seen.append(item["id"])
        return item["url"], 160
    monkeypatch.setattr(media, "resolve", resolve)
    groups = media.generate_media(story(), str(tmp_path), {})
    assert len(groups) == 14
    assert set(seen) == {"source:0", "source:1"}
    media.validate_segments(groups)


@pytest.mark.parametrize("failure", [requests.ReadTimeout, requests.ConnectionError])
def test_verifier_network_failure_uses_model_fallback(monkeypatch, failure):
    monkeypatch.setenv("GEMINI_API_KEY", "offline-test-only")
    monkeypatch.setenv("STORY_VIDEO_VERIFY_MODEL", "gemini-flash-lite-latest")
    monkeypatch.setattr(media, "_VERIFIER_MODELS", {})
    calls = []
    def post(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise failure()
        return SimpleNamespace(status_code=200, raise_for_status=lambda: None,
            json=lambda: {"candidates": [{"content": {"parts": [{"text": json.dumps(GOOD)}]}}]})
    monkeypatch.setattr(media.requests, "post", post)
    assert media.verification_passes(media.verify("Nelson Mandela", {}, candidate(), ["a", "b", "c"]))
    assert len(calls) == 2 and "gemini-3.8-flash" in calls[1]


def test_verifier_network_outage_fails_closed_after_three_attempts(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "offline-test-only")
    monkeypatch.setattr(media, "_VERIFIER_MODELS", {})
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        raise requests.ReadTimeout()
    monkeypatch.setattr(media.requests, "post", post)
    with pytest.raises(RuntimeError, match="unavailable after network retries"):
        media.verify("Nelson Mandela", {}, candidate(), ["a", "b", "c"])
    assert len(calls) == 3


def test_direct_subject_category_is_retained(monkeypatch):
    def fetch(url, **params):
        if params.get("generator") == "categorymembers":
            assert params["gcmtitle"] == "Category:Videos of Nelson Mandela"
        return {"query": {"pages": {"1": {"pageid": 1, "title": "Nelson Mandela speech",
            "categories": [{"title": "Category:Videos of Nelson Mandela"}],
            "imageinfo": [{"url": "https://example.org/video.webm", "mime": "video/webm"}]}}}}
    monkeypatch.setattr(media, "get_json", fetch)
    assert media.search_commons("Nelson Mandela")[0]["direct_subject"] is True


def test_first_identity_sample_comes_from_middle_of_recording(monkeypatch, tmp_path):
    stub_pipeline(monkeypatch)
    monkeypatch.setattr(media, "discover", lambda *args: [candidate()])
    starts = []
    def extract(url, start, length, path):
        starts.append(start)
        return length
    monkeypatch.setattr(media, "extract", extract)
    groups = media.generate_media(story(), str(tmp_path), {})
    intervals = media.windows(160, limit=24)
    assert starts[0] == intervals[len(intervals) // 2][0]
    media.validate_segments(groups)


@pytest.mark.parametrize("status", [429, 503])
def test_quota_or_server_error_moves_to_pinned_model(monkeypatch, status):
    monkeypatch.setenv("GEMINI_API_KEY", "offline-test-only")
    monkeypatch.setenv("STORY_VIDEO_VERIFY_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr(media, "_VERIFIER_MODELS", {})
    calls = []
    def post(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=status if len(calls) == 1 else 200, raise_for_status=lambda: None,
            json=lambda: {"candidates": [{"content": {"parts": [{"text": json.dumps(GOOD)}]}}]})
    monkeypatch.setattr(media.requests, "post", post)
    assert media.verification_passes(media.verify("Nelson Mandela", {}, candidate(), ["a", "b", "c"]))
    if status == 503:
        assert len(calls) == 2 and calls[1] == calls[0]
    else:
        assert len(calls) == 2 and "gemini-3.1-flash-lite" in calls[1]


def test_story_media_recovery_classifies_only_content_availability_failures():
    import story_identity_runner as runner
    assert runner._story_media_failure(
        RuntimeError("Insufficient verified real footage of Ernest Shackleton for scene 1, shot 1")
    )
    assert runner._story_media_failure(
        RuntimeError("No real video candidates found for Ernest Shackleton")
    )
    assert runner._story_media_failure(
        RuntimeError("Story video search budget exhausted; see story_video_audit.json")
    )
    assert not runner._story_media_failure(RuntimeError("Story visual verifier HTTP 429"))
    assert not runner._story_media_failure(RuntimeError("ffmpeg failed"))
    assert not runner._story_media_failure(RuntimeError("Final video quality gate failed"))


def test_story_failures_are_deferred_without_releasing_reservation():
    import story_identity_runner as runner
    assert runner._story_defer_failure(RuntimeError("Story video providers unavailable; reserved topic preserved for retry"))
    assert runner._story_defer_failure(RuntimeError("Story visual verifier HTTP 429"))
    assert runner._story_defer_failure(RuntimeError("Story verifier unavailable after network retries/model fallback"))
    assert not runner._story_defer_failure(RuntimeError("Insufficient verified real footage of Ernest Shackleton"))


def test_story_media_recovery_releases_and_quarantines_failed_subject(monkeypatch, tmp_path):
    import story_identity_runner as runner
    pending = {"pillar": "impossible_odds", "topic": "Bad subject story",
               "person": "Ernest Shackleton", "status": "reserved", "number": 7}
    released = []

    monkeypatch.setattr(runner.interactive_topics, "get_pending_story", lambda: pending)
    monkeypatch.setattr(
        "story_topic_runtime.release_reservation",
        lambda pillar=None, topic=None, person=None: released.append((pillar, topic, person)) or True,
    )
    candidates = tmp_path / "story_candidates.json"
    candidates.write_text(json.dumps([
        {"person": "Ernest Shackleton", "premise": "Bad footage"},
        {"person": "New Person", "premise": "Good footage"},
    ]), encoding="utf-8")
    monkeypatch.setattr(runner.interactive_topics, "CANDIDATES", candidates)

    runner._release_failed_story("Ernest Shackleton")

    assert released == [("impossible_odds", "Bad subject story", "Ernest Shackleton")]
    remaining = json.loads(candidates.read_text(encoding="utf-8"))
    assert [row["person"] for row in remaining] == ["New Person"]


def test_hybrid_media_falls_back_to_archival_only_for_content_shortage(monkeypatch, tmp_path):
    import story_hybrid_media as hybrid
    story_data = story()
    real_error = RuntimeError("Insufficient verified real footage of Nelson Mandela for scene 1, shot 1")
    fallback = [{"scene": i // 2 + 1, "shot": i % 2 + 1, "path": str(tmp_path / f"{i}.jpg"),
                 "type": "photo", "provider": "Wikimedia Commons",
                 "source_url": f"https://commons.example/{i}", "asset_key": f"photo:{i}", "score": 8}
                for i in range(14)]
    monkeypatch.setattr(hybrid.real_video, "generate_media", lambda *a, **k: (_ for _ in ()).throw(real_error))
    monkeypatch.setattr(hybrid.archival, "generate_media", lambda *a, **k: fallback)
    result = hybrid.generate_media(story_data, str(tmp_path), {})
    assert len(result) == 14
    assert all(row["type"] == "photo" for row in result)
    route = json.loads((tmp_path / "story_media_route.json").read_text())
    assert route["mode"] == "archival_video_or_photo"


def test_hybrid_media_fails_closed_on_verifier_outage(monkeypatch, tmp_path):
    import story_hybrid_media as hybrid
    outage = RuntimeError("Story verifier unavailable after network retries/model fallback")
    monkeypatch.setattr(hybrid.real_video, "generate_media", lambda *a, **k: (_ for _ in ()).throw(outage))
    monkeypatch.setattr(hybrid.archival, "generate_media", lambda *a, **k: pytest.fail("Archival fallback must not hide verifier outages"))
    with pytest.raises(RuntimeError, match="verifier unavailable"):
        hybrid.generate_media(story(), str(tmp_path), {})


def test_hybrid_discovery_accepts_archival_candidates_when_real_video_is_empty(monkeypatch):
    import story_hybrid_media as hybrid
    monkeypatch.setattr(hybrid.real_video, "discover", lambda person, audit: [])
    monkeypatch.setattr(hybrid.archival, "_candidate_pool",
                        lambda script, scene, want_video: [{"id": "photo:1", "title": "Nelson Mandela portrait",
                                                             "description": "Nelson Mandela historical photograph",
                                                             "relevance_score": 8}] if not want_video else [])
    audit = []
    result = hybrid.discover("Nelson Mandela", audit)
    assert result and result[0]["id"] == "photo:1"


def test_hybrid_source_credits_are_deduplicated(monkeypatch):
    import story_hybrid_media as hybrid
    hybrid._LAST_GROUPS = [
        {"provider": "Wikimedia Commons", "source_url": "https://commons.example/a", "creator": "Archive"},
        {"provider": "Wikimedia Commons", "source_url": "https://commons.example/a", "creator": "Archive"},
        {"provider": "Internet Archive", "source_url": "https://archive.example/b", "creator": ""},
    ]
    credits = hybrid.source_credits()
    assert credits.count("https://commons.example/a") == 1
    assert credits.count("https://archive.example/b") == 1


def test_daily_gemini_quota_marks_story_for_defer(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "offline-test-only")
    monkeypatch.setenv("STORY_VIDEO_VERIFY_MODEL", "gemini-test")
    payload = {
        "error": {
            "code": 429,
            "status": "RESOURCE_EXHAUSTED",
            "message": "Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests",
            "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                         "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}],
        }
    }

    class Response:
        status_code = 429
        def json(self):
            return payload

    monkeypatch.setattr(media.requests, "post", lambda *args, **kwargs: Response())
    with pytest.raises(RuntimeError, match="daily Gemini quota exhausted"):
        media.verify("Nelson Mandela", {}, candidate(), ["a", "b", "c"])
    assert (Path(".story_gemini_quota_deferred")).exists()


def test_daily_quota_detector_does_not_treat_minute_quota_as_daily():
    class Response:
        status_code = 429
        def json(self):
            return {"error": {"status": "RESOURCE_EXHAUSTED",
                              "message": "Quota exceeded for requests per minute"}}
    assert not media._is_daily_quota_response(Response())


def test_verifier_request_budget_stops_before_excess_calls(monkeypatch, tmp_path):
    stub_pipeline(monkeypatch)
    monkeypatch.setenv("STORY_GEMINI_MAX_REQUESTS", "2")
    calls = []
    def verify(*args):
        calls.append(1)
        return dict(GOOD)
    monkeypatch.setattr(media, "verify", verify)
    with pytest.raises(RuntimeError, match="request budget exhausted"):
        media.generate_media(story(), str(tmp_path), {})
    assert len(calls) == 2
    assert (Path(".story_gemini_budget_deferred")).exists()


def test_media_attempt_records_stage_and_error(monkeypatch, tmp_path):
    stub_pipeline(monkeypatch)
    monkeypatch.setattr(media, "discover", lambda *args: [candidate()])
    def fail(*args):
        raise AttributeError("sample decoder missing")
    monkeypatch.setattr(media, "frames", fail)
    with pytest.raises(RuntimeError, match="Insufficient verified"):
        media.generate_media(story(), str(tmp_path), {})
    audit = json.loads((tmp_path / "story_video_audit.json").read_text())
    attempt = audit["attempts"][0]
    assert attempt["stage"] == "frame_sample"
    assert attempt["error_type"] == "AttributeError"
    assert "sample decoder missing" in attempt["error"]


def test_invalid_verifier_result_fails_closed(monkeypatch, tmp_path):
    stub_pipeline(monkeypatch)
    monkeypatch.setattr(media, "verify", lambda *args: None)
    with pytest.raises(RuntimeError, match="invalid result type"):
        media.generate_media(story(), str(tmp_path), {})



def test_source_precheck_rejects_obvious_presenter_and_dramatization_metadata():
    assert "presenter" in media._source_precheck({
        "title": "Hedy Lamarr presenter interview", "description": ""
    })
    assert "actor portraying" in media._source_precheck({
        "title": "Actor portraying Hedy Lamarr", "description": ""
    })
    assert media._source_precheck({
        "title": "Hedy Lamarr archival interview", "description": "Hedy Lamarr speaking"
    }) is None


def test_frame_precheck_rejects_static_frames():
    from PIL import Image
    import io
    frames = []
    for _ in range(3):
        image = Image.new("RGB", (64, 36), (80, 80, 80))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        frames.append(base64.b64encode(buffer.getvalue()).decode())
    assert media._frame_precheck(frames) == "static frames/no detectable motion"


def test_frame_precheck_allows_motion_but_does_not_verify_identity():
    from PIL import Image, ImageDraw
    import io
    frames = []
    for offset in (0, 8, 16):
        image = Image.new("RGB", (64, 36), (30, 30, 30))
        ImageDraw.Draw(image).rectangle((offset, 8, offset + 18, 28), fill=(220, 220, 220))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        frames.append(base64.b64encode(buffer.getvalue()).decode())
    assert media._frame_precheck(frames) is None
