"""Independent Riddles Shorts pipeline. Does not modify Publish Shorts workflows."""
from __future__ import annotations
import json, os, time, yaml
from interactive_topics import get_next_topic, record_topic, get_pending_riddle, save_pending_riddle, next_riddle_number
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
    print(f"🧩 RIDDLE SHORT #{number} | {pillar} | {topic}")

    reveal = ""
    if previous:
        print(f"🔓 Revealing Riddle #{previous['number']} answer: {previous['answer']}")
        reveal = f'Reveal Riddle #{previous["number"]} answer naturally: "{previous["answer"]}". This reveal MUST be the opening of Scene 1, before any greeting, hook, new riddle, countdown, or other narration. Ask briefly whether viewers got it right, then introduce the new riddle.'
    else:
        reveal = "No previous riddle exists. Start directly with the new challenge."

    feedback = f"""RIDDLE SHORT #{number}.
{reveal}
NEW exact riddle: "{topic}"
NEW answer is locked internally: "{answer}".
Create an entertaining 7-scene spoken riddle short. Clearly ask the complete riddle, invite viewers to comment their answer, then perform a suspenseful spoken countdown from 10 to 1. NEVER reveal, display, explain, or strongly hint at the NEW answer. During the new riddle and countdown use thinking, suspense, curiosity, clocks, neutral clue imagery or people reasoning; never show the answer itself. End naturally with: "The answer to Riddle #{number} will be revealed in the next Riddle Short." Do not use Publish Shorts continuation or topic-teaser language. Narration length is flexible."""
    script = generate_script(topic, config, None, extra_feedback=feedback)
    script.update({"topic":topic,"riddle_number":number,"previous_riddle":previous,"interactive_pillar":pillar})
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
    save_pending_riddle(pillar,topic,answer,number)
    record_topic(topic,pillar,title,vid,workdir,answer=answer)
    record_analytics(vid,topic,pillar,title,workdir)
    print("📊 Comparison:",json.dumps(build_comparison(),ensure_ascii=False))

if __name__=="__main__": run()
