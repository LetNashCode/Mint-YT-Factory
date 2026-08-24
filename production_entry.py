"""Production entrypoint for Mint-YT-Factory."""
from __future__ import annotations
import inspect,json,os,glob,re,time
from runtime_overrides import patch_continuation,patch_tts_result,patch_visuals
from quality_overrides import patch_story_quality,patch_visual_diversity
from media_quality_overrides import patch_media_selection

MIN_NARRATION_SECONDS=35.0
MAX_NARRATION_SECONDS=43.90
MAX_SHORT_TTS_REGEN=2
PEXELS_GEMINI_RETRIES=3
PEXELS_GEMINI_BACKOFF=(4,8,16)

def _canonical_teaser(topic:str)->str:
    text=re.sub(r"\s+"," ",str(topic or "").strip()).rstrip(".!?")
    return f"Then comes an even weirder question: {text}."

def _is_bad_future_sentence(sentence:str,current_topic:str)->bool:
    norm=re.sub(r"[^a-z0-9 ]+"," ",sentence.lower()).strip();canonical=re.sub(r"[^a-z0-9 ]+"," ",current_topic.lower()).strip()
    if canonical and canonical in norm:return False
    return bool(re.search(r"\b(?:speaking of|on a related note|that makes you wonder|that makes you ask|another question|one more question|one more thing|which raises|which brings up|that brings us to|related question|then comes|coming next|next topic|next short|next video|next time|stay tuned|watch why|watch what|watch how)\b",norm,re.I))

def _split_sentences(text):return [x.strip() for x in re.split(r"(?<=[.!?])\s+",str(text or "").strip()) if x.strip()]
def _looks_like_future(sentence):
    text=str(sentence or "").strip()
    return bool(re.search(r"^(?:and\s+)?(?:next\b|next\s+time\b|watch\s+(?:why|what|how)\b|wonder\s+why\b|ever\s+wonder\s+why\b|curious\s+(?:why|how|what|when)\b|why\s+(?:do|does|is|are|can)\b|how\s+(?:do|does|is|are|can)\b|what\s+(?:makes|happens|causes|would|if)\b)",text,re.I))

def _clean_dangling_ending(text):
    text=re.sub(r"\s+"," ",str(text or "")).strip()
    text=re.sub(r"\s+(?:and|but|so|or|because|then)\s*[.!?]*$","",text,flags=re.I)
    return text.strip()

def _clean_regenerated_final_scene(scene,current_next:str):
    if not scene:return
    text=str(scene.get("narration","")).strip()
    if not text:return
    canonical=_canonical_teaser(current_next) if current_next else ""
    text=re.split(r"\s+(?:speaking\s+of|on\s+a\s+related\s+note|that\s+makes\s+you\s+wonder|that\s+makes\s+you\s+ask|another\s+question|one\s+more\s+question|one\s+more\s+thing|which\s+raises|which\s+brings\s+up|then\s+comes|next\s+time|watch\s+why|watch\s+what|watch\s+how)\b",text,maxsplit=1,flags=re.I)[0].strip()
    kept=[]
    for sentence in _split_sentences(text):
        if _looks_like_future(sentence):continue
        if sentence.rstrip().endswith("?") and current_next:
            norm=re.sub(r"[^a-z0-9 ]+"," ",sentence.lower()).strip();nxt=re.sub(r"[^a-z0-9 ]+"," ",current_next.lower()).strip()
            if nxt not in norm:continue
        kept.append(sentence)
    text=_clean_dangling_ending(" ".join(kept).strip())
    if text:
        scene["narration"]=text.rstrip(".!? ")+". "+canonical;scene["subtitle_text"]=scene["narration"]

