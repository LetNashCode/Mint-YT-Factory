"""Mint-YT-Factory production pipeline."""
from __future__ import annotations
import argparse, json, os, re, time, yaml
from topics import get_next_topic, save_next_short, commit_topic, validate_topic_for_pipeline, _generate_topic, _read_used, _PENDING_PREFIX
from generate_script import generate_script
from tts import synthesize_script
from stock_media_resilient import generate_media
from music import download_music
from sfx import generate_sfx
from assemble import assemble_video
from upload_youtube import upload_video
from validate_video import validate_final_video
from learning_context import load_learning_context
from learning_engine import refresh_playbook
from topic_history import record_topic

CONTINUATION_MANIFEST = "continuation_state.json"
EXPECTED_UPLOAD_BITRATE_MBPS = 100.0
EXPECTED_UPLOAD_RESOLUTION = (2160, 3840)
EXPECTED_UPLOAD_FPS = 60
MAX_SCRIPT_ATTEMPTS = 4
MAX_TRANSIENT_GEMINI_RETRIES = 8


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


def _word_count(value):
    return len(re.findall(r"\b[\w'-]+\b", str(value or "")))


def _split_sentences(text):
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if p.strip()]


_BANNED_BRIDGE_PATTERNS = (
    r"^(?:and\s+)?next\b",
    r"^then\s+comes\b",
    r"^coming\s+next\b",
    r"^up\s+next\b",
    r"^stay\s+tuned\b",
    r"^part\s+2\b",
    r"^have\s+you\s+ever\s+wondered\b",
    r"^ever\s+wondered\b",
    r"^wonder\s+why\b",
    r"^curious\s+(?:why|how|what)\b",
)


def _is_canned_bridge(sentence):
    return any(re.search(pattern, str(sentence or "").strip(), re.I) for pattern in _BANNED_BRIDGE_PATTERNS)


def _content_words(value):
    stop = {
        "why", "what", "when", "where", "how", "does", "do", "did", "is", "are",
        "the", "and", "that", "this", "with", "from", "into", "your", "about",
    }
    return {
        word for word in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if len(word) >= 4 and word not in stop
    }


def _bridge_matches_topic(bridge, topic):
    topic_words = _content_words(topic)
    if not topic_words:
        return True
    bridge_words = _content_words(bridge)
    return bool(topic_words & bridge_words)


def _generate_natural_bridge(current_topic, next_topic):
    """Build a deterministic, natural handoff without another Gemini failure point.

    The current story is generated and validated independently. The exact next topic is
    then inserted once by the pipeline so continuation cannot fail because a model omitted,
    paraphrased, duplicated, or formatted the topic incorrectly.
    """
    current = str(current_topic or "").strip().rstrip(".!?")
    nxt = str(next_topic or "").strip().rstrip(".!?")
    if not nxt:
        raise RuntimeError("Continuation topic is empty.")
    return f"That little everyday mystery opens another one: {nxt}."

def _lock_canonical_topic(script, current_topic):
    """Lock a valid next topic, repairing missing model metadata instead of failing."""
    used = [str(current_topic)]
    used.extend(item for item in _read_used() if not str(item).startswith(_PENDING_PREFIX))

    candidate = str((script.get("next_short") or {}).get("topic", "")).strip()
    if not validate_topic_for_pipeline(candidate, used=used, check_duplicate=True):
        # next_short is production metadata, not narration. A missing/bad model field
        # must not discard an otherwise good current-topic story.
        candidate = _generate_topic(used)
        print("🛠️ Repaired invalid next_short.topic with topic engine: " + candidate)

    if _word_count(candidate) > 7:
        raise RuntimeError("Generated next topic is too long for continuation metadata: " + candidate)

    script.setdefault("next_short", {})["topic"] = candidate
    return candidate

def lock_next_topic(script, current_topic):
    """Lock metadata and append the preview separately from story generation."""
    canonical = _lock_canonical_topic(script, current_topic)
    final_scene = script["scene_plan"][-1]
    bridge = _generate_natural_bridge(current_topic, canonical)
    payoff = str(final_scene.get("narration", "")).strip()
    if payoff and not payoff.endswith((".", "!", "?")):
        payoff += "."
    final_scene["narration"] = (payoff + " " + bridge).strip()
    final_scene["subtitle_text"] = final_scene["narration"]
    script.setdefault("next_short", {})["teaser"] = bridge
    print("🔒 Canonical next topic: " + canonical)
    print("🗣️ GEMINI FINAL BRIDGE: " + bridge)
    return script, canonical

