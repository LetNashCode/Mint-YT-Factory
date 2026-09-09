"""Narration-first Riddles Shorts generator."""
from __future__ import annotations
from . import entertainment as _base

MIN_WORDS = 60
MAX_WORDS = 95
SCENE_WORD_BUDGETS = ((8, 14), (10, 18), (8, 14), (8, 14), (8, 12), (5, 8), (13, 15))


def _feedback(extra=""):
    return (
        "RIDDLES SHORTS ONLY. This is an audio/narration-led puzzle, not a visual puzzle. "
        "The viewer must be able to solve the riddle with the phone face-down; stock visuals are atmosphere only and must never carry a required clue. "
        "Do not require a visual clue, visual inspection, on-screen text, or an object in the footage to solve the NEW riddle. "
        "A previous riddle answer may be revealed, but the NEW answer must remain locked. "
        "The ending must ask viewers to subscribe and follow for the NEW answer in the next Short; never say tomorrow, next day, or imply a fixed schedule. "
        f"Target {MIN_WORDS}-{MAX_WORDS} total spoken words, with strict scene pacing bands. Every sentence must earn its place. "
        + str(extra or "")
    )


def generate_script(topic, config, research=None, extra_feedback=""):
    from google import genai
    from google.genai import types
    import time

    topic = _base._clean(topic)
    if not topic:
        raise RuntimeError("Riddle topic is empty.")
    client = genai.Client(api_key=_base._api_key())
    prompt = f"""RIDDLES SHORTS MODE — NARRATION FIRST.
CURRENT RIDDLE: {topic}
Create exactly 7 scenes. Return the normal production JSON schema.

The Short must work as a spoken mini-game. The narration is the product; stock media is only mood/context and must never be needed to understand or solve the riddle.
Target {MIN_WORDS}-{MAX_WORDS} total spoken words. Aim for roughly 19-30 seconds at a natural energetic pace. Do not pad for length.
SCENE PACING BANDS — these are maximum/minimum guidance, not filler targets:
- Scene 1: 8-14 words. Immediate hook; if a previous answer exists, reveal it in one short sentence and pivot.
- Scene 2: 10-18 words. State the NEW riddle clearly. Reach the actual question immediately.
- Scene 3: 8-14 words. Trigger the obvious first interpretation with one curiosity gap.
- Scene 4: 8-14 words. One spoken trap, reversal, or assumption break. No explanation dump.
- Scene 5: 8-12 words. Force the viewer to lock in their FIRST answer.
- Scene 6: 5-8 words. Brief pressure ending with conversational 3…2…1. Never 10-to-1.
- Scene 7: 13-15 words. Preserve the NEW answer payoff gap and use a short subscribe/follow CTA for the answer in the next Short.

Vary the mechanic across episodes: wording traps, double meanings, obvious-answer traps, lateral thinking, expectation reversals, tiny logic mysteries, misconceptions and psychological traps. Use only a mechanic that genuinely fits the riddle.
Keep every clue solvable from spoken words alone. Avoid visual-puzzle formats and phrases like "look at this", "you can see", "notice the picture", or clues that depend on footage.
Do not reveal, spell out, strongly hint at, or explain the NEW answer. Do not accidentally leak it through examples or hypothetical guesses.
Avoid generic filler: "welcome back", "today's riddle", "here's today's riddle", "stay tuned", "guys", "don't forget to like and subscribe".
{_feedback(extra_feedback)}
"""
    last_error = None
    attempts = 0
    while attempts < _base.MAX_ATTEMPTS:
        try:
            retry = f"\nFix previous error: {last_error}" if last_error else ""
            response = client.models.generate_content(
                model=_base.MODEL_NAME,
                contents=prompt + retry,
                config=types.GenerateContentConfig(
                    system_instruction=_base.SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_json_schema=_base._build_schema(),
                    temperature=0.85,
                ),
            )
            raw = getattr(response, "text", None)
            if not raw:
                raise RuntimeError("Gemini returned an empty riddle script.")
            data = _base._parse(raw)
            data.setdefault("next_short", {"topic": "riddle answer reveal", "teaser": "answer reveal"})
            original_boundary = _base._ensure_scene7_boundary
            original_bridge = _base._validate_natural_bridge
            _base._ensure_scene7_boundary = lambda narration, next_topic: _base._clean(narration)
            _base._validate_natural_bridge = lambda narration, next_topic: "riddle continuation"
            try:
                result = _base._normalize(data, topic, enforce_word_contract=False)
            finally:
                _base._ensure_scene7_boundary = original_boundary
                _base._validate_natural_bridge = original_bridge
            scenes = result.get("scene_plan") or []
            if len(scenes) != 7:
                raise RuntimeError("Riddle script must contain exactly 7 scenes.")
            total = sum(len(_base._words(s.get("narration", ""))) for s in scenes)
            if not MIN_WORDS <= total <= MAX_WORDS:
                raise RuntimeError(f"Riddle narration length {total} outside optimized {MIN_WORDS}-{MAX_WORDS} range.")
            for index, (low, high) in enumerate(SCENE_WORD_BUDGETS):
                count = len(_base._words(scenes[index].get("narration", "")))
                if count < low or count > high:
                    raise RuntimeError(f"Riddle Scene {index + 1} has {count} words; expected {low}-{high} for pacing.")

            previous_answer = ""
            previous_number = None
            import re as _re
            m = _re.search(r'Reveal Riddle #(\d+) answer naturally: "([^"]+)"', str(extra_feedback or ""), _re.I)
            if m:
                previous_number = int(m.group(1))
                previous_answer = _base._clean(m.group(2))
                first = scenes[0]
                first_narration = _base._clean(first.get("narration", ""))
                if previous_answer.lower() not in first_narration.lower():
                    reveal_line = f"Last answer: {previous_answer}. Did you get it? "
                    first["narration"] = _base._clean(reveal_line + first_narration)
                first_narration = _base._clean(scenes[0].get("narration", ""))
                if previous_answer.lower() not in first_narration.lower():
                    raise RuntimeError(f"Previous riddle answer must be revealed in Scene 1: {previous_answer!r}")
                total = sum(len(_base._words(s.get("narration", ""))) for s in scenes)
                if total > MAX_WORDS:
                    raise RuntimeError(f"Riddle narration length {total} outside optimized {MIN_WORDS}-{MAX_WORDS} range after reveal insertion.")

            print(f"🧩 Riddles Shorts narration validated: {total} words" + (f" + Riddle #{previous_number} answer revealed in Scene 1" if previous_answer else ""))
            return result
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            attempts += 1
            if attempts < _base.MAX_ATTEMPTS:
                print(f"⚠️ Riddle script attempt {attempts} rejected: {last_error}")
                time.sleep(2)
    raise RuntimeError(f"RIDDLE SCRIPT GENERATION FAILED after bounded retries. Last error: {last_error}")
