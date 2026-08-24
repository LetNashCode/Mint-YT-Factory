"""Final hard gate for narration/visual coherence before TTS and Pexels."""
from __future__ import annotations

import inspect
import re

MAX_ATTEMPTS = 4

# These are not "bad writing" by themselves; they are bad INPUTS for a literal
# stock-footage pipeline because they turn into searches such as "chemical warfare"
# or "physics dances" instead of something a camera can actually show.
ABSTRACT_BEATS = (
    "plotting chemical warfare", "chemical warfare", "plotting", "secret code",
    "secret world", "underground world", "reveals its secret", "reveals the secret",
    "molecules dance", "atoms dance", "physics dances", "physics plays",
    "nature plays", "kitchen symphony", "becomes an orchestra", "plays an orchestra",
    "tiny workers", "invisible machine", "invisible machines", "magic happens",
    "the magic happens", "gets angry", "gets confused", "has a conversation",
    "is having a conversation", "tells a story", "tells us", "wins the battle",
    "loses the battle", "fights the", "comes alive", "searching for moisture",
    "desperate panic", "chemical invader", "secret", "invader",
)

# "scream" is allowed only when the sentence explicitly says it is a sound.
ABSTRACT_SINGLE_WORDS = {
    "climbs", "climb", "whispers", "dances", "thinks", "decides", "communicates",
    "remembers", "fights", "wins", "loses", "reveals", "plotting",
}

CTA_WORDS = (
    "subscribe", "follow for", "like and subscribe", "smash that", "comment below",
    "link in bio", "click the link", "watch next", "watch why", "watch how",
    "part 2", "stay tuned", "don't miss", "hit subscribe", "decode why",
)

FUTURE_MARKERS = (
    "another question", "one more question", "one more thing", "that makes you wonder",
    "that makes you ask", "speaking of", "on a related note", "coming next",
    "next topic", "next short", "next video", "then comes",
)

PHYSICAL_ACTIONS = {
    "cut", "cuts", "slice", "slices", "chop", "chops", "pour", "pours", "boil",
    "boils", "bubble", "bubbles", "rise", "rises", "fall", "falls", "drop", "drops",
    "melt", "melts", "freeze", "freezes", "crack", "cracks", "stick", "sticks",
    "rub", "rubs", "squeeze", "squeezes", "spin", "spins", "roll", "rolls",
    "shake", "shakes", "open", "opens", "close", "closes", "expand", "expands",
    "shrink", "shrinks", "change", "changes", "drip", "drips", "flow", "flows",
    "rush", "rushes", "escape", "escapes", "hit", "hits", "touch", "touches",
    "land", "lands", "bounce", "bounces", "bend", "bends", "break", "breaks",
    "tear", "tears", "burn", "burns", "glow", "glows", "flash", "flashes",
    "move", "moves", "turn", "turns", "shake", "shakes", "form", "forms",
    "collapse", "collapses", "spread", "spreads", "dry", "dries", "wet", "gets wet",
}


def _words(text):
    return re.findall(r"\b[\w'-]+\b", str(text or "").lower())


def _clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _sentences(text):
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", _clean(text)) if x.strip()]


def _hits(text, phrases):
    low = _clean(text).lower()
    return [p for p in phrases if p in low]


def _abstract_word_hits(text):
    words = set(_words(text))
    return sorted(words & ABSTRACT_SINGLE_WORDS)


def _physical_action(text):
    low = _clean(text).lower()
    return any(re.search(rf"\b{re.escape(x)}\b", low) for x in PHYSICAL_ACTIONS)


