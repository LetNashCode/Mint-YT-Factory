"""Production entrypoint for Mint-YT-Factory."""
from __future__ import annotations
import inspect,json,os,glob,re,time
from runtime_overrides import patch_continuation,patch_tts_result,patch_visuals
from quality_overrides import patch_story_quality,patch_visual_diversity
from media_quality_overrides import patch_media_selection

MIN_NARRATION_SECONDS=35.0
MAX_SHORT_TTS_REGEN=2
PEXELS_GEMINI_RETRIES=3
PEXELS_GEMINI_BACKOFF=(4,8,16)


def _canonical_teaser(topic:str)->str:
    text=re.sub(r"\s+"," ",str(topic or "").strip()).rstrip(".!?")
    return f"Then comes an even weirder question: {text}."


def _is_bad_future_sentence(sentence:str,current_topic:str)->bool:
    norm=re.sub(r"[^a-z0-9 ]+","",sentence.lower()).strip()
    canonical=re.sub(r"[^a-z0-9 ]+","",current_topic.lower()).strip()
    if canonical and canonical in norm:return False
    return bool(re.search(r"\b(?:speaking of|on a related note|that makes you wonder|that makes you ask|another question|one more question|one more thing|which raises|which brings up|that brings us to|related question|then comes|coming next|next topic|next short|next video|stay tuned)\b",norm,re.I))


def _strip_future_teasers(narration:str,current_topic:str)->str:
    sentences=[x.strip() for x in re.split(r"(?<=[.!?])\s+",str(narration or "").strip()) if x.strip()]
    kept=[x for x in sentences if not _is_bad_future_sentence(x,current_topic)]
    return " ".join(kept).strip()


def _clean_regenerated_final_scene(scene,current_next:str):
    """Keep Scene 7 as payoff + exactly one locked teaser.

    TTS-length regeneration is a second Gemini generation pass. Gemini can
    independently invent a tempting 'side mystery' in Scene 7 even when the
    original draft was clean. Remove that invented branch deterministically and
    restore the canonical locked teaser.
    """
    if not scene:return
    text=str(scene.get("narration","")).strip()
    if not text:return
    canonical=_canonical_teaser(current_next) if current_next else ""
    # Remove explicit continuation bridges and anything after them.
    text=re.split(r"\s+(?:speaking\s+of|on\s+a\s+related\s+note|that\s+makes\s+you\s+wonder|that\s+makes\s+you\s+ask|another\s+question|one\s+more\s+question|one\s+more\s+thing|which\s+raises|which\s+brings\s+up|then\s+comes)\b",text,maxsplit=1,flags=re.I)[0].strip()
    # Also remove a standalone unrelated question sentence from the end of the
    # payoff. The only question allowed in Scene 7 is the locked next topic.
    sentences=[x.strip() for x in re.split(r"(?<=[.!?])\s+",text) if x.strip()]
    kept=[]
    for sentence in sentences:
        if sentence.rstrip().endswith("?") and current_next:
            # If it is not the exact locked topic, it is an invented side mystery.
            norm=re.sub(r"[^a-z0-9 ]+"," ",sentence.lower()).strip()
            nxt=re.sub(r"[^a-z0-9 ]+"," ",current_next.lower()).strip()
            if nxt not in norm:
                continue
        kept.append(sentence)
    text=" ".join(kept).strip()
    if text:
        text=text.rstrip(".!? ")+"."
        if canonical:text += " " + canonical
        scene["narration"]=text
        scene["subtitle_text"]=text


def _patch_tts_duration(main):
    from moviepy.editor import AudioFileClip
    original=main.synthesize_script
    if getattr(original,"_mint_duration_guard",False):return
    def synthesize(script,config,out_dir):
        current_next=((script.get("next_short") or {}).get("topic") or "").strip(); topic=str(script.get("topic","")).strip()
        for attempt in range(MAX_SHORT_TTS_REGEN+1):
            audio=original(script,config,out_dir); clip=AudioFileClip(audio)
            try:duration=float(clip.duration)
            finally:clip.close()
            print(f"🎯 TTS duration gate: {duration:.2f}s")
            if duration>=MIN_NARRATION_SECONDS:return audio
            if attempt>=MAX_SHORT_TTS_REGEN:raise RuntimeError(f"Narration remained too short after {MAX_SHORT_TTS_REGEN} regeneration attempts: {duration:.2f}s")
            feedback=(f"The previous narration rendered at {duration:.2f} seconds. Rewrite the entire current story so natural narration is at least {MIN_NARRATION_SECONDS:.0f} seconds. Add concrete everyday details, stronger escalation and a satisfying payoff. Do not pad with scientific filler. Aim for about 115-135 words before the final teaser. IMPORTANT: the current topic is {topic!r}. Do not introduce any other mystery or question. Scene 7 must contain only the payoff for {topic!r}, followed by the exact locked continuation topic supplied by the production system. Do not invent a different teaser such as wine glasses, onions, stones, bubbles, toothpaste, or any other example. The production system will restore the locked continuation after the rewrite.")
            candidate=main.generate_script(topic,config,None,extra_feedback=feedback); candidate["topic"]=topic; candidate["title"]=candidate.get("title",script.get("title",topic))
            if len(candidate.get("scene_plan") or [])!=7:raise RuntimeError("Audio-length regeneration produced an invalid 7-scene script.")
            candidate["next_short"]=dict(candidate.get("next_short") or {}); candidate["next_short"]["topic"]=current_next
            candidate,locked_next=main.lock_next_topic(candidate,topic)
            if locked_next!=current_next:raise RuntimeError(f"TTS regeneration changed the locked next topic: {locked_next!r} != {current_next!r}")
            # Deterministically repair Scene 7 after every TTS regeneration.
            _clean_regenerated_final_scene(candidate.get("scene_plan",[])[-1],current_next)
            # Validate Scenes 1–6 against the CURRENT topic, not the NEXT topic.
            # The old code passed current_next here, causing valid 'why/how'
            # explanations to be treated as future-topic leakage.
            for scene_index,scene in enumerate(candidate.get("scene_plan") or [],1):
                if scene_index==7:continue
                for sentence in re.split(r"(?<=[.!?])\s+",str(scene.get("narration","")).strip()):
                    if _is_bad_future_sentence(sentence,topic):raise RuntimeError(f"TTS regeneration leaked future-topic language into Scene {scene_index}: {sentence}")
            script.clear();script.update(candidate)
            try:
                workdir=os.path.dirname(os.path.dirname(os.path.abspath(out_dir)))
                with open(os.path.join(workdir,"script.json"),"w",encoding="utf-8") as h:json.dump(script,h,indent=2,ensure_ascii=False)
                if hasattr(main,"write_continuation_manifest"):main.write_continuation_manifest(topic,current_next,"locked",workdir)
            except Exception as exc:print(f"⚠️ Could not refresh regenerated script artifact: {exc}")
        return audio
    synthesize._mint_duration_guard=True; main.synthesize_script=synthesize


