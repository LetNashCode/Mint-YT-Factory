"""Retention-focused narration polish for narration-led Riddles Shorts."""
from __future__ import annotations
import re

# Riddle Shorts should feel like a fast spoken mini-game rather than a compressed
# long-form script. The range corresponds roughly to 19-30 seconds at a natural pace.
MIN_WORDS = 60
MAX_WORDS = 95
SCENE_WORD_BUDGETS = (
    (8, 14),   # hook / previous-answer reveal
    (10, 18),  # new riddle
    (8, 14),   # first interpretation
    (8, 14),   # trap / reversal
    (8, 12),   # forced commitment
    (5, 8),    # countdown pressure
    (13, 15),  # payoff gap + CTA
)


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
        f"Last answer: {answer}. Did you get it?",
        f"Quick reveal: Riddle #{number - 1} was {answer}. Nailed it?",
        f"The last answer was {answer}. Be honest—did you get it?",
        f"Riddle #{number - 1} was {answer}. Nice catch if you had it.",
        f"Answer check: {answer}. Did your first guess match?",
    )
    return lines[variant % len(lines)]


def _bridge_line(variant):
    lines = (
        "Now this one is sneakier.",
        "Forget that one. New challenge.",
        "New puzzle. Trust your ears.",
        "Now don't trust your first instinct.",
        "Alright—new puzzle. Listen closely.",
    )
    return lines[variant % len(lines)]


def _ending_line(variant):
    lines = (
        "Lock it in. Subscribe and follow for the answer in the next Short.",
        "Keep your first answer. Subscribe and follow for the reveal in the next Short.",
        "Don't change your guess. Follow and subscribe for the answer in the next Short.",
        "Answer locked. Subscribe and follow to see if you were right in the next Short.",
        "Got your answer? Follow and subscribe for the answer in the next Short.",
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
        out = re.sub(pattern, "", out, flags=re.I)
    return out.strip()


def _remove_visual_dependency(text):
    out = str(text or "")
    replacements = {
        r"\blook at this\b": "listen to this",
        r"\blook closely\b": "listen closely",
        r"\blook carefully\b": "listen carefully",
        r"\bwhat do you see\b": "what do you think",
        r"\bin this picture\b": "in this riddle",
        r"\bon screen\b": "in the question",
        r"\bwatch this\b": "hear this",
    }
    for pattern, replacement in replacements.items():
        out = re.sub(pattern, replacement, out, flags=re.I)
    return out


def _trim_low_value_filler(text):
    out = str(text or "").strip()
    filler = re.compile(r"\b(?:okay|alright|so|basically|well|guys|come on|listen up),?\s+", re.I)
    for _ in range(2):
        new = filler.sub("", out, count=1).strip()
        if new == out:
            break
        out = new
    return out


def _compact_scene(scene):
    scene["narration"] = _trim_low_value_filler(
        _remove_visual_dependency(str(scene.get("narration", "")).strip())
    )


def polish_riddle_script(script, previous, number):
    """Enforce the short, narration-first retention contract after Gemini generation."""
    scenes = script.get("scene_plan") or []
    if len(scenes) != 7:
        raise RuntimeError("Riddle script must contain exactly 7 scenes before narration polish.")
    variant = (sum(ord(c) for c in str(script.get("topic", ""))) + number * 17) % 5

    for scene in scenes:
        _compact_scene(scene)

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

    # Hard-code the two pacing-critical beats rather than trusting a generated scene
    # to spend the right amount of time there.
    scenes[4]["narration"] = _trim_low_value_filler(str(scenes[4].get("narration", "")).strip())
    if not re.search(r"\b(first answer|first guess|lock|commit|pick|choose|guess)\b", scenes[4]["narration"], re.I):
        scenes[4]["narration"] = "Lock in your first answer. Don't change it."
    scenes[4]["retention_purpose"] = "forced_commitment"

    pressure = _trim_low_value_filler(str(scenes[5].get("narration", "")).strip())
    pressure = re.sub(
        r"\b(?:10|9|8|7|6|5|4|3|2|1)(?:\s*,?\s*(?:10|9|8|7|6|5|4|3|2|1)){2,}\b",
        "Final guess. Three… two… one.",
        pressure,
        count=1,
    )
    if not re.search(r"three[.… ]+two[.… ]+one|3[.… ]*2[.… ]*1", pressure, re.I):
        pressure = "Final guess. Three… two… one."
    scenes[5]["narration"] = pressure
    scenes[5]["retention_purpose"] = "countdown_pressure"

    last = scenes[-1]
    text = _replace_canned_ending(last.get("narration", ""))
    text = text.rstrip(" .!?")
    ending = _ending_line(variant + 2)
    last["narration"] = f"{text}. {ending}" if text else ending
    last["purpose"] = "ending"
    last["retention_purpose"] = "answer_loop_subscribe_follow"

    for scene in scenes:
        _compact_scene(scene)
        _sync_visuals(scene)

    total = sum(len(_words(s.get("narration", ""))) for s in scenes)
    if total < MIN_WORDS or total > MAX_WORDS:
        raise RuntimeError(f"Riddle narration length {total} outside optimized {MIN_WORDS}-{MAX_WORDS} range.")

    # Prevent one scene from becoming a hidden retention sink. These are validation
    # bands, not targets to pad toward; the generator must naturally fit them.
    for index, (low, high) in enumerate(SCENE_WORD_BUDGETS):
        count = len(_words(scenes[index].get("narration", "")))
        if count < low or count > high:
            raise RuntimeError(
                f"Riddle Scene {index + 1} has {count} words; expected {low}-{high} for pacing."
            )

    script["riddle_narration_version"] = "retention_v5_paced_narration"
    script["riddle_reveal_style"] = variant
    script["riddle_word_target"] = {"min": MIN_WORDS, "max": MAX_WORDS}
    script["riddle_scene_word_budgets"] = [list(x) for x in SCENE_WORD_BUDGETS]
    script["estimated_narration_seconds"] = round(total / 3.2, 1)
    script["visual_dependency"] = "none"
    return script
