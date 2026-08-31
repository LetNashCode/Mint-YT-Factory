"""Independent Interactive Mystery pipeline. Does not modify main.py or production_entry.py."""
from __future__ import annotations

import json
import os
import time
import yaml

from interactive_topics import get_next_topic, record_topic
from interactive_analytics import record as record_analytics, build_comparison
from generate_script.interactive import generate_script
from tts import synthesize_script
from stock_media_resilient import generate_media
from music import download_music
from sfx import generate_sfx
from assemble import assemble_video
from upload_youtube import upload_video
from validate_video import validate_final_video


def load_config():
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save(x, p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(x, f, indent=2, ensure_ascii=False)


def _resolve_narration_path(result):
    """Accept legacy/string and structured TTS returns, never silently pass a character."""
    value = result
    if isinstance(value, dict):
        value = value.get("audio_path") or value.get("path") or value.get("output_path")
    elif isinstance(value, (tuple, list)):
        value = next(
            (
                item
                for item in value
                if isinstance(item, (str, os.PathLike))
                and os.path.isfile(os.fspath(item))
            ),
            value[0] if value else None,
        )

    if not isinstance(value, (str, os.PathLike)):
        raise RuntimeError(f"Interactive narration generation returned invalid value: {value!r}")

    path = os.path.abspath(os.fspath(value))
    if not os.path.isfile(path):
        raise RuntimeError(f"Interactive narration file not found after TTS: {path!r}")
    if os.path.getsize(path) < 1024:
        raise RuntimeError(f"Interactive narration file is empty or too small: {path!r}")
    return path


def run():
    config = load_config()
    # Interactive Mystery Shorts have their own voice identity and must not alter
    # the Publish Shorts voice configured in config.yaml.
    config = dict(config or {})
    mystery_voice = dict(config.get("voice") or {})
    mystery_voice.update({
        "provider": "kokoro",
        "voice_name": "am_michael",
        "kokoro_lang": "a",
        "tone": "calm, deep, suspenseful mystery storyteller",
    })
    config["voice"] = mystery_voice
    print("🎙️ Interactive Mystery voice: am_michael (Kokoro)")
    pillar, topic = get_next_topic()
    print("🧩 INTERACTIVE MYSTERY |", pillar, "|", topic)

    feedback = f"""INTERACTIVE MYSTERY UNIVERSE. PILLAR: {pillar}. Write an entertaining 7-scene interactive Short, not a science explainer. Open with a concrete dilemma, clue, or psychological situation. Make the viewer choose or solve before the payoff. Use tension, reversals, specific details, and natural spoken English. Ask one genuine viewer question near the end. No generic like/subscribe CTA. Scene 7 must have a satisfying payoff and no continuation teaser."""

    script = generate_script(topic, config, None, extra_feedback=feedback)
    script["topic"] = topic
    script["interactive_pillar"] = pillar
    script["engagement"] = {
        "comment": (
            "What would YOU choose? Explain below 👇"
            if pillar != "solve_the_mystery"
            else "What was your solution? Drop it below 👇"
        )
    }

    workdir = os.path.join("output", "interactive", str(int(time.time())))
    os.makedirs(workdir, exist_ok=True)
    save(script, os.path.join(workdir, "script.json"))


    tts_result = synthesize_script(script, config, os.path.join(workdir, "audio"))
    audio = _resolve_narration_path(tts_result)
    print(f"🎙️ Interactive narration ready: {audio}")

    visuals = generate_media(script, os.path.join(workdir, "visuals"), config)
    sfx = generate_sfx(script, os.path.join(workdir, "sfx"))
    music = download_music(script, os.path.join(workdir, "music"))

    final = os.path.join(workdir, "final.mp4")
    # assemble_video accepts narration paths; keep the structured list contract.
    assemble_video(script, [audio], visuals, music, sfx, config, final)

    q = validate_final_video(final, expected_bitrate_mbps=100.0)
    save(q, os.path.join(workdir, "validation.json"))
    if not q.get("ok"):
        raise RuntimeError("Interactive final video validation failed.")

    title = str(script.get("title") or topic)[:100]
    desc = f"Can YOU figure this out? {topic}\n\n#Mystery #Psychology #Shorts"
    result = upload_video(
        final,
        title,
        desc,
        config,
        engagement_comment=script["engagement"]["comment"],
    )
    # upload_video() currently returns the video ID as a string; accept both string and legacy dict returns.\n    if isinstance(result, str):\n        vid = result\n    elif isinstance(result, dict):\n        vid = str(result.get("video_id") or result.get("id") or "")\n    else:\n        vid = ""
    record_topic(topic, pillar, title, vid, workdir)
    if vid:
        record_analytics(vid, topic, pillar, title, workdir)
    print("📊 Comparison:", json.dumps(build_comparison(), ensure_ascii=False))


if __name__ == "__main__":
    run()
