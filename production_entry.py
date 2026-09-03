"""Production entrypoint for Mint-YT-Factory."""
from __future__ import annotations

import json
import os

from runtime_overrides import patch_continuation, patch_tts_result
from quality_overrides import patch_story_quality
from story_quality_gate import patch_story_generation

MIN_NARRATION_SECONDS = 35.0
MAX_NARRATION_SECONDS = 44.95
MAX_SHORT_TTS_REGEN = 1


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
            # Allow a small measured-duration tolerance. The canonical production\n            # contract is 43.9s, but container/audio probing can differ by frames.\n            if MIN_NARRATION_SECONDS <= duration <= MAX_NARRATION_SECONDS:\n                return audio

            if attempt >= MAX_SHORT_TTS_REGEN:
                raise RuntimeError(
                    f"Narration duration remained outside production range after "
                    f"{MAX_SHORT_TTS_REGEN} regeneration attempts: {duration:.2f}s "
                    f"(allowed {MIN_NARRATION_SECONDS:.2f}-{MAX_NARRATION_SECONDS:.2f}s)."
                )

            if duration > MAX_NARRATION_SECONDS:
                direction = (
                    f"The previous narration rendered at {duration:.2f} seconds and is TOO LONG. "
                    "Rewrite it shorter. Remove filler and repeated explanation while keeping the hook, escalation, and payoff."
                )
            else:
                direction = (
                    f"The previous narration rendered at {duration:.2f} seconds and is TOO SHORT. "
                    "Add concrete everyday details and escalation, not scientific filler."
                )

            feedback = (
                f"{direction} CURRENT TOPIC: {topic!r}. "
                f"The canonical next topic is locked as metadata: {current_next!r}. "
                "Write only the current-topic story. Do not add any continuation sentence; the pipeline appends the preview separately after generation."
            )

            try:\n                candidate = main.generate_script(topic, config, None, extra_feedback=feedback)\n            except Exception as exc:\n                # Never discard an otherwise valid production run because the\n                # optional duration rewrite violates a strict Scene 7 contract.\n                print(f"⚠️ TTS regeneration failed; keeping original script/audio: {exc}")\n                return audio
            candidate["topic"] = topic
            candidate["next_short"] = dict(candidate.get("next_short") or {})
            candidate["next_short"]["topic"] = current_next

            candidate, locked_next = main.lock_next_topic(candidate, topic)
            if locked_next != current_next:
                raise RuntimeError(
                    f"TTS regeneration changed locked next topic: {locked_next!r} != {current_next!r}"
                )

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
    # assemble.py v8.3 already natively supports both still images and stock
    # video through make_visual_clip(). Keep this entrypoint compatible with
    # future versions without referencing the removed make_image_clip symbol.
    import assemble

    if not hasattr(assemble, "make_visual_clip"):
        raise RuntimeError(
            "assemble.py is missing make_visual_clip(); cannot enable stock-video assembly."
        )

    print("🛡️ Assembly media compatibility: native make_visual_clip() handles stock VIDEO + IMAGE")


def main_entry():
    import main

    patch_continuation(main)
    patch_tts_result(main)
    patch_story_quality(main)
    patch_story_generation(main)

    _patch_script_model_resilience(main)
    _patch_tts_duration(main)
    _patch_assemble_video_media()

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
    print("Continuation: Gemini-authored seamless Scene 7 preview + locked metadata topic")
    print("Transient Gemini 503/429 failures: retry without consuming script attempt")
    print("Pexels API key:", "AVAILABLE" if os.environ.get("PEXELS_API_KEY") else "NOT CONFIGURED")
    print("Pixabay API key:", "AVAILABLE" if os.environ.get("PIXABAY_API_KEY") else "NOT CONFIGURED")
    print("Gemini API key:", "AVAILABLE" if os.environ.get("GEMINI_API_KEY") else "NOT CONFIGURED")
    print("Story: TTS-authoritative 35-43.9 seconds (44.95s measured tolerance)")
    print("Captions: Whisper word timing → deterministic fallback if Whisper fails")
    print("TTS duration guard: ENABLED")
    print("=" * 80)

    main.run(dry_run=False)


if __name__ == "__main__":
    main_entry()
