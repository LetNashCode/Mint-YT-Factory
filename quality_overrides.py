"""Quality controls layered onto the existing Mint-YT-Factory pipeline.

The word count is a SOFT planning signal. Actual TTS duration is the production
truth because TikTok voice timing varies with punctuation and pronunciation.
"""
from __future__ import annotations
import re

FILLER = {
    "the","a","an","and","or","but","so","because","that","this","these","those",
    "your","you","yourself","is","are","was","were","be","been","being","to","of",
    "in","on","at","for","from","with","into","over","under","it","its","they","them",
    "their","there","here","just","really","very","then","than","when","where","what",
    "why","how","do","does","did","can","could","will","would","should","has","have",
    "had","as","like","about","one","two","three","some","any","even","also","still",
}

def _words(text):
    return re.findall(r"\b[\w'-]+\b", str(text or ""))

def _meaningful(text):
    out=[]
    filler={x.lower() for x in FILLER}
    for w in _words(text):
        key=w.lower().strip(".,!?;:'\"()[]")
        if len(key)>=4 and key not in filler and key not in [x.lower() for x in out]:
            out.append(w)
    return out

def _word_total(script):
    return sum(len(_words(scene.get("narration",""))) for scene in script.get("scene_plan",[]))

def _refresh_highlights(script):
    scenes=script.get("scene_plan") or []
    for index,scene in enumerate(scenes):
        words=_meaningful(scene.get("narration",""))
        chosen=words[:3]
        if index in (0,5,6) and len(words)>=3:
            chosen=[words[0],words[len(words)//2],words[-1]]
        scene["caption_highlights"]=[{"word":w,"emphasis":"strong"} for w in chosen]
        if chosen:
            scene["emphasis_word"]=chosen[0]

def _add_visual_contract_fields(script):
    scenes=script.get("scene_plan") or []
    for scene in scenes:
        narration=str(scene.get("narration","")).strip()
        visuals=scene.get("visuals") or []
        for vi,visual in enumerate(visuals):
            prompt=str(visual.get("image_prompt","")).strip()
            visual.setdefault("spoken_line", narration)
            visual.setdefault("visual_focus", prompt[:180] or narration[:180])
            visual.setdefault("visual_action", prompt[:220] or narration[:220])
            visual.setdefault("must_show", _meaningful(prompt)[:6] or _meaningful(narration)[:6])
            visual["story_beat"] = "establish" if vi == 0 else "advance"
            if vi == 1:
                visual["advance_rule"] = "show a changed physical state, reaction, closer detail, or consequence; do not repeat shot 1"

def patch_story_quality(main):
    original=main.generate_script

    def generate_script(topic,config,research=None,extra_feedback=""):
        feedback=(extra_feedback+"\n" if extra_feedback else "") + (
            "QUALITY TARGET: aim for approximately 115-140 spoken words across seven scenes, "
            "with a natural conversational delivery target of roughly 38-43 seconds. "
            "Word count is guidance, NOT a hard publish gate because TTS duration varies. "
            "Do not pad with filler; add concrete action, reaction, example, escalation or surprising consequence. "
            "Scene 1 must create a visually strange hook immediately. Every scene must advance the physical story. "
            "Shot 2 must not merely be a crop of shot 1."
        )
        last=None
        for attempt in range(3):
            script=original(topic,config,research,feedback)
            total=_word_total(script)
            print(f"🧮 Story length check {attempt+1}/3: {total} words (soft target 115-140)")
            if 115 <= total <= 140:
                _refresh_highlights(script)
                _add_visual_contract_fields(script)
                return script
            if total < 115:
                feedback += f"\nThe previous draft was {total} words. Expand the actual story with useful physical/action beats toward 115-140 words. Do not add filler."
            else:
                feedback += f"\nThe previous draft was {total} words. Tighten it toward 115-140 words without losing the hook, twist or payoff."
            last=total

        # Do one final generation, but do not fail the entire production merely
        # because Gemini prefers a shorter natural script.  TTS duration is the
        # authoritative runtime measurement later in the pipeline.
        script=original(topic,config,research,feedback)
        total=_word_total(script)
        print(f"🧮 Final story length: {total} words (soft gate; TTS duration is authoritative)")
        if total < 100 or total > 155:
            raise RuntimeError(f"Story narration length is {total} words; expected a usable natural range of 100-155 words.")
        _refresh_highlights(script)
        _add_visual_contract_fields(script)
        return script

    main.generate_script=generate_script

def patch_visual_diversity(generate_media_module):
    generate_media_module.MEDIA_DIVERSITY_REQUIRED=True
    print("🎞️ Media diversity: duplicate stock assets prohibited")