def _unwrap_per_image_gemini_gate(generate_images_module):
    fn=getattr(generate_images_module,"generate_image",None)
    if not fn or not getattr(fn,"_mint_strict_gate",False):return
    try:
        original=inspect.getclosurevars(fn).nonlocals.get("old_generate")
        if original:
            generate_images_module.generate_image=original; print("🧹 Removed per-image Gemini gate; quota-safe batch/policy checks remain")
    except Exception as exc:print(f"⚠️ Could not unwrap per-image Gemini gate: {exc}")


def _patch_pexels_gemini_retry(pexels_media):
    """Retry transient Gemini ranking outages without weakening visual QC."""
    original=getattr(pexels_media,"_gemini_rank_candidates",None)
    if not original or getattr(original,"_mint_transient_retry",False):return
    def rank(scene,visual,candidates,kind):
        last=[]
        for attempt in range(PEXELS_GEMINI_RETRIES+1):
            ranked=original(scene,visual,candidates,kind)
            if ranked:return ranked
            if attempt>=PEXELS_GEMINI_RETRIES:break
            delay=PEXELS_GEMINI_BACKOFF[min(attempt,len(PEXELS_GEMINI_BACKOFF)-1)]
            print(f"⏳ Gemini visual ranking unavailable; retrying in {delay}s ({attempt+1}/{PEXELS_GEMINI_RETRIES})")
            time.sleep(delay)
        return last
    rank._mint_transient_retry=True
    pexels_media._gemini_rank_candidates=rank
    print("🛡️ Gemini visual QC: transient 503 retry with exponential backoff enabled")


def _patch_pexels_media(main,generate_images_module):
    import pexels_media
    _unwrap_per_image_gemini_gate(generate_images_module)
    _patch_pexels_gemini_retry(pexels_media)
    patch_media_selection(pexels_media)
    def generate(script,output_dir,config):return pexels_media.generate_media(script,output_dir,config,generate_images_module)
    main.generate_images=generate; patch_visual_diversity(pexels_media)


def _patch_pexels_metadata(main):
    original=main.build_youtube_metadata
    def build(script,config):
        return original(script,config)
    main.build_youtube_metadata=build


def main_entry():
    import main
    patch_continuation(main)
    patch_tts_result(main)
    patch_story_quality(main)
    _patch_tts_duration(main)
    patch_visuals(main)
    try:
        import generate_images
        _patch_pexels_media(main,generate_images)
    except Exception as exc:print(f"⚠️ Visual runtime patch skipped: {exc}")
    print("="*80)
    print("🚀 MINT-YT-FACTORY STARTED")
    print("="*80)
    print("Script: entertainment-first + hard coherence gate + low-jargon contract")
    print("Visual provider: Pexels ONLY")
    print("Media order: Pexels verified VIDEO → Pexels verified PHOTO")
    print("AI image generation: DISABLED")
    print("Pollinations/FLUX: DISABLED")
    print("If Pexels cannot provide a relevant verified asset: production stops rather than using an unrelated fallback")
    print("Continuation: one locked next topic, final sentence only")
    print("Pexels API key:","AVAILABLE" if os.environ.get("PEXELS_API_KEY") else "NOT CONFIGURED")
    print("Story: soft 100-145 words / TTS-authoritative 35-44 seconds")
    print("Captions: Whisper word timing → deterministic fallback if Whisper fails")
    print("TTS duration guard: ENABLED")
    print("Gemini visual QC: retry transient 503s before failing")
    print("="*80)
    main.run(dry_run=False)


if __name__=="__main__":main_entry()
