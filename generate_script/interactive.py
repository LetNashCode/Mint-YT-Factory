"""Narration-first Riddles Shorts generator."""
from __future__ import annotations
from . import entertainment as _base


def _feedback(extra=""):
    return (
        "RIDDLES SHORTS ONLY. This is an audio/narration-led puzzle, not a visual puzzle. "
        "The viewer must be able to solve the riddle with the phone face-down; stock visuals are atmosphere only and must never carry a required clue. "
        "Do not require a visual clue, visual inspection, on-screen text, or an object in the footage to solve the NEW riddle. "
        "A previous riddle answer may be revealed, but the NEW answer must remain locked. "
        "The ending must ask viewers to subscribe and follow for the NEW answer in the next Short; never say tomorrow, next day, or imply a fixed schedule. "
        "Narration length is flexible and must never be forced into the Publish Shorts word contract. "
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
Use this retention arc, while varying the actual wording and mechanic:
- Scene 1: immediate pattern-interrupt hook; if a previous answer exists, reveal it immediately and pivot without a greeting.
- Scene 2: state the new riddle clearly and quickly. The viewer should know exactly what they are solving by roughly the first few seconds.
- Scene 3: create a natural curiosity gap or obvious first interpretation. Use a spoken misdirection, not a visual clue.
- Scene 4: introduce a second interpretation, wording trap, assumption, or surprising angle without exposing the answer.
- Scene 5: make the viewer commit to an answer. Ask for the FIRST answer rather than giving another long clue.
- Scene 6: apply brief pressure and finish with a conversational 3…2…1 countdown. Never use a long 10-to-1 countdown.
- Scene 7: create the payoff gap. Do not reveal the NEW answer. Ask viewers to subscribe and follow for the answer in the next Short. Never mention tomorrow.

Choose narration mechanics such as wording trap, double meaning, obvious-answer trap, lateral thinking, expectation reversal, tiny logic mystery, misconception, or psychological trap. Do not force a mechanic that does not fit the riddle.
Keep every clue solvable from spoken words alone. Avoid visual-puzzle formats and avoid phrases like "look at this", "you can see", "notice the picture", or clues that depend on footage.
Do not reveal, spell out, strongly hint at, or explain the NEW answer. Do not accidentally leak it through examples or hypothetical guesses.
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
            if not 20 <= total <= 260:
                raise RuntimeError(f"Riddle narration length {total} outside flexible 20-260 range.")

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
                    reveal_line = (
                        f"Before today's challenge, here's the answer to Riddle #{previous_number}: "
                        f"{previous_answer}. Did you get it right? "
                    )
                    first["narration"] = _base._clean(reveal_line + first_narration)
                first_narration = _base._clean(scenes[0].get("narration", ""))
                if previous_answer.lower() not in first_narration.lower():
                    raise RuntimeError(f"Previous riddle answer must be revealed in Scene 1: {previous_answer!r}")
                total = sum(len(_base._words(s.get("narration", ""))) for s in scenes)
                if total > 260:
                    raise RuntimeError(f"Riddle narration length {total} outside flexible 20-260 range after reveal insertion.")

            print(
                f"🧩 Riddles Shorts narration validated: {total} words"
                + (f" + Riddle #{previous_number} answer revealed in Scene 1" if previous_answer else "")
            )
            return result
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            attempts += 1
            if attempts < _base.MAX_ATTEMPTS:
                print(f"⚠️ Riddle script attempt {attempts} rejected: {last_error}")
                time.sleep(2)
    raise RuntimeError(f"RIDDLE SCRIPT GENERATION FAILED after bounded retries. Last error: {last_error}")
