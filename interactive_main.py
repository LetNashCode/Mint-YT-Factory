"""Independent Story Shorts pipeline. Replaces the former Riddles Shorts line and does not modify Publish Shorts."""
from __future__ import annotations
import json, os, time
import yaml
from interactive_topics import get_next_topic, record_topic, get_pending_story, save_pending_story, next_story_number
from interactive_analytics import record as record_analytics, build_comparison, refresh_live_metrics
from generate_script.interactive import generate_script
from tts import synthesize_script
from stock_media_resilient import generate_media
from music import download_music
from sfx import generate_sfx
from assemble import assemble_video
from upload_youtube import upload_video
from social_publish import publish_social_reels
from validate_video import validate_final_video


def load_config():
    with open("config.yaml", encoding="utf-8") as f: return yaml.safe_load(f)

def save(x,p):
    directory=os.path.dirname(p)
    if directory: os.makedirs(directory,exist_ok=True)
    with open(p,"w",encoding="utf-8") as f: json.dump(x,f,indent=2,ensure_ascii=False)

def _title(pillar,person):
    labels={
        "rise_from_nothing":"The Impossible Comeback",
        "one_decision":"The Decision That Changed Everything",
        "before_they_were_famous":"Before the Fame",
        "impossible_odds":"Against Impossible Odds",
        "strange_turning_point":"The Moment Everything Changed",
    }
    label=labels.get(pillar,"A Remarkable Story")
    return f"{label}: {person}"

def _validate_story_contract(script):
    scenes=script.get("scene_plan") or []
    if len(scenes)!=7: raise RuntimeError("Story contract requires exactly 7 scenes.")
    narration=" ".join(str(s.get("narration","")) for s in scenes).strip()
    if not narration: raise RuntimeError("Story narration is empty.")
    final=str(scenes[-1].get("narration",""))
    if "subscribe" not in final.lower() or "follow" not in final.lower(): raise RuntimeError("Story Scene 7 must contain subscribe and follow CTA.")

def _generate_story_script(topic,config,feedback):
    """Generate a standalone Story Short without applying the Publish-only continuation bridge."""
    return generate_script(topic,config,None,extra_feedback=feedback)

def run():
    config=dict(load_config() or {})
    voice=dict(config.get("voice") or {})
    voice.update({"provider":"kokoro","voice_name":"am_michael","kokoro_lang":"a","tone":"cinematic, warm, conversational storyteller"})
    config["voice"]=voice
    print("🎙️ Story Shorts voice: am_michael (Kokoro)")
    refresh_live_metrics()
    previous=get_pending_story(); pillar,topic,person=get_next_topic(); number=next_story_number()
    if previous and number<=int(previous.get("number",0)): raise RuntimeError(f"Invalid story sequence state: next #{number} must follow pending Story #{previous.get('number')}.")
    print(f"📖 STORY SHORT #{number} | {pillar} | {person}")
    feedback=f"""STORY SHORT #{number} — RETENTION-FIRST REAL-PERSON STORY.
SUBJECT: {topic}
PERSON: {person}
FORMAT: {pillar}
Create a self-contained story. Do not mention the previous story or tease a future specific person.
The viewer should understand the emotional arc with the phone face-down. Stock visuals are atmosphere/context only.
Use a hard hook, concrete stakes, an obstacle, a meaningful decision or turning point, escalation, and a satisfying payoff.
Do not turn the ending into a motivational lecture. The final CTA should be natural: subscribe and follow for another remarkable story.
Do not create or mention a next-topic teaser; this Story Shorts line is standalone.
"""
    script=_generate_story_script(topic,config,feedback)
    script.update({"topic":topic,"story_number":number,"story_person":person,"interactive_pillar":pillar,"story_visual_mode":"narration_atmosphere_v1"})
    _validate_story_contract(script)
    script["engagement"]={"comment":f"What would you have done in {person}'s situation? 👇"}
    workdir=os.path.join("output","interactive",str(int(time.time()))); os.makedirs(workdir,exist_ok=True); save(script,os.path.join(workdir,"script.json"))
    audio=synthesize_script(script,config,os.path.join(workdir,"audio"))
    if isinstance(audio,dict): audio=audio.get("audio_path") or audio.get("path") or audio.get("output_path")
    elif isinstance(audio,(tuple,list)): audio=next((x for x in audio if isinstance(x,(str,os.PathLike)) and os.path.isfile(os.fspath(x))),audio[0] if audio else None)
    if not isinstance(audio,(str,os.PathLike)) or not os.path.isfile(os.fspath(audio)): raise RuntimeError(f"Story narration file invalid: {audio!r}")
    audio=os.path.abspath(os.fspath(audio)); print(f"🎙️ Story narration ready: {audio}")
    visuals=generate_media(script,os.path.join(workdir,"visuals"),config)
    sfx=generate_sfx(script,os.path.join(workdir,"sfx")); music=download_music(script,os.path.join(workdir,"music")); final=os.path.join(workdir,"final.mp4")
    assemble_video(script,[audio],visuals,music,sfx,config,final)
    q=validate_final_video(final,expected_bitrate_mbps=100.0); save(q,os.path.join(workdir,"validation.json"))
    if not q.get("ok"): raise RuntimeError("Story final video validation failed.")
    title=_title(pillar,person)
    desc=f"A remarkable true story about {person} — the struggle, turning point, and moment that changed everything.\n\nWhat would you have done in {person}'s situation? 👇\n\nSubscribe and follow for more powerful stories about people who faced setbacks, made difficult choices, and changed their lives.\n\n#StoryShorts #TrueStory #Inspiration #Shorts"
    result=upload_video(final,title,desc,config,engagement_comment=script["engagement"]["comment"])
    vid=result if isinstance(result,str) else str(result.get("video_id") or result.get("id") or "") if isinstance(result,dict) else ""
    if not vid: raise RuntimeError("Story upload returned no video ID; sequence state was not advanced.")
    social_result=publish_social_reels(final,title,desc,config,workdir)
    print("📱 Story social publish summary:",json.dumps({name:(payload or {}).get("status") for name,payload in social_result.items() if name in {"instagram","facebook"}},ensure_ascii=False))
    record_topic(topic,pillar,title,vid,workdir,person=person); save_pending_story(pillar,topic,person,number)
    persisted=get_pending_story()
    if not persisted or int(persisted.get("number",0))!=number: raise RuntimeError("Failed to persist Story Shorts sequence state.")
    record_analytics(vid,topic,pillar,title,workdir,person=person); print("📊 Story comparison:",json.dumps(build_comparison(),ensure_ascii=False))

if __name__=="__main__": run()
