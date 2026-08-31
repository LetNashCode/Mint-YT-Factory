"""Interactive Mystery script generator wrapper.

Keeps the existing Publish Shorts generator unchanged. Interactive Shorts use the
same visual/storyboard schema, but Scene 7 ends the current story with a payoff
and a comment-driving viewer question instead of requiring next_short continuity.
"""
from __future__ import annotations

from . import entertainment as _base


def _interactive_feedback(extra_feedback=""):
    return (
        "INTERACTIVE MODE OVERRIDE: This is an Interactive Mystery Short. "
        "Do not require, invent, or tease a next_short topic. Scene 7 must end "
        "the CURRENT scenario only: first give the payoff or reveal, then ask "
        "one short, genuine viewer question that invites a comment. The final "
        "question must concern the current dilemma, mystery, or psychological "
        "choice. No continuation bridge, no 'next video' language, and no "
        "subscribe CTA. "
        + str(extra_feedback or "")
    )


def _validate_interactive_scene7(script):
    scenes = script.get("scene_plan") or []
    if len(scenes) != 7:
        raise RuntimeError("Interactive script must contain exactly 7 scenes.")
    text = _base._clean(scenes[6].get("narration"))
    sentences = _base._sentence_parts(text)
    if len(sentences) < 2:
        raise RuntimeError("Interactive Scene 7 must contain a payoff followed by a viewer question.")
    if "?" not in sentences[-1]:
        raise RuntimeError("Interactive Scene 7 must end with a genuine viewer question.")
    banned = ("next short", "next video", "coming next", "stay tuned", "part 2")
    if any(x in text.lower() for x in banned):
        raise RuntimeError("Interactive Scene 7 must not contain a continuation teaser.")
    return script


def generate_script(topic, config, research=None, extra_feedback=""):
    # Reuse the proven generator for schema/visual generation, but temporarily
    # adapt its normalizer only for this call. Restore immediately so main
    # Publish Shorts behavior is untouched.
    original_normalize = _base._normalize

    def interactive_normalize(script, current_topic):
        if not isinstance(script, dict):
            raise RuntimeError("Gemini returned a non-object script.")

        # Give the base normalizer a valid continuation target solely to preserve
        # its schema handling, then replace Scene 7 after generation validation.
        # This fallback should rarely be needed because the prompt below requests
        # the interactive ending explicitly.
        result = original_normalize(script, current_topic)
        scene7 = result["scene_plan"][6]
        text = _base._clean(scene7.get("narration"))
        sentences = _base._sentence_parts(text)
        if len(sentences) >= 2:
            # Remove only a detected continuation sentence and keep authored payoff.
            last = sentences[-1]
            if _base._normalise_phrase(result.get("next_short", {}).get("topic", "")) in _base._normalise_phrase(last):
                sentences = sentences[:-1]
                payoff = _base._clean(" ".join(sentences)) or text
                question = "What would YOU choose?"
                scene7["narration"] = f"{payoff} {question}"
                scene7["subtitle_text"] = scene7["narration"]
        result.pop("next_short", None)
        return _validate_interactive_scene7(result)

    _base._normalize = interactive_normalize
    try:
        return _base.generate_script(
            topic,
            config,
            research,
            extra_feedback=_interactive_feedback(extra_feedback),
        )
    finally:
        _base._normalize = original_normalize
