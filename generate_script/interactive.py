"""Interactive Mystery script generator wrapper.

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
        + " The COMPLETE narration must be 90–135 spoken words total. Aim for 105–120 words so normal variation stays inside the range. If a previous attempt was too short, expand the scenario with a concrete consequence, escalation, and payoff; never pad with filler."
        + str(extra_feedback or "")
    )


def _validate_interactive_scene7(script):
    scenes = script.get("scene_plan") or []
    if len(scenes) != 7:
        raise RuntimeError("Interactive script must contain exactly 7 scenes.")

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
    # Retry short/long interactive narrations instead of letting one bad model
    # response terminate the GitHub Actions workflow.
    max_length_attempts = 4
    last_error = None
    # entertainment._normalize normally enforces a next-topic bridge in Scene 7.
    # Patch only those continuation helpers during this call. The full production
    # schema/visual normalization still runs unchanged.
    original_boundary = _base._ensure_scene7_boundary
    original_bridge = _base._validate_natural_bridge

    def interactive_boundary(narration, next_topic):
        # Preserve the authored Scene 7 exactly; do not append a continuation.
        return _base._clean(narration)

    def interactive_bridge(narration, next_topic):
        # Scene 7 continuation validation is intentionally disabled for this mode.
        return "interactive-ending"

    _base._ensure_scene7_boundary = interactive_boundary
    _base._validate_natural_bridge = interactive_bridge
    try:
        for length_attempt in range(1, max_length_attempts + 1):
            feedback = _interactive_feedback(extra_feedback)
            if last_error:
                feedback += (
                    "\\n\\nREGENERATE THE ENTIRE SCRIPT. Previous attempt failed: "
                    + last_error
                    + " Keep exactly 7 scenes and produce 90–135 spoken words total."
                )
            try:
                result = _base.generate_script(
                    topic,
                    config,
                    research,
                    extra_feedback=feedback,
                )
                result = _validate_interactive_scene7(result)
                total_words = sum(
                    len(_base._words(scene.get("narration", "")))
                    for scene in (result.get("scene_plan") or [])
                )
                if 90 <= total_words <= 135:
                    print(f"🧩 Interactive narration validated: {total_words} words (attempt {length_attempt}/{max_length_attempts})")
                    return result
                last_error = (
                    f"Narration length is {total_words} words; target is 90–135 words."
                )
                print(f"⚠️ {last_error} Regenerating interactive script ({length_attempt}/{max_length_attempts})...")
            except RuntimeError as error:
                last_error = f"{type(error).__name__}: {error}"
                # Only retry generation/validation failures. Do not hide an
                # exhausted retry budget behind an immediate workflow crash.
                if length_attempt < max_length_attempts:
                    print(f"⚠️ Interactive script attempt {length_attempt} rejected: {last_error}")
                    continue
                raise
        raise RuntimeError(
            "Interactive script generation failed after "
            f"{max_length_attempts} length-validation attempts. Last error: {last_error}"
        )
    finally:
        _base._ensure_scene7_boundary = original_boundary
        _base._validate_natural_bridge = original_bridge
