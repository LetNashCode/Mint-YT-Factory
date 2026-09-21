"""Run Story Shorts with identity-first media routing and topic uniqueness protection."""
from __future__ import annotations

import runpy

import story_archival_media
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
        return original_upload(video_path, optimized, description, config, *args, **kwargs)

    optimized_upload._mint_story_title_optimizer = True
    upload_youtube.upload_video = optimized_upload


def main() -> None:
    next_number = validate_story_sequence_state()
    print(f"🔐 Story sequence preflight passed: next Story #{next_number}")

    def validated_next_story_number() -> int:
        return next_number
    validated_next_story_number._mint_validated_sequence_number = True
    interactive_topics.next_story_number = validated_next_story_number

    story_topic_uniqueness.install()
    _patch_story_portrait_export()
    _patch_story_titles()

    # IMPORTANT: stock_media_resilient intentionally routes Story scripts back
    # to Wikimedia archival media. For the emergency fallback we must call the
    # underlying stock director directly; otherwise the supposed fallback simply
    # invokes the same archival adapter again and can never recover.
    import stock_search
    stock_fallback = stock_search.generate_media

    def identity_generate_media(script, output_dir, config, gim=None):
        is_story = isinstance(script, dict) and bool(str(script.get("story_person") or "").strip())
        person = str(script.get("story_person") or "").strip() if is_story else ""
        if is_story:
            print(f"📚 Direct archival Story media routing: {person}")
            try:
                return story_archival_media.generate_media(script, output_dir, config, gim=gim)
            except Exception as archival_error:
                print(
                    "⚠️ Archival media unavailable; activating subject-specific "
                    f"stock fallback for {person}: {type(archival_error).__name__}: {archival_error}"
                )
                try:
                    return stock_fallback(script, output_dir, config, gim=gim)
                except Exception as stock_error:
                    raise RuntimeError(
                        f"Both archival and subject-specific stock media failed for {person}. "
                        f"Archival error: {archival_error}; Stock error: {stock_error}"
                    ) from stock_error
        return stock_fallback(script, output_dir, config, gim=gim)

    identity_generate_media._mint_story_identity_wrapper = True
    import stock_media_resilient
    stock_media_resilient.generate_media = identity_generate_media
    runpy.run_path("interactive_main.py", run_name="__main__")


if __name__ == "__main__":
    main()
