"""Quality controls layered onto the existing Mint-YT-Factory pipeline."""
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

MIN_STORY_WORDS = 105
MAX_STORY_WORDS = 120
MAX_REGEN_ATTEMPTS = 3


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


def _sanitize_final_scene(script):
    """Remove stale continuation fragments before runtime continuation locking."""
    scenes = script.get("scene_plan") or []
    if not scenes:
        return
    scene = scenes[-1]
    text = str(scene.get("narration", "")).strip()
    if not text:
        return

    text = re.split(
        r"\b(?:and\s+next\s*:|next\s+(?:video|short|topic)\s*:|coming\s+next\b|stay\s+tuned\b|part\s*2\b)",
        text,
        maxsplit=1,
        flags=re.I,
    )[0].strip()
    text = re.split(
        r"\s+(?:which|and\s+that)\s+(?:is\s+)?(?:also\s+)?why\b",
        text,
        maxsplit=1,
        flags=re.I,
    )[0].strip()
    text = re.split(
        r"\s+(?:and\s+that'?s\s+why|which\s+means)\b",
        text,
        maxsplit=1,
        flags=re.I,
    )[0].strip()

    if text:
        scene["narration"] = text.rstrip(".!? ") + "."
        scene["subtitle_text"] = scene["narration"]


def patch_story_quality(main):
    """Make story duration a real production gate, not a soft suggestion."""
    original = main.generate_script

    def generate_script(topic, config, research=None, extra_feedback=""):
        last = None
        for attempt in range(1, MAX_REGEN_ATTEMPTS + 1):
            feedback = extra_feedback or ""
            if last:
                feedback += (
                    "\nThe previous draft failed production length validation. "
                    "Rewrite the ENTIRE story for a natural 38-43 second narration. "
                    "Do not add filler. Expand the mystery, concrete demonstration, "
                    "escalation and payoff. Keep the final continuation sentence short."
                )
            # IMPORTANT: main.generate_script is wrapped by this module, so pass
            # the learning feedback by keyword. Passing a fourth positional
            # argument breaks the entertainment generator's public signature.
            script = original(
                topic,
                config,
                research,
                extra_feedback=feedback,
            )
            _sanitize_final_scene(script)
            total = _word_total(script)
            print(
                f"🧮 Story length: {total} words "
                f"(hard target {MIN_STORY_WORDS}-{MAX_STORY_WORDS}; target narration ~38-43s)"
            )
            if MIN_STORY_WORDS <= total <= MAX_STORY_WORDS:
                _refresh_highlights(script)
                _add_visual_contract_fields(script)
                return script
            last = f"story length {total} words outside {MIN_STORY_WORDS}-{MAX_STORY_WORDS}"
            print(f"⚠️ Story length rejected: {last}")

        raise RuntimeError(
            f"Could not generate a production-length story after {MAX_REGEN_ATTEMPTS} attempts."
        )

    main.generate_script = generate_script


def patch_visual_diversity(generate_media_module):
    generate_media_module.MEDIA_DIVERSITY_REQUIRED = True
    print("🎞️ Media diversity: duplicate stock assets prohibited")
