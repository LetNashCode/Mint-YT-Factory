"""Independent Riddles Shorts pipeline. Does not modify Publish Shorts workflows."""
from __future__ import annotations
import json, os, time, yaml
from interactive_topics import get_next_topic, record_topic, get_pending_riddle, save_pending_riddle, next_riddle_number
from interactive_analytics import record as record_analytics, build_comparison
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
    with open(p, "w", encoding="utf-8") as f: json.dump(x, f, indent=2, ensure_ascii=False)

def _resolve_narration_path(value):
    if isinstance(value, dict): value = value.get("audio_path") or value.get("path") or value.get("output_path")
    elif isinstance(value, (tuple, list)):
        value = next((x for x in value if isinstance(x, (str, os.PathLike)) and os.path.isfile(os.fspath(x))), value[0] if value else None)
    if not isinstance(value, (str, os.PathLike)): raise RuntimeError(f"Riddle narration returned invalid value: {value!r}")
    path = os.path.abspath(os.fspath(value))
    if not os.path.isfile(path) or os.path.getsize(path) < 1024: raise RuntimeError(f"Riddle narration file invalid: {path!r}")
    return path

def run():
    config = dict(load_config() or {})
    voice = dict(config.get("voice") or {})
    voice.update({"provider":"kokoro","voice_name":"am_michael","kokoro_lang":"a",
                  "tone":"fun, warm, playful, suspenseful riddle host"})
    config["voice"] = voice
    print("🎙️ Riddles Shorts voice: am_michael (Kokoro)")

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
        reveal = "No previous riddle exists. Start directly with a high-energy challenge hook."

    feedback = f"""RIDDLE SHORT #{number}.
{reveal}
NEW exact riddle: "{topic}"
NEW answer is locked internally: "{answer}".
Create an entertaining 7-scene spoken riddle short.
RETENTION STRUCTURE:
- Scene 1: pay off the previous riddle immediately, then pivot into the new challenge. No greeting or generic intro.
- Scenes 2-3: deliver the new riddle in short punchy beats with a curiosity gap and one playful misdirection.
- Scenes 4-5: make the viewer actively think; react to likely wrong guesses without revealing the answer.
- Scene 6: create pressure and anticipation; use only a short spoken countdown ending in 3…2…1, not a long robotic 10-to-1 recital.
- Scene 7: finish the current challenge with a memorable cliffhanger that makes the viewer want the next episode.
Do not make every episode sound structurally identical. Vary the reveal mood, transitions, misdirection and final cliffhanger.
NEVER reveal, display, explain, spell out, or strongly hint at the NEW answer. During the new riddle and countdown use thinking, suspense, neutral clue imagery or people reasoning; never show the answer itself.
The previous answer reveal is allowed ONLY because it belongs to the prior episode. Do not accidentally reveal the NEW answer while explaining the previous one.
Do not use generic phrases such as "welcome back", "today's riddle", "here's today's riddle", "stay tuned", or "don't forget to like and subscribe".
Do not use Publish Shorts continuation or topic-teaser language.
The ending must NOT be the same canned sentence every time. It must promise the NEW answer is coming next, but in a natural, varied way.
Narration length is flexible."""
    script = generate_script(topic, config, None, extra_feedback=feedback)
    script.update({"topic":topic,"riddle_number":number,"previous_riddle":previous,"interactive_pillar":pillar})
    script = polish_riddle_script(script, previous, number)
    script["engagement"]={"comment":f"Comment your answer to Riddle #{number} 👇 Did you solve it?"}

    workdir=os.path.join("output","interactive",str(int(time.time())))
    os.makedirs(workdir,exist_ok=True)
    save(script,os.path.join(workdir,"script.json"))
    audio=_resolve_narration_path(synthesize_script(script,config,os.path.join(workdir,"audio")))
    print(f"🎙️ Riddle narration ready: {audio}")
    visuals=generate_media(script,os.path.join(workdir,"visuals"),config)
    sfx=generate_sfx(script,os.path.join(workdir,"sfx"))
    music=download_music(script,os.path.join(workdir,"music"))
    final=os.path.join(workdir,"final.mp4")
    assemble_video(script,[audio],visuals,music,sfx,config,final)

    q=validate_final_video(final,expected_bitrate_mbps=100.0)
    save(q,os.path.join(workdir,"validation.json"))
    if not q.get("ok"): raise RuntimeError("Riddle final video validation failed.")

    title=f"Riddle #{number}: Can You Solve This? 🧩"
    desc=f"Riddle #{number}: {topic}\n\nComment your answer before the reveal in the next Riddle Short.\n\n#Riddle #BrainTeaser #Shorts"
    result=upload_video(final,title,desc,config,engagement_comment=script["engagement"]["comment"])
    vid=result if isinstance(result,str) else str(result.get("video_id") or result.get("id") or "") if isinstance(result,dict) else ""
    if not vid: raise RuntimeError("Riddle upload returned no video ID; pending state was not advanced.")

    social_result = publish_social_reels(final, title, desc, config, workdir)
    print("📱 Riddle social publish summary:", json.dumps({
        name: (payload or {}).get("status")
        for name, payload in social_result.items()
        if name in {"instagram", "facebook"}
    }, ensure_ascii=False))

    record_topic(topic,pillar,title,vid,workdir,answer=answer)
    save_pending_riddle(pillar,topic,answer,number)
    persisted = get_pending_riddle()
    if not persisted or int(persisted.get("number", 0)) != number:
        raise RuntimeError("Failed to persist the current riddle sequence state.")
    record_analytics(vid,topic,pillar,title,workdir)
    print("📊 Comparison:",json.dumps(build_comparison(),ensure_ascii=False))

if __name__=="__main__": run()
