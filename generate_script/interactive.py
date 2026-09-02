"""Riddle Challenge script generator wrapper.

Interactive Mystery Shorts use the production generator's schema and visual
normalization, but deliberately disable the normal Publish Shorts continuation
bridge requirement for Scene 7.
"""
from __future__ import annotations

from . import entertainment as _base


def _interactive_feedback(extra_feedback=""):
    return (
        "INTERACTIVE MODE — CRITICAL ENDING RULE: This is a self-contained "
        "Interactive Mystery Short. Do NOT tease, mention, or bridge to another "
        "topic. Scene 7 must first deliver the payoff/reveal for the CURRENT "
        "scenario, then end with one short genuine question about the CURRENT "
        "dilemma that invites comments. No next video, next short, stay tuned, "
        "part 2, or subscribe language. "
        + " Narration length is flexible and must fit the riddle naturally; never pad or truncate merely to satisfy a fixed word count."
        + str(extra_feedback or "")
    )


def _validate_interactive_scene7(script):
    scenes = script.get("scene_plan") or []
    if len(scenes) != 7:
        raise RuntimeError("Riddle script must contain exactly 7 scenes.")

    narration = _base._clean(scenes[6].get("narration"))
    # The model occasionally writes the payoff and question as one sentence or
    # uses punctuation that _sentence_parts normalizes differently. Validate the
    # semantic contract without rejecting an otherwise usable generation.
    question_pos = narration.rfind("?")
    if question_pos < 0:
        # Recover deterministically instead of killing the entire production run
        # when Gemini omits terminal punctuation.
        narration = narration.rstrip(".! ") + " What would you choose?"
        question_pos = narration.rfind("?")

    question = narration[: question_pos + 1].split("?")[-2].strip() if narration.count("?") else ""
    payoff = narration[:question_pos].strip()
    if not payoff or len(payoff.split()) < 3:
        raise RuntimeError(
            "Interactive Scene 7 must contain a payoff before the viewer question."
        )

    # Require the final non-space character to be the question mark so captions
    # and the interactive ending remain deterministic.
    if narration.rstrip()[-1] != "?":
        narration = narration.rstrip(".! ") + " What would you choose?"

    banned = ("next short", "next video", "coming next", "stay tuned", "part 2")
    if any(term in narration.lower() for term in banned):
        raise RuntimeError("Interactive Scene 7 must not contain a continuation teaser.")

    script.pop("next_short", None)
    scenes[6]["narration"] = narration
    scenes[6]["subtitle_text"] = narration
    return script


def generate_script(topic, config, research=None, extra_feedback=""):
    """Riddles Shorts generator with an independent flexible word contract."""
    from google import genai
    from google.genai import types
    import time

    topic = _base._clean(topic)
    if not topic:
        raise RuntimeError("Riddle topic is empty.")

    client = genai.Client(api_key=_base._api_key())
    feedback = _interactive_feedback(extra_feedback)
    prompt = f"""
RIDDLES SHORTS MODE — NOT PUBLISH SHORTS.

CURRENT RIDDLE:
{topic}

Create exactly 7 scenes for an entertaining YouTube Riddle Short.
Narration length is flexible. NEVER target 90–135 words. Never pad or
truncate merely to satisfy a fixed word count.

Follow the supplied prior feedback exactly, including the locked answer and
previous-riddle reveal instructions. Never reveal or strongly hint at the NEW
riddle answer unless explicitly instructed to reveal a PREVIOUS riddle.

During the new riddle and countdown, visuals must show thinking, suspense,
curiosity, clocks, neutral clue-related imagery, or people reasoning — never
the new answer itself. Return the normal production JSON schema.

{feedback}
"""

    last_error = None
    transient_failures = 0
    validation_attempts = 0
    while validation_attempts < _base.MAX_ATTEMPTS:
        try:
            retry = f"\n\nFIX THE PREVIOUS VALIDATION ERROR:\n{last_error}" if last_error else ""
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
            # Satisfy the shared schema without using a real Publish Shorts bridge.
            data.setdefault("next_short", {"topic": "riddle continuation", "teaser": "riddle continuation"})

            original_boundary = _base._ensure_scene7_boundary
            original_bridge = _base._validate_natural_bridge
            _base._ensure_scene7_boundary = lambda narration, next_topic: _base._clean(narration)
            _base._validate_natural_bridge = lambda narration, next_topic: "riddle-ending"
            try:
                result = _base._normalize(data, topic)
            finally:
                _base._ensure_scene7_boundary = original_boundary
                _base._validate_natural_bridge = original_bridge

            result = _validate_interactive_scene7(result)
            total_words = sum(
                len(_base._words(scene.get("narration", "")))
                for scene in (result.get("scene_plan") or [])
            )
            if 20 <= total_words <= 260:
                print(f"🧩 Riddles Shorts narration validated: {total_words} words")
                return result
            raise RuntimeError(
                f"Riddle narration length is {total_words} words; flexible range is 20–260."
            )

        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
            transient = (
                _base._is_quota_error(last_error)
                or "503" in last_error
                or "unavailable" in last_error.lower()
                or "high demand" in last_error.lower()
            )
            if transient:
                if transient_failures >= _base.TRANSIENT_RETRIES:
                    break
                delay = _base.TRANSIENT_BACKOFF_SECONDS[
                    min(transient_failures, len(_base.TRANSIENT_BACKOFF_SECONDS) - 1)
                ]
                transient_failures += 1
                print(
                    f"⏳ Gemini transient failure; retry "
                    f"{transient_failures}/{_base.TRANSIENT_RETRIES} in {delay}s"
                )
                time.sleep(delay)
                continue

            validation_attempts += 1
            if validation_attempts < _base.MAX_ATTEMPTS:
                print(f"⚠️ Riddle script attempt {validation_attempts} rejected: {last_error}")
                time.sleep(2)

    raise RuntimeError(
        f"RIDDLE SCRIPT GENERATION FAILED after bounded retries. Last error: {last_error}"
    )
