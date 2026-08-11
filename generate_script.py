"""
generate_script.py

Educational YouTube Shorts Script Generator
Version 5.4

Major fixes:
- Simplified Gemini structured-output schema
- Uses Gemini 3.1 Flash-Lite correctly
- No temperature/top_p with structured output
- Exact 7-scene enforcement
- Exact 45-second standard timing
- Automatic retry with previous validation error
- Automatic caption-highlight repair
- Automatic visual-duration repair
- Automatic scene-level visual compatibility fields
- Strong visual prompt generation
- Consistent visual identity
- Safer science / consciousness / near-death handling
- Keeps existing main.py interface
"""

import json
import os
import random
import re
import time
import uuid

from google import genai
from google.genai import types


# ==========================================================================
# SETTINGS
# ==========================================================================

MODEL_NAME = "gemini-3.1-flash-lite"

MAX_GENERATION_ATTEMPTS = 4

DEFAULT_SCENE_COUNT = 7
DEFAULT_TARGET_SECONDS = 45

STANDARD_SCENE_DURATIONS = [
    3,
    5,
    7,
    7,
    8,
    8,
    7,
]

VISUAL_IMPACT_REGEN_THRESHOLD = 5


# ==========================================================================
# ENUMS
# ==========================================================================

VALID_PURPOSE = {
    "hook",
    "question",
    "explanation",
    "example",
    "mindblowing_fact",
    "ending",
}

VALID_RETENTION_PURPOSE = {
    "open_loop",
    "escalation",
    "payoff",
    "reframe",
    "curiosity_gap",
    "pattern_break",
    "emotional_release",
    "closure",
}

VALID_SUBTITLE_STYLE = {
    "bold_center",
    "kinetic_word_by_word",
    "lower_third",
    "minimal_clean",
}

VALID_EMPHASIS = {
    "strong",
    "light",
}

VALID_EMOTIONAL_TONE = {
    "curious",
    "tense",
    "calm",
    "awe",
    "playful",
    "urgent",
    "satisfied",
}

VALID_VISUAL_PRIORITY = {
    "hero",
    "supporting",
}

VALID_CAMERA = {
    "close_up",
    "medium",
    "wide",
    "macro",
    "top_down",
    "side",
    "aerial",
    "orbit",
}

VALID_ANIMATION = {
    "zoom_in",
    "zoom_out",
    "pan_left",
    "pan_right",
    "rotate",
    "parallax",
    "highlight",
    "hold",
}

VALID_ZOOM_STRENGTH = {
    "subtle",
    "medium",
    "strong",
}

VALID_MOTION_INTENSITY = {
    "low",
    "medium",
    "high",
}

VALID_VISUAL_COMPLEXITY = {
    "simple",
    "moderate",
    "complex",
}

VALID_IMAGE_STYLE = {
    "realistic_3d_render",
    "scientific_illustration",
    "cinematic_photograph",
    "macro_photography",
    "infographic_diagram",
}

VALID_OVERLAY_TYPE = {
    "none",
    "arrow",
    "icon",
    "diagram",
    "comparison_graphic",
}

VALID_TRANSITION = {
    "hard_cut",
    "whip_pan",
    "match_cut",
    "dissolve",
    "none",
}

VALID_MUSIC_CUE = {
    "intro",
    "build",
    "swell",
    "drop",
    "fade_out",
    "none",
}

VALID_CONFIDENCE = {
    "high",
    "qualitative_estimate",
}

VALID_CATEGORY = {
    "space",
    "physics",
    "biology",
    "chemistry",
    "technology",
    "engineering",
    "earth_science",
    "human_body",
    "psychology",
}


ZOOM_STRENGTH_TO_FACTOR = {
    "subtle": 1.06,
    "medium": 1.15,
    "strong": 1.30,
}


MOTION_INTENSITY_TO_SPEED = {
    "low": 0.5,
    "medium": 1.0,
    "high": 1.6,
}


# ==========================================================================
# REQUIRED STRUCTURE
# ==========================================================================

REQUIRED_KEYS = [
    "title",
    "description",
    "tags",
    "category",
    "thumbnail_prompt",
    "voice_style",
    "music",
    "visual_identity",
    "retention_self_check",
    "scene_plan",
]


REQUIRED_SCENE_KEYS = [
    "scene",
    "purpose",
    "retention_purpose",
    "narration",
    "subtitle_text",
    "caption_highlights",
    "subtitle_style",
    "emphasis_word",
    "duration",
    "pause_after_ms",
    "emotional_tone",
    "visual_priority",
    "transition",
    "sfx_cue",
    "music_cue",
    "confidence",
    "visuals",
]


REQUIRED_VISUAL_KEYS = [
    "segment",
    "duration",
    "camera",
    "animation",
    "zoom_strength",
    "motion_intensity",
    "visual_complexity",
    "image_style",
    "lighting",
    "color_palette",
    "overlay",
    "image_prompt",
    "visual_impact",
]


# ==========================================================================
# BEAT TABLE
# ==========================================================================

_SHORT_FORM_BEAT_TABLE = """
1. HOOK             (0-3s)
   Start with the most surprising fact, consequence, or visual.
   Never start with a question.

2. QUESTION         (3-8s)
   Create a curiosity gap that makes the viewer need the explanation.

3. EXPLANATION      (8-15s)
   Explain the core mechanism simply.

4. EXAMPLE          (15-22s)
   Make the mechanism concrete and visual.

5. MIND-BLOWING     (22-30s)
   Reveal a deeper implication that changes how the viewer sees
   the original idea.

6. ESCALATION       (30-38s)
   Add one final consequence, comparison, or perspective shift.

7. ENDING           (38-45s)
   Finish with a memorable scientific insight.
   No summary.
   No "thanks for watching."
   No generic motivational line.
"""


