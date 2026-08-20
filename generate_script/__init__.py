"""Compatibility wrapper for the Mint-YT-Factory story engine.

This wrapper keeps the existing generator intact while adding a stricter
creative contract for:
- current-topic identity
- narration-to-visual alignment
- fun, conversational storytelling
- cinematic visual direction instead of default scientific-diagram styling
- continuation-topic format
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re


_ROOT = Path(__file__).resolve().parent.parent
_ORIGINAL_PATH = _ROOT / "generate_script.py"

_spec = importlib.util.spec_from_file_location(
    "_mint_original_generate_script",
    _ORIGINAL_PATH,
)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load original generate_script module: {_ORIGINAL_PATH}")

_original = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_original)


_NEXT_TOPIC_CONTRACT = r"""

============================================================
NEXT SHORT TOPIC — HARD FORMAT CONTRACT
============================================================

next_short.topic must already be a complete observable curiosity question.
It MUST begin with exactly one of:

Why does ...
Why do ...
Why is ...
Why are ...
Why can ...
How does ...
How do ...
How is ...
How are ...
How can ...

It must describe ONE observable phenomenon, be specific and researchable,
naturally follow the CURRENT story, and contain no terminal punctuation.
"""


_CREATIVE_STORY_CONTRACT = r"""

============================================================
CREATIVE STORYTELLING — HARD CONTRACT
============================================================

This channel explains real science like a clever friend telling you a
weird story, NOT like a professor reading lecture notes.

The facts MUST remain evidence-bound, but the delivery should be:

- conversational
- playful
- curious
- vivid
- surprising
- slightly quirky when appropriate
- easy for a non-scientist to understand

Use everyday language first. If a technical term is necessary, translate it
immediately into a simple mental picture.

Prefer concrete scenes and human reactions:
"You step on it and your brain goes, wait... why does that feel wet?"

Avoid textbook openings and filler such as:
"This phenomenon occurs because..."
"Researchers have discovered that..."
"The scientific explanation is..."
"In this video we will explore..."

Do not stack facts. Build one story with a setup, surprise, explanation,
reveal and satisfying payoff.

Use short punchy sentences, varied rhythm, and occasional rhetorical
phrasing. Humor is allowed when it does not distort the science.

IMPORTANT: Fun does NOT mean inventing facts, fake quotes, fake experiments,
or unsupported mechanisms. Make the LANGUAGE fun, not the SCIENCE inaccurate.

============================================================
VISUAL STORYTELLING — HARD CONTRACT
============================================================

Every visual must show what the viewer is hearing at that moment.

IMAGE PROMPTS ARE NOT GENERIC MOOD BOARDS.

For every shot, explicitly visualize the concrete nouns, objects, actions,
changes, or comparisons contained in that scene's narration.

If the narration says sand, show sand.
If it says a bare foot steps on sand, show the foot stepping on sand.
If it says the grains rearrange, show grains rearranging.
If it says the surface looks dry but feels wet, show that visual contrast.

Do NOT replace the actual topic with an abstract scientific cousin merely
because the mechanism is scientific.

For example, if the story is about dry sand feeling wet, do NOT show:
- colloidal droplets
- laboratory films
- generic microscopic particles
- unrelated laboratory glassware
- generic capillary diagrams
unless the narration explicitly talks about those things.

Use cinematic photography, realistic 3D visualization, macro close-ups,
everyday environments, and playful visual metaphors when useful.
Scientific diagrams are allowed only when they are genuinely the clearest
way to depict something explicitly being explained.

The first visual of each scene should answer: "What am I looking at?"
The second should answer: "What changed or what should I notice now?"

============================================================
CURRENT TOPIC LOCK
============================================================

The CURRENT TOPIC is the story's identity.

The title, narration, and visuals must clearly remain about that topic.
Do not silently substitute a related phenomenon.

Every scene must remain visually connected to the current topic, either by
showing the real-world subject directly or by showing a clearly recognizable
mechanism that is explicitly described in the narration.

============================================================
VISUAL STYLE LOCK
============================================================

Prefer a cinematic, realistic, premium visual language.
Avoid making the whole Short look like a laboratory presentation.