def _is_transient_gemini_error(error):
    text = str(error or "").lower()
    markers = (
        "503", "unavailable", "high demand", "resource exhausted",
        "429", "rate limit", "deadline exceeded", "timeout", "temporarily",
    )
    return any(marker in text for marker in markers)


def write_continuation_manifest(current_topic, next_topic, status, workdir=""):
    save_json({
        "status": status,
        "current_topic": current_topic,
        "next_topic": next_topic,
        "workdir": workdir,
        "updated_at": int(time.time()),
    }, CONTINUATION_MANIFEST)


def build_youtube_metadata(script):
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
        description += "\n\n" + " ".join(hashtags)
    return title, description[:4500]


def refresh_learning_before_generation():
    print("=" * 80)
    print("📊 REFRESHING LIVE YOUTUBE ANALYTICS BEFORE GENERATION")
    print("=" * 80)
    try:
        from youtube_analytics import refresh_registry
        summary = refresh_registry()
        print(f"📊 Analytics refreshed: {summary.get('video_count', 0)} videos | optimization_ready={summary.get('optimization_ready', False)}")
    except Exception as error:
        print(f"⚠️ Live analytics refresh unavailable: {type(error).__name__}: {error}")
    try:
        playbook = refresh_playbook()
        print(f"🧠 Learning playbook refreshed: {playbook.get('video_count', 0)} videos | learning_ready={playbook.get('learning_ready', False)}")
    except Exception as error:
        print(f"⚠️ Learning playbook refresh unavailable: {type(error).__name__}: {error}")


def _generate_valid_script(topic, config, learning_context, engagement_feedback):
    """Generate the current-topic story first; continuation metadata is repairable."""
    feedback = learning_context + engagement_feedback + """
CONTINUATION ARCHITECTURE:
Write ONLY the complete 7-scene story for the CURRENT TOPIC.
Scene 7 must end with a satisfying payoff for the CURRENT TOPIC.
Do not put a future-topic teaser, preview, CTA, or continuation sentence into any scene.
Return next_short.topic as metadata when possible. The production pipeline can repair
missing continuation metadata after the current story passes its quality gates.
"""
    last_error = None
    valid_attempt = 0
    transient_attempt = 0

    while valid_attempt < MAX_SCRIPT_ATTEMPTS:
        try:
            script = generate_script(topic, config, None, extra_feedback=feedback)
            _lock_canonical_topic(script, topic)
            return script
        except Exception as error:
            last_error = error
            if _is_transient_gemini_error(error) and transient_attempt < MAX_TRANSIENT_GEMINI_RETRIES:
                transient_attempt += 1
                delay = min(45, 5 * transient_attempt)
                print(f"⏳ Transient Gemini failure — retrying without consuming script attempt ({transient_attempt}/{MAX_TRANSIENT_GEMINI_RETRIES}) in {delay}s: {error}")
                time.sleep(delay)
                continue
            valid_attempt += 1
            print(f"⚠️ Story generation failed ({valid_attempt}/{MAX_SCRIPT_ATTEMPTS}): {error}")

    raise RuntimeError(
        f"Could not generate a valid current-topic story after {MAX_SCRIPT_ATTEMPTS} attempts: {last_error}"
    )

