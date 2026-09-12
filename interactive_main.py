"""Independent Story Shorts pipeline. Replaces the former Riddles Shorts line and does not modify Publish Shorts."""
from __future__ import annotations
import json, os, re, time
import yaml
from moviepy.editor import AudioFileClip
from interactive_topics import get_next_topic, record_topic, get_pending_story, save_pending_story, next_story_number
from interactive_analytics import record as record_analytics, build_comparison, refresh_live_metrics
from generate_script.interactive import generate_script
from tts import synthesize_script
from stock_media_resilient import generate_media
from story_person_media import generate_person_media, apply_person_media
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

def _content_words(text):
    stop={"the","a","an","and","or","but","so","to","of","in","on","at","for","with","from","was","were","is","are","this","that","it","he","she","they","his","her","their","had","have","has","as","by","not","what","when","who","how","then","just","one","more","because","after","before","into","than","very","would","could","did","do","does"}
    return {w.lower().strip(".,!?;:'\"()[]{}") for w in re.findall(r"\b[\w'-]+\b",str(text or "")) if w.lower() not in stop and len(w)>2}

def _last_sentence(text):
    parts=[x.strip() for x in re.split(r"(?<=[.!?])\s+",str(text or "").strip()) if x.strip()]
    return parts[-1] if parts else str(text or "").strip()

def _validate_story_contract(script):
    scenes=script.get("scene_plan") or []
    if len(scenes)!=7: raise RuntimeError("Story contract requires exactly 7 scenes.")
    narration=" ".join(str(s.get("narration","")) for s in scenes).strip()
    if not narration: raise RuntimeError("Story narration is empty.")
    final=str(scenes[-1].get("narration",""))
    if "subscribe" not in final.lower() or "follow" not in final.lower(): raise RuntimeError("Story Scene 7 must contain subscribe and follow CTA.")
    opening_hook=_last_sentence(str(scenes[0].get("narration","")))
    closing_loop=_last_sentence(final)
    overlap=_content_words(opening_hook) & _content_words(closing_loop)
    if len(overlap)<2: raise RuntimeError("Story contract loop seam is too weak: Scene 7 must echo at least two opening-hook words.")
    cta_positions=[m.end() for m in re.finditer(r"\b(?:subscribe|follow)\b",final,re.I)]
    if cta_positions and not final[max(cta_positions):].strip(" .,!?:;-—"): raise RuntimeError("Story contract requires the loop-closing sentence after the CTA.")
    print(f"🔁 Story contract loop validated: echo={', '.join(sorted(overlap)[:5])}")

def _generate_story_script(topic,config,feedback):
    """Generate a standalone looping Story Short without applying the Publish-only continuation bridge."""
    return generate_script(topic,config,None,extra_feedback=feedback)

def _person_credits(person_media):
    lines=[]
    for item in (person_media or {}).get("credits",[]):
        if not isinstance(item,dict): continue
        source=item.get("source_url") or ""
        title=item.get("title") or "Wikimedia Commons media"
        creator=item.get("creator") or "Unknown creator"
        license_name=item.get("license") or "license shown on source page"
        if source: lines.append(f"{title} — {creator} — {license_name} — {source}")
    return lines

def _audio_duration(path):
    clip=None
    try:
        clip=AudioFileClip(path)
        return float(clip.duration or 0.0)
    finally:
        if clip is not None:
            try: clip.close()
            except Exception: pass

def _assert_complete_story_audio(audio_path, minimum_expected_seconds=0.0):
    """Fail before assembly/upload if the narration file is unexpectedly short."""
    duration=_audio_duration(audio_path)
    if duration <= 0.05:
        raise RuntimeError(f"Story narration has invalid duration: {duration:.2f}s")
    if minimum_expected_seconds and duration + 0.05 < minimum_expected_seconds:
        raise RuntimeError(f"Story narration is shorter than expected: {duration:.2f}s < {minimum_expected_seconds:.2f}s")
    print(f"🛡️ COMPLETE STORY AUDIO CHECK: {duration:.2f}s — full narration file present")
    return duration

