"""Mint-YT-Factory production pipeline."""
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
EXPECTED_UPLOAD_BITRATE_MBPS = 100.0
EXPECTED_UPLOAD_RESOLUTION = (2160, 3840)
EXPECTED_UPLOAD_FPS = 60

def load_config():
    with open("config.yaml", "r", encoding="utf-8") as handle: config = yaml.safe_load(handle)
    if not isinstance(config, dict): raise RuntimeError("config.yaml is invalid.")
    return config

def save_json(data,path):
    directory=os.path.dirname(path)
    if directory: os.makedirs(directory,exist_ok=True)
    with open(path,"w",encoding="utf-8") as handle: json.dump(data,handle,indent=2,ensure_ascii=False)

def _normalise_topic_text(value): return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
def _word_count(value): return len(re.findall(r"\b[\w'-]+\b",str(value or "")))
def _split_sentences(text): return [p.strip() for p in re.split(r"(?<=[.!?])\s+",str(text or "").strip()) if p.strip()]
_BANNED_BRIDGE_PATTERNS=(r"^(?:and\s+)?next\b",r"^then\s+comes\b",r"^coming\s+next\b",r"^up\s+next\b",r"^stay\s+tuned\b",r"^part\s+2\b",r"^have\s+you\s+ever\s+wondered\b",r"^ever\s+wondered\b",r"^wonder\s+why\b",r"^curious\s+(?:why|how|what)\b",r"^why\s+(?:do|does|is|are)\b",r"^how\s+(?:do|does|is|are)\b",r"^what\s+(?:makes|happens|causes)\b")

def _is_canned_bridge(sentence): return any(re.search(pattern,str(sentence or "").strip(),re.I) for pattern in _BANNED_BRIDGE_PATTERNS)

def _is_future_teaser(sentence):
    text=_normalise_topic_text(sentence)
    if not text: return False
    if re.search(r"\bnext\s+(?:video|short|episode|topic|one)\b",text): return True
    if "next" in text and re.search(r"\b(?:why|how|what)\b",text): return True
    if re.search(r"\bwatch\s+what\s+happens\s+when\b",text) and "next" in text: return True
    if re.search(r"\b(?:coming|up)\s+next\b",text): return True
    return False

def _validate_gemini_scene7(script,canonical):
    scenes=script.get("scene_plan")
    if not isinstance(scenes,list) or len(scenes)!=7: raise RuntimeError("Script must contain exactly 7 scenes.")
    key=_normalise_topic_text(canonical)
    if not key: raise RuntimeError("Canonical next topic is empty.")
    early=" ".join(str(scene.get("narration","")) for scene in scenes[:6])
    if key in _normalise_topic_text(early): raise RuntimeError("Next topic appeared before Scene 7.")
    final_sentences=_split_sentences(scenes[-1].get("narration",""))
    if not final_sentences: raise RuntimeError("Scene 7 has no narration.")
    final_sentence=final_sentences[-1]
    if key not in _normalise_topic_text(final_sentence): raise RuntimeError("Scene 7 final sentence does not contain the locked next topic.")
    occurrence=len(re.findall(re.escape(key),_normalise_topic_text(scenes[-1].get("narration",""))))
    if occurrence != 1: raise RuntimeError("Locked next topic must occur exactly once in Scene 7.")
    if _is_canned_bridge(final_sentence): raise RuntimeError(f"Canned Scene 7 bridge rejected: {final_sentence}")
    count=_word_count(final_sentence)
    if count < 7 or count > 24: raise RuntimeError(f"Natural Scene 7 bridge has invalid length: {count} words")
    return final_sentence

def _lock_canonical_topic(script,current_topic):
    candidate=str((script.get("next_short") or {}).get("topic","")).strip()
    if not candidate: raise RuntimeError("Generated script did not provide next_short.topic.")
    used=[str(current_topic)]; used.extend(item for item in _read_used() if not str(item).startswith(_PENDING_PREFIX))
    canonical=candidate if validate_topic_for_pipeline(candidate,used=used,check_duplicate=True) else _generate_topic(used)
    if not validate_topic_for_pipeline(canonical,used=used,check_duplicate=True): raise RuntimeError(f"Could not create valid canonical next topic: {canonical}")
    if _word_count(canonical)>7: canonical=_generate_topic(used)
    script.setdefault("next_short",{})["topic"]=canonical
    return canonical

