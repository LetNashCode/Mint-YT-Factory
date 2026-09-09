"""Mint-YT-Factory production pipeline."""
from __future__ import annotations
import argparse, json, os, re, time, yaml
from topics import get_next_topic, save_next_short, commit_topic, validate_topic_for_pipeline, _generate_topic, _read_used, _PENDING_PREFIX, reserve_next_short
from generate_script import generate_script
from tts import synthesize_script
from stock_media_resilient import generate_media
from music import download_music
from sfx import generate_sfx
from assemble import assemble_video
from upload_youtube import upload_video
from pathlib import Path
from social_publish import publish_social_reels
from validate_video import validate_final_video
from learning_context import load_learning_context
from learning_engine import refresh_playbook, get_playbook, score_candidate_topic, select_creative_strategy
from topic_history import record_topic

CONTINUATION_MANIFEST = "continuation_state.json"
EXPECTED_UPLOAD_BITRATE_MBPS = 100.0
MIN_UPLOAD_BITRATE_MBPS = 80.0
EXPECTED_UPLOAD_RESOLUTION = (2160, 3840)
EXPECTED_UPLOAD_FPS = 60
MAX_SCRIPT_ATTEMPTS = 4
MAX_TRANSIENT_GEMINI_RETRIES = 8


def load_config():
    with open("config.yaml", "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict): raise RuntimeError("config.yaml is invalid.")
    return config

def save_json(data, path):
    directory = os.path.dirname(path)
    if directory: os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle: json.dump(data, handle, indent=2, ensure_ascii=False)

def _normalise_topic_text(value): return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
def _word_count(value): return len(re.findall(r"\b[\w'-]+\b", str(value or "")))
def _split_sentences(text): return [p.strip() for p in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if p.strip()]
_BANNED_BRIDGE_PATTERNS=(r"^(?:and\s+)?next\b",r"^then\s+comes\b",r"^coming\s+next\b",r"^up\s+next\b",r"^stay\s+tuned\b",r"^part\s+2\b",r"^have\s+you\s+ever\s+wondered\b",r"^ever\s+wondered\b",r"^wonder\s+why\b",r"^curious\s+(?:why|how|what)\b")
def _is_canned_bridge(sentence): return any(re.search(pattern,str(sentence or "").strip(),re.I) for pattern in _BANNED_BRIDGE_PATTERNS)
def _content_words(value):
    stop={"why","what","when","where","how","does","do","did","is","are","the","and","that","this","with","from","into","your","about"}
    return {w for w in re.findall(r"[a-z0-9]+",str(value or "").lower()) if len(w)>=4 and w not in stop}
def _bridge_matches_topic(bridge,topic): return bool(_content_words(topic)&_content_words(bridge)) if _content_words(topic) else True

def _generate_natural_bridge(current_topic,next_topic):
    """Create a natural spoken handoff while keeping the exact locked topic."""
    current=str(current_topic or "").strip().rstrip(".!?")
    nxt=str(next_topic or "").strip().rstrip(".!?")
    if not nxt: raise RuntimeError("Continuation topic is empty.")
    variants=(
        f"And once you notice that, there's another everyday mystery hiding in plain sight: {nxt}?",
        f"So now you know the trick behind {current.lower()}; here's another one you'll probably notice today: {nxt}?",
        f"And that's the fun part of everyday life—one mystery solved, another waiting for you: {nxt}?",
        f"Now that little mystery makes sense. But here's one more you can't unsee once you notice it: {nxt}?",
    )
    seed=sum(ord(c) for c in current+"|"+nxt)
    return variants[seed%len(variants)]+""

def _lock_canonical_topic(script,current_topic,locked_topic=None):
    used=[str(current_topic)]; used.extend(x for x in _read_used() if not str(x).startswith(_PENDING_PREFIX))
    candidate=str(locked_topic or (script.get("next_short") or {}).get("topic","")).strip()
    if not validate_topic_for_pipeline(candidate,used=used,check_duplicate=True):
        candidate=_generate_topic(used); print("🛠️ Repaired invalid next_short.topic with topic engine: "+candidate)
    if _word_count(candidate)>7: raise RuntimeError("Generated next topic is too long for continuation metadata: "+candidate)
    script.setdefault("next_short",{})["topic"]=candidate; return candidate

def _strip_model_continuation_from_scene7(final_scene,stale_topics):
    narration=str(final_scene.get("narration","")).strip(); sentences=_split_sentences(narration)
    stale_keys=[_normalise_topic_text(x) for x in stale_topics if _normalise_topic_text(x)]
    kept=[]; removed=False
    for sentence in sentences:
        if any(k and k in _normalise_topic_text(sentence) for k in stale_keys): removed=True
        else: kept.append(sentence)
    payoff=" ".join(kept).strip() if removed else narration
    if removed: print("🧹 Removed model-authored continuation from Scene 7 before canonical lock")
    if payoff:
        p=payoff.rstrip(".!? ").strip()
        for visual in final_scene.get("visuals") or []:
            if not isinstance(visual,dict): continue
            visual["spoken_line"]=payoff; visual["visual_focus"]=p[:180]; visual["visual_action"]=f"Show the exact physical payoff described by: {p}."; visual["must_show"]=list(_content_words(p))[:6]; visual["must_not_show"]=["unrelated second topic","different object","new mystery","continuation topic"]; visual["image_prompt"]=("Realistic cinematic close-up showing the exact physical payoff: "+p+". Keep the same subject and environment as the current story, natural lighting, believable materials, no text.")[:900]
    return payoff

def lock_next_topic(script,current_topic,locked_topic=None):
    previous=str((script.get("next_short") or {}).get("topic") or "").strip(); canonical=_lock_canonical_topic(script,current_topic,locked_topic=locked_topic); final_scene=script["scene_plan"][-1]
    payoff=_strip_model_continuation_from_scene7(final_scene,[previous,canonical]); bridge=_generate_natural_bridge(current_topic,canonical)
    if payoff and not payoff.endswith((".","!","?")): payoff+="."
    final_scene["narration"]=(payoff+" "+bridge).strip(); final_scene["subtitle_text"]=final_scene["narration"]; script.setdefault("next_short",{})["teaser"]=bridge
    print("🔒 Canonical next topic: "+canonical); print("🗣️ NATURAL FINAL BRIDGE: "+bridge); return script,canonical

def _is_transient_gemini_error(error):
    text=str(error or "").lower(); return any(x in text for x in ("503","unavailable","high demand","resource exhausted","429","rate limit","deadline exceeded","timeout","temporarily"))
def write_continuation_manifest(current_topic,next_topic,status,workdir=""): save_json({"status":status,"current_topic":current_topic,"next_topic":next_topic,"workdir":workdir,"updated_at":int(time.time())},CONTINUATION_MANIFEST)
def build_youtube_metadata(script):
    topic=str(script.get("topic","Wonder Minute curiosity")).strip(); title=str(script.get("title",topic or "Wonder Minute Short")).strip()[:100]; description=f"A quick look at {topic} and the everyday mystery behind it."; tags=script.get("tags",[]); hashtags=[]
    if isinstance(tags,list):
        for tag in tags[:12]:
            tag=str(tag).strip().replace("#","").replace(" ","")
            if tag: hashtags.append("#"+tag)
    if hashtags: description+="\n\n"+" ".join(hashtags)
    return title,description[:4500]
def refresh_learning_before_generation():
    print("="*80); print("📊 REFRESHING LIVE YOUTUBE ANALYTICS BEFORE GENERATION"); print("="*80)
    try:
        from youtube_analytics import refresh_registry; summary=refresh_registry(); print(f"📊 Analytics refreshed: {summary.get('video_count',0)} videos | optimization_ready={summary.get('optimization_ready',False)}")
    except Exception as error: print(f"⚠️ Live analytics refresh unavailable: {type(error).__name__}: {error}")
    try:
        playbook=refresh_playbook(); print(f"🧠 Learning playbook refreshed: {playbook.get('video_count',0)} videos | learning_ready={playbook.get('learning_ready',False)}")
    except Exception as error: print(f"⚠️ Learning playbook refresh unavailable: {type(error).__name__}: {error}")
def _generate_valid_script(topic,config,learning_context,engagement_feedback):
    feedback=learning_context+engagement_feedback+"""
CONTINUATION ARCHITECTURE:
Write ONLY the complete 7-scene story for the CURRENT TOPIC.
Scene 7 must end with a satisfying payoff for the CURRENT TOPIC.
Do not put a future-topic teaser, preview, CTA, or continuation sentence into any scene.
Return next_short.topic as metadata when possible. The production pipeline can repair missing continuation metadata after the current story passes its quality gates.
"""; last_error=None; valid_attempt=0; transient_attempt=0
    while valid_attempt<MAX_SCRIPT_ATTEMPTS:
        try: script=generate_script(topic,config,None,extra_feedback=feedback); _lock_canonical_topic(script,topic); return script
        except Exception as error:
            last_error=error
            if _is_transient_gemini_error(error) and transient_attempt<MAX_TRANSIENT_GEMINI_RETRIES:
                transient_attempt+=1; delay=min(45,5*transient_attempt); print(f"⏳ Transient Gemini failure — retrying without consuming script attempt ({transient_attempt}/{MAX_TRANSIENT_GEMINI_RETRIES}) in {delay}s: {error}"); time.sleep(delay); continue
            valid_attempt+=1; print(f"⚠️ Story generation failed ({valid_attempt}/{MAX_SCRIPT_ATTEMPTS}): {error}")
    raise RuntimeError(f"Could not generate a valid current-topic story after {MAX_SCRIPT_ATTEMPTS} attempts: {last_error}")

def _find_pending_resume():
    candidates=sorted(Path("output").glob("*/final.mp4"),key=lambda p:p.stat().st_mtime,reverse=True)
    for video in candidates:
        workdir=video.parent; manifest=workdir/"publish_state.json"; script_path=workdir/"script.json"
        if manifest.exists() and script_path.exists():
            try:
                state=json.loads(manifest.read_text(encoding="utf-8"))
                if state.get("status")=="ready_for_upload" and not state.get("uploaded"): return workdir,video,json.loads(script_path.read_text(encoding="utf-8")),state
            except Exception: pass
    return None
def _save_publish_state(workdir,state): save_json(state,os.path.join(workdir,"publish_state.json"))

def _mark_topic_bookkeeping(script,topic,next_topic,video_id,title,workdir):
    """Commit current topic and reserve its successor immediately after YouTube publication."""
    record_topic(topic,title=title,video_id=video_id,workdir=workdir,status="published")
    try:
        from youtube_analytics import record_upload
        experiment=script.get("learning_experiment") or {}
        production_metadata={"topic_category":str(script.get("category","")),"hook_type":str((script.get("scene_plan") or [{}])[0].get("purpose","")),"story_structure":"7_scene_entertainment","visual_style":str((script.get("visual_identity") or {}).get("style","")),"music_type":str((script.get("music") or {}).get("search","")),"voice":str((script.get("voice_style") or {}).get("tone","")),"engagement_experiment":str((script.get("engagement") or {}).get("experiment","")),"audio_duration_seconds":float(script.get("audio_duration_seconds",0) or 0),"words_per_second":float(script.get("words_per_second",0) or 0),"creative_strategy":str(experiment.get("strategy","")),"creative_experiment_id":str(experiment.get("experiment_id","")),"creative_selected_pattern":str(experiment.get("selected_pattern",""))}; record_upload(video_id,topic,title,workdir=workdir,production_metadata=production_metadata); print("🧠 Published creative metadata recorded for future learning.")
    except Exception as error: print(f"⚠️ Learning metadata recording skipped: {type(error).__name__}: {error}")
    save_next_short(next_topic); commit_topic(topic); write_continuation_manifest(topic,next_topic,"published",workdir); print(f"✅ TOPIC PROGRESSION COMMITTED | current={topic} | next={next_topic}")

def _record_audio_timing(script, audio_path):
    """Persist the actual rendered narration duration so learning uses real pacing."""
    try:
        from moviepy.editor import AudioFileClip
        clip=AudioFileClip(audio_path)
        try:
            duration=float(clip.duration or 0.0)
        finally:
            clip.close()
        narration=" ".join(str(scene.get("narration","")) for scene in (script.get("scene_plan") or []) if isinstance(scene,dict))
        words=_word_count(narration)
        script["audio_duration_seconds"]=round(duration,3)
        script["narration_word_count"]=words
        script["words_per_second"]=round(words/duration,3) if duration>0 else 0.0
        print(f"⏱️ Actual narration timing: {duration:.2f}s | words={words} | WPS={script['words_per_second']:.2f}")
    except Exception as error:
        print(f"⚠️ Could not record narration timing: {type(error).__name__}: {error}")

def run(dry_run=False):
    config=load_config(); resumed=_find_pending_resume()
    if resumed:
        workdir_path,video_path,script,publish_state=resumed; workdir=str(workdir_path); final_video=str(video_path); topic=str(script.get("topic","")); next_topic=str((script.get("next_short") or {}).get("topic","")); print(f"♻️ RESUMING UNPUBLISHED FINAL VIDEO: {final_video}"); print("⏭️ Skipping generation, narration, visuals and rendering.")
    else: workdir=None; final_video=None
    print("="*80); print("🚀 MINT-YT-FACTORY — ENTERTAINMENT-FIRST + SELF-LEARNING + SFX"); print("="*80); print("🧠 Self-learning: ENABLED"); print("💬 Engagement learning: sequential comment/share experiments ENABLED")
    if not resumed: refresh_learning_before_generation(); topic=get_next_topic()
    if not resumed and topic:
        decision=score_candidate_topic(topic,get_playbook()); print(f"🧠 Learning topic score: {decision['score']} | features={decision['features']}");
        if decision.get("reasons"): print("🧠 Learning signals: "+"; ".join(decision["reasons"]))
    if not resumed and not topic: raise RuntimeError("No topic available.")
    print(f"🎯 CURRENT TOPIC: {topic}")
    if not resumed:
        try:
            from engagement_experiments import assign,summarize; engagement=assign(topic); print(f"🧪 Engagement experiment: {engagement['experiment']} | phase={engagement['phase']}"); print(f"💬 Planned comment: {engagement['comment']}"); print(f"🔄 Share trigger: {engagement['share_prompt']}"); print(f"📊 Existing experiment results: {json.dumps(summarize(),ensure_ascii=False)}")
        except Exception as error: engagement={"experiment":"none","phase":"disabled","spoken_prompt":"","comment":"","share_prompt":""}; print(f"⚠️ Engagement experiment setup skipped: {type(error).__name__}: {error}")
    else:
        engagement=dict((script.get("engagement") or {})); engagement.setdefault("comment",""); engagement.setdefault("experiment","resume"); engagement.setdefault("phase","resume"); engagement.setdefault("spoken_prompt",""); engagement.setdefault("share_prompt","")
    if not resumed:
        playbook=get_playbook(); creative_strategy=select_creative_strategy(playbook); print(f"🧪 Creative strategy: {creative_strategy['strategy']} | mix={creative_strategy['slot']}/10 | id={creative_strategy['experiment_id']}");
        if creative_strategy.get("selected_pattern"): print(f"🧠 Selected learned pattern: {creative_strategy['selected_pattern']} | score={creative_strategy['selected_score']:.2f} | n={creative_strategy['selected_sample_size']}")
        learning_context=load_learning_context(); creative_feedback=f"\nCREATIVE EXPERIMENT FOR THIS SHORT:\nStrategy: {creative_strategy['strategy']}\nExperiment ID: {creative_strategy['experiment_id']}\nTarget mix: 70% proven / 20% adjacent / 10% wild.\nSelected learned pattern: {creative_strategy.get('selected_pattern') or 'none'}\nExperiment guidance: {creative_strategy['guidance']}\nDo not copy any learned wording, topic, example, or visual concept. Preserve originality and story quality.\n"; engagement_feedback=f"\nENGAGEMENT EXPERIMENT FOR THIS SHORT: {engagement['experiment']}\nUse the mechanic naturally if it fits. Never sound like engagement bait.\nSuggested spoken interaction: {engagement['spoken_prompt']}\nDo not add generic like/subscribe language.\n"; print("✍️ GENERATING ENTERTAINING STORY WITH LEARNED PATTERNS"); script=_generate_valid_script(topic,config,learning_context,creative_feedback+engagement_feedback); script["learning_experiment"]={"strategy":creative_strategy["strategy"],"experiment_id":creative_strategy["experiment_id"],"slot":creative_strategy["slot"],"cycle":creative_strategy["cycle"],"target_mix":creative_strategy["target_mix"],"selected_pattern":creative_strategy.get("selected_pattern",""),"selected_score":creative_strategy.get("selected_score",0.0),"selected_sample_size":creative_strategy.get("selected_sample_size",0),"evidence_based":creative_strategy.get("evidence_based",False)}; next_topic=reserve_next_short(str((script.get("next_short") or {}).get("topic") or ""),current_topic=topic); script["next_short"]=dict(script.get("next_short") or {}); script["next_short"]["topic"]=next_topic; script,next_topic=lock_next_topic(script,topic,locked_topic=next_topic); script["engagement"]={"experiment":engagement["experiment"],"phase":engagement["phase"],"spoken_prompt":engagement["spoken_prompt"],"comment":engagement["comment"],"share_prompt":engagement["share_prompt"]}; workdir=os.path.join("output",str(int(time.time()))); os.makedirs(workdir,exist_ok=True); save_json(script,os.path.join(workdir,"script.json")); write_continuation_manifest(topic,next_topic,"locked",workdir); print(f"✅ Script ready: {workdir}/script.json");
        if dry_run: print("✅ DRY RUN COMPLETE"); return
    if not resumed:
        audio=synthesize_script(script,config,os.path.join(workdir,"audio")); _record_audio_timing(script,audio); save_json(script,os.path.join(workdir,"script.json")); visuals=generate_media(script,os.path.join(workdir,"visuals"),config); sfx=generate_sfx(script,os.path.join(workdir,"sfx")); music=download_music(script,os.path.join(workdir,"music")); final_video=os.path.join(workdir,"final.mp4"); assemble_video(script,audio,visuals,music,sfx,config,final_video); _save_publish_state(workdir,{"status":"ready_for_upload","uploaded":False,"topic":topic,"next_topic":next_topic})
    if not os.path.exists(final_video): raise RuntimeError("Final video was not created.")
    quality=validate_final_video(final_video,expected_bitrate_mbps=EXPECTED_UPLOAD_BITRATE_MBPS); save_json(quality,os.path.join(workdir,"validation.json"))
    if not quality.get("ok",False): raise RuntimeError("Final video validation failed.")
    if (quality.get("width"),quality.get("height"))!=EXPECTED_UPLOAD_RESOLUTION: raise RuntimeError("Upload blocked: final video is not 2160x3840 4K portrait.")
    if abs(float(quality.get("fps",0))-EXPECTED_UPLOAD_FPS)>0.05: raise RuntimeError("Upload blocked: final video is not 60 fps.")
    if float(quality.get("bitrate_mbps",0))<MIN_UPLOAD_BITRATE_MBPS: raise RuntimeError(f"Upload blocked: final video bitrate is below the {MIN_UPLOAD_BITRATE_MBPS:.0f} Mbps production floor.")
    title,description=build_youtube_metadata(script); engagement_comment=str((script.get("engagement") or {}).get("comment") or "").strip() or None; thumbnail_path=os.path.join(workdir,"thumbnail.jpg"); thumbnail_path=thumbnail_path if os.path.exists(thumbnail_path) else None
    upload_result=upload_video(final_video,title,description,config,thumbnail_path=thumbnail_path,engagement_comment=engagement_comment); video_id=str(upload_result or "").strip()
    if not video_id: raise RuntimeError("Upload succeeded without a video ID; refusing to mutate topic state.")
    _save_publish_state(workdir,{"status":"youtube_published","uploaded":True,"topic":topic,"next_topic":next_topic,"video_id":video_id})
    _mark_topic_bookkeeping(script,topic,next_topic,video_id,title,workdir)
    social_result=publish_social_reels(final_video,title,description,config,workdir); print("📱 Social publish summary:",json.dumps({name:(payload or {}).get("status") for name,payload in social_result.items() if name in {"instagram","facebook"}},ensure_ascii=False))
    state_path=Path(workdir)/"publish_state.json"
    try: state=json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    except Exception: state={}
    state.update({"status":"uploaded","uploaded":True,"topic":topic,"next_topic":next_topic,"video_id":video_id}); _save_publish_state(workdir,state); print("✅ PUBLISH SHORTS COMPLETE | topic progression is already committed")

if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--dry-run",action="store_true"); args=parser.parse_args(); run(dry_run=args.dry_run)