def _patch_lock_next_topic(main):
    original=main.lock_next_topic
    if getattr(original,"_mint_locked_v3",False):return
    def lock(script,current_topic):
        next_short=script.get("next_short") or {};candidate=str(next_short.get("topic","")).strip()
        if not candidate:raise RuntimeError("Generated script did not provide next_short.topic.")
        from topics import validate_topic_for_pipeline,_generate_topic,_read_used,_PENDING_PREFIX
        used=[str(current_topic)];used.extend(item for item in _read_used() if not str(item).startswith(_PENDING_PREFIX))
        canonical=candidate if validate_topic_for_pipeline(candidate,used=used,check_duplicate=True) else _generate_topic(used)
        if not validate_topic_for_pipeline(canonical,used=used,check_duplicate=True):raise RuntimeError(f"Could not create valid canonical next topic: {canonical}")
        if len(re.findall(r"\b[\w'-]+\b",canonical))>7:
            canonical=_generate_topic(used)
            if len(re.findall(r"\b[\w'-]+\b",canonical))>7:raise RuntimeError(f"Generated continuation is still too long: {canonical}")
        script.setdefault("next_short",{})["topic"]=canonical;script["next_short"]["teaser"]=_canonical_teaser(canonical)
        scenes=script.get("scene_plan")
        if not isinstance(scenes,list) or len(scenes)!=7:raise RuntimeError("Script must contain exactly 7 scenes.")
        final=scenes[-1];original_text=str(final.get("narration","")).strip();kept=[];canon_norm=re.sub(r"[^a-z0-9 ]+"," ",canonical.lower()).strip()
        for sentence in _split_sentences(original_text):
            norm=re.sub(r"[^a-z0-9 ]+"," ",sentence.lower()).strip()
            if canon_norm and canon_norm in norm:continue
            if _looks_like_future(sentence):continue
            if re.search(r"\b(?:bigger question|one more thing to wonder about|one more question|another question|related question|next topic|next short|next video|next time)\b",sentence,re.I):continue
            kept.append(sentence)
        base=_clean_dangling_ending(" ".join(kept).strip())
        if not base:base="And that is the strange part."
        sentences=_split_sentences(base)
        if sentences:base=sentences[-1]
        base=_clean_dangling_ending(base).rstrip(".!? ")+"."
        final["narration"]=base+" "+_canonical_teaser(canonical);final["subtitle_text"]=final["narration"]
        final["pause_after_ms"]=250;final["emotional_tone"]="satisfied";final["music_cue"]="fade_out"
        words=re.findall(r"\b[\w'-]+\b",canonical);final["caption_highlights"]=[{"word":w,"emphasis":"strong"} for w in words[:3]];final["emphasis_word"]=words[0] if words else canonical.split()[0]
        if sum(1 for s in _split_sentences(final["narration"]) if canon_norm in re.sub(r"[^a-z0-9 ]+"," ",s.lower()).strip())!=1:raise RuntimeError("Continuation integrity failed: canonical topic must appear exactly once in Scene 7.")
        for scene in scenes[:6]:
            if canon_norm in re.sub(r"[^a-z0-9 ]+"," ",str(scene.get("narration","")).lower()).strip():raise RuntimeError("Next topic appeared before Scene 7.")
        print(f"🔒 Canonical next topic: {canonical}");print(f"🗣️ FINAL SPOKEN TEASE: {final['narration']}")
        return script,canonical
    lock._mint_locked_v3=True;main.lock_next_topic=lock

def _patch_assemble_video_media(main):
    import assemble
    from moviepy.editor import VideoFileClip,vfx
    original=assemble.make_image_clip
    if getattr(original,"_mint_media_v2",False):return
    video_ext={".mp4",".mov",".m4v",".webm",".avi",".mkv"}
    def make_media_clip(path,frame_size):
        if os.path.splitext(str(path))[1].lower() not in video_ext:return original(path,frame_size)
        width,height=frame_size;print(f"🎞️ Assembler: reading VIDEO asset as VideoFileClip: {os.path.basename(str(path))}")
        clip=VideoFileClip(path,audio=False);scale=max(width/clip.w,height/clip.h);clip=clip.resize(scale);crop_x=max(0,int((clip.w-width)/2));crop_y=max(0,int((clip.h-height)/2));clip=clip.crop(x1=crop_x,y1=crop_y,x2=crop_x+width,y2=crop_y+height);return clip.fx(vfx.loop,duration=10.0)
    make_media_clip._mint_media_v2=True;assemble.make_image_clip=make_media_clip;print("🛡️ Assembly media compatibility: Pexels MP4 → VideoFileClip + safe loop")

