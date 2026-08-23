"""Mint-YT-Factory production pipeline.

CURRENT MODE: ENTERTAINMENT-FIRST + SELF-LEARNING

Topic -> fresh analytics refresh -> learned creative brief -> entertaining
script/storyboard -> TTS -> AI visuals -> music -> assembly -> quality
validation -> upload -> analytics registry.
"""
from __future__ import annotations
import argparse,json,os,re,time,yaml
from topics import (get_next_topic,save_next_short,commit_topic,validate_topic_for_pipeline,_generate_topic,_read_used,_PENDING_PREFIX)
from generate_script import generate_script
from tts import synthesize_script
from generate_images import generate_images
from music import download_music
from assemble import assemble_video
from upload_youtube import upload_video
from validate_video import validate_final_video
from learning_context import load_learning_context
from learning_engine import refresh_playbook
CONTINUATION_MANIFEST="continuation_state.json"
def load_config():
    with open("config.yaml","r",encoding="utf-8") as handle: config=yaml.safe_load(handle)
    if not isinstance(config,dict): raise RuntimeError("config.yaml is invalid.")
    return config
def save_json(data,path):
    directory=os.path.dirname(path)
    if directory: os.makedirs(directory,exist_ok=True)
    with open(path,"w",encoding="utf-8") as handle: json.dump(data,handle,indent=2,ensure_ascii=False)
def _normalise_topic_text(value): return re.sub(r"[^a-z0-9]+"," ",str(value or "").lower()).strip()
def _topic_is_same(a,b): return _normalise_topic_text(a)==_normalise_topic_text(b)
def _word_count(value): return len(re.findall(r"\b[\w'-]+\b",str(value or "")))
def _split_sentences(text): return [p.strip() for p in re.split(r"(?<=[.!?])\s+",str(text or "").strip()) if p.strip()]
def _looks_like_future_topic_teaser(sentence):
    text=str(sentence or "").strip()
    if not text:return False
    patterns=(r"^(?:and\s+)?next\b",r"^wonder\s+why\b",r"^ever\s+wonder\s+why\b",r"^curious\s+(?:why|how|what|when)\b",r"^why\s+(?:do|does|is|are|can|doesn['’]t|isn['’]t)\b",r"^how\s+(?:do|does|is|are|can|come)\b",r"^what\s+(?:makes|happens|causes|would|if)\b",r"^watch\s+what\s+happens\b",r"^(?:then\s+comes|which\s+brings\s+us\s+to|the\s+weird\s+part\??|i['’]?m\s+still\s+wondering)\b",r"\b(?:next\s+video|coming\s+next|stay\s+tuned|part\s+2)\b")
    return any(re.search(pattern,text,re.I) for pattern in patterns)
def _remove_existing_continuation(narration,next_topic):
    topic_key=_normalise_topic_text(next_topic);kept=[]
    for sentence in _split_sentences(narration):
        key=_normalise_topic_text(sentence)
        if topic_key and topic_key in key:continue
        if _looks_like_future_topic_teaser(sentence):continue
        if re.search(r"\b(bigger question|one more thing to wonder about)\b",sentence,re.I):continue
        kept.append(sentence)
    return " ".join(kept).strip()
def _topic_as_natural_question(next_topic):
    text=re.sub(r"\s+"," ",str(next_topic or "").strip()).rstrip(".!?")
    text=re.sub(r"^why\s+do\s+","why ",text,flags=re.I);text=re.sub(r"^why\s+does\s+","why ",text,flags=re.I);text=re.sub(r"^why\s+is\s+","why ",text,flags=re.I);text=re.sub(r"^why\s+are\s+","why ",text,flags=re.I);text=re.sub(r"^how\s+do\s+","how ",text,flags=re.I);text=re.sub(r"^how\s+does\s+","how ",text,flags=re.I);text=re.sub(r"^what\s+makes\s+","what makes ",text,flags=re.I)
    return text.strip()
def _build_locked_final_sentence(next_topic):return f"Then comes an even weirder question: {_topic_as_natural_question(next_topic)}?"
def _final_scene_has_only_one_continuation_topic(narration,canonical):
    sentences=_split_sentences(narration);canonical_key=_normalise_topic_text(canonical);continuation_sentences=[s for s in sentences if _looks_like_future_topic_teaser(s)]
    return len(continuation_sentences)==1 and bool(canonical_key and canonical_key in _normalise_topic_text(continuation_sentences[0]))