def _generate_beat_table(scene_count, target_seconds):

    if (
        scene_count == 7
        and target_seconds == 45
    ):
        return _SHORT_FORM_BEAT_TABLE

    per_scene = target_seconds / scene_count

    lines = []

    elapsed = 0

    for i in range(scene_count):

        if i == 0:
            purpose = "hook"

        elif i == 1:
            purpose = "question"

        elif i == scene_count - 1:
            purpose = "ending"

        else:
            middle = [
                "explanation",
                "example",
                "mindblowing_fact",
                "escalation",
            ]

            purpose = middle[
                (i - 2) % len(middle)
            ]

        start = int(elapsed)

        elapsed += per_scene

        end = int(elapsed)

        lines.append(
            f"{i + 1}. {purpose.upper()} ({start}-{end}s)"
        )

    return "\n".join(lines)


# ==========================================================================
# SYSTEM PROMPT
# ==========================================================================

def build_system_prompt(
    scene_count=DEFAULT_SCENE_COUNT,
    target_seconds=DEFAULT_TARGET_SECONDS,
):

    beat_table = _generate_beat_table(
        scene_count,
        target_seconds,
    )

    if (
        scene_count == 7
        and target_seconds == 45
    ):

        duration_instruction = """
EXACT TIMING:

Scene 1 = 3 seconds
Scene 2 = 5 seconds
Scene 3 = 7 seconds
Scene 4 = 7 seconds
Scene 5 = 8 seconds
Scene 6 = 8 seconds
Scene 7 = 7 seconds

Total = exactly 45 seconds.

These durations are mandatory.
"""

    else:

        duration_instruction = f"""
The total target duration is {target_seconds} seconds.
Each scene must be between 3 and 8 seconds.
"""

    return f"""
You are an expert educational YouTube Shorts writer and visual
director.

Create one original educational Short about the supplied topic.

The video contains EXACTLY {scene_count} scenes.

The target duration is {target_seconds} seconds.

======================================================================
STRUCTURE
======================================================================

{beat_table}

{duration_instruction}

======================================================================
SCENE COUNT
======================================================================

The scene_plan MUST contain exactly {scene_count} objects.

For 7 scenes:

1
2
3
4
5
6
7

Never return 6 scenes.
Never return 8 scenes.
Never combine scenes.

======================================================================
WRITING
======================================================================

Use Grade 6 reading level.

Use short, punchy sentences.

Start with a strong statement.

Never start with:

"Did you know..."

Never start with a question.

Never say:

"in this video"
"let's explore"
"today we're going to"

No listicles.

No countdowns.

No Top 5.

No generic motivation.

Teach ONE interesting phenomenon.

Every sentence must move the story forward.

======================================================================
ACCURACY
======================================================================

Only use scientifically defensible claims.

Do not invent statistics.

If an exact number is uncertain, avoid giving it.

Use qualitative language when appropriate.

If evidence is incomplete, say:

"Scientists have proposed..."
"One possible explanation is..."
"Researchers still debate..."

Do not turn hypotheses into facts.

======================================================================
BIOLOGY / CONSCIOUSNESS
======================================================================

Human biology and neuroscience are allowed.

Near-death experiences, consciousness, death and altered states
must be treated scientifically.

Never claim:

- near-death experiences prove an afterlife
- consciousness survives death
- supernatural explanations are proven
- the brain literally enters another world

Focus on neuroscience and physiology.

======================================================================
SAFETY
======================================================================

Never provide:

- medical diagnosis
- medical treatment
- medication instructions
- financial advice
- political persuasion
- religious persuasion
- dangerous challenges
- dangerous self-experimentation
- prolonged breath-holding instructions
- violence
- gore
- conspiracy theories presented as fact

Explain dangerous phenomena scientifically instead of encouraging
people to reproduce them.

======================================================================
VISUAL DIRECTION
======================================================================

The visual style must feel like a premium educational documentary.

Prefer:

- realistic scientific visualization
- cinematic 3D reconstruction
- macro photography
- realistic human environments
- scientifically accurate anatomy
- cinematic lighting
- strong depth
- dramatic scale
- clear subject
- simple composition

Avoid:

- generic AI art
- fantasy appearance
- cartoon appearance
- random objects
- excessive glowing effects
- abstract blobs
- unnecessary text
- fake labels
- watermarks
- logos

All scenes must share the same visual identity.

Each image must communicate one clear idea.

======================================================================
OUTPUT
======================================================================

Return ONLY valid JSON.

No markdown.

No code fences.

No explanation.

The JSON must contain:

title
description
tags
category
thumbnail_prompt
voice_style
music
visual_identity
retention_self_check
scene_plan

The scene_plan must contain exactly {scene_count} scenes.

======================================================================
SCENE FIELDS
======================================================================

Each scene must contain:

scene
purpose
retention_purpose
narration
subtitle_text
caption_highlights
subtitle_style
emphasis_word
duration
pause_after_ms
emotional_tone
visual_priority
transition
sfx_cue
music_cue
confidence
visuals

======================================================================
CAPTION HIGHLIGHTS
======================================================================

Every caption highlight word MUST appear literally inside
subtitle_text.

Do not use synonyms.

Use 1-3 highlights.

======================================================================
VISUALS
======================================================================

Each scene must contain 1 or 2 visuals.

Each visual must contain:

segment
duration
camera
animation
zoom_strength
motion_intensity
visual_complexity
image_style
lighting
color_palette
overlay
image_prompt
visual_impact

Each image_prompt must:

- describe exactly one visual
- identify the main subject
- describe the subject's state or action
- explain the environment
- describe camera composition
- describe lighting
- describe the visual style
- be suitable for vertical 9:16
- contain no text
- contain no labels
- contain no logos
- contain no watermark

Make image prompts concrete.

Do NOT write vague prompts such as:

"beautiful scientific image"

Instead describe exactly what the viewer should see.

======================================================================
FINAL SCENE
======================================================================

Scene {scene_count} must have:

purpose = "ending"

transition = "none"

======================================================================
VISUAL PRIORITY
======================================================================

Maximum 3 scenes may have:

visual_priority = "hero"

======================================================================
JSON
======================================================================

Return ONLY the JSON object.
"""