def _validate(script, topic):
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
        total_words += len(_words(narration))
        if not narration:
            errors.append(f"Scene {si}: empty narration")
            continue

        if _hits(narration, CTA_WORDS):
            errors.append(f"Scene {si}: CTA/marketing language inside narration")

        if si < 7 and _hits(narration, FUTURE_MARKERS):
            errors.append(f"Scene {si}: future-topic transition leaked into story")

        # Reject metaphorical visual language even when a real object is also named.
        # This is the exact failure that let "onion ... plotting chemical warfare"
        # pass the previous gate merely because the word "onion" was present.
        abstract = _hits(narration, ABSTRACT_BEATS)
        if abstract:
            # A literal sound comparison is acceptable: "sounds like a scream as steam..."
            low = narration.lower()
            scream_ok = "sounds like a scream" in low or "sounds almost like a scream" in low
            abstract = [x for x in abstract if not (x == "scream" and scream_ok)]
            if abstract:
                errors.append(f"Scene {si}: non-literal narration: {', '.join(abstract[:4])}")

        word_hits = _abstract_word_hits(narration)
        if word_hits:
            errors.append(f"Scene {si}: abstract action words: {', '.join(word_hits)}")

        if si == 7 and next_topic:
            sentences = _sentences(narration)
            if not sentences or next_topic.lower() not in sentences[-1].lower():
                errors.append("Scene 7: final sentence must name the generated next topic")
            if len([s for s in sentences if next_topic.lower() in s.lower()]) != 1:
                errors.append("Scene 7: next topic must appear exactly once")

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
            combined = " ".join((focus, action, prompt))
            label = f"Scene {si} Shot {vi}"

            if len(prompt.split()) < 8:
                errors.append(f"{label}: image prompt too vague")
            if len(prompt.split()) > 60:
                errors.append(f"{label}: image prompt too long")
            if not focus or not action:
                errors.append(f"{label}: missing concrete focus/action")

            abstract_visual = _hits(combined, ABSTRACT_BEATS)
            if abstract_visual:
                errors.append(f"{label}: non-literal visual wording: {', '.join(abstract_visual[:4])}")
            if _abstract_word_hits(combined):
                errors.append(f"{label}: abstract visual action")

            if _hits(combined, CTA_WORDS):
                errors.append(f"{label}: CTA text in visual contract")

            # A visual beat should contain an observable action or a concrete state.
            # This catches prose such as "the onion plots..." before it reaches Pexels.
            if not _physical_action(combined):
                errors.append(f"{label}: no searchable physical action")

            if spoken:
                narration_words = set(_words(narration))
                spoken_words = {w for w in _words(spoken) if len(w) >= 4}
                overlap = len(spoken_words & narration_words) / max(1, len(spoken_words))
                if overlap < 0.35:
                    errors.append(f"{label}: spoken_line does not map to narration")

            if vi == 2 and previous_focus and focus.lower() == previous_focus.lower():
                errors.append(f"{label}: Shot 2 duplicates Shot 1 focus")
            previous_focus = focus

    if total_words < 95 or total_words > 115:
        errors.append(f"story word count {total_words} outside 95–115")

    return errors


def patch_story_generation(main):
    """Wrap the already-existing generator with a final pre-TTS hard gate."""
    original = main.generate_script
    if getattr(original, "_mint_final_story_gate", False):
        return

    def generate_script(topic, config, research=None, extra_feedback=""):
        last_error = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            feedback = extra_feedback or ""
            feedback += (
                "\n\nFINAL MINT VISUAL RULES — NON-NEGOTIABLE:\n"
                "Every narration beat must describe a literal, observable physical event. "
                "Do not use metaphorical actions such as plotting, chemical warfare, dancing, "
                "revealing secrets, invisible workers, screaming, or secret worlds. "
                "If an idea is invisible, describe the visible consequence instead. "
                "Do not put Subscribe, Follow, CTA, or a different future mystery inside the story. "
                "Scene 7 must end with exactly the generated next_short.topic and nothing after it. "
                "Every visual needs a concrete subject, physical action/state, and context. "
                "Shot 2 must physically advance Shot 1.\n"
            )
            if last_error:
                feedback += f"\nTHE PREVIOUS DRAFT FAILED THIS HARD GATE:\n{last_error}\nRewrite the entire story."

            script = original(topic, config, research, extra_feedback=feedback)
            errors = _validate(script, topic)
            if not errors:
                print(f"🛡️ Final story/visual gate: PASS (attempt {attempt})")
                return script

            last_error = " | ".join(errors[:8])
            print(f"🛡️ Final story/visual gate: FAIL (attempt {attempt}/{MAX_ATTEMPTS}) — {last_error}")

        raise RuntimeError(f"Final story/visual quality gate failed after {MAX_ATTEMPTS} attempts: {last_error}")

    generate_script._mint_final_story_gate = True
    main.generate_script = generate_script