def lock_next_topic(script,current_topic):
    next_short=script.get("next_short") or {};candidate=str(next_short.get("topic","")).strip()
    if not candidate:raise RuntimeError("Generated script did not provide next_short.topic.")
    used=[str(current_topic)];used.extend(item for item in _read_used() if not str(item).startswith(_PENDING_PREFIX))
    canonical=candidate if validate_topic_for_pipeline(candidate,used=used,check_duplicate=True) else _generate_topic(used)
    if not validate_topic_for_pipeline(canonical,used=used,check_duplicate=True):raise RuntimeError(f"Could not create valid canonical next topic: {canonical}")
    if _word_count(canonical)>7:
        canonical=_generate_topic(used)
        if _word_count(canonical)>7:raise RuntimeError(f"Generated continuation is still too long: {canonical}")
    script["next_short"]["topic"]=canonical;script["next_short"]["teaser"]=_build_locked_final_sentence(canonical);scenes=script.get("scene_plan")
    if not isinstance(scenes,list) or len(scenes)!=7:raise RuntimeError("Script must contain exactly 7 scenes.")
    final_scene=scenes[-1];base=_remove_existing_continuation(str(final_scene.get("narration","")).strip(),canonical)
    if not base:base="And that is the strange part"
    final_scene["narration"]=f"{_compact_payoff(base,10)} {_build_locked_final_sentence(canonical)}".strip();final_scene["subtitle_text"]=final_scene["narration"];final_scene["pause_after_ms"]=250;final_scene["emotional_tone"]="satisfied";final_scene["music_cue"]="fade_out"
    teaser_words=re.findall(r"\b[\w'-]+\b",canonical);final_scene["caption_highlights"]=[{"word":w,"emphasis":"strong"} for w in teaser_words[:3]] or [{"word":canonical.split()[0],"emphasis":"strong"}];final_scene["emphasis_word"]=teaser_words[0] if teaser_words else canonical.split()[0];canonical_key=_normalise_topic_text(canonical)
    if canonical_key not in _normalise_topic_text(final_scene["narration"]):raise RuntimeError("Canonical next topic was not inserted into final narration.")
    for scene in scenes[:6]:
        if canonical_key and canonical_key in _normalise_topic_text(scene.get("narration","")):raise RuntimeError("Next topic appeared before Scene 7.")
    if not _final_scene_has_only_one_continuation_topic(final_scene["narration"],canonical):raise RuntimeError("Scene 7 contains more than one future-topic teaser; continuation integrity failed.")
    print(f"🔒 Canonical next topic: {canonical}");print(f"🗣️ FINAL SPOKEN TEASE: {final_scene['narration']}");return script,canonical
def _compact_payoff(narration,max_words=10):
    sentences=_split_sentences(narration);chosen=[];total=0
    for sentence in reversed(sentences):
        if _looks_like_future_topic_teaser(sentence):continue
        words=_word_count(sentence)
        if not words:continue
        if total+words<=max_words:chosen.insert(0,sentence.rstrip(".!? "));total+=words
        elif not chosen:chosen.insert(0," ".join(re.findall(r"\S+",sentence)[:max_words]).rstrip(".!? "));break
        else:break
    return (" ".join(chosen).strip() or "And that is the strange part").rstrip(".!?")+"."
def write_continuation_manifest(current_topic,next_topic,status,workdir=""):save_json({"status":status,"current_topic":current_topic,"next_topic":next_topic,"workdir":workdir,"updated_at":int(time.time())},CONTINUATION_MANIFEST)
def build_youtube_metadata(script):
    topic=str(script.get("topic","Wonder Minute curiosity")).strip();title=str(script.get("title",topic or "Wonder Minute Short")).strip()[:100];description=f"A quick look at {topic} and the everyday mystery behind it.";tags=script.get("tags",[]);hashtags=[]
    if isinstance(tags,list):
        for tag in tags[:12]:
            tag=str(tag).strip().replace("#","").replace(" ","")
            if tag:hashtags.append(f"#{tag}")
    if hashtags:description=f"{description}\n\n{' '.join(hashtags)}"
    return title,description[:4500]
def refresh_learning_before_generation():
    print("="*80);print("📊 REFRESHING LIVE YOUTUBE ANALYTICS BEFORE GENERATION");print("="*80)
    try:
        from youtube_analytics import refresh_registry
        summary=refresh_registry();print(f"📊 Analytics refreshed: {summary.get('video_count',0)} videos | optimization_ready={summary.get('optimization_ready',False)}")
    except Exception as error:print(f"⚠️ Live analytics refresh unavailable: {type(error).__name__}: {error}");print("⚠️ Continuing with the last saved learning state.")
    try:
        playbook=refresh_playbook();print(f"🧠 Learning playbook refreshed: {playbook.get('video_count',0)} videos | learning_ready={playbook.get('learning_ready',False)}")
    except Exception as error:print(f"⚠️ Learning playbook refresh unavailable: {type(error).__name__}: {error}")