# ==========================================================================
# USER PROMPT
# ==========================================================================

def build_user_prompt(topic, config):

    scene_count = int(
        config["script"].get(
            "scene_count",
            DEFAULT_SCENE_COUNT,
        )
    )

    target_seconds = int(
        config["script"].get(
            "target_narration_seconds",
            DEFAULT_TARGET_SECONDS,
        )
    )

    return f"""
TOPIC:
{topic}

AUDIENCE:
{config["channel"]["audience"]}

TONE:
{config["channel"]["tone"]}

LANGUAGE:
{config["script"]["language"]}

TARGET LENGTH:
{target_seconds} seconds

SCENE COUNT:
{scene_count}

Create the complete production storyboard.

The output MUST contain exactly {scene_count} scenes.

For the standard format this means exactly:

Scene 1
Scene 2
Scene 3
Scene 4
Scene 5
Scene 6
Scene 7

Return ONLY JSON.
"""


# ==========================================================================
# GEMINI RESPONSE SCHEMA
# ==========================================================================

def _string_enum(values):

    return {
        "type": "string",
        "enum": list(values),
    }


def build_response_schema(scene_count):

    visual_schema = {
        "type": "object",

        "properties": {

            "segment": {
                "type": "integer"
            },

            "duration": {
                "type": "integer"
            },

            "camera": _string_enum([
                "close_up",
                "medium",
                "wide",
                "macro",
                "top_down",
                "side",
                "aerial",
                "orbit",
            ]),

            "animation": _string_enum([
                "zoom_in",
                "zoom_out",
                "pan_left",
                "pan_right",
                "rotate",
                "parallax",
                "highlight",
                "hold",
            ]),

            "zoom_strength": _string_enum([
                "subtle",
                "medium",
                "strong",
            ]),

            "motion_intensity": _string_enum([
                "low",
                "medium",
                "high",
            ]),

            "visual_complexity": _string_enum([
                "simple",
                "moderate",
                "complex",
            ]),

            "image_style": _string_enum([
                "realistic_3d_render",
                "scientific_illustration",
                "cinematic_photograph",
                "macro_photography",
                "infographic_diagram",
            ]),

            "lighting": {
                "type": "string"
            },

            "color_palette": {
                "type": "string"
            },

            "overlay": {
                "type": "object",

                "properties": {

                    "type": _string_enum([
                        "none",
                        "arrow",
                        "icon",
                        "diagram",
                        "comparison_graphic",
                    ]),

                    "description": {
                        "type": "string"
                    },
                },

                "required": [
                    "type",
                    "description",
                ],
            },

            "image_prompt": {
                "type": "string"
            },

            "visual_impact": {
                "type": "integer"
            },
        },

        "required": [
            "segment",
            "duration",
            "camera",
            "animation",
            "zoom_strength",
            "motion_intensity",
            "visual_complexity",
            "image_style",
            "lighting",
            "color_palette",
            "overlay",
            "image_prompt",
            "visual_impact",
        ],
    }

    scene_schema = {
        "type": "object",

        "properties": {

            "scene": {
                "type": "integer"
            },

            "purpose": _string_enum([
                "hook",
                "question",
                "explanation",
                "example",
                "mindblowing_fact",
                "ending",
            ]),

            "retention_purpose": _string_enum([
                "open_loop",
                "escalation",
                "payoff",
                "reframe",
                "curiosity_gap",
                "pattern_break",
                "emotional_release",
                "closure",
            ]),

            "narration": {
                "type": "string"
            },

            "subtitle_text": {
                "type": "string"
            },

            "caption_highlights": {
                "type": "array",

                "items": {
                    "type": "object",

                    "properties": {

                        "word": {
                            "type": "string"
                        },

                        "emphasis": _string_enum([
                            "strong",
                            "light",
                        ]),
                    },

                    "required": [
                        "word",
                        "emphasis",
                    ],
                },
            },

            "subtitle_style": _string_enum([
                "bold_center",
                "kinetic_word_by_word",
                "lower_third",
                "minimal_clean",
            ]),

            "emphasis_word": {
                "type": "string"
            },

            "duration": {
                "type": "integer"
            },

            "pause_after_ms": {
                "type": "integer"
            },

            "emotional_tone": _string_enum([
                "curious",
                "tense",
                "calm",
                "awe",
                "playful",
                "urgent",
                "satisfied",
            ]),

            "visual_priority": _string_enum([
                "hero",
                "supporting",
            ]),

            "transition": _string_enum([
                "hard_cut",
                "whip_pan",
                "match_cut",
                "dissolve",
                "none",
            ]),

            "sfx_cue": {
                "type": "object",

                "properties": {

                    "term": {
                        "type": "string"
                    },

                    "at_ms": {
                        "type": "integer"
                    },
                },

                "required": [
                    "term",
                    "at_ms",
                ],
            },

            "music_cue": _string_enum([
                "intro",
                "build",
                "swell",
                "drop",
                "fade_out",
                "none",
            ]),

            "confidence": _string_enum([
                "high",
                "qualitative_estimate",
            ]),

            "visuals": {
                "type": "array",
                "items": visual_schema,
            },
        },

        "required": [
            "scene",
            "purpose",
            "retention_purpose",
            "narration",
            "subtitle_text",
            "caption_highlights",
            "subtitle_style",
            "emphasis_word",
            "duration",
            "pause_after_ms",
            "emotional_tone",
            "visual_priority",
            "transition",
            "sfx_cue",
            "music_cue",
            "confidence",
            "visuals",
        ],
    }

    return {
        "type": "object",

        "properties": {

            "title": {
                "type": "string"
            },

            "description": {
                "type": "string"
            },

            "tags": {
                "type": "array",
                "items": {
                    "type": "string"
                },
            },

            "category": _string_enum([
                "space",
                "physics",
                "biology",
                "chemistry",
                "technology",
                "engineering",
                "earth_science",
                "human_body",
                "psychology",
            ]),

            "thumbnail_prompt": {
                "type": "string"
            },

            "voice_style": {
                "type": "object",

                "properties": {

                    "tone": {
                        "type": "string"
                    },

                    "pace": _string_enum([
                        "slow",
                        "medium",
                        "fast",
                    ]),

                    "pitch": _string_enum([
                        "low",
                        "medium",
                        "high",
                    ]),
                },

                "required": [
                    "tone",
                    "pace",
                    "pitch",
                ],
            },

            "music": {
                "type": "object",

                "properties": {

                    "search": {
                        "type": "string"
                    },

                    "arc": {
                        "type": "string"
                    },
                },

                "required": [
                    "search",
                    "arc",
                ],
            },

            "visual_identity": {
                "type": "object",

                "properties": {

                    "style": {
                        "type": "string"
                    },

                    "palette": {
                        "type": "string"
                    },

                    "mood_arc": {
                        "type": "string"
                    },
                },

                "required": [
                    "style",
                    "palette",
                    "mood_arc",
                ],
            },

            "retention_self_check": {
                "type": "object",

                "properties": {

                    "weakest_scene": {
                        "type": "integer"
                    },

                    "reason": {
                        "type": "string"
                    },
                },

                "required": [
                    "weakest_scene",
                    "reason",
                ],
            },

            "scene_plan": {
                "type": "array",
                "items": scene_schema,
            },
        },

        "required": [
            "title",
            "description",
            "tags",
            "category",
            "thumbnail_prompt",
            "voice_style",
            "music",
            "visual_identity",
            "retention_self_check",
            "scene_plan",
        ],
    }


