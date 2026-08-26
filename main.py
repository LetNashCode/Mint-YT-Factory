"""Mint-YT-Factory production pipeline.

CURRENT MODE: entertainment-first + self-learning + story-aware SFX + engagement experiments.
Continuation ownership is Gemini: Python validates/locks it but never writes a canned bridge.
"""
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
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if p.strip()]


_BANNED_BRIDGE_PATTERNS = (
    r"^(?:and\s+)?next\b", r"^then\s+comes\b", r"^coming\s+next\b",
    r"^in\s+the\s+next\s+(?:video|short)\b", r"^stay\s+tuned\b", r"^part\s+2\b",
    r"^have\s+you\s+ever\s+wondered\b", r"^ever\s+wondered\b", r"^wonder\s+why\b",
    r"^curious\s+(?:why|how|what)\b", r"^why\s+(?:do|does|is|are)\b",
    r"^how\s+(?:do|does|is|are)\b", r"^what\s+(?:makes|happens|causes)\b",
)


def _is_canned_bridge(sentence):
    return any(re.search(pattern, str(sentence or "").strip(), re.I) for pattern in _BANNED_BRIDGE_PATTERNS)


def _bridge_sentences_for_topic(narration, canonical):
    key = _normalise_topic_text(canonical)
    return [s for s in _split_sentences(narration) if key and key in _normalise_topic_text(s)]


def _validate_gemini_scene7(script, canonical):
    scenes = script.get("scene_plan")
    if not isinstance(scenes, list) or len(scenes) != 7:
        raise RuntimeError("Script must contain exactly 7 scenes.")
    for scene in scenes[:6]:
        if _normalise_topic_text(canonical) in _normalise_topic_text(scene.get("narration", "")):
            raise RuntimeError("Next topic appeared before Scene 7.")
    narration = str(scenes[-1].get("narration", "")).strip()
    sentences = _split_sentences(narration)
    matches = _bridge_sentences_for_topic(narration, canonical)
    if len(matches) != 1:
        raise RuntimeError("Gemini must place the locked next topic exactly once in Scene 7.")
    bridge = matches[0]
    if _is_canned_bridge(bridge):
        raise RuntimeError(f"Canned Scene 7 bridge rejected: {bridge}")
    if len(sentences) < 2:
        raise RuntimeError("Scene 7 must contain a current-topic payoff followed by a natural bridge.")
    if _normalise_topic_text(sentences[-1]) != _normalise_topic_text(bridge):
        raise RuntimeError("The next-topic bridge must be the final sentence of Scene 7.")
    if any(_is_canned_bridge(s) for s in sentences[:-1]):
        raise RuntimeError("Scene 7 contains a canned/future-topic transition before the final bridge.")
    if _word_count(bridge) < 3 or _word_count(bridge) > 18:
        raise RuntimeError("Natural Scene 7 bridge has an invalid length.")
    return bridge


def _lock_canonical_topic(script, current_topic):
    candidate = str((script.get("next_short") or {}).get("topic", "")).strip()
    if not candidate:
        raise RuntimeError("Generated script did not provide next_short.topic.")
    used = [str(current_topic)]
    used.extend(item for item in _read_used() if not str(item).startswith(_PENDING_PREFIX))
    canonical = candidate if validate_topic_for_pipeline(candidate, used=used, check_duplicate=True) else _generate_topic(used)
    if not validate_topic_for_pipeline(canonical, used=used, check_duplicate=True):
        raise RuntimeError(f"Could not create valid canonical next topic: {canonical}")
    if _word_count(canonical) > 7:
        canonical = _generate_topic(used)
        if _word_count(canonical) > 7:
            raise RuntimeError(f"Generated continuation is still too long: {canonical}")
    script.setdefault("next_short", {})["topic"] = canonical
    return canonical


def lock_next_topic(script, current_topic):
    canonical = _lock_canonical_topic(script, current_topic)
    bridge = _validate_gemini_scene7(script, canonical)
    script["next_short"]["teaser"] = bridge
    final_scene = script["scene_plan"][-1]
    final_scene["subtitle_text"] = final_scene.get("narration", "")
    final_scene["pause_after_ms"] = int(final_scene.get("pause_after_ms", 250) or 250)
    final_scene["emotional_tone"] = final_scene.get("emotional_tone", "satisfied")
    final_scene["music_cue"] = final_scene.get("music_cue", "fade_out")
    print(f"🔒 Canonical next topic: {canonical}")
    print(f"🗣️ GEMINI NATURAL FINAL BRIDGE: {bridge}")
    return script, canonical


def write_continuation_manifest(current_topic, next_topic, status, workdir=""):
    save_json({"status": status, "current_topic": current_topic, "next_topic": next_topic, "workdir": workdir, "updated_at": int(time.time())}, CONTINUATION_MANIFEST)


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
    print("=" * 80); print("📊 REFRESHING LIVE YOUTUBE ANALYTICS BEFORE GENERATION"); print("=" * 80)
    try:
        from youtube_analytics import refresh_registry
        summary = refresh_registry()
        print(f"📊 Analytics refreshed: {summary.get('video_count', 0)} videos | optimization_ready={summary.get('optimization_ready', False)}")
    except Exception as error:
        print(f"⚠️ Live analytics refresh unavailable: {type(error).__name__}: {error}")
        print("⚠️ Continuing with the last saved learning state.")
    try:
        playbook = refresh_playbook()
        print(f"🧠 Learning playbook refreshed: {playbook.get('video_count', 0)} videos | learning_ready={playbook.get('learning_ready', False)}")
    except Exception as error:
        print(f"⚠️ Learning playbook refresh unavailable: {type(error).__name__}: {error}")


