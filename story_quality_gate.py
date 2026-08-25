"""Final quality gate for Mint-YT-Factory's Writer -> Visual Director flow.

IMPORTANT ARCHITECTURE RULE:
The entertainment writer owns narration quality. The visual director owns visual
searchability. This gate therefore NEVER rejects entertaining narration merely
because a sentence is metaphorical or not directly searchable.

It validates the visual contract downstream, after the narration has been written.
"""
from __future__ import annotations

import re

MAX_ATTEMPTS = 6
MIN_STORY_WORDS = 80
MAX_STORY_WORDS = 112

CTA_WORDS = (
    "subscribe", "follow for", "like and subscribe", "smash that", "comment below",
    "link in bio", "click the link", "watch next", "watch why", "watch how",
    "part 2", "stay tuned", "don't miss", "hit subscribe",
)

FUTURE_MARKERS = (
    "another question", "one more question", "one more thing", "that makes you wonder",
    "that makes you ask", "speaking of", "on a related note", "coming next",
    "next topic", "next short", "next video", "then comes",
)

ABSTRACT_VISUAL_WORDS = {
    "whispers", "dances", "thinks", "decides", "communicates", "remembers",
    "plotting", "reveals", "invades", "imagines", "wonders",
}

ABSTRACT_VISUAL_PHRASES = (
    "plotting chemical warfare", "chemical warfare", "secret code", "secret world",
    "underground world", "molecules dance", "atoms dance", "physics dances",
    "physics plays", "nature plays", "kitchen symphony", "becomes an orchestra",
    "tiny workers", "invisible machine", "invisible machines", "magic happens",
    "gets angry", "gets confused", "has a conversation", "is having a conversation",
    "wins the battle", "loses the battle", "comes alive",
)

# Broad, searchable physical actions AND visible states. A visual can pass with
# either an action or a directly visible state; it does not need a stock-footage
# keyword that happens to be a verb.
PHYSICAL_VISUAL_TERMS = {
    "cut", "cuts", "slice", "slices", "chop", "chops", "pour", "pours",
    "boil", "boils", "bubble", "bubbles", "rise", "rises", "fall", "falls",
    "drop", "drops", "melt", "melts", "freeze", "freezes", "crack", "cracks",
    "stick", "sticks", "rub", "rubs", "squeeze", "squeezes", "spin", "spins",
    "roll", "rolls", "shake", "shakes", "open", "opens", "close", "closes",
    "expand", "expands", "shrink", "shrinks", "change", "changes", "drip", "drips",
    "flow", "flows", "rush", "rushes", "escape", "escapes", "hit", "hits",
    "touch", "touches", "land", "lands", "bounce", "bounces", "bend", "bends",
    "break", "breaks", "tear", "tears", "burn", "burns", "glow", "glows",
    "flash", "flashes", "move", "moves", "turn", "turns", "form", "forms",
    "collapse", "collapses", "spread", "spreads", "dry", "dries", "wet", "wets",
    "mix", "mixes", "react", "reacts", "release", "releases", "reach", "reaches",
    "fill", "fills", "irritate", "irritates", "sting", "stings", "swell", "swells",
    "water", "waters", "stream", "streams", "pouring", "cutting", "slicing",
    "opening", "closing", "rising", "falling", "floating", "appearing", "forming",
    "changing", "visible", "shown", "shows", "showing", "close-up", "closeup",
    "wetness", "liquid", "droplets", "droplet", "steam", "smoke", "foam",
    "teardrop", "red", "watery", "swollen", "cracked", "broken", "hot", "cold",
    "cloudy", "mist", "misting", "spray", "sprays", "leak", "leaks", "hold",
    "holds", "push", "pushes", "pull", "pulls", "sealed", "seal", "seals",
    "pressurized", "pressure", "compressed", "compression", "carbonated", "hiss",
    "hisses", "fizz", "fizzes", "fizzing", "splash", "splashes", "burst", "bursts",
    "sound", "noisy", "opened", "bottle", "container", "surface", "texture", "vapor",
    # Common visible states that were missing from the old gate.
    "sits", "sitting", "rests", "resting", "stands", "standing", "contains", "containing",
    "surrounds", "surrounded", "covered", "coated", "filled", "empty", "solid", "liquid",
    "hollow", "deep", "shallow", "raised", "lower", "lowered", "higher", "higher-level",
    "centered", "central", "outer", "inner", "exposed", "hidden", "attached", "separated",
    "aligned", "tilted", "upright", "horizontal", "vertical", "still", "stationary",
    "larger", "smaller", "thick", "thin", "smooth", "rough", "clear", "cloudy",
}


def _words(text):
    return re.findall(r"\b[\w'-]+\b", str(text or "").lower())


def _clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _hits(text, phrases):
    low = _clean(text).lower()
    return [p for p in phrases if p in low]


def _physical_visual(text):
    low = _clean(text).lower()
    return any(re.search(rf"\b{re.escape(term)}\b", low) for term in PHYSICAL_VISUAL_TERMS)


def _abstract_visual_hits(text):
    low = _clean(text).lower()
    hits = [p for p in ABSTRACT_VISUAL_PHRASES if p in low]
    hits.extend(sorted(set(_words(low)) & ABSTRACT_VISUAL_WORDS))
    return sorted(set(hits))


