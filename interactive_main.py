"""Independent Riddles Shorts pipeline. Does not modify Publish Shorts workflows."""
from __future__ import annotations
import json, os, time, yaml
from interactive_topics import get_next_topic, record_topic, get_pending_riddle, save_pending_riddle, next_riddle_number
from interactive_analytics import record as record_analytics, build_comparison, refresh_live_metrics
from generate_script.interactive import generate_script
from riddle_narration import polish_riddle_script
from tts import synthesize_script
from stock_media_resilient import generate_media
from music import download_music
from sfx import generate_sfx
from assemble import assemble_video
from upload_youtube import upload_video
from social_publish import publish_social_reels
from validate_video import validate_final_video


def load_config():
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save(x, p):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(x, f, indent=2, ensure_ascii=False)


def _resolve_narration_path(value):
    if isinstance(value, dict):
        value = value.get("audio_path") or value.get("path") or value.get("output_path")
    elif isinstance(value, (tuple, list)):
        value = next((x for x in value if isinstance(x, (str, os.PathLike)) and os.path.isfile(os.fspath(x))), value[0] if value else None)
    if not isinstance(value, (str, os.PathLike)):
        raise RuntimeError(f"Riddle narration returned invalid value: {value!r}")
    path = os.path.abspath(os.fspath(value))
    if not os.path.isfile(path) or os.path.getsize(path) < 1024:
        raise RuntimeError(f"Riddle narration file invalid: {path!r}")
    return path


def run():
    config = dict(load_config() or {})
    voice = dict(config.get("voice") or {})
    voice.update({"provider": "kokoro", "voice_name": "am_michael", "kokoro_lang": "a",
                  "tone": "fun, warm, playful, suspenseful riddle host"})
    config["voice"] = voice
    print("🎙️ Riddles Shorts voice: am_michael (Kokoro)")

    refresh_live_metrics()

    previous = get_pending_riddle()
    pillar, topic, answer = get_next_topic()
    number = next_riddle_number()

    if previous and number <= int(previous.get("number", 0)):
        raise RuntimeError(
            f"Invalid riddle sequence state: next #{number} must follow pending "
            f"Riddle #{previous.get('number')}."
        )
    print(f"🧩 RIDDLE SHORT #{number} | {pillar} | {topic}")

    if previous:
        print(f"🔓 Revealing Riddle #{previous['number']} answer: {previous['answer']}")
        reveal = (
            f'Previous answer: "{previous["answer"]}". '
            "This reveal must be the very first spoken beat of Scene 1. "
            "Make it playful and conversational, ask briefly if viewers got it right, then pivot into the new challenge."
        )
    else:
        reveal = "No previous riddle exists. Start directly with a high-energy spoken challenge hook."

    feedback = f"""RIDDLE SHORT #{number} — NARRATION-FIRST RETENTION.
{reveal}
NEW exact riddle: "{topic}"
NEW answer is locked internally: "{answer}".
Create an entertaining 7-scene spoken mini-game. The viewer must be able to solve everything with the phone face-down. Stock footage/images are atmosphere only, never a clue.
RETENTION STRUCTURE:
- Scene 1: immediate pattern interrupt; if there is a previous riddle, reveal its answer first, then pivot immediately. No greeting.
- Scene 2: state the NEW riddle clearly and quickly. No unnecessary setup.
- Scene 3: create the obvious first interpretation and a spoken curiosity gap.
- Scene 4: introduce a second interpretation, wording trap, assumption, or expectation reversal. Do not reveal the answer.
- Scene 5: force commitment: ask viewers to lock in their FIRST answer. Keep it punchy.
- Scene 6: brief pressure and conversational 3…2…1 countdown. No 10-to-1 countdown.
- Scene 7: preserve the NEW answer as a payoff gap and end with a subscribe/follow CTA promising the answer in the next Short. Never say tomorrow or next day.
Vary the underlying riddle mechanic and phrasing between episodes: wording traps, double meanings, obvious-answer traps, lateral thinking, expectation reversals, tiny logic mysteries, misconceptions and psychological traps.
Never depend on visuals, on-screen text, a diagram, or a stock object being recognizable for the solution.
NEVER reveal, display, spell out, or strongly hint at the NEW answer, including through examples of possible answers.
Do not use generic phrases such as "welcome back", "today's riddle", "here's today's riddle", "stay tuned", or "don't forget to like and subscribe".
The final CTA must use the subscribe/follow → answer in the next Short loop. Do not promise a publishing day.
Narration length is flexible."""

    script = generate_script(topic, config, None, extra_feedback=feedback)
    script.update({"topic": topic, "riddle_number": number, "previous_riddle": previous, "interactive_pillar": pillar})
    script = polish_riddle_script(script, previous, number)
    script["engagement"] = {
        "comment": f"Lock in your FIRST answer to Riddle #{number} 👇 What was your guess?"
    }

    workdir = os.path.join("output", "interactive", str(int(time.time())))
    os.makedirs(workdir, exist_ok=True)
    save(script, os.path.join(workdir, "script.json"))
    audio = _resolve_narration_path(synthesize_script(script, config, os.path.join(workdir, "audio")))
    print(f"🎙️ Riddle narration ready: {audio}")
    visuals = generate_media(script, os.path.join(workdir, "visuals"), config)
    sfx = generate_sfx(script, os.path.join(workdir, "sfx"))
    music = download_music(script, os.path.join(workdir, "music"))
    final = os.path.join(workdir, "final.mp4")
    assemble_video(script, [audio], visuals, music, sfx, config, final)

    q = validate_final_video(final, expected_bitrate_mbps=100.0)
    save(q, os.path.join(workdir, "validation.json"))
    if not q.get("ok"):
        raise RuntimeError("Riddle final video validation failed.")

    title = f"Riddle #{number}: Can You Solve This? 🧩"
    desc = f"Riddle #{number}: {topic}\n\nLock in your first answer. Subscribe and follow for the answer in the next Riddle Short.\n\n#Riddle #BrainTeaser #Shorts"
    result = upload_video(final, title, desc, config, engagement_comment=script["engagement"]["comment"])
    vid = result if isinstance(result, str) else str(result.get("video_id") or result.get("id") or "") if isinstance(result, dict) else ""
    if not vid:
        raise RuntimeError("Riddle upload returned no video ID; pending state was not advanced.")

    social_result = publish_social_reels(final, title, desc, config, workdir)
    print("📱 Riddle social publish summary:", json.dumps({
        name: (payload or {}).get("status") for name, payload in social_result.items()
        if name in {"instagram", "facebook"}
    }, ensure_ascii=False))

    record_topic(topic, pillar, title, vid, workdir, answer=answer)
    save_pending_riddle(pillar, topic, answer, number)
    persisted = get_pending_riddle()
    if not persisted or int(persisted.get("number", 0)) != number:
        raise RuntimeError("Failed to persist the current riddle sequence state.")
    record_analytics(vid, topic, pillar, title, workdir)
    print("📊 Comparison:", json.dumps(build_comparison(), ensure_ascii=False))


if __name__ == "__main__":
    run()
