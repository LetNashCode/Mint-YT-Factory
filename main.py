"""Mint-YT-Factory production pipeline.

CURRENT MODE: ENTERTAINMENT-FIRST

Topic -> entertaining script/storyboard -> TTS -> AI visuals -> music ->
assembly -> final quality validation -> optional YouTube upload.

Continuation is treated as a production contract: the exact next topic is
locked before narration, spoken as the final sentence, and queued unchanged.
The final scene is also compacted so the continuation is fully spoken instead
of being clipped at the 45-second render boundary.
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


CONTINUATION_MANIFEST = "continuation_state.json"


def load_config():
    with open("config.yaml", "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict):
        raise RuntimeError("config.yaml is invalid.")
    return config


def save_json(data, path):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def _normalise_topic_text(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _topic_is_same(a, b):
    return _normalise_topic_text(a) == _normalise_topic_text(b)


def _word_count(value):
    return len(re.findall(r"\b[\w'-]+\b", str(value or "")))


def _split_sentences(text):
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", str(text or "").strip())
        if part.strip()
    ]


def _compact_payoff(narration, max_words=10):
    """Keep a short, coherent payoff before the continuation sentence."""
    sentences = _split_sentences(narration)
    if not sentences:
        return "That is the strange part."

    # Gemini often puts its best payoff in the final sentence. Keep that
    # sentence first, then add earlier short context only if it still fits.
    chosen = []
    total = 0
    for sentence in reversed(sentences):
        # Never keep an old continuation sentence; main.py owns it now.
        if re.search(r"\b(next video|coming next|stay tuned|part 2)\b", sentence, re.I):
            continue
        words = _word_count(sentence)
        if words == 0:
            continue
        if total + words <= max_words:
            chosen.insert(0, sentence.rstrip(".!? "))
            total += words
        elif not chosen:
            short_words = re.findall(r"\S+", sentence)[:max_words]
            chosen.insert(0, " ".join(short_words).rstrip(".!? "))
            break
        else:
            break

    payoff = " ".join(chosen).strip()
    if not payoff:
        payoff = "And that is the strange part"
    return payoff.rstrip(".!? ") + "."


def _remove_existing_continuation(narration, next_topic):
    """Remove an already-appended teaser so it can be rebuilt exactly once."""
    sentences = _split_sentences(narration)
    topic_key = _normalise_topic_text(next_topic)
    kept = []
    for sentence in sentences:
        key = _normalise_topic_text(sentence)
        if topic_key and topic_key in key:
            continue
        if re.search(r"\b(bigger question|one more thing to wonder about|next video|coming next|stay tuned|part 2)\b", sentence, re.I):
            continue
        kept.append(sentence)
    return " ".join(kept).strip()


def _build_locked_final_sentence(next_topic):
    # Keep this sentence short enough to be completely spoken inside Scene 7.
    return f"And next: {next_topic}."


def lock_next_topic(script, current_topic):
    """Lock one canonical next topic BEFORE TTS and build a short final tease.

    The exact same canonical value is used for:
      1. the final spoken sentence,
      2. script.json,
      3. the post-upload continuation queue.

    Scene 7 is deliberately compacted because the old guard could append a
    long continuation to an already-full 7-second scene. The result was a
    teaser that ended mid-sentence (often only the final word was heard).
    """
    next_short = script.get("next_short") or {}
    candidate = str(next_short.get("topic", "")).strip()
    if not candidate:
        raise RuntimeError("Generated script did not provide next_short.topic.")

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

    # Keep future topics short enough to fit naturally in the final sentence.
    if _word_count(canonical) > 7:
        print(f"⚠️ Next topic is too long for a clean spoken tease: {canonical}")
        canonical = _generate_topic(used)
        if _word_count(canonical) > 7:
            raise RuntimeError(f"Generated continuation is still too long: {canonical}")
        print(f"🔗 Short canonical next topic: {canonical}")

    script["next_short"]["topic"] = canonical
    script["next_short"]["teaser"] = _build_locked_final_sentence(canonical)

    scenes = script.get("scene_plan")
    if not isinstance(scenes, list) or len(scenes) != 7:
        raise RuntimeError("Script must contain exactly 7 scenes.")

    final_scene = scenes[-1]
    original = str(final_scene.get("narration", "")).strip()
    base = _remove_existing_continuation(original, canonical)
    payoff = _compact_payoff(base, max_words=10)
    teaser = _build_locked_final_sentence(canonical)
    final_scene["narration"] = f"{payoff} {teaser}".strip()
    final_scene["subtitle_text"] = final_scene["narration"]
    final_scene["pause_after_ms"] = 250
    final_scene["emotional_tone"] = "satisfied"
    final_scene["music_cue"] = "fade_out"

    # Rebuild highlights so the final teaser is caption-highlighted correctly.
    teaser_words = re.findall(r"\b[\w'-]+\b", canonical)
    final_scene["caption_highlights"] = [
        {"word": word, "emphasis": "strong"}
        for word in teaser_words[:3]
    ] or [{"word": canonical.split()[0], "emphasis": "strong"}]
    final_scene["emphasis_word"] = teaser_words[0] if teaser_words else canonical.split()[0]

    # Hard contract: the exact canonical topic must occur once in the final
    # narration and nowhere in Scenes 1-6.
    canonical_key = _normalise_topic_text(canonical)
    final_key = _normalise_topic_text(final_scene["narration"])
    if canonical_key not in final_key:
        raise RuntimeError("Canonical next topic was not inserted into final narration.")

    for scene in scenes[:6]:
        if canonical_key and canonical_key in _normalise_topic_text(scene.get("narration", "")):
            raise RuntimeError("Next topic appeared before Scene 7.")

    print(f"🎯 CANONICAL NEXT TOPIC: {canonical}")
    print(f"🗣️ FINAL SPOKEN TEASE: {final_scene['narration']}")
    print(f"⏱️ Scene 7 words: {_word_count(final_scene['narration'])}")
    return script, canonical


def write_continuation_manifest(current_topic, next_topic, status, workdir=""):
    data = {
        "status": status,
        "current_topic": current_topic,
        "next_topic": next_topic,
        "workdir": workdir,
        "updated_at": int(time.time()),
    }
    save_json(data, CONTINUATION_MANIFEST)
    print(f"🧾 Continuation manifest: {status} -> {next_topic}")


def build_youtube_metadata(script):
    """Build metadata from the current topic only."""
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
    print("Continuation lock: ENABLED")
    print("Scene 7 ending guard: ENABLED")
    print("=" * 80)

    topic = get_next_topic()
    if not topic:
        raise RuntimeError("No topic available.")

    print(f"🎯 CURRENT TOPIC: {topic}")

    print("=" * 80)
    print("✍️ GENERATING ENTERTAINING STORY")
    print("=" * 80)
    script = generate_script(topic, config, None)
    script, next_topic = lock_next_topic(script, topic)

    workdir = os.path.join("output", str(int(time.time())))
    os.makedirs(workdir, exist_ok=True)
    save_json(script, os.path.join(workdir, "script.json"))
    write_continuation_manifest(topic, next_topic, "locked", workdir)

    print(f"✅ Script ready: {workdir}/script.json")
    print(f"➡️ LOCKED Next Short: {next_topic}")
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
    print("🗣️ VERIFYING NARRATION BUDGET")
    print("=" * 80)
    # The compact Scene 7 should leave a small visual/music tail instead of
    # ending exactly on the final spoken syllable.
    try:
        from moviepy.editor import AudioFileClip
        narration_check = AudioFileClip(audio)
        narration_duration = float(narration_check.duration)
        narration_check.close()
        print(f"Narration duration: {narration_duration:.2f}s")
        if narration_duration > 44.35:
            raise RuntimeError(
                f"Narration is too long ({narration_duration:.2f}s). "
                "Scene 7 must be shortened before rendering."
            )
        print(f"Ending safety margin: {44.35 - narration_duration:.2f}s")
    except RuntimeError:
        raise
    except Exception as error:
        print(f"⚠️ Narration duration check skipped: {error}")

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

    # Mark the exact locked continuation as published BEFORE touching the
    # durable queue. If the runner crashes after upload, the manifest tells
    # the next run which topic must continue.
    write_continuation_manifest(topic, next_topic, "published", workdir)

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
    if not _topic_is_same(queued_topic, next_topic):
        raise RuntimeError(
            f"CONTINUATION INTEGRITY FAILURE: spoken={next_topic!r}, queued={queued_topic!r}"
        )

    print(f"✅ Next Short queued EXACTLY: {queued_topic}")

    print("=" * 80)
    print("📌 COMMITTING CURRENT TOPIC")
    print("=" * 80)
    committed = commit_topic(topic)
    if committed is False:
        raise RuntimeError("Upload succeeded but current topic could not be committed.")

    write_continuation_manifest(topic, next_topic, "queued", workdir)

    print("=" * 80)
    print("🎉 ENTERTAINMENT-FIRST PIPELINE COMPLETE")
    print("=" * 80)
    print(f"Published: {topic}")
    print(f"Next run MUST use: {next_topic}")
    print(f"Artifacts: {workdir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
