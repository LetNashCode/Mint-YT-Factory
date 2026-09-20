"""Run Story Shorts with identity-first media routing and topic uniqueness protection."""
from __future__ import annotations

import runpy

import story_identity_media
import story_topic_uniqueness
import interactive_topics
from interactive_topics import validate_story_sequence_state


def _patch_story_portrait_export() -> None:
    """Apply the shared border-free portrait export after Story Shorts assembly."""
    import assemble
    from portrait_export_guard import ensure_portrait_export

    original_assemble = getattr(assemble, "assemble_video", None)
    if original_assemble is None or getattr(original_assemble, "_mint_story_portrait_guard", False):
        return

    def guarded_assemble_video(*args, **kwargs):
        result = original_assemble(*args, **kwargs)
        output_path = kwargs.get("output_path")
        if output_path is None and args:
            output_path = args[-1]
        if output_path:
            ensure_portrait_export(output_path)
        return result

    guarded_assemble_video._mint_story_portrait_guard = True
    assemble.assemble_video = guarded_assemble_video
    print("📱 Story portrait guard: full-frame 9:16 crop enabled")


def main() -> None:
    # Hard-stop before topic generation, candidate-pool mutation, or person reservation.
    # A corrupt/stale sequence state must never trigger a search for another person.
    next_number = validate_story_sequence_state()
    print(f"🔐 Story sequence preflight passed: next Story #{next_number}")

    # Make the validated number authoritative for the entire run. This prevents
    # interactive_main.py from independently deriving a stale number after other
    # startup hooks have run.
    def validated_next_story_number() -> int:
        return next_number

    validated_next_story_number._mint_validated_sequence_number = True
    interactive_topics.next_story_number = validated_next_story_number

    story_topic_uniqueness.install()
    _patch_story_portrait_export()

    import stock_media_resilient

    original = stock_media_resilient.generate_media

    def identity_generate_media(script, output_dir, config, gim=None):
        is_story = isinstance(script, dict) and bool(str(script.get("story_person") or "").strip())
        if is_story:
            person = str(script.get("story_person") or "").strip()
            story_identity_media.begin_story(person)
            print(f"👤 Identity-first Story routing enabled for: {person}")
        try:
            return original(script, output_dir, config, gim=gim)
        finally:
            if is_story:
                story_identity_media.end_story()

    identity_generate_media._mint_story_identity_wrapper = True
    stock_media_resilient.generate_media = identity_generate_media
    runpy.run_path("interactive_main.py", run_name="__main__")


if __name__ == "__main__":
    main()
