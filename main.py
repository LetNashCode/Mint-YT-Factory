"""Mint-YT-Factory production pipeline.

CURRENT MODE: ENTERTAINMENT-FIRST

Topic -> entertaining script/storyboard -> TTS -> AI visuals -> music ->
assembly -> optional YouTube upload.

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

from topics import get_next_topic, save_next_short, commit_topic
from generate_script import generate_script
from tts import synthesize_script
from generate_images import generate_images
from music import download_music
from assemble import assemble_video
from upload_youtube import upload_video


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


def ensure_next_topic_is_spoken(script):
    """Guarantee the queued next topic is actually spoken in the final scene.

    Gemini is instructed to do this already, but a post-generation guard is
    safer than allowing a successful video to publish without the continuation
    promise that the topic engine relies on.
    """
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

    # Keep the continuation as the final spoken sentence. Do not reveal it in
    # the description and do not use "next video" / "coming next" language.
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
    title = str(script.get("title", "Wonder Minute Short")).strip()[:100]
    description = str(script.get("description", "")).strip()
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
    print("=" * 80)

    topic = get_next_topic()
    if not topic:
        raise RuntimeError("No topic available.")

    print(f"🎯 CURRENT TOPIC: {topic}")

    print("=" * 80)
    print("✍️ GENERATING ENTERTAINING STORY")
    print("=" * 80)
    script = generate_script(topic, config, None)
    script = ensure_next_topic_is_spoken(script)

    next_topic = str(script.get("next_short", {}).get("topic", "")).strip()
    if not next_topic:
        raise RuntimeError("Generated script did not provide next_short.topic.")

    workdir = os.path.join("output", str(int(time.time())))
    os.makedirs(workdir, exist_ok=True)
    save_json(script, os.path.join(workdir, "script.json"))

    print(f"✅ Script ready: {workdir}/script.json")
    print(f"➡️ Next Short: {next_topic}")
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

    if not config.get("upload", {}).get("auto_upload", False):
        print("⚠️ AUTO UPLOAD DISABLED — topic remains uncommitted.")
        return

    title, description = build_youtube_metadata(script)

    print("=" * 80)
    print("🚀 UPLOADING SHORT")
    print("=" * 80)
    upload_result = upload_video(final_video, title, description, config)
    print(f"✅ Upload completed: {upload_result}")

    # Analytics must NEVER make an already-successful YouTube upload fail.
    # The durable registry is committed by the workflow after the run.
    try:
        from youtube_analytics import record_upload
        record_upload(upload_result, topic, title, workdir)
    except Exception as analytics_error:
        print(f"⚠️ Analytics registry update skipped: {analytics_error}")

    print("=" * 80)
    print("🔗 SAVING NEXT SHORT")
    print("=" * 80)
    if not save_next_short(next_topic):
        raise RuntimeError("Upload succeeded but next_short could not be saved.")

    print(f"✅ Next Short queued: {next_topic}")

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
    print(f"Next run: {next_topic}")
    print(f"Artifacts: {workdir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
