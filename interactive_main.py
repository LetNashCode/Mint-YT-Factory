"""Independent Story Shorts pipeline. Replaces the former Riddles Shorts line and does not modify Publish Shorts."""
from __future__ import annotations
import json, os, re, time
import yaml
from publication_state import save as save_publication_state
from moviepy.editor import AudioFileClip
from interactive_topics import get_next_topic, record_topic, get_pending_story, save_pending_story, next_story_number
from interactive_analytics import record as record_analytics, build_comparison, refresh_live_metrics
from generate_script.interactive import generate_script
from tts import synthesize_script
from stock_media_resilient import generate_media
from story_media_preflight import validate_story_media
from music import download_music
from sfx import generate_sfx
from assemble import assemble_video
from upload_youtube import upload_video
from social_publish import publish_social_reels
from validate_video import validate_final_video

SOCIAL_QUEUE_PATH = "story_social_queue.json"
RENDER_MANIFEST = "render_manifest.json"

def load_config():
    with open("config.yaml", encoding="utf-8") as f: return yaml.safe_load(f)
def save(x,p):
    directory=os.path.dirname(p)
    if directory: os.makedirs(directory,exist_ok=True)
    with open(p,"w",encoding="utf-8") as f: json.dump(x,f,indent=2,ensure_ascii=False)
def _title(pillar,person):
    labels={"rise_from_nothing":"The Impossible Comeback","one_decision":"The Decision That Changed Everything","before_they_were_famous":"Before the Fame","impossible_odds":"Against Impossible Odds","strange_turning_point":"The Moment Everything Changed"}
    return f"{labels.get(pillar,'A Remarkable Story')}: {person}"
def _content_words(text):
    stop={"the","a","an","and","or","but","so","to","of","in","on","at","for","with","from","was","were","is","are","this","that","it","he","she","they","his","her","their","had","have","has","as","by","not","what","when","who","how","then","just","one","more","because","after","before","into","than","very","would","could","did","do","does"}
    return {w.lower().strip(".,!?;:'\\\"()[]{}") for w in re.findall(r"\b[\w'-]+\b",str(text or "")) if w.lower() not in stop and len(w)>2}
def _first_sentence(text):
    parts=[x.strip() for x in re.split(r"(?<=[.!?])\s+",str(text or "").strip()) if x.strip()]
    return parts[0] if parts else str(text or "").strip()
def _last_sentence(text):
    parts=[x.strip() for x in re.split(r"(?<=[.!?])\s+",str(text or "").strip()) if x.strip()]
    return parts[-1] if parts else str(text or "").strip()
def _stem(word):
    word=re.sub(r"[^a-z0-9]","",str(word or "").lower())
    if len(word)<5: return word
    for suffix in ("ingly","edly","ation","ments","ment","ness","less","ing","ers","ies","ied","ed","es","s"):
        if word.endswith(suffix) and len(word)-len(suffix)>=4: return word[:-len(suffix)]
    return word
def _loop_overlap(opening,ending):
    opening_terms={w for w in _content_words(opening) if len(w)>3}; closing_terms={w for w in _content_words(ending) if len(w)>3}; exact=opening_terms & closing_terms
    if len(exact)>=2: return exact
    closing_stems={_stem(w):w for w in closing_terms}
    return {closing_stems[_stem(w)] for w in opening_terms if _stem(w) in closing_stems}
def _validate_story_contract(script):
    scenes=script.get("scene_plan") or []
    if len(scenes)!=7: raise RuntimeError("Story contract requires exactly 7 scenes.")
    narration=" ".join(str(s.get("narration","")) for s in scenes).strip()
    if not narration: raise RuntimeError("Story narration is empty.")
    opening_hook=_first_sentence(str(scenes[0].get("narration",""))); closing_loop=_last_sentence(str(scenes[-1].get("narration",""))); overlap=_loop_overlap(opening_hook,closing_loop)
    if len(overlap)<2: raise RuntimeError("Story contract loop seam is too weak: Scene 7 must echo at least two opening-hook words.")
    print(f"🔁 Story contract loop validated: echo={', '.join(sorted(overlap)[:5])} | CTA=OFF")
def _generate_story_script(topic,config,feedback): return generate_script(topic,config,None,extra_feedback=feedback)
def _audio_duration(path):
    clip=None
    try:
        clip=AudioFileClip(path); return float(clip.duration or 0.0)
    finally:
        if clip is not None:
            try: clip.close()
            except Exception: pass
def _assert_complete_story_audio(audio_path, minimum_expected_seconds=0.0):
    duration=_audio_duration(audio_path)
    if duration<=0.05: raise RuntimeError(f"Story narration has invalid duration: {duration:.2f}s")
    if minimum_expected_seconds and duration+0.05<minimum_expected_seconds: raise RuntimeError(f"Story narration is shorter than expected: {duration:.2f}s < {minimum_expected_seconds:.2f}s")
    print(f"🛡️ COMPLETE STORY AUDIO CHECK: {duration:.2f}s — full narration file present"); return duration