# ==========================================================================
# JSON PARSER
# ==========================================================================

def parse_gemini_json(text):

    if not text:

        raise RuntimeError(
            "Gemini returned an empty response."
        )

    text = text.strip()

    try:

        data = json.loads(text)

        if not isinstance(data, dict):

            raise RuntimeError(
                "Gemini JSON response is not an object."
            )

        return data

    except json.JSONDecodeError:
        pass

    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
    ).strip()

    try:

        data = json.loads(cleaned)

        if not isinstance(data, dict):

            raise RuntimeError(
                "Gemini JSON response is not an object."
            )

        return data

    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start >= 0 and end > start:

        candidate = cleaned[
            start:end + 1
        ]

        candidate = re.sub(
            r",(\s*[}\]])",
            r"\1",
            candidate,
        )

        try:

            data = json.loads(candidate)

            if isinstance(data, dict):

                return data

        except json.JSONDecodeError as error:

            raise RuntimeError(
                "Failed to parse Gemini JSON: "
                f"{error}"
            )

    raise RuntimeError(
        "Gemini did not return valid JSON."
    )


# ==========================================================================
# HELPERS
# ==========================================================================

def _check_enum(
    value,
    allowed,
    label,
):

    if value not in allowed:

        raise RuntimeError(
            f"{label}: invalid value '{value}'. "
            f"Expected one of {sorted(allowed)}."
        )


def _slugify(text):

    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        str(text).lower(),
    ).strip("-")

    return slug[:40] or "video"


def _build_style_lock(
    visual_identity,
):

    style = str(
        visual_identity.get(
            "style",
            "",
        )
    ).strip()

    palette = str(
        visual_identity.get(
            "palette",
            "",
        )
    ).strip()

    if not style and not palette:

        return ""

    parts = []

    if style:
        parts.append(style)

    if palette:
        parts.append(
            f"color palette {palette}"
        )

    return (
        "Consistent premium educational documentary "
        "visual identity: "
        + ", ".join(parts)
        + "."
    )


def _word_tokens(text):

    return re.findall(
        r"\b[\w'-]+\b",
        str(text),
    )


# ==========================================================================
# CAPTION REPAIR
# ==========================================================================

def _repair_caption_highlights(
    scene,
    index,
):

    subtitle = str(
        scene.get(
            "subtitle_text",
            "",
        )
    ).strip()

    tokens = _word_tokens(
        subtitle
    )

    if not tokens:

        raise RuntimeError(
            f"Scene {index} subtitle_text contains no usable words."
        )

    lookup = {
        token.lower(): token
        for token in tokens
    }

    original = scene.get(
        "caption_highlights",
        [],
    )

    repaired = []

    if isinstance(
        original,
        list,
    ):

        for item in original:

            if not isinstance(
                item,
                dict,
            ):

                continue

            word = str(
                item.get(
                    "word",
                    "",
                )
            ).strip()

            emphasis = str(
                item.get(
                    "emphasis",
                    "strong",
                )
            ).strip()

            if (
                word.lower() in lookup
                and emphasis in VALID_EMPHASIS
            ):

                repaired.append({
                    "word": lookup[
                        word.lower()
                    ],
                    "emphasis": emphasis,
                })

    # Deduplicate.
    result = []

    seen = set()

    for item in repaired:

        key = item[
            "word"
        ].lower()

        if key not in seen:

            seen.add(key)

            result.append(item)

    # Fallback.
    if not result:

        # Prefer a meaningful longer word.
        candidates = sorted(
            tokens,
            key=lambda x: len(x),
            reverse=True,
        )

        result = [
            {
                "word": candidates[0],
                "emphasis": "strong",
            }
        ]

    scene[
        "caption_highlights"
    ] = result[:3]


