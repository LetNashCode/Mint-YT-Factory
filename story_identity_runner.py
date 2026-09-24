"""Run Story Shorts with identity-first archival media and topic uniqueness protection."""
from __future__ import annotations

import runpy
from pathlib import Path

import story_real_video_media
import story_topic_uniqueness
import interactive_topics
from interactive_topics import validate_story_sequence_state


def _patch_story_portrait_export() -> None:
    import assemble
    from portrait_export_guard import ensure_portrait_export
    original_assemble = getattr(assemble, "assemble_video", None)
    if original_assemble is None or getattr(original_assemble, "_mint_story_portrait_guard", False):
        return
    def guarded_assemble_video(*args, **kwargs):
        result = original_assemble(*args, **kwargs)
        output_path = kwargs.get("output_path") or (args[-1] if args else None)
        if output_path:
            ensure_portrait_export(output_path)
        return result
    guarded_assemble_video._mint_story_portrait_guard = True
    assemble.assemble_video = guarded_assemble_video
    print("📱 Story portrait guard: full-frame 9:16 crop enabled")


def _patch_story_titles() -> None:
    import upload_youtube
    from story_title_optimizer import optimize_title
    original_upload = getattr(upload_youtube, "upload_video", None)
    if original_upload is None or getattr(original_upload, "_mint_story_title_optimizer", False):
        return
    def optimized_upload(video_path, title, description, config, *args, **kwargs):
        raw_title = str(title or "")
        person = raw_title.split(":", 1)[1].strip() if ":" in raw_title else ""
        optimized = optimize_title(raw_title, person, raw_title, "")
        print(f"🎯 Story title optimized: {optimized}")
        description = str(description or "") + story_real_video_media.source_credits()
        return original_upload(video_path, optimized, description, config, *args, **kwargs)
    optimized_upload._mint_story_title_optimizer = True
    upload_youtube.upload_video = optimized_upload


def _patch_story_visual_director() -> None:
    import generate_script.interactive as story_generator
    from story_visual_director import direct_story_visuals
    original_generate_script = getattr(story_generator, "generate_script", None)
    if original_generate_script is None or getattr(original_generate_script, "_mint_story_visual_director", False):
        return
    def directed_generate_script(*args, **kwargs):
        result = original_generate_script(*args, **kwargs)
        directed = direct_story_visuals(result)
        print("🎬 Story visual director: evidence-led visual briefs attached")
        return directed
    directed_generate_script._mint_story_visual_director = True
    story_generator.generate_script = directed_generate_script


