"""Retention-focused narration polish for narration-led Riddles Shorts."""
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
        visual["visual_action"] = "Atmospherically support the exact spoken beat only; stock media is not a clue and must never reveal the current riddle answer."
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


def _bridge_line(variant):
    lines = (
        "Now reset your brain, because this next one is sneakier.",
        "Good. Forget that answer for a second. Your next challenge starts now.",
        "One mystery down. Let's see what your brain does with this one.",
        "Nice catch. Now don't trust your first instinct on the next one.",
        "Alright, new puzzle. And this time, listen to every word.",
    )
    return lines[variant % len(lines)]


def _ending_line(variant):
    lines = (
        "Lock in your first answer. Subscribe and follow us for the answer in the next Short.",
        "Think you've cracked it? Keep that answer. Subscribe and follow for the reveal in the next Short.",
        "Don't change your guess. Follow and subscribe, and we'll reveal the answer in the next Short.",
        "Your answer is locked. Subscribe and follow us to find out if you were right in the next Short.",
        "Got your answer? Good. Follow and subscribe for the answer in the next Short.",
    )
    return lines[variant % len(lines)]


def _replace_canned_ending(text):
    patterns = (
        r"(?:the answer to riddle\s*#?\d+\s*(?:will be|comes|is).*?$)",
        r"(?:answer.*?next riddle short.*?$)",
        r"(?:answer.*?next short.*?$)",
        r"(?:subscribe.*?next short.*?$)",
        r"(?:follow.*?next short.*?$)",
    )
    out = str(text or "").strip()
    for pattern in patterns:
        out = re.sub(pattern, "", out, flags=re.I).strip()
    return out


def _remove_visual_dependency(text):
    out = str(text or "")
    replacements = {
        r"\blook at this\b": "listen to this",
        r"\blook closely\b": "listen closely",
        r"\blook carefully\b": "listen carefully",
        r"\bwhat do you see\b": "what do you think",
        r"\bin this picture\b": "in this riddle",
        r"\bon screen\b": "in the question",
    }
    for pattern, replacement in replacements.items():
        out = re.sub(pattern, replacement, out, flags=re.I)
    return out


def polish_riddle_script(script, previous, number):
    """Enforce the narration-first retention contract after Gemini generation."""
    scenes = script.get("scene_plan") or []
    if len(scenes) != 7:
        raise RuntimeError("Riddle script must contain exactly 7 scenes before narration polish.")
    variant = (sum(ord(c) for c in str(script.get("topic", ""))) + number * 17) % 5

    for scene in scenes:
        scene["narration"] = _remove_visual_dependency(str(scene.get("narration", "")).strip())

    if previous:
        answer = str(previous.get("answer", "")).strip()
        previous_number = int(previous.get("number", number - 1))
        if answer:
            first = scenes[0]
            existing = str(first.get("narration", "")).strip()
            existing = re.sub(
                rf"^(?:before today.?s challenge,?\s*)?(?:here.?s|here is|the answer to)?\s*riddle\s*#?{previous_number}[^.?!]*[.?!]\s*",
                "",
                existing,
                flags=re.I,
            )
            reveal = _reveal_line(previous_number + 1, answer, variant)
            transition = _bridge_line(variant + 1)
            first["narration"] = f"{reveal} {transition} {existing}".strip()
            first["purpose"] = "hook"
            first["retention_purpose"] = "pattern_break_and_payoff"
            _sync_visuals(first)

    # Ensure the final scene is a subscribe/follow answer loop, without promising tomorrow.
    last = scenes[-1]
    text = _replace_canned_ending(last.get("narration", ""))
    text = text.rstrip(" .!?")
    ending = _ending_line(variant + 2)
    last["narration"] = f"{text}. {ending}" if text else ending
    last["purpose"] = "ending"
    last["retention_purpose"] = "answer_loop_subscribe_follow"
    _sync_visuals(last)

    # Replace long countdowns with a compact pressure beat.
    countdown_re = re.compile(r"\b(?:10|9|8|7|6|5|4|3|2|1)(?:\s*,?\s*(?:10|9|8|7|6|5|4|3|2|1)){3,}\b")
    for scene in scenes:
        text = str(scene.get("narration", "")).strip()
        if countdown_re.search(text):
            text = countdown_re.sub("Final guess. Three… two… one.", text, count=1)
            scene["narration"] = text
        _sync_visuals(scene)

    # Keep narration compact and remove only low-value filler if necessary.
    total = sum(len(_words(s.get("narration", ""))) for s in scenes)
    if total > 260:
        filler = re.compile(r"\b(?:okay|alright|so|basically|well|guys|come on),?\s+", re.I)
        for scene in scenes:
            scene["narration"] = filler.sub("", str(scene.get("narration", "")), count=1).strip()
            _sync_visuals(scene)
            total = sum(len(_words(s.get("narration", ""))) for s in scenes)
            if total <= 260:
                break
    if total < 20:
        raise RuntimeError(f"Riddle narration too short after retention polish: {total} words.")

    script["riddle_narration_version"] = "retention_v3_narration_first"
    script["riddle_reveal_style"] = variant
    script["visual_dependency"] = "none"
    return script