# ==========================================================================
# VISUAL REPAIR
# ==========================================================================

def _repair_visual(
    visual,
    scene_index,
    visual_index,
):

    visual["segment"] = visual_index

    # Safe defaults.

    visual.setdefault(
        "camera",
        "medium",
    )

    visual.setdefault(
        "animation",
        "zoom_in",
    )

    visual.setdefault(
        "zoom_strength",
        "subtle",
    )

    visual.setdefault(
        "motion_intensity",
        "medium",
    )

    visual.setdefault(
        "visual_complexity",
        "moderate",
    )

    visual.setdefault(
        "image_style",
        "realistic_3d_render",
    )

    visual.setdefault(
        "lighting",
        "cinematic soft directional lighting with realistic depth",
    )

    visual.setdefault(
        "color_palette",
        "cinematic neutral tones with subtle blue and warm highlights",
    )

    visual.setdefault(
        "overlay",
        {
            "type": "none",
            "description": "",
        },
    )

    visual.setdefault(
        "image_prompt",
        "",
    )

    visual.setdefault(
        "visual_impact",
        7,
    )

    if not isinstance(
        visual["overlay"],
        dict,
    ):

        visual["overlay"] = {
            "type": "none",
            "description": "",
        }

    visual[
        "overlay"
    ].setdefault(
        "description",
        "",
    )

    if visual[
        "overlay"
    ].get(
        "type"
    ) not in VALID_OVERLAY_TYPE:

        visual[
            "overlay"
        ][
            "type"
        ] = "none"

    if visual[
        "camera"
    ] not in VALID_CAMERA:

        visual["camera"] = "medium"

    if visual[
        "animation"
    ] not in VALID_ANIMATION:

        visual["animation"] = "zoom_in"

    if visual[
        "zoom_strength"
    ] not in VALID_ZOOM_STRENGTH:

        visual[
            "zoom_strength"
        ] = "subtle"

    if visual[
        "motion_intensity"
    ] not in VALID_MOTION_INTENSITY:

        visual[
            "motion_intensity"
        ] = "medium"

    if visual[
        "visual_complexity"
    ] not in VALID_VISUAL_COMPLEXITY:

        visual[
            "visual_complexity"
        ] = "moderate"

    if visual[
        "image_style"
    ] not in VALID_IMAGE_STYLE:

        visual[
            "image_style"
        ] = "realistic_3d_render"

    try:

        impact = int(
            visual[
                "visual_impact"
            ]
        )

    except Exception:

        impact = 7

    visual[
        "visual_impact"
    ] = max(
        1,
        min(
            10,
            impact,
        ),
    )

    visual[
        "image_prompt"
    ] = str(
        visual[
            "image_prompt"
        ]
    ).strip()

    if not visual[
        "image_prompt"
    ]:

        raise RuntimeError(
            f"Scene {scene_index} visual "
            f"{visual_index} has an empty image_prompt."
        )


# ==========================================================================
# SCENE VISUAL COMPATIBILITY
# ==========================================================================

def _add_scene_visual_compatibility(
    scene,
    visual_identity,
):

    """
    Your current generate_images.py reads visual fields directly
    from scene instead of scene["visuals"].

    This copies the primary visual fields onto the scene so both
    architectures work.
    """

    visuals = scene.get(
        "visuals",
        [],
    )

    if not visuals:

        return

    primary = visuals[0]

    scene[
        "image_prompt"
    ] = primary.get(
        "image_prompt",
        "",
    )

    scene[
        "image_style"
    ] = primary.get(
        "image_style",
        "realistic_3d_render",
    )

    scene[
        "lighting"
    ] = primary.get(
        "lighting",
        "",
    )

    scene[
        "color_palette"
    ] = primary.get(
        "color_palette",
        "",
    )

    scene[
        "camera"
    ] = primary.get(
        "camera",
        "medium",
    )

    scene[
        "visual_role"
    ] = scene.get(
        "visual_priority",
        "supporting",
    )

    scene[
        "mood"
    ] = scene.get(
        "emotional_tone",
        "curious",
    )

    scene[
        "visual_identity"
    ] = (
        f"{visual_identity.get('style', '')}. "
        f"{visual_identity.get('palette', '')}. "
        f"{visual_identity.get('mood_arc', '')}"
    ).strip()


# ==========================================================================
# VISUAL PROMPT ENHANCEMENT
# ==========================================================================

def _enhance_image_prompt(
    scene,
    visual,
    style_lock,
):

    prompt = str(
        visual.get(
            "image_prompt",
            "",
        )
    ).strip()

    additions = [
        "Premium educational documentary visual.",
        "One clearly identifiable main subject.",
        "Realistic physical proportions.",
        "Natural material detail.",
        "Cinematic depth.",
        "Strong subject-background separation.",
        "Professional documentary photography or scientific visualization quality.",
        "Vertical 9:16 composition.",
        "No text.",
        "No labels.",
        "No logo.",
        "No watermark.",
    ]

    if visual.get("camera"):

        additions.append(
            f"Camera composition: {visual['camera']}."
        )

    if visual.get("lighting"):

        additions.append(
            f"Lighting: {visual['lighting']}."
        )

    if visual.get("color_palette"):

        additions.append(
            f"Color palette: {visual['color_palette']}."
        )

    if style_lock:

        additions.append(
            style_lock
        )

    additions.append(
        "The image must communicate the scientific idea immediately."
    )

    additions.append(
        "Avoid generic AI-art appearance, fantasy elements, "
        "unnecessary glowing effects, distorted anatomy, "
        "extra objects, duplicated subjects, and visual clutter."
    )

    return (
        prompt
        + " "
        + " ".join(additions)
    )