def _validate_final_videos() -> None:
    from final_video_quality_gate import validate_video
    roots = [Path("output/interactive"), Path("output")]
    videos = []
    for root in roots:
        if root.exists():
            videos.extend(root.rglob("final.mp4"))
    unique = []
    seen = set()
    for video in videos:
        resolved = str(video.resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique.append(video)
    if not unique:
        raise RuntimeError("Final video quality gate could not find final.mp4")
    target = max(unique, key=lambda path: path.stat().st_mtime)
    validate_video(str(target))
    print(f"✅ Final video quality gate passed: {target}")


def _patch_story_video_topics() -> None:
    """Reject subjects with no real-video candidates before script/TTS generation."""
    original = interactive_topics.get_next_topic
    if getattr(original, "_mint_video_topic_preflight", False):
        return
    def video_ready_topic():
        from story_topic_runtime import release_reservation
        for attempt in range(8):
            pillar, topic, person = original()
            audit = []
            candidates = story_real_video_media.discover(person, audit)
            print(f"Story footage preflight: {person} | candidates={len(candidates)} | providers={audit}", flush=True)
            if candidates:
                return pillar, topic, person
            if audit and all("error" in row for row in audit):
                raise RuntimeError("Story video providers unavailable; reserved topic preserved for retry")
            release_reservation(pillar, topic, person)
            print(f"Skipping Story subject without accessible video candidates ({attempt + 1}/8): {person}", flush=True)
        raise RuntimeError("No unused Story subject with real-video candidates found in eight attempts")
    video_ready_topic._mint_video_topic_preflight = True
    interactive_topics.get_next_topic = video_ready_topic


def _apply_requested_story() -> None:
    """Optional manual subject; keep the same history and reservation safeguards."""
    import os
    import re
    person = os.environ.get("STORY_PERSON", "").strip()
    topic = os.environ.get("STORY_TOPIC", "").strip()
    if not person and not topic:
        return
    if not person or not topic:
        raise RuntimeError("Manual Story selection requires both person and topic")
    normalize = lambda value: re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    used = {normalize(row.get("person")) for row in interactive_topics._load_history() if isinstance(row, dict)}
    if normalize(person) in used:
        raise RuntimeError(f"Manual Story subject already published: {person}")
    interactive_topics._save(interactive_topics.PENDING, {
        "pillar": "impossible_odds", "topic": f"{person}: {topic}",
        "person": person, "number": 0, "status": "reserved",
    })
    print(f"Manual Story subject reserved: {person}", flush=True)


def _story_media_failure(exc: Exception) -> bool:
    """Return True only for content-availability failures safe to recover with another subject."""
    text = str(exc or "").lower()
    markers = (
        "insufficient verified real footage",
        "no real video candidates found",
        "story video search budget exhausted",
    )
    return any(marker in text for marker in markers)


def _story_defer_failure(exc: Exception) -> bool:
    """Return True for temporary provider/verifier failures that must preserve the reservation."""
    text = str(exc or "").lower()
    markers = (
        "story video providers unavailable",
        "no unused story subject with real-video candidates",
        "story candidate pool is empty",
        "story visual verifier http 429",
        "story visual verifier http 500",
        "story visual verifier http 502",
        "story visual verifier http 503",
        "story visual verifier http 504",
        "story verifier unavailable after network retries/model fallback",
    )
    return any(marker in text for marker in markers)


def _release_failed_story(person: str = "") -> None:
    """Release the current reservation and quarantine the failed person for this run."""
    try:
        from story_topic_runtime import release_reservation
        pending = interactive_topics.get_pending_story() or {}
        release_reservation(
            pending.get("pillar"),
            pending.get("topic"),
            person or pending.get("person"),
        )
    except Exception as exc:
        print(f"⚠️ Could not release failed Story reservation cleanly: {exc}", flush=True)

    # Remove the failed person from the current candidate pool so the same
    # unavailable subject cannot immediately be selected again.
    try:
        path = Path(interactive_topics.CANDIDATES)
        rows = interactive_topics._load(path, [])
        failed = str(person or "").strip().lower()
        filtered = [
            row for row in rows
            if not isinstance(row, dict)
            or str(row.get("person") or "").strip().lower() != failed
        ]
        interactive_topics._save(path, filtered)
    except Exception as exc:
        print(f"⚠️ Could not quarantine failed Story candidate: {exc}", flush=True)


def _defer_story(reason: str) -> None:
    """Finish the GitHub run successfully when Story cannot be safely published."""
    Path(".story_deferred").write_text(
        str(reason).strip()[:1000] + "\n", encoding="utf-8"
    )
    print(f"⏸️ Story Shorts deferred safely: {reason}", flush=True)


def main() -> None:
    next_number = validate_story_sequence_state()
    print(f"🔐 Story sequence preflight passed: next Story #{next_number}")
    def validated_next_story_number() -> int:
        return next_number
    validated_next_story_number._mint_validated_sequence_number = True
    interactive_topics.next_story_number = validated_next_story_number
    _apply_requested_story()
    story_topic_uniqueness.install()
    _patch_story_video_topics()
    _patch_story_portrait_export()
    _patch_story_titles()
    _patch_story_visual_director()

    def identity_generate_media(script, output_dir, config, gim=None):
        is_story = isinstance(script, dict) and bool(str(script.get("story_person") or "").strip())
        person = str(script.get("story_person") or "").strip() if is_story else ""
        if is_story:
            print(f"🎬 Verified real-video Story media routing: {person}")
            return story_real_video_media.generate_media(script, output_dir, config, gim=gim)
        import stock_search
        return stock_search.generate_media(script, output_dir, config, gim=gim)
    identity_generate_media._mint_story_identity_wrapper = True
    import stock_media_resilient
    stock_media_resilient.generate_media = identity_generate_media

    # A topic can pass metadata-only discovery and still fail the visual
    # identity gate (as happened with Shackleton: Commons returned South
    # Georgia footage, but Gemini correctly rejected it). Treat that as a
    # content-availability failure, not a broken CI run: release the subject,
    # choose another unused subject, and retry the complete Story generation.
    max_story_attempts = 4
    for attempt in range(1, max_story_attempts + 1):
        try:
            runpy.run_path("interactive_main.py", run_name="__main__")
            break
        except Exception as exc:
            if Path(".story_gemini_quota_deferred").exists():
                print("⏸️ Story Shorts deferred because Gemini quota is exhausted; no final video is expected in this run.")
                return
            if _story_defer_failure(exc):
                _defer_story(str(exc))
                return
            if not _story_media_failure(exc):
                raise
            pending = interactive_topics.get_pending_story() or {}
            failed_person = str(pending.get("person") or "").strip()
            if not failed_person:
                # The generated script still identifies the person even if the
                # durable reservation was changed by a later stage.
                failed_person = str(getattr(exc, "story_person", "") or "").strip()
            _release_failed_story(failed_person)
            if attempt >= max_story_attempts:
                _defer_story(
                    f"Unable to obtain verified real-person footage after {max_story_attempts} subjects; "
                    "no generic stock/photo fallback was used."
                )
                return
            print(
                f"🔁 Story media recovery: subject {failed_person or 'unknown'} failed identity/availability "
                f"gate; retrying with a new unused subject ({attempt + 1}/{max_story_attempts})",
                flush=True,
            )

    if Path(".story_gemini_quota_deferred").exists() or Path(".story_deferred").exists():
        return
    _validate_final_videos()


if __name__ == "__main__":
    main()