def _install_natural_bridge(script,canonical):
    """Strip Gemini's entire attempted teaser and install exactly one controlled bridge."""
    scenes=script.get("scene_plan")
    if not isinstance(scenes,list) or len(scenes)!=7: raise RuntimeError("Script must contain exactly 7 scenes.")
    final=scenes[-1]
    sentences=_split_sentences(final.get("narration",""))
    key=_normalise_topic_text(canonical)
    clean_sentences=[]
    removed=[]
    for sentence in sentences:
        normalized=_normalise_topic_text(sentence)
        if key in normalized or _is_future_teaser(sentence):
            removed.append(sentence)
            continue
        clean_sentences.append(sentence)
    if removed:
        print(f"🧹 Removed Gemini Scene 7 teaser sentence(s): {len(removed)}")
    if not clean_sentences:
        clean_sentences=["And that is the weird little trick hiding inside this everyday moment."]
    topic_spoken=canonical.strip().rstrip("?.!").lower()
    bridge=f"Our next everyday mystery is {topic_spoken}."
    final["narration"]=" ".join(clean_sentences+[bridge])
    return bridge

def lock_next_topic(script,current_topic):
    canonical=_lock_canonical_topic(script,current_topic)
    bridge=_install_natural_bridge(script,canonical)
    _validate_gemini_scene7(script,canonical)
    script["next_short"]["teaser"]=bridge
    final_scene=script["scene_plan"][-1]
    final_scene["subtitle_text"]=final_scene.get("narration","")
    final_scene["pause_after_ms"]=int(final_scene.get("pause_after_ms",250) or 250)
    final_scene["emotional_tone"]=final_scene.get("emotional_tone","satisfied")
    final_scene["music_cue"]=final_scene.get("music_cue","fade_out")
    print(f"🔒 Canonical next topic: {canonical}")
    print(f"🗣️ CONTROLLED FINAL BRIDGE: {bridge}")
    return script,canonical

def write_continuation_manifest(current_topic,next_topic,status,workdir=""):
    save_json({"status":status,"current_topic":current_topic,"next_topic":next_topic,"workdir":workdir,"updated_at":int(time.time())},CONTINUATION_MANIFEST)