# ==========================================================================
# VALIDATOR
# ==========================================================================

def validate_script(
    script,
    expected_scene_count=DEFAULT_SCENE_COUNT,
):

    if not isinstance(
        script,
        dict,
    ):

        raise RuntimeError(
            "Gemini did not return a JSON object."
        )

    # ----------------------------------------------------------------------
    # REQUIRED TOP LEVEL
    # ----------------------------------------------------------------------

    for key in REQUIRED_KEYS:

        if key not in script:

            raise RuntimeError(
                f"Missing required key: {key}"
            )

    # ----------------------------------------------------------------------
    # TOP LEVEL OBJECTS
    # ----------------------------------------------------------------------

    for key in [
        "voice_style",
        "music",
        "visual_identity",
        "retention_self_check",
    ]:

        if not isinstance(
            script[key],
            dict,
        ):

            raise RuntimeError(
                f"{key} must be an object."
            )

    # ----------------------------------------------------------------------
    # SCENE PLAN
    # ----------------------------------------------------------------------

    scene_plan = script[
        "scene_plan"
    ]

    if not isinstance(
        scene_plan,
        list,
    ):

        raise RuntimeError(
            "scene_plan must be a list."
        )

    if len(scene_plan) != expected_scene_count:

        raise RuntimeError(
            f"Expected {expected_scene_count} scenes "
            f"but got {len(scene_plan)}."
        )

    # ----------------------------------------------------------------------
    # SEED / STYLE
    # ----------------------------------------------------------------------

    seed = random.randint(
        1,
        2_147_483_647,
    )

    style_lock = _build_style_lock(
        script[
            "visual_identity"
        ]
    )

    total_duration = 0

    hero_count = 0

    hold_count = 0

    # ----------------------------------------------------------------------
    # SCENES
    # ----------------------------------------------------------------------

    for index, scene in enumerate(
        scene_plan,
        start=1,
    ):

        if not isinstance(
            scene,
            dict,
        ):

            raise RuntimeError(
                f"Scene {index} is not an object."
            )

        # Required fields.
        for key in REQUIRED_SCENE_KEYS:

            if key not in scene:

                raise RuntimeError(
                    f"Scene {index} missing '{key}'."
                )

        # Scene number.
        try:

            scene_number = int(
                scene[
                    "scene"
                ]
            )

        except Exception:

            raise RuntimeError(
                f"Scene {index} has invalid scene number."
            )

        if scene_number != index:

            raise RuntimeError(
                f"Scene {index} has scene number "
                f"{scene_number}."
            )

        # Enums.
        _check_enum(
            scene[
                "purpose"
            ],
            VALID_PURPOSE,
            f"Scene {index} purpose",
        )

        _check_enum(
            scene[
                "retention_purpose"
            ],
            VALID_RETENTION_PURPOSE,
            f"Scene {index} retention_purpose",
        )

        _check_enum(
            scene[
                "subtitle_style"
            ],
            VALID_SUBTITLE_STYLE,
            f"Scene {index} subtitle_style",
        )

        _check_enum(
            scene[
                "emotional_tone"
            ],
            VALID_EMOTIONAL_TONE,
            f"Scene {index} emotional_tone",
        )

        _check_enum(
            scene[
                "visual_priority"
            ],
            VALID_VISUAL_PRIORITY,
            f"Scene {index} visual_priority",
        )

        _check_enum(
            scene[
                "transition"
            ],
            VALID_TRANSITION,
            f"Scene {index} transition",
        )

        _check_enum(
            scene[
                "music_cue"
            ],
            VALID_MUSIC_CUE,
            f"Scene {index} music_cue",
        )

        _check_enum(
            scene[
                "confidence"
            ],
            VALID_CONFIDENCE,
            f"Scene {index} confidence",
        )

        # Final scene.
        if index == expected_scene_count:

            if scene[
                "purpose"
            ] != "ending":

                raise RuntimeError(
                    "Final scene must have purpose='ending'."
                )

            if scene[
                "transition"
            ] != "none":

                raise RuntimeError(
                    "Final scene transition must be 'none'."
                )

        # Hero.
        if scene[
            "visual_priority"
        ] == "hero":

            hero_count += 1

        # ------------------------------------------------------------------
        # CAPTIONS
        # ------------------------------------------------------------------

        scene[
            "narration"
        ] = str(
            scene[
                "narration"
            ]
        ).strip()

        scene[
            "subtitle_text"
        ] = str(
            scene[
                "subtitle_text"
            ]
        ).strip()

        scene[
            "emphasis_word"
        ] = str(
            scene[
                "emphasis_word"
            ]
        ).strip()

        if not scene[
            "narration"
        ]:

            raise RuntimeError(
                f"Scene {index} narration is empty."
            )

        if not scene[
            "subtitle_text"
        ]:

            raise RuntimeError(
                f"Scene {index} subtitle_text is empty."
            )

        _repair_caption_highlights(
            scene,
            index,
        )

        # ------------------------------------------------------------------
        # DURATION
        # ------------------------------------------------------------------

        try:

            duration = int(
                scene[
                    "duration"
                ]
            )

        except Exception:

            raise RuntimeError(
                f"Scene {index} duration is invalid."
            )

        duration = max(
            3,
            min(
                8,
                duration,
            ),
        )

        if (
            expected_scene_count == 7
            and expected_scene_count == len(
                STANDARD_SCENE_DURATIONS
            )
        ):

            expected_duration = (
                STANDARD_SCENE_DURATIONS[
                    index - 1
                ]
            )

            if duration != expected_duration:

                raise RuntimeError(
                    f"Scene {index} duration must be "
                    f"{expected_duration}s but Gemini returned "
                    f"{duration}s."
                )

        scene[
            "duration"
        ] = duration

        total_duration += duration

        # ------------------------------------------------------------------
        # PAUSE
        # ------------------------------------------------------------------

        try:

            pause = int(
                scene.get(
                    "pause_after_ms",
                    0,
                )
            )

        except Exception:

            pause = 0

        scene[
            "pause_after_ms"
        ] = max(
            0,
            min(
                600,
                pause,
            ),
        )

        # ------------------------------------------------------------------
        # SFX
        # ------------------------------------------------------------------

        if not isinstance(
            scene[
                "sfx_cue"
            ],
            dict,
        ):

            scene[
                "sfx_cue"
            ] = {
                "term": "",
                "at_ms": 0,
            }

        scene[
            "sfx_cue"
        ].setdefault(
            "term",
            "",
        )

        try:

            sfx_at = int(
                scene[
                    "sfx_cue"
                ].get(
                    "at_ms",
                    0,
                )
            )

        except Exception:

            sfx_at = 0

        scene[
            "sfx_cue"
        ][
            "at_ms"
        ] = max(
            0,
            sfx_at,
        )

        # ------------------------------------------------------------------
        # VISUALS
        # ------------------------------------------------------------------

        visuals = scene[
            "visuals"
        ]

        if not isinstance(
            visuals,
            list,
        ):

            raise RuntimeError(
                f"Scene {index} visuals must be a list."
            )

        if not (
            1 <= len(visuals) <= 2
        ):

            raise RuntimeError(
                f"Scene {index} must have 1 or 2 visuals."
            )

        # If there are two visuals, split scene duration.
        if len(visuals) == 1:

            visual_durations = [
                duration
            ]

        else:

            first = max(
                2,
                duration // 2,
            )

            second = (
                duration - first
            )

            if second < 2:

                first = duration - 2
                second = 2

            visual_durations = [
                first,
                second,
            ]

        visuals_duration_sum = 0

        for v_index, visual in enumerate(
            visuals,
            start=1,
        ):

            if not isinstance(
                visual,
                dict,
            ):

                raise RuntimeError(
                    f"Scene {index} visual "
                    f"{v_index} is invalid."
                )

            # Allow missing optional visual metadata to be repaired.
            _repair_visual(
                visual,
                index,
                v_index,
            )

            # Force valid duration allocation.
            visual[
                "duration"
            ] = visual_durations[
                v_index - 1
            ]

            visuals_duration_sum += (
                visual[
                    "duration"
                ]
            )

            if visual[
                "animation"
            ] == "hold":

                hold_count += 1

                if (
                    index == 1
                    and v_index == 1
                ):

                    visual[
                        "animation"
                    ] = "zoom_in"

            # Concrete editor values.
            visual[
                "zoom_factor"
            ] = (
                ZOOM_STRENGTH_TO_FACTOR[
                    visual[
                        "zoom_strength"
                    ]
                ]
            )

            visual[
                "motion_speed"
            ] = (
                MOTION_INTENSITY_TO_SPEED[
                    visual[
                        "motion_intensity"
                    ]
                ]
            )

            visual[
                "needs_regeneration"
            ] = (
                scene[
                    "visual_priority"
                ] == "hero"
                and visual[
                    "visual_impact"
                ]
                < VISUAL_IMPACT_REGEN_THRESHOLD
            )

            # Enhance image prompt.
            visual[
                "image_prompt"
            ] = _enhance_image_prompt(
                scene,
                visual,
                style_lock,
            )

        if visuals_duration_sum != duration:

            raise RuntimeError(
                f"Scene {index} visual durations "
                f"sum to {visuals_duration_sum}s "
                f"but scene duration is {duration}s."
            )

        # ------------------------------------------------------------------
        # CURRENT GENERATE_IMAGES.PY COMPATIBILITY
        # ------------------------------------------------------------------

        _add_scene_visual_compatibility(
            scene,
            script[
                "visual_identity"
            ],
        )

    # ----------------------------------------------------------------------
    # GLOBAL RULES
    # ----------------------------------------------------------------------

    if hero_count > 3:

        raise RuntimeError(
            f"{hero_count} hero scenes detected. "
            "Maximum is 3."
        )

    if hold_count > 1:

        raise RuntimeError(
            f"'hold' animation used {hold_count} times. "
            "Maximum is 1."
        )

    # ----------------------------------------------------------------------
    # TOTAL DURATION
    # ----------------------------------------------------------------------

    target_seconds = int(
        script.get(
            "video_structure",
            {},
        ).get(
            "target_duration_seconds",
            DEFAULT_TARGET_SECONDS,
        )
    )

    if (
        expected_scene_count == 7
        and target_seconds == 45
    ):

        if total_duration != 45:

            raise RuntimeError(
                f"Total duration must be exactly 45 seconds "
                f"but is {total_duration} seconds."
            )

    # ----------------------------------------------------------------------
    # TOP LEVEL NORMALIZATION
    # ----------------------------------------------------------------------

    script[
        "title"
    ] = str(
        script[
            "title"
        ]
    ).strip()[:60]

    script[
        "description"
    ] = str(
        script[
            "description"
        ]
    ).strip()

    script[
        "tags"
    ] = [
        str(tag)
        .strip()
        .lower()
        for tag in script[
            "tags"
        ]
        if str(tag).strip()
    ]

    # Remove duplicate tags.
    script[
        "tags"
    ] = list(
        dict.fromkeys(
            script[
                "tags"
            ]
        )
    )

    script[
        "tags"
    ] = script[
        "tags"
    ][:12]

    category = str(
        script[
            "category"
        ]
    ).strip().lower()

    if category not in VALID_CATEGORY:

        category = "biology"

    script[
        "category"
    ] = category

    script[
        "thumbnail_prompt"
    ] = str(
        script[
            "thumbnail_prompt"
        ]
    ).strip()

    if style_lock:

        script[
            "thumbnail_prompt"
        ] = (
            f"{script['thumbnail_prompt']} "
            f"{style_lock}. "
            "Vertical 9:16. No text, no logo, no watermark."
        )

    # ----------------------------------------------------------------------
    # PIPELINE METADATA
    # ----------------------------------------------------------------------

    script[
        "image_generation"
    ] = {
        "seed": seed,
        "style_lock": style_lock,
    }

    script[
        "video_id"
    ] = (
        f"{_slugify(script['title'])}-"
        f"{uuid.uuid4().hex[:8]}"
    )

    script[
        "generated_at"
    ] = int(
        time.time()
    )

    script.setdefault(
        "video_structure",
        {},
    )

    script[
        "video_structure"
    ][
        "actual_duration_seconds"
    ] = total_duration

    script[
        "video_structure"
    ][
        "scene_count"
    ] = expected_scene_count

    script[
        "video_structure"
    ][
        "target_duration_seconds"
    ] = target_seconds

    return script


