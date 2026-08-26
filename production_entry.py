"""Production entrypoint for Mint-YT-Factory."""
from __future__ import annotations
import json, os, re
from runtime_overrides import patch_continuation, patch_tts_result
from quality_overrides import patch_story_quality
from story_quality_gate import patch_story_generation

MIN_NARRATION_SECONDS=35.0
MAX_NARRATION_SECONDS=43.90
MAX_SHORT_TTS_REGEN=2

def _patch_script_model_resilience(main):
    original=main.generate_script
    if getattr(original,"_mint_model_resilient",False): return
    globals_dict=getattr(original,"__globals__",{})
    primary="gemini-3.5-flash-lite"; fallback="gemini-2.5-flash-lite"
    globals_dict["MODEL_NAME"]=primary
    def resilient(topic,config,research=None,extra_feedback=""):
        last=None
        for model in (primary,fallback):
            globals_dict["MODEL_NAME"]=model
            try:
                print(f"🧠 Script model: {model}")
                return original(topic,config,research,extra_feedback=extra_feedback)
            except Exception as exc:
                last=exc; text=str(exc).lower()
                transient=("503" in text or "unavailable" in text or "high demand" in text or "serviceunavailable" in text or "resource_exhausted" in text)
                if not transient or model==fallback: raise
                print(f"⚠️ Gemini script model unavailable ({model}); failing over to {fallback}")
        raise last or RuntimeError("Gemini script generation failed.")
    resilient._mint_model_resilient=True
    main.generate_script=resilient
    print(f"🛡️ Script Gemini resilience: {primary} → {fallback} on transient availability failures")

def _patch_scene7_sanitizer(main):
    """Preserve Gemini's authored final continuation bridge."""
    original=main.generate_script
    globals_dict=getattr(original,"__globals__",{})
    old=globals_dict.get("_sanitize_scene7")
    if old is None or getattr(old,"_mint_preserve_bridge",False): return
    def preserve_bridge(scene7,earlier_scenes):
        text=str(scene7.get("narration","") or "").strip()
        sentences=[s.strip() for s in re.split(r"(?<=[.!?])\s+",text) if s.strip()]
        if not sentences: return text
        bad=re.compile(r"^(now watch|speaking of|and now|meanwhile|another weird|here's another|here is another)\b",re.I)
        kept=[]
        for i,sentence in enumerate(sentences):
            if i==len(sentences)-1:
                kept.append(sentence)
                continue
            if bad.search(sentence):
                continue
            kept.append(sentence)
        return " ".join(kept).strip()
    preserve_bridge._mint_preserve_bridge=True
    globals_dict["_sanitize_scene7"]=preserve_bridge
    print("🛡️ Scene 7 sanitizer: Gemini final continuation bridge preserved")

def _patch_scene7_validator(main):
    """Make Scene 7 validation structural, not punctuation-fragile."""
    original_generate=main.generate_script
    globals_dict=getattr(original_generate,"__globals__",{})
    old_validator=globals_dict.get("_validate_natural_bridge")
    if old_validator is None or getattr(old_validator,"_mint_structural_bridge",False): return

    def validate(scene7_narration,next_topic):
        text=" ".join(str(scene7_narration or "").split()).strip()
        key=re.sub(r"[^a-z0-9]+"," ",str(next_topic or "").lower()).strip()
        if not text or not key:
            raise RuntimeError("Scene 7 must contain a payoff followed by a natural continuation bridge.")
        normalized=re.sub(r"[^a-z0-9]+"," ",text.lower()).strip()
        if normalized.count(key)!=1:
            raise RuntimeError("The exact next topic must appear exactly once in Scene 7.")
        sentences=[s.strip() for s in re.split(r"(?<=[.!?])\s+",text) if s.strip()]
        matches=[s for s in sentences if key in re.sub(r"[^a-z0-9]+"," ",s.lower()).strip()]
        if len(sentences)==1:
            # Gemini occasionally returns the payoff and bridge as one long sentence.
            # Accept it here; lock_next_topic will insert the sentence boundary before
            # the exact next topic. This avoids wasting a full Gemini generation attempt.
            if normalized.endswith(key):
                return text
            raise RuntimeError("Scene 7 must end with the continuation topic.")
        if not matches or matches[-1]!=sentences[-1]:
            raise RuntimeError("The continuation topic must be in Scene 7's final sentence.")
        bridge=matches[-1]
        banned=(r"^(?:and\s+)?next\b",r"^then\s+comes\b",r"^coming\s+next\b",r"^in\s+the\s+next\s+(?:video|short)\b",r"^stay\s+tuned\b",r"^part\s+2\b",r"^have\s+you\s+ever\s+wondered\b",r"^ever\s+wondered\b",r"^wonder\s+why\b",r"^curious\s+(?:why|how|what)\b",r"^why\s+(?:do|does|is|are)\b",r"^how\s+(?:do|does|is|are)\b",r"^what\s+(?:makes|happens|causes)\b")
        if any(re.search(p,bridge,re.I) for p in banned):
            raise RuntimeError(f"Canned continuation bridge rejected: {bridge}")
        word_count=len(re.findall(r"\b[\w'-]+\b",bridge))
        if word_count<4 or word_count>40:
            raise RuntimeError("Natural continuation bridge is too short or too long.")
        return bridge

    validate._mint_structural_bridge=True
    globals_dict["_validate_natural_bridge"]=validate
    print("🛡️ Scene 7 validator: structural bridge validation + long-topic tolerance enabled")