def build_youtube_metadata(script):
    topic=str(script.get("topic","Wonder Minute curiosity")).strip()
    title=str(script.get("title",topic or "Wonder Minute Short")).strip()[:100]
    description=f"A quick look at {topic} and the everyday mystery behind it."
    tags=script.get("tags",[]); hashtags=[]
    if isinstance(tags,list):
        for tag in tags[:12]:
            tag=str(tag).strip().replace("#","").replace(" ","")
            if tag: hashtags.append(f"#{tag}")
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
CONTINUATION HARD REQUIREMENT:
Return a valid 7-scene story and a candidate next_short.topic. Do NOT write ANY next-topic teaser or future-video sentence in Scene 7. Do not mention the candidate next topic anywhere in Scenes 1-6, title, or description. Scene 7 must finish the current topic's payoff naturally. The production pipeline will strip any accidental future teaser and install the only allowed final handoff.
"""
    last_error=None
    for attempt in range(1,5):
        try:
            script=generate_script(topic,config,None,extra_feedback=feedback)
            candidate=str((script.get("next_short") or {}).get("topic","")).strip()
            if not candidate: raise RuntimeError("Missing next_short.topic")
            canonical=_lock_canonical_topic(script,topic)
            _install_natural_bridge(script,canonical)
            _validate_gemini_scene7(script,canonical)
            return script
        except Exception as error:
            last_error=error
            print(f"⚠️ Continuation/story validation failed ({attempt}/4): {error}")
            feedback+=f"\nPREVIOUS ATTEMPT FAILED: {error}. Do not write a Scene 7 teaser; return only the current story plus next_short.topic.\n"
    raise RuntimeError(f"Could not generate a valid natural Scene 7 continuation after 4 attempts: {last_error}")

def run(dry_run=False):
    config=load_config(); print("="*80); print("🚀 MINT-YT-FACTORY — ENTERTAINMENT-FIRST + SELF-LEARNING + SFX"); print("="*80); print("🧠 Self-learning: ENABLED"); print("💬 Engagement learning: sequential comment/share experiments ENABLED")
    refresh_learning_before_generation(); topic=get_next_topic()
    if not topic: raise RuntimeError("No topic available.")
    print(f"🎯 CURRENT TOPIC: {topic}")
    try:
        from engagement_experiments import assign,summarize; engagement=assign(topic); print(f"🧪 Engagement experiment: {engagement['experiment']} | phase={engagement['phase']}"); print(f"💬 Planned comment: {engagement['comment']}"); print(f"🔄 Share trigger: {engagement['share_prompt']}"); print(f"📊 Existing experiment results: {json.dumps(summarize(),ensure_ascii=False)}")
    except Exception as error:
        engagement={"experiment":"none","phase":"disabled","spoken_prompt":"","comment":"","share_prompt":""}; print(f"⚠️ Engagement experiment setup skipped: {type(error).__name__}: {error}")
    learning_context=load_learning_context(); engagement_feedback=f"\nENGAGEMENT EXPERIMENT FOR THIS SHORT: {engagement['experiment']}\nUse the mechanic naturally if it fits. Never sound like engagement bait.\nSuggested spoken interaction: {engagement['spoken_prompt']}\nDo not add generic like/subscribe language.\n"
    print("✍️ GENERATING ENTERTAINING STORY WITH LEARNED PATTERNS"); script=_generate_valid_script(topic,config,learning_context,engagement_feedback); script,next_topic=lock_next_topic(script,topic); script["engagement"]={"experiment":engagement["experiment"],"phase":engagement["phase"],"spoken_prompt":engagement["spoken_prompt"],"comment":engagement["comment"],"share_prompt":engagement["share_prompt"]}
    workdir=os.path.join("output",str(int(time.time()))); os.makedirs(workdir,exist_ok=True); save_json(script,os.path.join(workdir,"script.json")); write_continuation_manifest(topic,next_topic,"locked",workdir); print(f"✅ Script ready: {workdir}/script.json")
    if dry_run: print("✅ DRY RUN COMPLETE"); return
    audio=synthesize_script(script,config,os.path.join(workdir,"audio")); visuals=generate_media(script,os.path.join(workdir,"visuals"),config); sfx=generate_sfx(script,os.path.join(workdir,"sfx")); music=download_music(script,os.path.join(workdir,"music")); final_video=os.path.join(workdir,"final.mp4"); assemble_video(script,audio,visuals,music,sfx,config,final_video)
    if not os.path.exists(final_video): raise RuntimeError("Final video was not created.")
    quality=validate_final_video(final_video,expected_bitrate_mbps=EXPECTED_UPLOAD_BITRATE_MBPS); save_json(quality,os.path.join(workdir,"validation.json"))
    if not quality.get("ok",False): raise RuntimeError("Final video validation failed.")
    if (quality.get("width"),quality.get("height")) != EXPECTED_UPLOAD_RESOLUTION: raise RuntimeError("Upload blocked: final video is not 2160x3840 4K portrait.")
    if abs(float(quality.get("fps",0))-EXPECTED_UPLOAD_FPS) > 0.05: raise RuntimeError("Upload blocked: final video is not 60 fps.")
    if float(quality.get("bitrate_mbps",0)) < EXPECTED_UPLOAD_BITRATE_MBPS*0.90: raise RuntimeError("Upload blocked: final video bitrate is below the 100 Mbps production floor.")
    title,description=build_youtube_metadata(script); engagement_comment=str((script.get("engagement") or {}).get("comment") or "").strip() or None; thumbnail_path=os.path.join(workdir,"thumbnail.jpg"); thumbnail_path=thumbnail_path if os.path.exists(thumbnail_path) else None
    upload_video(final_video,title,description,config,thumbnail_path=thumbnail_path,engagement_comment=engagement_comment)
    commit_topic(topic); save_next_short(next_topic)

if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--dry-run",action="store_true"); args=parser.parse_args(); run(dry_run=args.dry_run)