def _assert_final_audio_contains_story(final_path,narration_duration):
    duration=_audio_duration(final_path)
    if duration+0.05<narration_duration: raise RuntimeError(f"Final MP4 audio is shorter than source narration: {duration:.2f}s < {narration_duration:.2f}s")
    print(f"🛡️ FINAL STORY AUDIO CHECK: {duration:.2f}s >= narration {narration_duration:.2f}s"); return duration
def _save_social_queue(data):
    save(data,SOCIAL_QUEUE_PATH); print(f"💾 Story social recovery queued | run={data.get('run_id')} | artifact={data.get('artifact_name')}")
def _clear_social_queue():
    try: os.remove(SOCIAL_QUEUE_PATH); print("✅ Story social recovery queue cleared")
    except FileNotFoundError: pass
def _social_has_failures(result):
    return any(isinstance(payload,dict) and str(payload.get("status") or "").lower()=="failed" for payload in (result or {}).values())
def _set_publication_status(status, video_id="", reason=""):
    save_publication_state(".story_publication_status.json", {
        "status": status,
        "video_id": str(video_id or ""),
        "youtube_url": f"https://www.youtube.com/shorts/{video_id}" if video_id else "",
        "reason": str(reason or ""),
        "updated_at": int(time.time()),
    })
def _render_is_reusable(final_path,manifest_path,script_path):
    if not (os.path.isfile(final_path) and os.path.isfile(manifest_path) and os.path.isfile(script_path)): return False
    try:
        with open(manifest_path,encoding="utf-8") as f: manifest=json.load(f)
        with open(script_path,encoding="utf-8") as f: script=json.load(f)
        return bool(manifest.get("status")=="complete" and manifest.get("story_number")==script.get("story_number") and manifest.get("person")==script.get("story_person") and os.path.getsize(final_path)>0)
    except (OSError,ValueError,TypeError): return False
