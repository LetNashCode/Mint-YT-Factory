"""Retention-focused narration polish for narration-led Riddles Shorts."""
from __future__ import annotations
import hashlib
import re

MIN_WORDS = 60
MAX_WORDS = 95
SCENE_WORD_BUDGETS = ((8, 14), (10, 18), (8, 14), (8, 14), (8, 12), (5, 8), (13, 15))

REVEAL_STYLES = (
    "answer_check",
    "quick_payoff",
    "listener_score",
    "confidence_check",
    "clean_reveal",
    "retro_reveal",
    "challenge_reveal",
    "curiosity_reveal",
)

REVEAL_LINES = {
    "answer_check": (
        "Quick answer check: {answer}. Did you have it?",
        "Let's settle the last one: {answer}. Were you right?",
    ),
    "quick_payoff": (
        "The mystery from the last Short? {answer}.",
        "That last puzzle had a simple answer: {answer}.",
    ),
    "listener_score": (
        "Score one if you said {answer}.",
        "If you guessed {answer}, give yourself the point.",
    ),
    "confidence_check": (
        "Be honest—the last answer was {answer}.",
        "Your last guess was either {answer}… or nowhere close.",
    ),
    "clean_reveal": (
        "For the last riddle, the answer was {answer}.",
        "The answer we left hanging was {answer}.",
    ),
    "retro_reveal": (
        "Before we move on, reveal time: {answer}.",
        "One loose end first: the previous answer was {answer}.",
    ),
    "challenge_reveal": (
        "Did you beat the last puzzle? The answer was {answer}.",
        "Last round's answer: {answer}. Did your brain catch that?",
    ),
    "curiosity_reveal": (
        "Remember that last puzzle? Its answer was {answer}.",
        "That little mystery we left open? It was {answer}.",
    ),
}

BRIDGE_LINES = {
    "answer_check": ("Now earn the next point.", "Here's a fresh one.",),
    "quick_payoff": ("But we're not done yet.", "And this one plays differently.",),
    "listener_score": ("Keep that score going.", "Your next test starts now.",),
    "confidence_check": ("Now forget that answer and reset.", "Don't let that guess help you now.",),
    "clean_reveal": ("Now for a completely new puzzle.", "Let's switch gears.",),
    "retro_reveal": ("Loose end tied. New puzzle.", "That's settled. Try this one.",),
    "challenge_reveal": ("Round two starts now.", "Think faster this time.",),
    "curiosity_reveal": ("And now, another mystery.", "That one's done. This one isn't.",),
}

ENDING_LINES = (
    "Lock in your answer. Subscribe and follow for the reveal in the next Short.",
    "Keep your first guess. Follow and subscribe to find out if you were right in the next Short.",
    "Don't change it now. Subscribe and follow for the answer in the next Short.",
    "Answer locked. Follow and subscribe for the reveal in the next Short.",
    "Got your guess? Subscribe and follow for the answer in the next Short.",
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


def _variant(topic, number, answer):
    seed = f"{topic}|{number}|{answer}"
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % len(REVEAL_STYLES)


def _reveal_line(number, answer, variant):
    style = REVEAL_STYLES[variant % len(REVEAL_STYLES)]
    lines = REVEAL_LINES[style]
    text = lines[(variant // len(REVEAL_STYLES)) % len(lines)].format(answer=answer)
    return text, style


def _bridge_line(variant, style):
    lines = BRIDGE_LINES[style]
    return lines[(variant // 2) % len(lines)]


def _ending_line(variant):
    return ENDING_LINES[variant % len(ENDING_LINES)]


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
    """Enforce narration-first pacing while making the previous-answer reveal vary per episode."""
    scenes = script.get("scene_plan") or []
    if len(scenes) != 7:
        raise RuntimeError("Riddle script must contain exactly 7 scenes before narration polish.")
    variant = _variant(str(script.get("topic", "")), number, str((previous or {}).get("answer", "")))

    for scene in scenes:
        _compact_scene(scene)

    reveal_style = "none"
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
            reveal, reveal_style = _reveal_line(previous_number + 1, answer, variant)
            transition = _bridge_line(variant, reveal_style)
            first["narration"] = f"{reveal} {transition} {existing}".strip()
            first["purpose"] = "hook"
            first["retention_purpose"] = "pattern_break_and_payoff"

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

    for index, (low, high) in enumerate(SCENE_WORD_BUDGETS):
        count = len(_words(scenes[index].get("narration", "")))
        if count < low or count > high:
            raise RuntimeError(
                f"Riddle Scene {index + 1} has {count} words; expected {low}-{high} for pacing."
            )

    script["riddle_narration_version"] = "retention_v6_unique_reveals"
    script["riddle_reveal_style"] = reveal_style
    script["riddle_reveal_variant"] = variant
    script["riddle_word_target"] = {"min": MIN_WORDS, "max": MAX_WORDS}
    script["riddle_scene_word_budgets"] = [list(x) for x in SCENE_WORD_BUDGETS]
    script["estimated_narration_seconds"] = round(total / 3.2, 1)
    script["visual_dependency"] = "none"
    return script
