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
        + str(extra_feedback or "")
    )


def _validate_interactive_scene7(script):
    scenes = script.get("scene_plan") or []
    if len(scenes) != 7:
        raise RuntimeError("Interactive script must contain exactly 7 scenes.")

    narration = _base._clean(scenes[6].get("narration"))
    sentences = _base._sentence_parts(narration)
    if len(sentences) < 2:
        raise RuntimeError(
            "Interactive Scene 7 must contain a payoff followed by a viewer question."
        )
    if "?" not in sentences[-1]:
        raise RuntimeError("Interactive Scene 7 must end with a genuine viewer question.")

    banned = ("next short", "next video", "coming next", "stay tuned", "part 2")
    if any(term in narration.lower() for term in banned):
        raise RuntimeError("Interactive Scene 7 must not contain a continuation teaser.")

    script.pop("next_short", None)
    scenes[6]["narration"] = narration
    scenes[6]["subtitle_text"] = narration
    return script


def generate_script(topic, config, research=None, extra_feedback=""):
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
        result = _base.generate_script(
            topic,
            config,
            research,
            extra_feedback=_interactive_feedback(extra_feedback),
        )
        return _validate_interactive_scene7(result)
    finally:
        _base._ensure_scene7_boundary = original_boundary
        _base._validate_natural_bridge = original_bridge