def run():
    _set_publication_status("pending")
    config=dict(load_config() or {}); voice=dict(config.get("voice") or {}); voice.update({"provider":"kokoro","voice_name":"am_michael","kokoro_lang":"a","tone":"cinematic, warm, conversational storyteller"}); config["voice"]=voice
    print("🎙️ Story Shorts voice: am_michael (Kokoro)"); refresh_live_metrics()
    previous=get_pending_story(); pillar,topic,person=get_next_topic(); number=next_story_number()
    if previous and number<=int(previous.get("number",0)): raise RuntimeError(f"Invalid story sequence state: next #{number} must follow pending Story #{previous.get('number')}.")
    print(f"📖 STORY SHORT #{number} | {pillar} | {person}")
    feedback=f"""STORY SHORT #{number} — RETENTION-FIRST REAL-PERSON LOOP STORY.
SUBJECT: {topic}
PERSON: {person}
FORMAT: {pillar}
Create a self-contained story. Do not mention the previous story or tease a future specific person.
The viewer must hear the COMPLETE story from hook through payoff. Never omit, truncate, or compress away the final story beat just to meet a preferred duration.
This Short MUST use a spoken loop: Scene 1 opens with a distinctive hook; Scene 7 ends with a natural sentence that echoes that hook so the restart feels like the continuation of the ending.
The viewer should understand the emotional arc with the phone face-down.
ALL PRODUCTION MEDIA MUST COME FROM THE STORY ARCHIVAL MEDIA ADAPTER. Prefer real-person archival videos first, then archival photographs when suitable video is unavailable. Do not use generic commercial stock footage or generic stock images for identity moments.
Use a hard hook, concrete stakes, an obstacle, a meaningful decision or turning point, escalation, and a satisfying payoff.
Do NOT include a subscribe/follow CTA in the narration. End the spoken story on the natural loop-closing sentence.
Do not turn the ending into a motivational lecture. Do not create or mention a next-topic teaser; this Story Shorts line is standalone.
Do not expose the loop with words like replay, loop, watch again, or back to the beginning.
"""
    try:
        script=_generate_story_script(topic,config,feedback); script.update({"topic":topic,"story_number":number,"story_person":person,"interactive_pillar":pillar,"story_visual_mode":"person_first_archival_video_first"}); _validate_story_contract(script)
    except Exception as error:
        if str(error).startswith("STORY_GEMINI_QUOTA_DEFERRED:"):
            Path(".story_gemini_quota_deferred").write_text(
                "STORY_GEMINI_QUOTA_DEFERRED\\n",
                encoding="utf-8",
            )
            print("⏸️ Story Shorts production intentionally deferred; reserved subject remains authoritative for the next run.")
            return
        try:
            from story_topic_runtime import release_reservation
            release_reservation(pillar,topic,person)
        except Exception as release_error: print(f"⚠️ Story reservation release failed: {type(release_error).__name__}: {release_error}")
        raise
    workdir=os.path.join("output","interactive",str(int(time.time()))); os.makedirs(workdir,exist_ok=True); script_path=os.path.join(workdir,"script.json"); save(script,script_path)
    audio=synthesize_script(script,config,os.path.join(workdir,"audio"))
    if isinstance(audio,dict): audio=audio.get("audio_path") or audio.get("path") or audio.get("output_path")
    elif isinstance(audio,(tuple,list)): audio=next((x for x in audio if isinstance(x,(str,os.PathLike)) and os.path.isfile(os.fspath(x))),audio[0] if audio else None)
    if not isinstance(audio,(str,os.PathLike)) or not os.path.isfile(os.fspath(audio)): raise RuntimeError(f"Story narration file invalid: {audio!r}")
    audio=os.path.abspath(os.fspath(audio)); narration_duration=_assert_complete_story_audio(audio); print(f"🎙️ Story narration ready: {audio}")
    visuals=generate_media(script,os.path.join(workdir,"visuals"),config)
    media_paths=[str(item.get("path")) for item in visuals if isinstance(item,dict) and item.get("path")]
    validate_story_media(media_paths)
    if len(visuals)!=14: raise RuntimeError(f"Story visual contract requires 14 provider assets; received {len(visuals)}.")
    print(f"👤 Story archival visuals applied: {len(visuals)} assets validated")
    script["story_person_media"]={"source":"Story archival media adapter","verified_assets":len(visuals),"target_scenes":[1,2,3,4,5,6,7]}; save(script,script_path)
    sfx=generate_sfx(script,os.path.join(workdir,"sfx")); music=download_music(script,os.path.join(workdir,"music")); final=os.path.join(workdir,"final.mp4"); manifest_path=os.path.join(workdir,RENDER_MANIFEST)
    if _render_is_reusable(final,manifest_path,script_path):
        print(f"♻️ REUSING COMPLETED STORY RENDER: {final}")
    else:
        assemble_video(script,[audio],visuals,music,sfx,config,final)
        save({"schema_version":1,"status":"complete","story_number":number,"person":person,"final":final,"created_at":int(time.time())},manifest_path)
        print(f"✅ Story render completed and checkpointed: {final}")
    _assert_final_audio_contains_story(final,narration_duration); q=validate_final_video(final); save(q,os.path.join(workdir,"validation.json"))
    if not q.get("ok"): raise RuntimeError("Story final video validation failed.")
    title=_title(pillar,person); desc=f"A remarkable true story about {person} — the struggle, turning point, and moment that changed everything.\n\nWhat would you have done in {person}'s situation? 👇\n\nSubscribe and follow for more powerful stories about people who faced setbacks, made difficult choices, and changed their lives.\n\n#StoryShorts #TrueStory #Inspiration #Shorts"
    engagement=(script.get("engagement") or {}).get("comment") or f"What would you have done in {person}'s situation? 👇"
    script["engagement"]={"comment":engagement}; save(script,script_path)
    result=upload_video(final,title,desc,config,engagement_comment=engagement)
    vid=result if isinstance(result,str) else str(result.get("video_id") or result.get("id") or "") if isinstance(result,dict) else ""
    if not vid:
        _set_publication_status("upload_failed", reason="YouTube upload returned no video ID")
        raise RuntimeError("Story upload returned no video ID; sequence state was not advanced.")
    _set_publication_status("youtube_uploaded", vid)
    _save_social_queue({"schema_version":1,"run_id":str(os.environ.get("GITHUB_RUN_ID") or ""),"artifact_name":f"story-shorts-{os.environ.get('GITHUB_RUN_ID','')}","workdir":workdir,"final_relative":os.path.relpath(final,"."),"video_id":vid,"topic":topic,"pillar":pillar,"person":person,"number":number,"title":title,"description":desc})
    social_result=publish_social_reels(final,title,desc,config,workdir); print("📱 Story social publish summary:",json.dumps({name:(payload or {}).get("status") for name,payload in social_result.items() if name in {"instagram","facebook"}},ensure_ascii=False))
    if _social_has_failures(social_result):
        failed = [name for name, payload in (social_result or {}).items() if isinstance(payload, dict) and str(payload.get("status") or "").lower()=="failed"]
        _set_publication_status("social_failed", vid, "Failed social destinations: " + ", ".join(failed))
        raise RuntimeError("Story social publishing failed: " + ", ".join(failed))
    _clear_social_queue()
    _set_publication_status("complete", vid)
    record_topic(topic,pillar,title,vid,workdir,person=person); save_pending_story(pillar,topic,person,number); record_analytics(vid,topic,pillar,title,workdir,person=person); print("📊 Story comparison:",json.dumps(build_comparison(),ensure_ascii=False))
if __name__=="__main__": run()
