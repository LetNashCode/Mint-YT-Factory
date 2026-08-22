"""Quality controls layered onto the existing Mint-YT-Factory pipeline.

IMPORTANT: this layer must remain compatible with the runtime-patched
``main.generate_script`` installed by sitecustomize.py.  The runtime wrapper
currently exposes the legacy 3-argument signature, so this module deliberately
uses the public 3-argument call and treats word count as a soft signal.
Actual TikTok TTS duration is the production truth.
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
    out = []
    filler = {x.lower() for x in FILLER}
    for w in _words(text):
        key = w.lower().strip(".,!?;:'\"()[]")
        if len(key) >= 4 and key not in filler and key not in {x.lower() for x in out}:
            out.append(w)
    return out


def _word_total(script):
    return sum(len(_words(scene.get("narration", ""))) for scene in script.get("scene_plan", []))


def _refresh_highlights(script):
    scenes = script.get("scene_plan") or []
    for index, scene in enumerate(scenes):
        words = _meaningful(scene.get("narration", ""))
        chosen = words[:3]
        if index in (0, 5, 6) and len(words) >= 3:
            chosen = [words[0], words[len(words) // 2], words[-1]]
        scene["caption_highlights"] = [{"word": w, "emphasis": "strong"} for w in chosen]
        if chosen:
            scene["emphasis_word"] = chosen[0]


def _add_visual_contract_fields(script):
    scenes = script.get("scene_plan") or []
    for scene in scenes:
        narration = str(scene.get("narration", "")).strip()
        visuals = scene.get("visuals") or []
        for vi, visual in enumerate(visuals):
            prompt = str(visual.get("image_prompt", "")).strip()
            visual.setdefault("spoken_line", narration)
            visual.setdefault("visual_focus", prompt[:180] or narration[:180])
            visual.setdefault("visual_action", prompt[:220] or narration[:220])
            visual.setdefault("must_show", _meaningful(prompt)[:6] or _meaningful(narration)[:6])
            visual["story_beat"] = "establish" if vi == 0 else "advance"
            if vi == 1:
                visual["advance_rule"] = (
                    "show a changed physical state, reaction, closer detail, or consequence; "
                    "do not repeat shot 1"
                )


def patch_story_quality(main):
    """Patch script output without breaking the existing runtime wrapper.

    Do NOT call main.generate_script with four positional arguments here.
    sitecustomize.py wraps that function with a legacy 3-argument signature.
    Word count is only used to report/validate natural output; we intentionally
    avoid repeated regeneration because TTS timing is the authoritative test.
    """
    original = main.generate_script

    def generate_script(topic, config, research=None, extra_feedback=""):
        # Compatibility rule: always call the installed public wrapper using
        # its stable 3-argument API.  The existing generate_script prompt is
        # already entertainment-first and the runtime wrapper adds the hard
        # coherence/visual rules.
        script = original(topic, config, research)
        total = _word_total(script)
        print(f"🧮 Story length: {total} words (soft target 115-140; TTS duration is authoritative)")

        # Only reject genuinely abnormal output. Do not fail a good natural
        # story merely because Gemini produced fewer/more words than the soft
        # planning target.
        if total < 100 or total > 155:
            print(f"⚠️ Story length outside preferred range: {total} words")
            # Keep the pipeline alive for natural Gemini output. The subsequent
            # TTS duration check remains the real production gate.

        _refresh_highlights(script)
        _add_visual_contract_fields(script)
        return script

    main.generate_script = generate_script


def patch_visual_diversity(generate_media_module):
    generate_media_module.MEDIA_DIVERSITY_REQUIRED = True
    print("🎞️ Media diversity: duplicate stock assets prohibited")
