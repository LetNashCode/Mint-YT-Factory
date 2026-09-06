"""Production entrypoint for Mint-YT-Factory."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from runtime_overrides import patch_continuation, patch_tts_result
from quality_overrides import patch_story_quality
from story_quality_gate import patch_story_generation

MIN_NARRATION_SECONDS = 35.0
MAX_NARRATION_SECONDS = 44.95
MAX_SHORT_TTS_REGEN = 1
COMPLETED_PUBLICATIONS = Path("completed_publications.json")


def _patch_script_model_resilience(main):
    original = main.generate_script
    if getattr(original, "_mint_model_resilient", False):
        return
    globals_dict = getattr(original, "__globals__", {})
    primary = "gemini-flash-lite-latest"
    globals_dict["MODEL_NAME"] = primary

    def resilient(topic, config, research=None, extra_feedback=""):
        globals_dict["MODEL_NAME"] = primary
        print(f"🧠 Script model: {primary}")
        return original(topic, config, research, extra_feedback=extra_feedback)

    resilient._mint_model_resilient = True
    main.generate_script = resilient
    print(f"🛡️ Script Gemini model: {primary}")


def _patch_tts_duration(main):
    from moviepy.editor import AudioFileClip

    original = main.synthesize_script
    if getattr(original, "_mint_duration_guard", False):
        return

    def synthesize(script, config, out_dir):
        current_next = ((script.get("next_short") or {}).get("topic") or "").strip()
        topic = str(script.get("topic", "")).strip()
        for attempt in range(MAX_SHORT_TTS_REGEN + 1):
            audio = original(script, config, out_dir)
            clip = AudioFileClip(audio)
            try:
                duration = float(clip.duration)
            finally:
                clip.close()
            print(f"🎯 TTS duration gate: {duration:.2f}s")
            if MIN_NARRATION_SECONDS <= duration <= MAX_NARRATION_SECONDS:
                return audio
            if attempt >= MAX_SHORT_TTS_REGEN:
                raise RuntimeError(
                    f"Narration duration remained outside production range after {MAX_SHORT_TTS_REGEN} regeneration attempts: {duration:.2f}s "
                    f"(allowed {MIN_NARRATION_SECONDS:.2f}-{MAX_NARRATION_SECONDS:.2f}s)."
                )
            direction = (
                f"The previous narration rendered at {duration:.2f} seconds and is TOO LONG. Rewrite it shorter. Remove filler and repeated explanation while keeping the hook, escalation, and payoff."
                if duration > MAX_NARRATION_SECONDS
                else f"The previous narration rendered at {duration:.2f} seconds and is TOO SHORT. Add concrete everyday details and escalation, not scientific filler."
            )
            feedback = (
                f"{direction} CURRENT TOPIC: {topic!r}. The canonical next topic is locked as metadata: {current_next!r}. "
                "Write only the current-topic story. Do not add any continuation sentence; the pipeline appends the preview separately after generation."
            )
            try:
                candidate = main.generate_script(topic, config, None, extra_feedback=feedback)
            except Exception as exc:
                print(f"⚠️ TTS regeneration failed; keeping original script/audio: {exc}")
                return audio
            candidate["topic"] = topic
            candidate["next_short"] = dict(candidate.get("next_short") or {})
            candidate["next_short"]["topic"] = current_next
            candidate, locked_next = main.lock_next_topic(candidate, topic)
            if locked_next != current_next:
                raise RuntimeError(f"TTS regeneration changed locked next topic: {locked_next!r} != {current_next!r}")
            script.clear()
            script.update(candidate)
            workdir = os.path.dirname(os.path.dirname(os.path.abspath(out_dir)))
            try:
                with open(os.path.join(workdir, "script.json"), "w", encoding="utf-8") as handle:
                    json.dump(script, handle, indent=2, ensure_ascii=False)
                if hasattr(main, "write_continuation_manifest"):
                    main.write_continuation_manifest(topic, current_next, "locked", workdir)
            except Exception as exc:
                print(f"⚠️ Could not refresh regenerated script artifact: {exc}")
        return audio

    synthesize._mint_duration_guard = True
    main.synthesize_script = synthesize


def _patch_assemble_video_media():
    import assemble
    if not hasattr(assemble, "make_visual_clip"):
        raise RuntimeError("assemble.py is missing make_visual_clip(); cannot enable stock-video assembly.")
    print("🛡️ Assembly media compatibility: native make_visual_clip() handles stock VIDEO + IMAGE")


def _load_state(workdir):
    path = Path(workdir) / "publish_state.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(workdir, state):
    path = Path(workdir) / "publish_state.json"
    state["updated_at"] = int(time.time())
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _state_is_complete(state):
    """Return True only when every enabled publication destination is terminal."""
    enabled_platforms = [
        p for p in ("youtube", "instagram", "facebook")
        if (state.get(p) or {}).get("enabled", True)
    ]
    if not enabled_platforms:
        return False
    return all(
        str((state.get(p) or {}).get("status") or "").lower() in {"published", "skipped"}
        for p in enabled_platforms
    )


def _load_completed_publications():
    try:
        data = json.loads(COMPLETED_PUBLICATIONS.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _is_tombstoned(workdir, state):
    workdir_text = str(workdir).replace("\\", "/")
    youtube_id = str(
        state.get("video_id") or ((state.get("youtube") or {}).get("video_id") or "")
    ).strip()
    for item in _load_completed_publications():
        if not isinstance(item, dict):
            continue
        if str(item.get("workdir") or "").replace("\\", "/") == workdir_text:
            return True
        if youtube_id and str(item.get("video_id") or "").strip() == youtube_id:
            return True
    return False


def _record_completed_publications():
    """Persist terminal publications so an old failed Actions artifact cannot resurrect them."""
    entries = _load_completed_publications()
    by_key = {
        (str(x.get("workdir") or ""), str(x.get("video_id") or "")):
        for x in entries if isinstance(x, dict)
    }
    added = 0
    for state_path in Path("output").glob("*/publish_state.json"):
        try:
            state = _normalise_resume_state(state_path.parent, json.loads(state_path.read_text(encoding="utf-8")))
        except Exception:
            continue
        if not _state_is_complete(state):
            continue
        workdir = str(state_path.parent).replace("\\", "/")
        video_id = str(
            state.get("video_id") or ((state.get("youtube") or {}).get("video_id") or "")
        ).strip()
        key = (workdir, video_id)
        if key in by_key:
            continue
        entries.append({
            "workdir": workdir,
            "video_id": video_id,
            "topic": str(state.get("topic") or ""),
            "completed_at": int(time.time()),
        })
        by_key.add(key)
        added += 1
    if added:
        COMPLETED_PUBLICATIONS.write_text(
            json.dumps(entries[-100:], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"🪦 Publication tombstones recorded: {added}")


def _normalise_resume_state(workdir, state):
    """Repair legacy state and promote fully published artifacts to terminal."""
    changed = False
    youtube_id = str(state.get("video_id") or "").strip()
    youtube = state.get("youtube") or {}

    if youtube_id and bool(state.get("uploaded")):
        if (
            str(youtube.get("status") or "").lower() != "published"
            or str(youtube.get("video_id") or "").strip() != youtube_id
        ):
            state["youtube"] = {
                "status": "published",
                "enabled": True,
                "video_id": youtube_id,
            }
            youtube = state["youtube"]
            changed = True

    if _state_is_complete(state) and str(state.get("status") or "").lower() != "uploaded":
        state["status"] = "uploaded"
        state["uploaded"] = True
        changed = True
    elif youtube and str(youtube.get("status") or "").lower() == "published":
        instagram = state.get("instagram") or {}
        facebook = state.get("facebook") or {}
        social_incomplete = (
            str(instagram.get("status") or "").lower() not in {"published", "skipped"}
            or str(facebook.get("status") or "").lower() not in {"published", "skipped"}
        )
        if social_incomplete and str(state.get("status") or "").lower() == "youtube_published":
            state["status"] = "partial"
            changed = True

    if changed:
        _save_state(workdir, state)
    return state


def _patch_publish_resume(main):
    """Resume only genuinely incomplete publication work; never resurrect completed work."""
    original_find = main._find_pending_resume
    if not getattr(original_find, "_mint_cross_run_resume", False):
        def find_pending_resume():
            candidates = sorted(
                Path("output").glob("*/final.mp4"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for video in candidates:
                workdir = video.parent
                manifest = workdir / "publish_state.json"
                script_path = workdir / "script.json"
                if not manifest.exists() or not script_path.exists():
                    continue
                try:
                    raw_state = json.loads(manifest.read_text(encoding="utf-8"))
                    if not isinstance(raw_state, dict):
                        continue
                    state = _normalise_resume_state(workdir, raw_state)
                    if _is_tombstoned(workdir, state):
                        print(f"⏭️ Completed publication tombstone ignored: {workdir}")
                        continue
                    if _state_is_complete(state):
                        print(f"⏭️ Completed publication artifact ignored: {workdir}")
                        continue
                    status = str(state.get("status") or "").lower()
                    if status not in {"ready_for_upload", "partial", "uploading"}:
                        continue
                    script = json.loads(script_path.read_text(encoding="utf-8"))
                    return workdir, video, script, state
                except Exception:
                    continue
            # Never call main's legacy scanner here.
            return None

        find_pending_resume._mint_cross_run_resume = True
        main._find_pending_resume = find_pending_resume

    original_upload = main.upload_video
    if getattr(original_upload, "_mint_resume_upload", False):
        return

    def resumable_upload(final_video, title, description, config, *args, **kwargs):
        workdir = Path(final_video).parent
        state = _normalise_resume_state(workdir, _load_state(workdir))
        youtube = state.get("youtube") or {}
        existing_id = str(youtube.get("video_id") or state.get("video_id") or "").strip()
        if str(youtube.get("status") or "").lower() == "published" and existing_id:
            print(f"♻️ YOUTUBE STATUS: PUBLISHED | video_id={existing_id} — skipping duplicate upload")
            state["youtube"] = {"status": "published", "enabled": True, "video_id": existing_id}
            state["status"] = "partial"
            state["uploaded"] = True
            _save_state(workdir, state)
            return existing_id
        state.setdefault("youtube", {"status": "uploading", "enabled": True})
        state["status"] = "uploading"
        _save_state(workdir, state)
        result = original_upload(final_video, title, description, config, *args, **kwargs)
        video_id = str(result or "").strip()
        if not video_id:
            raise RuntimeError("Upload succeeded without a video ID; refusing to mark YouTube complete.")
        state = _load_state(workdir)
        state["youtube"] = {"status": "published", "enabled": True, "video_id": video_id}
        state["status"] = "partial"
        state["uploaded"] = True
        state["video_id"] = video_id
        _save_state(workdir, state)
        print(f"💾 Durable Publish Shorts state: YouTube complete ({video_id})")
        return video_id

    resumable_upload._mint_resume_upload = True
    main.upload_video = resumable_upload


def main_entry():
    import main
    patch_continuation(main)
    patch_tts_result(main)
    patch_story_quality(main)
    patch_story_generation(main)
    _patch_script_model_resilience(main)
    _patch_tts_duration(main)
    _patch_assemble_video_media()
    _patch_publish_resume(main)
    original_run = main.run
    if not getattr(original_run, "_mint_completion_tombstones", False):
        def run_with_completion_tombstones(*args, **kwargs):
            result = original_run(*args, **kwargs)
            _record_completed_publications()
            return result
        run_with_completion_tombstones._mint_completion_tombstones = True
        main.run = run_with_completion_tombstones
    print("=" * 80)
    print("🚀 MINT-YT-FACTORY STARTED")
    print("=" * 80)
    print("Script: entertainment-first + hard coherence gate + low-jargon contract")
    print("Visual/Search Director: Gemini")
    print("Media pipeline: stock_search.generate_media (authoritative)")
    print("Media priority: Pexels VIDEO → Pixabay VIDEO → Pexels PHOTO → Pixabay PHOTO")
    print("Visual verification: ENABLED — Gemini inspects stock candidates")
    print("Visual verification threshold: 7.5/10")
    print("Fallback: provider fallback only; no unrelated-media fallback")
    print("Continuation: production-owned canonical Scene 7 bridge + locked metadata topic")
    print("Transient Gemini 503/429 failures: retry without consuming script attempt")
    print("Pexels API key:", "AVAILABLE" if os.environ.get("PEXELS_API_KEY") else "NOT CONFIGURED")
    print("Pixabay API key:", "AVAILABLE" if os.environ.get("PIXABAY_API_KEY") else "NOT CONFIGURED")
    print("Gemini API key:", "AVAILABLE" if os.environ.get("GEMINI_API_KEY") else "NOT CONFIGURED")
    print("Story: TTS-authoritative 35-43.9 seconds (44.95s measured tolerance)")
    print("Captions: Whisper word timing → deterministic fallback if Whisper fails")
    print("TTS duration guard: ENABLED")
    print("Publish Shorts resume: cross-run recovery + terminal-completion tombstones ENABLED")
    print("=" * 80)
    main.run(dry_run=False)


if __name__ == "__main__":
    main_entry()