def _strip_cta_sentences(text):
    kept = []
    for sentence in re.split(r"(?<=[.!?])\s+", _clean(text)):
        if not sentence:
            continue
        if _hits(sentence, CTA_WORDS):
            print(f"🧹 Removed accidental CTA from Scene 7 draft: {sentence}")
            continue
        kept.append(sentence)
    return _clean(" ".join(kept))


def _validate(script, topic):
    """Validate the finished Writer + Visual Director output.

    Narration is judged for storytelling hygiene only. Visual searchability is
    checked exclusively on visual fields. This is the critical separation that
    the previous gate violated.
    """
    errors = []
    scenes = script.get("scene_plan") or []
    if len(scenes) != 7:
        return [f"expected 7 scenes, got {len(scenes)}"]

    next_topic = _clean((script.get("next_short") or {}).get("topic"))
    if not next_topic:
        errors.append("next_short.topic is empty")

    total_words = 0

    for si, scene in enumerate(scenes, 1):
        narration = _clean(scene.get("narration"))
        if si == 7:
            narration = _strip_cta_sentences(narration)
            scene["narration"] = narration
            scene["subtitle_text"] = narration
        total_words += len(_words(narration))

        if not narration:
            errors.append(f"Scene {si}: empty narration")
            continue

        # Narration QA: no marketing language and no premature continuation.
        if _hits(narration, CTA_WORDS):
            errors.append(f"Scene {si}: CTA/marketing language inside narration")
        if si < 7 and _hits(narration, FUTURE_MARKERS):
            errors.append(f"Scene {si}: future-topic transition leaked into story")

        visuals = scene.get("visuals") or []
        if len(visuals) != 2:
            errors.append(f"Scene {si}: exactly 2 visuals required")
            continue

        previous_focus = ""
        for vi, visual in enumerate(visuals, 1):
            focus = _clean(visual.get("visual_focus"))
            action = _clean(visual.get("visual_action"))
            prompt = _clean(visual.get("image_prompt"))
            spoken = _clean(visual.get("spoken_line"))
            must_show = " ".join(_clean(x) for x in (visual.get("must_show") or []))
            combined = " ".join((focus, action, prompt, must_show))
            label = f"Scene {si} Shot {vi}"

            if not focus:
                errors.append(f"{label}: missing visual_focus")
            if not action:
                errors.append(f"{label}: missing visual_action/state")
            if len(prompt.split()) < 8:
                errors.append(f"{label}: image prompt too vague")
            if len(prompt.split()) > 60:
                errors.append(f"{label}: image prompt too long")

            abstract_visual = _abstract_visual_hits(combined)
            if abstract_visual:
                errors.append(f"{label}: abstract visual wording: {', '.join(abstract_visual[:4])}")

            if _hits(combined, CTA_WORDS):
                errors.append(f"{label}: CTA text in visual contract")

            if not _physical_visual(combined):
                errors.append(f"{label}: no searchable physical action/state")

            if spoken:
                narration_words = set(_words(narration))
                spoken_words = {w for w in _words(spoken) if len(w) >= 4}
                overlap = len(spoken_words & narration_words) / max(1, len(spoken_words))
                if overlap < 0.35:
                    errors.append(f"{label}: spoken_line does not map to narration")

            if vi == 2 and previous_focus and focus.lower() == previous_focus.lower():
                errors.append(f"{label}: Shot 2 duplicates Shot 1 focus")
            previous_focus = focus

    if total_words < MIN_STORY_WORDS or total_words > MAX_STORY_WORDS:
        errors.append(f"story word count {total_words} outside {MIN_STORY_WORDS}–{MAX_STORY_WORDS}")

    return errors


def patch_story_generation(main):
    """Wrap the existing generator with a downstream visual QA pass.

    Crucially, feedback from this gate is directed at the Visual Director. It
    never tells the entertainment writer to rewrite a metaphor into stock-footage
    language. That keeps the two responsibilities separate.
    """
    original = main.generate_script
    if getattr(original, "_mint_final_story_gate", False):
        return

    def generate_script(topic, config, research=None, extra_feedback=""):
        last_error = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            feedback = (extra_feedback or "") + """

FINAL MINT TWO-STAGE QUALITY RULES:
1. The entertainment writer owns narration. Preserve conversational, playful, surprising language.
2. Do NOT rewrite a good narration sentence merely because it is metaphorical or difficult to search.
3. The Visual Director owns visual searchability. Translate narration into literal visible subjects,
actions, changes, or states in visual_focus, visual_action, must_show, must_not_show, and image_prompt.
4. Every visual must contain a concrete subject and either a physical action OR a clearly visible physical state.
5. Shot 2 must advance or reveal a different physical state, action, angle, or consequence.
6. Keep the story 80–112 words and avoid filler.
7. The production continuation system owns the locked next-topic sentence.
"""
            if last_error:
                feedback += f"""

PREVIOUS VISUAL QA FAILED:
{last_error}
Fix the VISUAL FIELDS, not the personality of the narration. Keep the narration entertaining unless it independently violates a narration rule.
"""

            script = original(topic, config, research, extra_feedback=feedback)
            errors = _validate(script, topic)
            if not errors:
                print(f"🛡️ Final story/visual gate: PASS (attempt {attempt})")
                return script

            last_error = " | ".join(errors[:8])
            print(f"🛡️ Final story/visual gate: FAIL (attempt {attempt}/{MAX_ATTEMPTS}) — {last_error}")

        raise RuntimeError(
            f"Final story/visual quality gate failed after {MAX_ATTEMPTS} attempts: {last_error}"
        )

    generate_script._mint_final_story_gate = True
    main.generate_script = generate_script