def run(dry_run=False):
    config=load_config();print("="*80);print("🚀 MINT-YT-FACTORY — ENTERTAINMENT-FIRST + SELF-LEARNING");print("="*80);print("🧠 Self-learning: ENABLED");print("📈 Objective: views + subscriber growth + YPP readiness");print("🔁 Learning strategy: 70% proven patterns / 20% adjacent experiments / 10% wild experiments");print("🚫 Duplicate-topic protection: ENABLED");refresh_learning_before_generation();topic=get_next_topic()
    if not topic:raise RuntimeError("No topic available.")
    print(f"🎯 CURRENT TOPIC: {topic}");learning_context=load_learning_context();print("="*80);print("🧠 LOADED CHANNEL LEARNING PLAYBOOK");print("="*80);print(learning_context[:3500]);print("="*80);print("✍️ GENERATING ENTERTAINING STORY WITH LEARNED PATTERNS");print("="*80)
    script=generate_script(topic,config,None,extra_feedback=learning_context);script,next_topic=lock_next_topic(script,topic);workdir=os.path.join("output",str(int(time.time())));os.makedirs(workdir,exist_ok=True);save_json(script,os.path.join(workdir,"script.json"));write_continuation_manifest(topic,next_topic,"locked",workdir);print(f"✅ Script ready: {workdir}/script.json");print(f"➡️ LOCKED Next Short: {next_topic}")
    if dry_run:print("✅ DRY RUN COMPLETE");return
    print("="*80);print("🎙️ GENERATING NARRATION");print("="*80);audio=synthesize_script(script,config,os.path.join(workdir,"audio"))
    try:
        from moviepy.editor import AudioFileClip
        clip=AudioFileClip(audio);duration=float(clip.duration);clip.close();print(f"Narration duration: {duration:.2f}s")
        if duration>44.35:raise RuntimeError(f"Narration is too long ({duration:.2f}s).")
    except RuntimeError:raise
    except Exception as error:print(f"⚠️ Narration duration check skipped: {error}")
    print("="*80);print("🖼️ GENERATING STORY-DRIVEN VISUALS");print("="*80);visuals=generate_images(script,os.path.join(workdir,"visuals"),config);print("="*80);print("🎵 SELECTING MUSIC");print("="*80);music=download_music(script,os.path.join(workdir,"music"));sfx=[];final_video=os.path.join(workdir,"final.mp4");print("="*80);print("🎬 ASSEMBLING SHORT");print("="*80);assemble_video(script,audio,visuals,music,sfx,config,final_video)
    if not os.path.exists(final_video):raise RuntimeError("Final video was not created.")
    video_settings=config.get("video",{});target_bitrate=68.0
    try:target_bitrate=float(str(video_settings.get("bitrate","68M")).upper().replace("M",""))
    except Exception:pass
    quality=validate_final_video(final_video,expected_bitrate_mbps=target_bitrate);save_json(quality,os.path.join(workdir,"video_quality.json"))
    if not config.get("upload",{}).get("auto_upload",False):print("⚠️ AUTO UPLOAD DISABLED — topic remains uncommitted.");return
    title,description=build_youtube_metadata(script);print("="*80);print("🚀 UPLOADING SHORT");print("="*80);upload_result=upload_video(final_video,title,description,config);print(f"✅ Upload completed: {upload_result}");write_continuation_manifest(topic,next_topic,"published",workdir)
    try:
        from youtube_analytics import record_upload
        record_upload(upload_result,topic,title,workdir,production_metadata={"topic_category":script.get("topic_category",topic),"hook_type":script.get("hook_type",script.get("scene_plan",[{}])[0].get("retention_purpose","")),"story_structure":"7-scene curiosity story","visual_style":script.get("visual_identity",{}).get("style",""),"music_type":script.get("music",{}).get("arc",""),"voice":script.get("voice_style",{}).get("tone","")});refresh_playbook()
    except Exception as analytics_error:print(f"⚠️ Analytics/learning refresh skipped: {analytics_error}")
    print("="*80);print("🔗 SAVING EXACT NEXT SHORT");print("="*80);queued_topic=save_next_short(next_topic)
    if not queued_topic:raise RuntimeError("Upload succeeded but next_short could not be saved.")
    if not _topic_is_same(queued_topic,next_topic):raise RuntimeError(f"CONTINUATION INTEGRITY FAILURE: spoken={next_topic!r}, queued={queued_topic!r}")
    print(f"✅ Next Short queued EXACTLY: {queued_topic}");print("="*80);print("📌 COMMITTING CURRENT TOPIC");print("="*80);committed=commit_topic(topic)
    if committed is False:raise RuntimeError("Upload succeeded but current topic could not be committed.")
    write_continuation_manifest(topic,next_topic,"queued",workdir);print("🎉 SELF-LEARNING PIPELINE COMPLETE");print(f"Published: {topic}");print(f"Next run MUST use: {next_topic}")
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--dry-run",action="store_true");args=parser.parse_args();run(dry_run=args.dry_run)
