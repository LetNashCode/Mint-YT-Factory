"""Quality controls layered onto the existing Mint-YT-Factory pipeline."""
from __future__ import annotations
import inspect
import re

FILLER={"the","a","an","and","or","but","so","because","that","this","these","those","your","you","yourself","is","are","was","were","be","been","being","to","of","in","on","at","for","from","with","into","over","under","it","its","they","them","their","there","here","just","really","very","then","than","when","where","what","why","how","do","does","did","can","could","will","would","should","has","have","had","as","like","about","one","two","three","some","any","even","also","still"}

# Word count is a soft generation guard only. Actual TTS duration is authoritative.
MIN_STORY_WORDS=100
MAX_STORY_WORDS=145
MAX_REGEN_ATTEMPTS=3

def _words(text): return re.findall(r"\b[\w'-]+\b",str(text or ""))
def _meaningful(text):
    out=[]; filler={x.lower() for x in FILLER}
    for w in _words(text):
        key=w.lower().strip(".,!?;:'\"()[]")
        if len(key)>=4 and key not in filler and key not in {x.lower() for x in out}: out.append(w)
    return out

def _word_total(script): return sum(len(_words(scene.get("narration",""))) for scene in script.get("scene_plan",[]))
def _refresh_highlights(script):
    for index,scene in enumerate(script.get("scene_plan") or []):
        words=_meaningful(scene.get("narration","")); chosen=words[:3]
        if index in (0,5,6) and len(words)>=3: chosen=[words[0],words[len(words)//2],words[-1]]
        scene["caption_highlights"]=[{"word":w,"emphasis":"strong"} for w in chosen]
        if chosen: scene["emphasis_word"]=chosen[0]

def _add_visual_contract_fields(script):
    for scene in script.get("scene_plan") or []:
        narration=str(scene.get("narration","")).strip()
        for vi,visual in enumerate(scene.get("visuals") or []):
            prompt=str(visual.get("image_prompt","")).strip()
            visual.setdefault("spoken_line",narration); visual.setdefault("visual_focus",prompt[:180] or narration[:180]); visual.setdefault("visual_action",prompt[:220] or narration[:220]); visual.setdefault("must_show",_meaningful(prompt)[:6] or _meaningful(narration)[:6]); visual["story_beat"]="establish" if vi==0 else "advance"
            if vi==1: visual["advance_rule"]="show a changed physical state, reaction, closer detail, or consequence; do not repeat shot 1"

def _sanitize_final_scene(script):
    scenes=script.get("scene_plan") or []
    if not scenes:return
    scene=scenes[-1]; text=str(scene.get("narration","")).strip()
    if not text:return
    text=re.split(r"\b(?:and\s+next\s*:|next\s+(?:video|short|topic)\s*:|coming\s+next\b|stay\s+tuned\b|part\s*2\b)",text,maxsplit=1,flags=re.I)[0].strip()
    text=re.split(r"\s+(?:which|and\s+that)\s+(?:is\s+)?(?:also\s+)?why\b",text,maxsplit=1,flags=re.I)[0].strip()
    text=re.split(r"\s+(?:and\s+that'?s\s+why|which\s+means)\b",text,maxsplit=1,flags=re.I)[0].strip()
    if text: scene["narration"]=text.rstrip(".!? ")+"."; scene["subtitle_text"]=scene["narration"]

def _call_original(original,topic,config,research,feedback):
    try:
        params=inspect.signature(original).parameters
        if "extra_feedback" in params or any(p.kind==inspect.Parameter.VAR_KEYWORD for p in params.values()): return original(topic,config,research,extra_feedback=feedback)
    except (TypeError,ValueError): pass
    return original(topic,config,research)

def patch_story_quality(main):
    original=main.generate_script
    def generate_script(topic,config,research=None,extra_feedback=""):
        last=None
        for attempt in range(1,MAX_REGEN_ATTEMPTS+1):
            feedback=extra_feedback or ""
            if last:
                feedback += "\nThe previous draft was outside the preferred length. Rewrite the ENTIRE story naturally. Aim for roughly 105-135 words before the final next-topic teaser. Prioritize a punchy hook, concrete everyday details, escalation and a satisfying payoff. Do not pad with scientific filler."
            script=_call_original(original,topic,config,research,feedback); _sanitize_final_scene(script); total=_word_total(script)
            print(f"🧮 Story length: {total} words (soft production range {MIN_STORY_WORDS}-{MAX_STORY_WORDS}; TTS duration is authoritative)")
            if MIN_STORY_WORDS<=total<=MAX_STORY_WORDS:
                _refresh_highlights(script); _add_visual_contract_fields(script); return script
            last=f"story length {total} words outside soft range {MIN_STORY_WORDS}-{MAX_STORY_WORDS}"; print(f"⚠️ Story length outside soft range: {last}")
            if attempt==MAX_REGEN_ATTEMPTS:
                print("⚠️ Accepting final draft; real TTS duration will decide production viability.")
                _refresh_highlights(script); _add_visual_contract_fields(script); return script
        raise RuntimeError("Unreachable story generation state")
    main.generate_script=generate_script

def patch_visual_diversity(generate_media_module):
    generate_media_module.MEDIA_DIVERSITY_REQUIRED=True
    print("🎞️ Media diversity: duplicate stock assets prohibited")
