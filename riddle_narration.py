"""Retention-focused narration polish for Riddles Shorts."""
from __future__ import annotations
import re


def _sentences(text):
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if x.strip()]


def _words(text):
    return re.findall(r"\b[\w'-]+\b", str(text or ""))


def _sync_visuals(scene):
    narration = str(scene.get("narration", "")).strip()
    for visual in scene.get("visuals") or []:
        if not isinstance(visual, dict):
            continue
        visual["spoken_line"] = narration
        visual["visual_focus"] = narration[:180]
        visual["visual_action"] = "Visually support the exact spoken beat; do not reveal the current riddle answer."
    scene["subtitle_text"] = narration


def _reveal_line(number, answer, variant):
    lines = (
        f"Alright, who guessed {answer}? Riddle #{number - 1} was {answer}. If you got it, nice catch.",
        f"Time to settle the last one: the answer was {answer}. Did you have it? Be honest.",
        f"Okay, reveal time. The answer to Riddle #{number - 1} is {answer}. Your brain either nailed that… or absolutely did not.",
        f"Let's close the loop on the last riddle: {answer}. If that was your guess, take the win.",
        f"Before we move on, the last answer was {answer}. Did you spot it before the countdown ended?",
    )
    return lines[variant % len(lines)]


def _bridge_line(number, variant):
    lines = (
        "Nice. Now let's see if the next one catches you off guard.",
        "That one was the warm-up. This next one plays a nastier trick.",
        "One mystery down. Your next ten seconds start now.",
        "If you got that, don't celebrate yet. The next one is sneakier.",
        "Alright, reset your brain. The next riddle is waiting.",
    )
    return lines[variant % len(lines)]


def _ending_line(number, variant):
    lines = (
        f"Lock in your answer. I'm not giving away Riddle #{number} yet—its reveal opens the next Short.",
        f"Got a guess? Keep it. Riddle #{number} gets its answer in the next Short.",
        f"No peeking. Remember your answer, because Riddle #{number} is getting revealed next time.",
        f"Think you've cracked it? Hold that thought. The answer to Riddle #{number} comes next Short.",
        f"Your answer is locked. I'll tell you whether you're right when Riddle #{number} returns.",
    )
    return lines[variant % len(lines)]


def polish_riddle_script(script, previous, number):
    """Apply deterministic episode-to-episode variation after Gemini generation."""
    scenes = script.get("scene_plan") or []
    if len(scenes) != 7:
        raise RuntimeError("Riddle script must contain exactly 7 scenes before narration polish.")
    variant = (sum(ord(c) for c in str(script.get("topic", ""))) + number * 17) % 5

    if previous:
        answer = str(previous.get("answer", "")).strip()
        previous_number = int(previous.get("number", number - 1))
        if answer:
            first = scenes[0]
            existing = str(first.get("narration", "")).strip()
            # Remove a model-generated previous-answer opener to prevent double reveals.
            existing = re.sub(
                rf"^(?:before today.?s challenge,?\s*)?(?:here.?s|here is|the answer to)?\s*riddle\s*#?{previous_number}[^.?!]*[.?!]\s*",
                "",
                existing,
                flags=re.I,
            )
            reveal = _reveal_line(previous_number + 1, answer, variant)
            transition = _bridge_line(number, variant + 1)
            first["narration"] = f"{reveal} {transition} {existing}".strip()
            first["purpose"] = "hook"
            first["retention_purpose"] = "pattern_break"
            _sync_visuals(first)

    # Never leave the old repetitive stock ending. Replace it with a varied cliffhanger.
    last = scenes[-1]
    text = str(last.get("narration", "")).strip()
    text = re.sub(r"(?:the answer to riddle\s*#?\d+\s*(?:will be|comes|is).*?$)", "", text, flags=re.I).strip()
    text = re.sub(r"(?:answer.*?next riddle short.*?$)", "", text, flags=re.I).strip()
    ending = _ending_line(number, variant + 2)
    last["narration"] = f"{text.rstrip(' .!?')} . {ending}".strip(" .")
    last["purpose"] = "ending"
    last["retention_purpose"] = "open_loop"
    _sync_visuals(last)

    # Replace literal 10-to-1 narration instructions with a more conversational pressure beat.
    countdown_re = re.compile(r"\b(?:10|9|8|7|6|5|4|3|2|1)(?:\s*,?\s*(?:10|9|8|7|6|5|4|3|2|1)){3,}\b")
    for i, scene in enumerate(scenes):
        text = str(scene.get("narration", "")).strip()
        if countdown_re.search(text):
            text = countdown_re.sub("Ten seconds. Think fast. Don't overthink it. Five seconds. Lock in your guess. Three… two… one.", text, count=1)
            scene["narration"] = text
            _sync_visuals(scene)

    # Keep the total in the existing flexible production range.
    total = sum(len(_words(s.get("narration", ""))) for s in scenes)
    if total > 260:
        # Trim only redundant transition chatter, never the riddle itself.
        for scene in scenes:
            scene["narration"] = re.sub(r"\b(?:okay|alright),?\s+", "", str(scene.get("narration", "")), flags=re.I, count=1).strip()
            _sync_visuals(scene)
            total = sum(len(_words(s.get("narration", ""))) for s in scenes)
            if total <= 260:
                break
    if total < 20:
        raise RuntimeError(f"Riddle narration too short after retention polish: {total} words.")

    script["riddle_narration_version"] = "retention_v2"
    script["riddle_reveal_style"] = variant
    return script