def _patch_locked_continuation(main):
    """Normalize a punctuation-free Gemini payoff+bridge before final locking."""
    original=main.lock_next_topic
    if getattr(original,"_mint_bridge_normalizer",False): return
    def lock(script,current_topic):
        scenes=script.get("scene_plan") or []
        if scenes:
            final=scenes[-1]
            text=" ".join(str(final.get("narration","") or "").split()).strip()
            next_topic=str((script.get("next_short") or {}).get("topic","") or "").strip()
            key=re.sub(r"[^a-z0-9]+"," ",next_topic.lower()).strip()
            normalized=re.sub(r"[^a-z0-9]+"," ",text.lower()).strip()
            if key and normalized.endswith(key) and len(re.findall(r"[.!?]",text))==0:
                pos=normalized.rfind(key)
                # Map normalized topic length back to the original text by searching
                # the literal topic case-insensitively first; generated topics are exact.
                literal_pos=text.lower().rfind(next_topic.lower())
                if literal_pos>0:
                    prefix=text[:literal_pos].rstrip(" ,;:-")
                    if prefix and prefix[-1] not in ".!?":
                        text=prefix+". "+text[literal_pos:].lstrip()
                        final["narration"]=text
                        final["subtitle_text"]=text
        return original(script,current_topic)
    lock._mint_bridge_normalizer=True
    main.lock_next_topic=lock
    print("🛡️ Continuation lock: punctuation-free Scene 7 bridge normalized")

def _patch_tts_duration(main):
    from moviepy.editor import AudioFileClip
    original=main.synthesize_script
    if getattr(original,"_mint_duration_guard",False): return
    def synthesize(script,config,out_dir):
        current_next=((script.get("next_short") or {}).get("topic") or "").strip(); topic=str(script.get("topic","")).strip()
        for attempt in range(MAX_SHORT_TTS_REGEN+1):
            audio=original(script,config,out_dir); clip=AudioFileClip(audio)
            try: duration=float(clip.duration)
            finally: clip.close()
            print(f"🎯 TTS duration gate: {duration:.2f}s")
            if MIN_NARRATION_SECONDS<=duration<=MAX_NARRATION_SECONDS: return audio
            if attempt>=MAX_SHORT_TTS_REGEN: raise RuntimeError(f"Narration duration remained outside production range after {MAX_SHORT_TTS_REGEN} regeneration attempts: {duration:.2f}s (allowed {MIN_NARRATION_SECONDS:.2f}-{MAX_NARRATION_SECONDS:.2f}s).")
            if duration>MAX_NARRATION_SECONDS:
                direction=f"The previous narration rendered at {duration:.2f} seconds and is TOO LONG. Rewrite it shorter. Target 90-100 words before the locked continuation. Remove filler, repeated explanations and extra setup while keeping the hook, escalation and payoff."
            else:
                direction=f"The previous narration rendered at {duration:.2f} seconds and is TOO SHORT. Target 100-110 words before the locked continuation. Add concrete everyday details and escalation, not scientific filler."
            feedback=f"{direction} IMPORTANT: current topic is {topic!r}. Do not introduce another mystery. Scene 7 must contain only the payoff for {topic!r}, followed by the exact locked continuation topic {current_next!r}. Do not invent a different teaser."
            candidate=main.generate_script(topic,config,None,extra_feedback=feedback); candidate["topic"]=topic; candidate["next_short"]=dict(candidate.get("next_short") or {}); candidate["next_short"]["topic"]=current_next; candidate,locked_next=main.lock_next_topic(candidate,topic)
            if locked_next!=current_next: raise RuntimeError(f"TTS regeneration changed locked next topic: {locked_next!r} != {current_next!r}")
            script.clear(); script.update(candidate)
            workdir=os.path.dirname(os.path.dirname(os.path.abspath(out_dir)))
            try:
                with open(os.path.join(workdir,"script.json"),"w",encoding="utf-8") as handle: json.dump(script,handle,indent=2,ensure_ascii=False)
                if hasattr(main,"write_continuation_manifest"): main.write_continuation_manifest(topic,current_next,"locked",workdir)
            except Exception as exc: print(f"⚠️ Could not refresh regenerated script artifact: {exc}")
        return audio
    synthesize._mint_duration_guard=True; main.synthesize_script=synthesize

