"""Mint-YT-Factory production pipeline.

CURRENT MODE: ENTERTAINMENT-FIRST

Topic -> entertaining script/storyboard -> TTS -> AI visuals -> music ->
assembly -> final quality validation -> optional YouTube upload.

The pipeline also keeps a durable continuation state and a lightweight
YouTube performance registry so future production can learn from actual
channel results.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time

import yaml

from topics import (
    get_next_topic,
    save_next_short,
    commit_topic,
    validate_topic_for_pipeline,
    _generate_topic,
    _read_used,
    _PENDING_PREFIX,
)
from generate_script import generate_script
from tts import synthesize_script
from generate_images import generate_images
from music import download_music
from assemble import assemble_video
from upload_youtube import upload_video
from validate_video import validate_final_video


def load_config():
    with open("config.yaml", "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise RuntimeError("config.yaml is invalid.")
    return config


def save_json(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def _normalise_topic_text(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _topic_is_same(a, b):
    return _normalise_topic_text(a) == _normalise_topic_text(b)


def lock_next_topic(script, current_topic):
    """Resolve the exact next-video topic BEFORE TTS/rendering.

    The old pipeline generated the teaser first and only later called
    save_next_short(). That function could repair an invalid/duplicate topic,
    meaning the spoken teaser and the queued topic could silently diverge.

    This function makes one canonical topic authoritative before narration is
    synthesized. The exact same value is then persisted after a successful
    upload.
    """
    next_short = script.get("next_short") or {}
    candidate = str(next_short.get("topic", "")).strip()
    if not candidate:
        raise RuntimeError("Generated script did not provide next_short.topic.")

    # Include the current topic in duplicate protection even though it has not
    # been committed to used_topics.json yet.
    used = [str(current_topic)]
    used.extend(
        item for item in _read_used()
        if not str(item).startswith(_PENDING_PREFIX)
    )

    if validate_topic_for_pipeline(candidate, used=used, check_duplicate=True):
        canonical = candidate
        print(f"🔒 Next topic locked before narration: {canonical}")
    else:
        print(f"⚠️ Gemini next topic failed continuation policy: {candidate}")
        print("🔧 Generating a replacement BEFORE TTS so the spoken tease stays exact.")
        canonical = _generate_topic(used)
        if not validate_topic_for_pipeline(canonical, used=used, check_duplicate=True):
            raise RuntimeError(f"Could not create a valid canonical next topic: {canonical}")
        print(f"🔗 Canonical replacement next topic: {canonical}")

    script["next_short"]["topic"] = canonical

    # The teaser that gets spoken must contain the exact canonical topic.
    # Rebuild the final scene if Gemini used a different continuation.
    scenes = script.get("scene_plan")
    if not isinstance(scenes, list) or not scenes:
        raise RuntimeError("Script has no scene_plan.")

    final_scene = scenes[-1]
    narration = str(final_scene.get("narration", "")).strip()
    canonical_key = _normalise_topic_text(canonical)
    narration_key = _normalise_topic_text(narration)

    if canonical_key not in narration_key:
        connector = "One more thing to wonder about:"
        final_scene["narration"] = (
            f"{narration.rstrip('.!? ')}. {connector} {canonical}."
        ).strip()
        final_scene["subtitle_text"] = final_scene["narration"]
        print("🔧 Final scene updated with the canonical next topic.")

    print(f"🎯 CANONICAL NEXT TOPIC: {canonical}")
    return script, canonical


def ensure_next_topic_is_spoken(script):
    """Guarantee the queued next topic is actually spoken in the final scene."""
    next_topic = str(script.get("next_short", {}).get("topic", "")).strip()
    scenes = script.get("scene_plan")
    if not next_topic or not isinstance(scenes, list) or not scenes:
        raise RuntimeError("Script is missing a next topic or scene plan.")

    final_scene = scenes[-1]
    narration = str(final_scene.get("narration", "")).strip()
    topic_key = _normalise_topic_text(next_topic)
    narration_key = _normalise_topic_text(narration)

    if topic_key and topic_key in narration_key:
        return script

    connector = "One more thing to wonder about:"
    final_scene["narration"] = (
        f"{narration.rstrip('.!? ')}. {connector} {next_topic}."
    ).strip()
    final_scene["subtitle_text"] = final_scene["narration"]

    print("⚠️ Next topic was not spoken by Gemini.")
    print("🔧 Added a deterministic final-sentence continuation guard.")
    print(f"🔗 Spoken next topic: {next_topic}")
    return script


def build_youtube_metadata(script):
    """Build metadata from the current topic only.

    This intentionally ignores Gemini's free-form description so the next
    video's continuation topic can never leak into the current description.
    """
    topic = str(script.get("topic", "Wonder Minute curiosity")).strip()
    title = str(script.get("title", topic or "Wonder Minute Short")).strip()[:100]
    description = f"A quick look at {topic} and the everyday mystery behind it."

    tags = script.get("tags", [])
    hashtags = []
    if isinstance(tags, list):
        for tag in tags[:12]:
            tag = str(tag).strip().replace("#", "").replace(" ", "")
            if tag:
                hashtags.append(f"#{tag}")
    if hashtags:
        description = f"{description}\n\n{' '.join(hashtags)}"
    return title, description[:4500]


def run(dry_run=False):
    config = load_config()

    print("=" * 80)
    print("🚀 MINT-YT-FACTORY — ENTERTAINMENT-FIRST MODE")
    print("=" * 80)
    print("Research layer: DISABLED")
    print("Claim verification: DISABLED")
    print("Goal: make the Short entertaining first")
    print("Production render: 2160x3840 / 60 FPS / 68 Mbps")
    print("=" * 80)

    topic = get_next_topic()
    if not topic:
        raise RuntimeError("No topic available.")

    print(f"🎯 CURRENT TOPIC: {topic}")

    print("=" * 80)
    print("✍️ GENERATING ENTERTAINING STORY")
    print("=" * 80)
    script = generate_script(topic, config, None)

    # IMPORTANT: canonicalize and lock the next topic BEFORE TTS, visuals,
    # captions and upload. The teaser and future queued Short now share one
    # immutable topic value.
    script, next_topic = lock_next_topic(script, topic)
    script = ensure_next_topic_is_spoken(script)

    # Re-read after the guard so the value saved later is exactly the one that
    # was spoken in the final scene.
    next_topic = str(script.get("next_short", {}).get("topic", "")).strip()
    if not next_topic:
        raise RuntimeError("Canonical next topic is empty.")

    workdir = os.path.join("output", str(int(time.time())))
    os.makedirs(workdir, exist_ok=True)
    save_json(script, os.path.join(workdir, "script.json"))

    print(f"✅ Script ready: {workdir}/script.json")
    print(f"➡️ Next Short (locked): {next_topic}")
    print("Research: SKIPPED BY DESIGN")

    if dry_run:
        print("=" * 80)
        print("✅ DRY RUN COMPLETE — no TTS/images/video/upload")
        print("=" * 80)
        return

    print("=" * 80)
    print("🎙️ GENERATING NARRATION")
    print("=" * 80)
    audio = synthesize_script(script, config, os.path.join(workdir, "audio"))

    print("=" * 80)
    print("🖼️ GENERATING STORY-DRIVEN VISUALS")
    print("=" * 80)
    visuals = generate_images(script, os.path.join(workdir, "visuals"), config)

    print("=" * 80)
    print("🎵 SELECTING MUSIC")
    print("=" * 80)
    music = download_music(script, os.path.join(workdir, "music"))

    print("=" * 80)
    print("💥 SOUND EFFECTS DISABLED")
    print("=" * 80)
    sfx = []

    final_video = os.path.join(workdir, "final.mp4")
    print("=" * 80)
    print("🎬 ASSEMBLING SHORT")
    print("=" * 80)
    assemble_video(script, audio, visuals, music, sfx, config, final_video)

    if not os.path.exists(final_video):
        raise RuntimeError("Final video was not created.")

    print(f"✅ VIDEO CREATED: {final_video}")

    video_settings = config.get("video", {})
    target_bitrate = 68.0
    try:
        target_bitrate = float(str(video_settings.get("bitrate", "68M")).upper().replace("M", ""))
    except Exception:
        pass

    quality = validate_final_video(
        final_video,
        expected_bitrate_mbps=target_bitrate,
    )
    save_json(quality, os.path.join(workdir, "video_quality.json"))

    if not config.get("upload", {}).get("auto_upload", False):
        print("⚠️ AUTO UPLOAD DISABLED — topic remains uncommitted.")
        return

    title, description = build_youtube_metadata(script)

    print("=" * 80)
    print("🚀 UPLOADING SHORT")
    print("=" * 80)
    upload_result = upload_video(final_video, title, description, config)
    print(f"✅ Upload completed: {upload_result}")

    try:
        from youtube_analytics import record_upload
        record_upload(upload_result, topic, title, workdir)
    except Exception as analytics_error:
        print(f"⚠️ Analytics registry update skipped: {analytics_error}")

    print("=" * 80)
    print("🔗 SAVING EXACT NEXT SHORT")
    print("=" * 80)
    queued_topic = save_next_short(next_topic)
    if not queued_topic:
        raise RuntimeError("Upload succeeded but next_short could not be saved.")

    # Hard safety check: persistence must return the exact topic that was
    # spoken. If the persistence layer ever repairs it, fail loudly rather
    # than silently publishing a mismatched continuation chain.
    if not _topic_is_same(queued_topic, next_topic):
        raise RuntimeError(
            "Continuation integrity failure: queued topic differs from spoken topic. "
            f"spoken={next_topic!r} queued={queued_topic!r}"
        )

    print(f"✅ Next Short queued EXACTLY: {queued_topic}")

    print("=" * 80)
    print("📌 COMMITTING CURRENT TOPIC")
    print("=" * 80)
    committed = commit_topic(topic)
    if committed is False:
        raise RuntimeError("Upload succeeded but current topic could not be committed.")

    print("=" * 80)
    print("🎉 ENTERTAINMENT-FIRST PIPELINE COMPLETE")
    print("=" * 80)
    print(f"Published: {topic}")
    print(f"Next run: {queued_topic}")
    print(f"Artifacts: {workdir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
