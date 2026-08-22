"""Quality controls layered onto the existing Mint-YT-Factory pipeline.

Goals:
- keep narration naturally in the 38–43 second range;
- make the first seconds visually hookier;
- make captions emphasize meaningful words instead of filler;
- prevent duplicate stock assets inside one Short;
- push each second visual to advance the physical beat.
"""
from __future__ import annotations

import inspect
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
    seen=set()
    for w in _words(text):
        key=w.lower().strip(".,!?;:'\"()[]")
        if len(key)>=4 and key not in FILLER and key not in seen:
            out.append(w)
            seen.add(key)
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
    for si,scene in enumerate(scenes):
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


def _call_generator(original, topic, config, research, feedback):
    """Call whichever generate_script wrapper is currently installed.

    sitecustomize.py wraps generate_script with a legacy three-argument
    signature, while the real generator supports extra_feedback. This adapter
    prevents those two runtime layers from crashing each other.
    """
    try:
        signature = inspect.signature(original)
        parameters = signature.parameters
        accepts_feedback = "extra_feedback" in parameters or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()
        )
        if accepts_feedback:
            return original(topic, config, research, extra_feedback=feedback)
        if len(parameters) >= 4:
            return original(topic, config, research, feedback)
    except (TypeError, ValueError):
        pass

    # Compatibility fallback for the three-argument runtime wrapper.
    return original(topic, config, research)


def patch_story_quality(main):
    original=main.generate_script
    def generate_script(topic,config,research=None,extra_feedback=""):
        feedback=(extra_feedback+"\n" if extra_feedback else "")+(
            "QUALITY TARGET: create 125-140 spoken words across the seven scenes. "
            "The finished narration must naturally land around 38-43 seconds at a normal conversational pace. "
            "Do not pad with filler; add a concrete beat, reaction, example, or surprising consequence instead. "
            "Scene 1 must create a visually strange hook in its first sentence. "
            "Every scene must advance the physical story. Shot 2 must not merely be a crop of shot 1."
        )
        for attempt in range(3):
            script=_call_generator(original,topic,config,research,feedback)
            total=_word_total(script)
            print(f"🧮 Story length check {attempt+1}/3: {total} words")
            if 125 <= total <= 140:
                _refresh_highlights(script)
                _add_visual_contract_fields(script)
                return script
            if total < 125:
                feedback += f"\nThe previous draft was only {total} words. Expand the actual story with useful visual/action beats until it reaches 125-140 words."
            else:
                feedback += f"\nThe previous draft was {total} words. Tighten it to 125-140 words without losing the hook, twist or payoff."

        script=_call_generator(original,topic,config,research,feedback)
        total=_word_total(script)
        print(f"🧮 Final story length: {total} words")
        if total < 115 or total > 150:
            raise RuntimeError(f"Story narration length is {total} words; expected approximately 125-140 words for a 38-43s Short.")
        _refresh_highlights(script)
        _add_visual_contract_fields(script)
        return script
    main.generate_script=generate_script


def patch_visual_diversity(generate_media_module):
    """Expose the production requirement that stock assets must not repeat."""
    generate_media_module.MEDIA_DIVERSITY_REQUIRED=True
    print("🎞️ Media diversity: duplicate stock assets prohibited")