def _patch_assemble_video_media():
    import assemble
    from moviepy.editor import VideoFileClip,vfx
    original=assemble.make_image_clip
    if getattr(original,"_mint_media_v3",False): return
    video_ext={".mp4",".mov",".m4v",".webm",".avi",".mkv"}
    def make_media_clip(path,frame_size):
        if os.path.splitext(str(path))[1].lower() not in video_ext: return original(path,frame_size)
        width,height=frame_size; print("🎞️ Assembler: verified stock VIDEO asset → VideoFileClip: "+os.path.basename(str(path)))
        clip=VideoFileClip(path,audio=False); scale=max(width/clip.w,height/clip.h); clip=clip.resize(scale); crop_x=max(0,int((clip.w-width)/2)); crop_y=max(0,int((clip.h-height)/2)); clip=clip.crop(x1=crop_x,y1=crop_y,x2=crop_x+width,y2=crop_y+height); return clip.fx(vfx.loop,duration=10.0)
    make_media_clip._mint_media_v3=True; assemble.make_image_clip=make_media_clip
    print("🛡️ Assembly media compatibility: verified stock MP4 → VideoFileClip + safe loop")

def main_entry():
    import main
    patch_continuation(main); patch_tts_result(main); patch_story_quality(main); patch_story_generation(main)
    _patch_scene7_sanitizer(main); _patch_scene7_validator(main); _patch_script_model_resilience(main); _patch_locked_continuation(main); _patch_tts_duration(main); _patch_assemble_video_media()
    print("="*80); print("🚀 MINT-YT-FACTORY STARTED"); print("="*80)
    print("Script: entertainment-first + hard coherence gate + low-jargon contract")
    print("Visual/Search Director: Gemini")
    print("Media pipeline: stock_search.generate_media (authoritative)")
    print("Media priority: Pexels VIDEO → Pixabay VIDEO → Pexels PHOTO → Pixabay PHOTO")
    print("Visual verification: ENABLED — Gemini inspects stock candidates")
    print("Visual verification threshold: 7.5/10")
    print("Fallback: provider fallback only; no unrelated-media fallback")
    print("Continuation: one locked next topic, final sentence only")
    print("Pexels API key:","AVAILABLE" if os.environ.get("PEXELS_API_KEY") else "NOT CONFIGURED")
    print("Pixabay API key:","AVAILABLE" if os.environ.get("PIXABAY_API_KEY") else "NOT CONFIGURED")
    print("Gemini API key:","AVAILABLE" if os.environ.get("GEMINI_API_KEY") else "NOT CONFIGURED")
    print("Story: TTS-authoritative 35-43.9 seconds"); print("Captions: Whisper word timing → deterministic fallback if Whisper fails"); print("TTS duration guard: ENABLED"); print("="*80)
    main.run(dry_run=False)

if __name__=="__main__": main_entry()
