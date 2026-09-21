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
    runpy.run_path("interactive_main.py", run_name="__main__")
    _validate_final_videos()


if __name__ == "__main__":
    main()