def run(dry_run=False):
    config = load_config()
    print("=" * 80)
    print("🚀 MINT-YT-FACTORY — ENTERTAINMENT-FIRST + SELF-LEARNING + SFX")
    print("=" * 80)
    print("🧠 Self-learning: ENABLED")
    print("💬 Engagement learning: sequential comment/share experiments ENABLED")

    refresh_learning_before_generation()
    topic = get_next_topic()
    if not topic:
        raise RuntimeError("No topic available.")
    print(f"🎯 CURRENT TOPIC: {topic}")

    try:
        from engagement_experiments import assign, summarize
        engagement = assign(topic)
        print(f"🧪 Engagement experiment: {engagement['experiment']} | phase={engagement['phase']}")
        print(f"💬 Planned comment: {engagement['comment']}")
        print(f"🔄 Share trigger: {engagement['share_prompt']}")
        print(f"📊 Existing experiment results: {json.dumps(summarize(), ensure_ascii=False)}")
    except Exception as error:
        engagement = {"experiment": "none", "phase": "disabled", "spoken_prompt": "", "comment": "", "share_prompt": ""}
        print(f"⚠️ Engagement experiment setup skipped: {type(error).__name__}: {error}")

    learning_context = load_learning_context()
    engagement_feedback = (
        f"\nENGAGEMENT EXPERIMENT FOR THIS SHORT: {engagement['experiment']}"
        f"\nUse the mechanic naturally if it fits. Never sound like engagement bait."
        f"\nSuggested spoken interaction: {engagement['spoken_prompt']}"
        "\nDo not add generic like/subscribe language.\n"
    )

    print("✍️ GENERATING ENTERTAINING STORY WITH LEARNED PATTERNS")
    script = _generate_valid_script(topic, config, learning_context, engagement_feedback)
    script, next_topic = lock_next_topic(script, topic)
    script["engagement"] = {
        "experiment": engagement["experiment"],
        "phase": engagement["phase"],
        "spoken_prompt": engagement["spoken_prompt"],
        "comment": engagement["comment"],
        "share_prompt": engagement["share_prompt"],
    }

    workdir = os.path.join("output", str(int(time.time())))
    os.makedirs(workdir, exist_ok=True)
    save_json(script, os.path.join(workdir, "script.json"))
    write_continuation_manifest(topic, next_topic, "locked", workdir)
    print(f"✅ Script ready: {workdir}/script.json")

    if dry_run:
        print("✅ DRY RUN COMPLETE")
        return

    audio = synthesize_script(script, config, os.path.join(workdir, "audio"))
    visuals = generate_media(script, os.path.join(workdir, "visuals"), config)
    sfx = generate_sfx(script, os.path.join(workdir, "sfx"))
    music = download_music(script, os.path.join(workdir, "music"))
    final_video = os.path.join(workdir, "final.mp4")
    assemble_video(script, audio, visuals, music, sfx, config, final_video)

    if not os.path.exists(final_video):
        raise RuntimeError("Final video was not created.")

    quality = validate_final_video(final_video, expected_bitrate_mbps=EXPECTED_UPLOAD_BITRATE_MBPS)
    save_json(quality, os.path.join(workdir, "validation.json"))

    if not quality.get("ok", False):
        raise RuntimeError("Final video validation failed.")
    if (quality.get("width"), quality.get("height")) != EXPECTED_UPLOAD_RESOLUTION:
        raise RuntimeError("Upload blocked: final video is not 2160x3840 4K portrait.")
    if abs(float(quality.get("fps", 0)) - EXPECTED_UPLOAD_FPS) > 0.05:
        raise RuntimeError("Upload blocked: final video is not 60 fps.")
    if float(quality.get("bitrate_mbps", 0)) < EXPECTED_UPLOAD_BITRATE_MBPS * 0.95:
        raise RuntimeError("Upload blocked: final video bitrate is below the 95 Mbps production floor for the 100 Mbps target.")

    title, description = build_youtube_metadata(script)
    engagement_comment = str((script.get("engagement") or {}).get("comment") or "").strip() or None
    thumbnail_path = os.path.join(workdir, "thumbnail.jpg")
    thumbnail_path = thumbnail_path if os.path.exists(thumbnail_path) else None

    upload_result = upload_video(
        final_video, title, description, config,
        thumbnail_path=thumbnail_path,
        engagement_comment=engagement_comment,
    )
    commit_topic(topic)
    video_id = ""
    if isinstance(upload_result, dict):
        video_id = str(upload_result.get("video_id") or upload_result.get("id") or "")
    record_topic(topic, title=title, video_id=video_id, workdir=workdir, status="published")
    # Upload success is final. Continuation is best-effort and must never mark a published Short as failed.
    try:
        save_next_short(next_topic)
    except Exception as error:
        print(f"⚠️ Next-topic queue rejected after successful upload: {type(error).__name__}: {error}")
        print("🛠️ Generating a fresh unused continuation topic instead.")
        try:
            used = [topic]
            used.extend(item for item in _read_used() if not str(item).startswith(_PENDING_PREFIX))
            replacement = _generate_topic(used)
            save_next_short(replacement)
            next_topic = replacement
            print(f"🔗 Replacement next-video topic: {next_topic}")
        except Exception as replacement_error:
            print(f"⚠️ Continuation queue unavailable; upload remains successful: {type(replacement_error).__name__}: {replacement_error}")
    write_continuation_manifest(topic, next_topic, "published", workdir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