# ==========================================================================
# GENERATION
# ==========================================================================

def generate_script(
    topic,
    config,
):

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "GEMINI_API_KEY environment variable is missing."
        )

    client = genai.Client(
        api_key=api_key
    )

    scene_count = int(
        config[
            "script"
        ].get(
            "scene_count",
            DEFAULT_SCENE_COUNT,
        )
    )

    target_seconds = int(
        config[
            "script"
        ].get(
            "target_narration_seconds",
            DEFAULT_TARGET_SECONDS,
        )
    )

    prompt = build_user_prompt(
        topic,
        config,
    )

    system_prompt = build_system_prompt(
        scene_count,
        target_seconds,
    )

    response_schema = build_response_schema(
        scene_count
    )

    print("=" * 80)
    print("GENERATING SCRIPT")
    print("=" * 80)
    print(
        f"Model: {MODEL_NAME}"
    )
    print(
        f"Scenes: {scene_count}"
    )
    print(
        f"Target: {target_seconds}s"
    )
    print(topic)
    print("=" * 80)

    last_error = None

    for attempt in range(
        1,
        MAX_GENERATION_ATTEMPTS + 1,
    ):

        print(
            f"🧠 Gemini generation attempt "
            f"{attempt}/{MAX_GENERATION_ATTEMPTS}"
        )

        try:

            attempt_prompt = prompt

            # --------------------------------------------------------------
            # RETRY FEEDBACK
            # --------------------------------------------------------------

            if (
                attempt > 1
                and last_error
            ):

                attempt_prompt += f"""

IMPORTANT RETRY NOTICE

Your previous response failed validation.

Previous error:

{last_error}

Fix the problem.

Return the COMPLETE storyboard again.

Do not return only a correction.

The scene_plan MUST contain exactly {scene_count} scenes.

Return ONLY JSON.
"""

            # --------------------------------------------------------------
            # GEMINI REQUEST
            # --------------------------------------------------------------

            response = client.models.generate_content(

                model=MODEL_NAME,

                contents=attempt_prompt,

                config=types.GenerateContentConfig(

                    system_instruction=system_prompt,

                    response_mime_type="application/json",

                    response_json_schema=response_schema,

                ),
            )

            text = response.text

            if not text:

                raise RuntimeError(
                    "Gemini returned an empty response."
                )

            script = parse_gemini_json(
                text
            )

            # --------------------------------------------------------------
            # METADATA BEFORE VALIDATION
            # --------------------------------------------------------------

            script[
                "topic"
            ] = topic

            script[
                "video_structure"
            ] = {
                "format": (
                    "short_form"
                    if (
                        scene_count == 7
                        and target_seconds == 45
                    )
                    else "custom"
                ),
                "scene_count": scene_count,
                "target_duration_seconds": target_seconds,
            }

            # --------------------------------------------------------------
            # VALIDATE
            # --------------------------------------------------------------

            script = validate_script(
                script,
                expected_scene_count=scene_count,
            )

            print("=" * 80)
            print("✅ SCRIPT GENERATED AND VALIDATED")
            print("=" * 80)

            print(
                json.dumps(
                    script,
                    indent=2,
                    ensure_ascii=False,
                )
            )

            print("=" * 80)

            return script

        except Exception as error:

            last_error = error

            print("=" * 80)
            print(
                f"❌ GENERATION ATTEMPT "
                f"{attempt} FAILED"
            )
            print("=" * 80)
            print(
                f"{type(error).__name__}: {error}"
            )
            print("=" * 80)

            if attempt < MAX_GENERATION_ATTEMPTS:

                print(
                    "Retrying Gemini generation..."
                )

                time.sleep(2)

    raise RuntimeError(
        "Gemini failed to produce a valid storyboard "
        f"after {MAX_GENERATION_ATTEMPTS} attempts. "
        f"Last error: {last_error}"
    )


# ==========================================================================
# MANUAL TEST
# ==========================================================================

if __name__ == "__main__":

    import yaml

    with open(
        "config.yaml",
        "r",
        encoding="utf-8",
    ) as file:

        config = yaml.safe_load(
            file
        )

    test_topics = [

        "Why can't you tickle yourself",

        "Why do onions make you cry",

        "Why is space silent",

        "How WiFi finds your phone",

        "Why birds don't get electrocuted on power lines",

        "How airplanes fly",

        "Why the ocean is salty",
    ]

    for topic in test_topics:

        print("=" * 100)
        print("TOPIC")
        print(topic)
        print("=" * 100)

        result = generate_script(
            topic,
            config,
        )

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            )
        )

        print("=" * 100)
        print("SCRIPT VALID")
        print("=" * 100)