Default visual feel:
cinematic realism + macro detail + natural environments + tactile textures
+ occasional realistic 3D visualization for invisible mechanisms.

Keep a coherent palette, but NEVER let palette/style instructions overpower
semantic relevance. A relevant ordinary-looking shot is better than a
beautiful but unrelated scientific illustration.
"""


_original_build_system_prompt = _original.build_system_prompt
_original_build_user_prompt = _original.build_user_prompt
_original_normalize_next_short = _original._normalize_next_short
_original_validate_script = _original.validate_script


def build_system_prompt():
    return (
        _original_build_system_prompt().rstrip()
        + "\n"
        + _CREATIVE_STORY_CONTRACT
        + "\n"
        + _NEXT_TOPIC_CONTRACT
    )


def build_user_prompt(topic, config, research):
    return (
        _original_build_user_prompt(topic, config, research).rstrip()
        + "\n"
        + _CREATIVE_STORY_CONTRACT
        + "\n"
        + _NEXT_TOPIC_CONTRACT
        + f"\n\nCURRENT TOPIC — DO NOT DRIFT:\n{topic}\n"
    )


def _normalize_next_short(script):
    _original_normalize_next_short(script)

    topic = str(script["next_short"]["topic"]).strip()

    if not re.match(
        r"^(why does|why do|why is|why are|why can|how does|how do|how is|how are|how can)\s+.+",
        topic,
        flags=re.IGNORECASE,
    ):
        raise RuntimeError(
            "next_short.topic must be a complete observable question "
            "starting with Why/How."
        )

    script["next_short"]["topic"] = topic.rstrip("?!.").strip()


def _meaningful_words(text):
    stop = {
        "why", "how", "does", "do", "is", "are", "can", "the", "a", "an",
        "and", "or", "to", "of", "in", "on", "at", "for", "with", "from",
        "when", "you", "your", "it", "this", "that", "they", "their", "than",
        "then", "what", "why", "sometimes", "suddenly", "really", "very", "just",
        "some", "one", "thing", "things", "like", "into", "because", "while",
    }
    return {
        w for w in re.findall(r"[a-z0-9]+", str(text or "").lower())
        if len(w) >= 4 and w not in stop
    }


def _topic_anchor_words(topic, research):
    topic_words = _meaningful_words(topic)
    vocabulary = research.get("research_vocabulary", {}) if isinstance(research, dict) else {}
    if isinstance(vocabulary, dict):
        for key in ("subject", "phenomenon"):
            values = vocabulary.get(key, [])
            if isinstance(values, list):
                for value in values[:5]:
                    topic_words.update(_meaningful_words(value))
    return topic_words


def _overlap_score(a, b):
    left = _meaningful_words(a)
    right = _meaningful_words(b)
    if not left or not right:
        return 0
    return len(left & right)


def _visual_style_for_scene(scene_index, purpose):
    if scene_index in (1, 2, 4, 7):
        return "cinematic_photograph"
    if purpose in {"example", "hook", "ending"}:
        return "cinematic_photograph"
    if scene_index in (3, 5, 6):
        return "realistic_3d_render"
    return "macro_photography"


def _repair_creative_visuals(script, topic, research):
    """Normalize visual direction without changing the semantic prompt."""
    identity = script.get("visual_identity")
    if not isinstance(identity, dict):
        identity = {}

    identity["style"] = (
        "cinematic realistic visual storytelling with tactile macro detail "
        "and realistic 3D only for invisible mechanisms"
    )
    identity["palette"] = (
        "natural cinematic colors, warm neutrals, believable real-world textures"
    )
    identity["mood_arc"] = (
        "curiosity, playful surprise, discovery, escalating wonder, satisfying payoff"
    )
    script["visual_identity"] = identity

    anchors = _topic_anchor_words(topic, research)
    scenes = script.get("scene_plan", [])

    for scene_index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        narration = str(scene.get("narration", ""))
        visuals = scene.get("visuals", [])
        if not isinstance(visuals, list):
            continue

        for visual in visuals:
            if not isinstance(visual, dict):
                continue

            # Stop the model's style metadata from turning the whole video into
            # a laboratory slideshow. The actual image_prompt remains intact.
            visual["image_style"] = _visual_style_for_scene(
                scene_index,
                scene.get("purpose", ""),
            )

            visual["lighting"] = (
                "natural cinematic lighting with clear subject separation"
            )

            visual["color_palette"] = (
                "natural warm neutrals with realistic tactile detail"
            )

            prompt = str(visual.get("image_prompt", ""))
            visual["image_prompt"] = re.sub(r"\s+", " ", prompt).strip()

        # At least one shot in every scene must visibly anchor the current topic.
        combined_visuals = " ".join(
            str(v.get("image_prompt", "")) for v in visuals if isinstance(v, dict)
        )
        if anchors and not any(word in _meaningful_words(combined_visuals) for word in anchors):
            raise RuntimeError(
                f"VISUAL TOPIC DRIFT: Scene {scene_index} visuals do not contain "
                "a recognizable anchor from the current topic."
            )

        # The visuals must share concrete language with what is being spoken.
        if _overlap_score(narration, combined_visuals) < 2:
            raise RuntimeError(
                f"VISUAL NARRATION MISMATCH: Scene {scene_index} image prompts "
                "do not visibly represent enough of the spoken content."
            )


def validate_script(script, verified_research):
    result = _original_validate_script(script, verified_research)

    topic = str(script.get("topic", "")).strip()
    if not topic:
        raise RuntimeError("CURRENT TOPIC LOCK FAILED: topic is empty.")

    scenes = script.get("scene_plan", [])
    narration = " ".join(
        str(scene.get("narration", ""))
        for scene in scenes
        if isinstance(scene, dict)
    )

    topic_words = _meaningful_words(topic)
    story_words = _meaningful_words(narration)

    if topic_words and len(topic_words & story_words) < min(2, len(topic_words)):
        raise RuntimeError(
            "CURRENT TOPIC DRIFT: narration does not clearly identify the "
            "current topic."
        )

    title = str(script.get("title", ""))
    if topic_words and len(topic_words & _meaningful_words(title)) < 1:
        raise RuntimeError(
            "CURRENT TOPIC DRIFT: title does not clearly identify the current topic."
        )

    # Reject generic laboratory visuals when the narration is about an everyday
    # phenomenon. The retry gets the complete creative contract again.
    lab_words = _meaningful_words(
        "colloidal droplet colloidal film laboratory glassware meniscus drying film"
    )
    if any(
        word in _meaningful_words(narration)
        for word in lab_words
    ) is False:
        for scene_index, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict):
                continue
            for visual in scene.get("visuals", []):
                if not isinstance(visual, dict):
                    continue
                prompt_words = _meaningful_words(visual.get("image_prompt", ""))
                if len(prompt_words & lab_words) >= 2 and len(prompt_words & topic_words) == 0:
                    raise RuntimeError(
                        f"VISUAL TOPIC DRIFT: Scene {scene_index} contains a laboratory "
                        "visual unrelated to the current everyday topic."
                    )

    _repair_creative_visuals(script, topic, verified_research)

    # The narration remains the source of truth for captions.
    for scene in scenes:
        if isinstance(scene, dict):
            scene["subtitle_text"] = scene.get("narration", "")

    script.setdefault("publishing", {})["fun_conversational_storytelling"] = True
    script["publishing"]["semantic_visual_alignment_required"] = True
    script["publishing"]["cinematic_visual_direction"] = True

    return result


# Patch the ORIGINAL module's globals because generate_script() executes
# inside that module namespace.
_original.build_system_prompt = build_system_prompt
_original.build_user_prompt = build_user_prompt
_original._normalize_next_short = _normalize_next_short
_original.validate_script = validate_script


# Export the complete original API after patching its internal functions.
for _name, _value in vars(_original).items():
    if _name.startswith("__"):
        continue
    globals()[_name] = _value

globals()["build_system_prompt"] = build_system_prompt
globals()["build_user_prompt"] = build_user_prompt
globals()["validate_script"] = validate_script