def _generate_valid_script(topic, config, learning_context, engagement_feedback):
    feedback = learning_context + engagement_feedback + """

CONTINUATION HARD REQUIREMENT:
The final sentence of Scene 7 must contain the exact next_short.topic, but Gemini must
write a fresh, natural bridge around it. NEVER start that sentence with 'And next',
'Then comes', 'Coming next', 'Have you ever wondered', 'Ever wondered', 'Wonder why',
'Why do/does', 'How do/does', 'What makes', or any other canned question/teaser.
The bridge should feel like the current story naturally opens a door to the next curiosity.
Do not mention the next topic anywhere in Scenes 1-6, title, or description.
Scene 7 must finish the current topic's payoff before the bridge.
"""
    last_error = None
    for attempt in range(1, 5):
        try:
            script = generate_script(topic, config, None, extra_feedback=feedback)
            candidate = str((script.get("next_short") or {}).get("topic", "")).strip()
            if not candidate:
                raise RuntimeError("Missing next_short.topic")
            canonical = _lock_canonical_topic(script, topic)
            _validate_gemini_scene7(script, canonical)
            return script
        except Exception as error:
            last_error = error
            print(f"⚠️ Continuation/story validation failed ({attempt}/4): {error}")
            feedback += f"\nPREVIOUS ATTEMPT FAILED: {error}. Rewrite the entire story and make Scene 7's final bridge natural and unique.\n"
    raise RuntimeError(f"Could not generate a valid natural Scene 7 continuation after 4 attempts: {last_error}")


def run(dry_run=False):
    config = load_config()
    print("=" * 80); print("🚀 MINT-YT-FACTORY — ENTERTAINMENT-FIRST + SELF-LEARNING + SFX"); print("=" * 80)
    print("🧠 Self-learning: ENABLED"); print("📈 Objective: views + subscriber growth + YPP readiness")
    print("🔁 Learning strategy: 70% proven patterns / 20% adjacent experiments / 10% wild experiments")
    print("💬 Engagement learning: sequential comment/share experiments ENABLED"); print("🚫 Duplicate-topic protection: ENABLED")
    print("🔊 Story-aware SFX: ENABLED (free local procedural)"); print("🧠 Gemini owns Scene 7 bridge: ENABLED")
    print("🚫 Hard-coded continuation sentence: DISABLED")
    refresh_learning_before_generation()
    topic = get_next_topic()
    if not topic: raise RuntimeError("No topic available.")
    print(f"🎯 CURRENT TOPIC: {topic}")
    try:
        from engagement_experiments import assign, summarize
        engagement = assign(topic)
        print(f"🧪 Engagement experiment: {engagement['experiment']} | phase={engagement['phase']}")
        print(f"💬 Planned comment: {engagement['comment']}"); print(f"🔄 Share trigger: {engagement['share_prompt']}")
        print(f"📊 Existing experiment results: {json.dumps(summarize(), ensure_ascii=False)}")
    except Exception as error:
        engagement = {"experiment": "none", "phase": "disabled", "spoken_prompt": "", "comment": "", "share_prompt": ""}
        print(f"⚠️ Engagement experiment setup skipped: {type(error).__name__}: {error}")
    learning_context = load_learning_context()
    engagement_feedback = f"""
ENGAGEMENT EXPERIMENT FOR THIS SHORT: {engagement['experiment']}
Use the mechanic naturally if it fits. Never sound like engagement bait.
Suggested spoken interaction: {engagement['spoken_prompt']}
"""
    script = _generate_valid_script(topic, config, learning_context, engagement_feedback)
    script, next_topic = lock_next_topic(script, topic)
    script["topic"] = topic
    script["engagement_experiment"] = engagement
    save_json(script, os.path.join("work", "script.json"))
    print(f"💾 Script saved. Next topic locked: {next_topic}")
    if dry_run:
        print("🧪 DRY RUN — stopping after script generation.")
        return
    workdir = os.path.join("work", re.sub(r"[^a-zA-Z0-9_-]+", "_", topic)[:80])
    os.makedirs(workdir, exist_ok=True)
    write_continuation_manifest(topic, next_topic, "generating", workdir)
    synthesize_script(script, workdir, config)
    media = generate_media(script, os.path.join(workdir, "media"), config)
    download_music(script, workdir, config)
    generate_sfx(script, workdir, config)
    video_path = assemble_video(script, media, workdir, config)
    validate_final_video(video_path, script, config)
    title, description = build_youtube_metadata(script)
    upload_video(video_path, title, description, script.get("tags", []), config)
    save_next_short(next_topic)
    commit_topic(topic)
    write_continuation_manifest(topic, next_topic, "completed", workdir)
    refresh_playbook()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