def _assert_final_audio_contains_story(final_path, narration_duration):
    """Verify the encoded MP4 still contains the complete narration before upload."""
    duration=_audio_duration(final_path)
    if duration + 0.05 < narration_duration:
        raise RuntimeError(f"Final MP4 audio is shorter than source narration: {duration:.2f}s < {narration_duration:.2f}s")
    print(f"🛡️ FINAL STORY AUDIO CHECK: {duration:.2f}s >= narration {narration_duration:.2f}s")
    return duration

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
    feedback=f"""STORY SHORT #{number} — RETENTION-FIRST REAL-PERSON LOOP STORY.
SUBJECT: {topic}
PERSON: {person}
FORMAT: {pillar}
Create a self-contained story. Do not mention the previous story or tease a future specific person.
The viewer must hear the COMPLETE story from hook through payoff before the CTA. Never omit, truncate, or compress away the final story beat just to meet a preferred duration.
This Short MUST use a spoken loop: Scene 1 opens with a distinctive hook; Scene 7 ends with a natural sentence that echoes that hook so the restart feels like the continuation of the ending.
The viewer should understand the emotional arc with the phone face-down. Real-person photos/footage may be used for key identity moments; supporting stock visuals must remain atmosphere/context only.
Use a hard hook, concrete stakes, an obstacle, a meaningful decision or turning point, escalation, and a satisfying payoff.
The final CTA must be concise and come BEFORE the final loop-closing sentence. Do not make the CTA the last spoken thought.
Do not turn the ending into a motivational lecture. Do not create or mention a next-topic teaser; this Story Shorts line is standalone.
Do not expose the loop with words like replay, loop, watch again, or back to the beginning.
"""
    script=_generate_story_script(topic,config,feedback)
    script.update({"topic":topic,"story_number":number,"story_person":person,"interactive_pillar":pillar,"story_visual_mode":"real_person_plus_atmosphere_v1"})
    _validate_story_contract(script)
    script["engagement"]={"comment":f"What would you have done in {person}'s situation? 👇"}
    workdir=os.path.join("output","interactive",str(int(time.time()))); os.makedirs(workdir,exist_ok=True); save(script,os.path.join(workdir,"script.json"))
    audio=synthesize_script(script,config,os.path.join(workdir,"audio"))
    if isinstance(audio,dict): audio=audio.get("audio_path") or audio.get("path") or audio.get("output_path")
    elif isinstance(audio,(tuple,list)): audio=next((x for x in audio if isinstance(x,(str,os.PathLike)) and os.path.isfile(os.fspath(x))),audio[0] if audio else None)
    if not isinstance(audio,(str,os.PathLike)) or not os.path.isfile(os.fspath(audio)): raise RuntimeError(f"Story narration file invalid: {audio!r}")
    audio=os.path.abspath(os.fspath(audio)); narration_duration=_assert_complete_story_audio(audio); print(f"🎙️ Story narration ready: {audio}")
    person_media=generate_person_media(script,os.path.join(workdir,"person_media"),person)
    visuals=generate_media(script,os.path.join(workdir,"visuals"),config)
    visuals=apply_person_media(visuals,person_media)
    real_count=sum(1 for x in visuals if x.get("person_visual"))
    print(f"👤 Story real-person visuals applied: {real_count}/{len((person_media or {}).get('assets',[]))} verified assets")
    script["story_person_media"]={
        "source":"Wikimedia Commons",
        "verified_assets":real_count,
        "target_scenes":[1,2,4,6,7],
        "credits":_person_credits(person_media),
    }
    save(script,os.path.join(workdir,"script.json"))
    sfx=generate_sfx(script,os.path.join(workdir,"sfx")); music=download_music(script,os.path.join(workdir,"music")); final=os.path.join(workdir,"final.mp4")
    assemble_video(script,[audio],visuals,music,sfx,config,final)
    _assert_final_audio_contains_story(final,narration_duration)
    q=validate_final_video(final,expected_bitrate_mbps=100.0); save(q,os.path.join(workdir,"validation.json"))
    if not q.get("ok"): raise RuntimeError("Story final video validation failed.")
    title=_title(pillar,person)
    credits=_person_credits(person_media)
    credit_block=("\n\nReal-person media credits:\n"+"\n".join(credits)) if credits else ""
    desc=f"A remarkable true story about {person} — the struggle, turning point, and moment that changed everything.\n\nWhat would you have done in {person}'s situation? 👇\n\nSubscribe and follow for more powerful stories about people who faced setbacks, made difficult choices, and changed their lives.\n\n#StoryShorts #TrueStory #Inspiration #Shorts"+credit_block
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