def _patch_tts_duration(main):
    from moviepy.editor import AudioFileClip
    original=main.synthesize_script
    if getattr(original,"_mint_duration_guard",False):return
    def synthesize(script,config,out_dir):
        current_next=((script.get("next_short") or {}).get("topic") or "").strip();topic=str(script.get("topic","")).strip()
        for attempt in range(MAX_SHORT_TTS_REGEN+1):
            audio=original(script,config,out_dir);clip=AudioFileClip(audio)
            try:duration=float(clip.duration)
            finally:clip.close()
            print(f"🎯 TTS duration gate: {duration:.2f}s")
            if MIN_NARRATION_SECONDS<=duration<=MAX_NARRATION_SECONDS:return audio
            if attempt>=MAX_SHORT_TTS_REGEN:raise RuntimeError(f"Narration duration remained outside production range after {MAX_SHORT_TTS_REGEN} regeneration attempts: {duration:.2f}s (allowed {MIN_NARRATION_SECONDS:.2f}-{MAX_NARRATION_SECONDS:.2f}s).")
            if duration>MAX_NARRATION_SECONDS:
                direction=f"The previous narration rendered at {duration:.2f} seconds and is TOO LONG. Rewrite it shorter. Target 90-100 words before the locked continuation. Remove filler, repeated explanations and extra setup while keeping the hook, escalation and payoff."
            else:
                direction=f"The previous narration rendered at {duration:.2f} seconds and is TOO SHORT. Target 100-110 words before the locked continuation. Add concrete everyday details and escalation, not scientific filler."
            feedback=(f"{direction} IMPORTANT: the current topic is {topic!r}. Do not introduce any other mystery or question. Scene 7 must contain only the payoff for {topic!r}, followed by the exact locked continuation topic supplied by the production system. Do not invent a different teaser. The production system will restore the locked continuation after the rewrite.")
            candidate=main.generate_script(topic,config,None,extra_feedback=feedback);candidate["topic"]=topic;candidate["title"]=candidate.get("title",script.get("title",topic));candidate["next_short"]=dict(candidate.get("next_short") or {});candidate["next_short"]["topic"]=current_next
            candidate,locked_next=main.lock_next_topic(candidate,topic)
            if locked_next!=current_next:raise RuntimeError(f"TTS regeneration changed the locked next topic: {locked_next!r} != {current_next!r}")
            _clean_regenerated_final_scene(candidate.get("scene_plan",[])[-1],current_next)
            for scene_index,scene in enumerate(candidate.get("scene_plan") or [],1):
                if scene_index==7:continue
                for sentence in _split_sentences(scene.get("narration","")):
                    if _is_bad_future_sentence(sentence,topic):raise RuntimeError(f"TTS regeneration leaked future-topic language into Scene {scene_index}: {sentence}")
            script.clear();script.update(candidate)
            try:
                workdir=os.path.dirname(os.path.dirname(os.path.abspath(out_dir)))
                with open(os.path.join(workdir,"script.json"),"w",encoding="utf-8") as h:json.dump(script,h,indent=2,ensure_ascii=False)
                if hasattr(main,"write_continuation_manifest"):main.write_continuation_manifest(topic,current_next,"locked",workdir)
            except Exception as exc:print(f"⚠️ Could not refresh regenerated script artifact: {exc}")
        return audio
    synthesize._mint_duration_guard=True;main.synthesize_script=synthesize

def _unwrap_per_image_gemini_gate(generate_images_module):
    fn=getattr(generate_images_module,"generate_image",None)
    if not fn or not getattr(fn,"_mint_strict_gate",False):return
    try:
        original=inspect.getclosurevars(fn).nonlocals.get("old_generate")
        if original:generate_images_module.generate_image=original;print("🧹 Removed per-image Gemini gate; quota-safe batch/policy checks remain")
    except Exception as exc:print(f"⚠️ Could not unwrap per-image Gemini gate: {exc}")

def _patch_pexels_gemini_retry(pexels_media):
    original=getattr(pexels_media,"_gemini_rank_candidates",None)
    if not original or getattr(original,"_mint_transient_retry",False):return
    def rank(scene,visual,candidates,kind):
        for attempt in range(PEXELS_GEMINI_RETRIES+1):
            ranked=original(scene,visual,candidates,kind)
            if ranked:return ranked
            if attempt>=PEXELS_GEMINI_RETRIES:break
            delay=PEXELS_GEMINI_BACKOFF[min(attempt,len(PEXELS_GEMINI_BACKOFF)-1)];print(f"⏳ Gemini visual ranking unavailable; retrying in {delay}s ({attempt+1}/{PEXELS_GEMINI_RETRIES})");time.sleep(delay)
        return []
    rank._mint_transient_retry=True;pexels_media._gemini_rank_candidates=rank;print("🛡️ Gemini visual QC: transient 503 retry with exponential backoff enabled")

def _patch_pexels_media(main,generate_images_module):
    import pexels_media
    _unwrap_per_image_gemini_gate(generate_images_module);_patch_pexels_gemini_retry(pexels_media);patch_media_selection(pexels_media)
    def generate(script,output_dir,config):return pexels_media.generate_media(script,output_dir,config,generate_images_module)
    main.generate_images=generate;patch_visual_diversity(pexels_media)

def main_entry():
    import main
    patch_continuation(main);patch_tts_result(main);patch_story_quality(main);_patch_lock_next_topic(main);_patch_tts_duration(main);patch_visuals(main);_patch_assemble_video_media(main)
    try:
        import generate_images
        _patch_pexels_media(main,generate_images)
    except Exception as exc:print(f"⚠️ Visual runtime patch skipped: {exc}")
    print("="*80);print("🚀 MINT-YT-FACTORY STARTED");print("="*80);print("Script: entertainment-first + hard coherence gate + low-jargon contract");print("Visual provider: Pexels ONLY");print("Media order: Pexels verified VIDEO → Pexels verified PHOTO");print("AI image generation: DISABLED");print("Pollinations/FLUX: DISABLED");print("If Pexels cannot provide a relevant verified asset: production stops rather than using an unrelated fallback");print("Continuation: one locked next topic, final sentence only");print("Pexels API key:","AVAILABLE" if os.environ.get("PEXELS_API_KEY") else "NOT CONFIGURED");print("Story: TTS-authoritative 35-43.9 seconds");print("Captions: Whisper word timing → deterministic fallback if Whisper fails");print("TTS duration guard: ENABLED");print("Gemini visual QC: retry transient 503s before failing");print("="*80);main.run(dry_run=False)

if __name__=="__main__":main_entry()
