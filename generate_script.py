"""
generate_script.py

Mint-YT-Factory
Version 6.1

Production format:
    7 scenes
    3 visuals per scene
    21 images per Short
    45 seconds

Main improvements:
- Short, specific narration-driven image prompts
- Exactly 7 scenes
- Exactly 3 visuals per scene
- Exactly 21 visuals
- Exactly 45 seconds
- Automatic caption repair
- Automatic visual metadata repair
- No hero-scene limitation
- Final scene automatically repaired
- Better Gemini retry handling
- Compatible with existing main.py
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

VISUALS_PER_SCENE = 3
TOTAL_VISUALS = 21

STANDARD_SCENE_DURATIONS = [
    3,
    5,
    7,
    7,
    8,
    8,
    7,
]


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
# BEAT TABLE
# ==========================================================================

BEAT_TABLE = """
1. HOOK (0-3s)
   Start with the most surprising fact, consequence, or visual.
   Never start with a question.

2. QUESTION (3-8s)
   Create a curiosity gap that makes the viewer need the explanation.

3. EXPLANATION (8-15s)
   Explain the core mechanism simply.

4. EXAMPLE (15-22s)
   Make the mechanism concrete and visual.

5. MIND-BLOWING (22-30s)
   Reveal a deeper implication that changes how the viewer sees
   the original idea.

6. ESCALATION (30-38s)
   Add one final consequence, comparison, or perspective shift.

7. ENDING (38-45s)
   Finish with a memorable scientific insight.
   No summary.
   No "thanks for watching."
   No generic motivational line.
"""


# ==========================================================================
# SYSTEM PROMPT
# ==========================================================================

def build_system_prompt(
    scene_count=DEFAULT_SCENE_COUNT,
    target_seconds=DEFAULT_TARGET_SECONDS,
):

    return f"""
You are an expert educational YouTube Shorts writer and visual director.

Create one original educational Short about the supplied topic.

======================================================================
HARD PRODUCTION FORMAT
======================================================================

Exactly {scene_count} scenes.

Exactly 3 visuals inside EVERY scene.

Exactly 21 visuals total.

Exactly 45 seconds.

Scene durations:

Scene 1 = 3 seconds
Scene 2 = 5 seconds
Scene 3 = 7 seconds
Scene 4 = 7 seconds
Scene 5 = 8 seconds
Scene 6 = 8 seconds
Scene 7 = 7 seconds

Total = exactly 45 seconds.

======================================================================
STORY STRUCTURE
======================================================================

{BEAT_TABLE}

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

All scenes should share the same visual identity.

======================================================================
EXACTLY 3 VISUALS PER SCENE
======================================================================

Visual 1:

Show the first important idea, action, subject, or state expressed
by the narration.

Visual 2:

Show a DIFFERENT visual moment, angle, scale, detail, or state
corresponding to another part of the narration.

Visual 3:

Show the consequence, mechanism, reaction, comparison, environment,
or visual payoff of the narration.

Never make three nearly identical shots.

The three shots must follow the narration in logical order.

They should feel like consecutive documentary shots from the
same production.

======================================================================
IMAGE PROMPTS
======================================================================

Each image_prompt must be SHORT and SPECIFIC.

Target approximately 20-40 words.

Use this structure:

MAIN SUBJECT + ACTION/STATE + ENVIRONMENT +
CAMERA/COMPOSITION + KEY VISUAL DETAIL

Good:

"Human eye receiving incoming light, microscopic retina activating,
neural cells beginning to fire, realistic biological detail, dark
scientific environment, cinematic macro view."

Bad:

"Beautiful scientific image of the brain."

Write ONLY what should be visible.

The image prompt must directly visualize the corresponding part
of the scene narration.

Do NOT explain the science inside the image prompt.

Do NOT mention:

YouTube
narration
audio
subtitles
viewers
AI
image generation
prompt quality

No text.

No labels.

No captions.

No logos.

No watermarks.

Each image must communicate ONE clear visual idea.

======================================================================
FINAL SCENE
======================================================================

Scene 7 MUST represent the ending.

Its transition will be automatically normalized by the pipeline
to "none" if Gemini returns another value.

======================================================================
OUTPUT
======================================================================

Return ONLY valid JSON.

No markdown.

No code fences.

No explanation.

The scene_plan must contain exactly 7 scenes.

Every scene must contain exactly 3 visuals.

Total visuals must be exactly 21.
"""


# ==========================================================================
# USER PROMPT
# ==========================================================================

def build_user_prompt(topic, config):

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
45 seconds

SCENE COUNT:
7

VISUALS PER SCENE:
3

TOTAL VISUALS:
21

Create the complete production storyboard.

Every visual must correspond to a distinct part, action, state,
detail, mechanism, consequence, or payoff in its scene narration.

The three visuals in each scene must NOT repeat the same composition.

Keep every image_prompt short and specific.

Return ONLY JSON.
"""


# ==========================================================================
# ENUM HELPER
# ==========================================================================

def _enum(values):
    return {
        "type": "string",
        "enum": list(values),
    }


# ==========================================================================
# RESPONSE SCHEMA
# ==========================================================================

def build_response_schema(scene_count=7):

    visual_schema = {
        "type": "object",

        "properties": {

            "segment": {
                "type": "integer",
            },

            "duration": {
                "type": "integer",
            },

            "camera": _enum(
                VALID_CAMERA
            ),

            "animation": _enum(
                VALID_ANIMATION
            ),

            "zoom_strength": _enum(
                VALID_ZOOM_STRENGTH
            ),

            "motion_intensity": _enum(
                VALID_MOTION_INTENSITY
            ),

            "visual_complexity": _enum(
                VALID_VISUAL_COMPLEXITY
            ),

            "image_style": _enum(
                VALID_IMAGE_STYLE
            ),

            "lighting": {
                "type": "string",
            },

            "color_palette": {
                "type": "string",
            },

            "overlay": {

                "type": "object",

                "properties": {

                    "type": _enum(
                        VALID_OVERLAY_TYPE
                    ),

                    "description": {
                        "type": "string",
                    },
                },

                "required": [
                    "type",
                    "description",
                ],
            },

            "image_prompt": {
                "type": "string",
            },

            "visual_impact": {
                "type": "integer",
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
                "type": "integer",
            },

            "purpose": _enum(
                VALID_PURPOSE
            ),

            "retention_purpose": _enum(
                VALID_RETENTION_PURPOSE
            ),

            "narration": {
                "type": "string",
            },

            "subtitle_text": {
                "type": "string",
            },

            "caption_highlights": {

                "type": "array",

                "items": {

                    "type": "object",

                    "properties": {

                        "word": {
                            "type": "string",
                        },

                        "emphasis": _enum(
                            VALID_EMPHASIS
                        ),
                    },

                    "required": [
                        "word",
                        "emphasis",
                    ],
                },
            },

            "subtitle_style": _enum(
                VALID_SUBTITLE_STYLE
            ),

            "emphasis_word": {
                "type": "string",
            },

            "duration": {
                "type": "integer",
            },

            "pause_after_ms": {
                "type": "integer",
            },

            "emotional_tone": _enum(
                VALID_EMOTIONAL_TONE
            ),

            "visual_priority": _enum(
                VALID_VISUAL_PRIORITY
            ),

            "transition": _enum(
                VALID_TRANSITION
            ),

            "sfx_cue": {

                "type": "object",

                "properties": {

                    "term": {
                        "type": "string",
                    },

                    "at_ms": {
                        "type": "integer",
                    },
                },

                "required": [
                    "term",
                    "at_ms",
                ],
            },

            "music_cue": _enum(
                VALID_MUSIC_CUE
            ),

            "confidence": _enum(
                VALID_CONFIDENCE
            ),

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
                "type": "string",
            },

            "description": {
                "type": "string",
            },

            "tags": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },

            "category": _enum(
                VALID_CATEGORY
            ),

            "thumbnail_prompt": {
                "type": "string",
            },

            "voice_style": {

                "type": "object",

                "properties": {

                    "tone": {
                        "type": "string",
                    },

                    "pace": _enum([
                        "slow",
                        "medium",
                        "fast",
                    ]),

                    "pitch": _enum([
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
                        "type": "string",
                    },

                    "arc": {
                        "type": "string",
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
                        "type": "string",
                    },

                    "palette": {
                        "type": "string",
                    },

                    "mood_arc": {
                        "type": "string",
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
                        "type": "integer",
                    },

                    "reason": {
                        "type": "string",
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

        data = json.loads(
            text
        )

        if isinstance(
            data,
            dict,
        ):
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

        data = json.loads(
            cleaned
        )

        if isinstance(
            data,
            dict,
        ):
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

            data = json.loads(
                candidate
            )

            if isinstance(
                data,
                dict,
            ):
                return data

        except json.JSONDecodeError as error:

            raise RuntimeError(
                f"Failed to parse Gemini JSON: {error}"
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

    mood = str(
        visual_identity.get(
            "mood_arc",
            "",
        )
    ).strip()

    parts = [
        value
        for value in (
            style,
            palette,
            mood,
        )
        if value
    ]

    if not parts:
        return ""

    return (
        "Consistent premium educational documentary "
        "visual identity: "
        + ", ".join(parts)
        + "."
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

    tokens = re.findall(
        r"\b[\w'-]+\b",
        subtitle,
    )

    if not tokens:

        raise RuntimeError(
            f"Scene {index} subtitle_text "
            "contains no usable words."
        )

    lookup = {
        token.lower(): token
        for token in tokens
    }

    repaired = []

    original = scene.get(
        "caption_highlights",
        [],
    )

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

    result = []

    seen = set()

    for item in repaired:

        key = item[
            "word"
        ].lower()

        if key not in seen:

            seen.add(key)

            result.append(
                item
            )

    if not result:

        candidates = sorted(
            tokens,
            key=len,
            reverse=True,
        )

        result = [{
            "word": candidates[0],
            "emphasis": "strong",
        }]

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

    visual[
        "segment"
    ] = visual_index

    defaults = {

        "camera":
            "medium",

        "animation":
            "zoom_in",

        "zoom_strength":
            "subtle",

        "motion_intensity":
            "medium",

        "visual_complexity":
            "moderate",

        "image_style":
            "realistic_3d_render",

        "lighting":
            "soft cinematic directional lighting "
            "with realistic depth",

        "color_palette":
            "cinematic neutral tones with subtle "
            "blue and warm highlights",

        "overlay": {
            "type": "none",
            "description": "",
        },

        "visual_impact":
            7,
    }

    for key, value in defaults.items():

        visual.setdefault(
            key,
            value,
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

        visual[
            "camera"
        ] = "medium"

    if visual[
        "animation"
    ] not in VALID_ANIMATION:

        visual[
            "animation"
        ] = "zoom_in"

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
            visual.get(
                "visual_impact",
                7,
            )
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
        visual.get(
            "image_prompt",
            "",
        )
    ).strip()

    if not visual[
        "image_prompt"
    ]:

        raise RuntimeError(
            f"Scene {scene_index} visual "
            f"{visual_index} has an empty "
            "image_prompt."
        )


# ==========================================================================
# IMAGE PROMPT ENHANCEMENT
# ==========================================================================

def _enhance_image_prompt(
    visual,
    style_lock,
):

    """
    Gemini creates the semantic image prompt.

    We only add minimal consistency information here.
    """

    prompt = str(
        visual[
            "image_prompt"
        ]
    ).strip()

    additions = []

    if visual.get(
        "camera"
    ):

        additions.append(
            f"{visual['camera']} composition"
        )

    if visual.get(
        "lighting"
    ):

        additions.append(
            visual[
                "lighting"
            ]
        )

    if visual.get(
        "color_palette"
    ):

        additions.append(
            f"{visual['color_palette']} color palette"
        )

    if style_lock:

        additions.append(
            style_lock
        )

    additions.extend([
        "vertical 9:16",
        "realistic",
        "no text",
        "no labels",
        "no logos",
        "no watermark",
    ])

    return (
        prompt
        + ", "
        + ", ".join(
            additions
        )
        + "."
    )


# ==========================================================================
# VISUAL DURATION ALLOCATION
# ==========================================================================

def _allocate_visual_durations(
    scene_duration,
):

    base = scene_duration // 3

    remainder = scene_duration % 3

    durations = [
        base,
        base,
        base,
    ]

    for index in range(
        remainder
    ):

        durations[
            index
        ] += 1

    return durations


# ==========================================================================
# COMPATIBILITY
# ==========================================================================

def _add_scene_visual_compatibility(
    scene,
    visual_identity,
):

    """
    Preserve compatibility with existing
    generate_images.py / main.py.
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
# VALIDATION
# ==========================================================================

def validate_script(
    script,
    expected_scene_count=7,
):

    required_top = [

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

    for key in required_top:

        if key not in script:

            raise RuntimeError(
                f"Missing required key: {key}"
            )

    scenes = script[
        "scene_plan"
    ]

    if not isinstance(
        scenes,
        list,
    ):

        raise RuntimeError(
            "scene_plan must be a list."
        )

    if len(scenes) != expected_scene_count:

        raise RuntimeError(
            f"Expected exactly "
            f"{expected_scene_count} scenes "
            f"but got {len(scenes)}."
        )

    style_lock = _build_style_lock(
        script[
            "visual_identity"
        ]
    )

    total_duration = 0

    total_visuals = 0

    hold_count = 0

    seed = random.randint(
        1,
        2_147_483_647,
    )

    # ======================================================================
    # EVERY SCENE
    # ======================================================================

    for index, scene in enumerate(
        scenes,
        start=1,
    ):

        if not isinstance(
            scene,
            dict,
        ):

            raise RuntimeError(
                f"Scene {index} is invalid."
            )

        required_scene = [

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

        for key in required_scene:

            if key not in scene:

                raise RuntimeError(
                    f"Scene {index} "
                    f"missing '{key}'."
                )

        # ------------------------------------------------------------------
        # SCENE NUMBER
        # ------------------------------------------------------------------

        try:

            scene_number = int(
                scene["scene"]
            )

        except Exception:

            raise RuntimeError(
                f"Scene {index} has invalid "
                "scene number."
            )

        if scene_number != index:

            raise RuntimeError(
                f"Scene {index} has scene "
                f"number {scene_number}."
            )

        # ------------------------------------------------------------------
        # ENUMS
        # ------------------------------------------------------------------

        _check_enum(
            scene["purpose"],
            VALID_PURPOSE,
            f"Scene {index} purpose",
        )

        _check_enum(
            scene["retention_purpose"],
            VALID_RETENTION_PURPOSE,
            f"Scene {index} retention_purpose",
        )

        _check_enum(
            scene["subtitle_style"],
            VALID_SUBTITLE_STYLE,
            f"Scene {index} subtitle_style",
        )

        _check_enum(
            scene["emotional_tone"],
            VALID_EMOTIONAL_TONE,
            f"Scene {index} emotional_tone",
        )

        _check_enum(
            scene["visual_priority"],
            VALID_VISUAL_PRIORITY,
            f"Scene {index} visual_priority",
        )

        _check_enum(
            scene["transition"],
            VALID_TRANSITION,
            f"Scene {index} transition",
        )

        _check_enum(
            scene["music_cue"],
            VALID_MUSIC_CUE,
            f"Scene {index} music_cue",
        )

        _check_enum(
            scene["confidence"],
            VALID_CONFIDENCE,
            f"Scene {index} confidence",
        )

        # ------------------------------------------------------------------
        # FINAL SCENE REPAIR
        # ------------------------------------------------------------------

        if index == expected_scene_count:

            # Do NOT fail the entire generation because Gemini
            # returned slightly incorrect metadata.

            scene[
                "purpose"
            ] = "ending"

            scene[
                "transition"
            ] = "none"

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
            scene.get(
                "emphasis_word",
                "",
            )
        ).strip()

        if not scene[
            "narration"
        ]:

            raise RuntimeError(
                f"Scene {index} narration "
                "is empty."
            )

        if not scene[
            "subtitle_text"
        ]:

            raise RuntimeError(
                f"Scene {index} subtitle_text "
                "is empty."
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
                f"Scene {index} duration "
                "is invalid."
            )

        expected_duration = (
            STANDARD_SCENE_DURATIONS[
                index - 1
            ]
        )

        if duration != expected_duration:

            raise RuntimeError(
                f"Scene {index} duration "
                f"must be {expected_duration}s "
                f"but Gemini returned "
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
            scene.get(
                "sfx_cue"
            ),
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
                f"Scene {index} visuals "
                "must be a list."
            )

        if len(visuals) != 3:

            raise RuntimeError(
                f"Scene {index} must contain "
                f"exactly 3 visuals but Gemini "
                f"returned {len(visuals)}."
            )

        visual_durations = (
            _allocate_visual_durations(
                duration
            )
        )

        visual_sum = 0

        # ------------------------------------------------------------------
        # EVERY VISUAL
        # ------------------------------------------------------------------

        for visual_index, visual in enumerate(
            visuals,
            start=1,
        ):

            if not isinstance(
                visual,
                dict,
            ):

                raise RuntimeError(
                    f"Scene {index} visual "
                    f"{visual_index} is invalid."
                )

            _repair_visual(
                visual,
                index,
                visual_index,
            )

            visual[
                "duration"
            ] = visual_durations[
                visual_index - 1
            ]

            visual_sum += visual[
                "duration"
            ]

            # --------------------------------------------------------------
            # EDITOR VALUES
            # --------------------------------------------------------------

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

            # --------------------------------------------------------------
            # LOW IMPACT FLAG
            # --------------------------------------------------------------

            visual[
                "needs_regeneration"
            ] = (
                visual[
                    "visual_impact"
                ] < 5
            )

            # --------------------------------------------------------------
            # PROMPT
            # --------------------------------------------------------------

            visual[
                "image_prompt"
            ] = _enhance_image_prompt(
                visual,
                style_lock,
            )

            if visual[
                "animation"
            ] == "hold":

                hold_count += 1

        if visual_sum != duration:

            raise RuntimeError(
                f"Scene {index} visual "
                f"durations sum to "
                f"{visual_sum}s but scene "
                f"duration is {duration}s."
            )

        total_visuals += 3

        # ------------------------------------------------------------------
        # COMPATIBILITY
        # ------------------------------------------------------------------

        _add_scene_visual_compatibility(
            scene,
            script[
                "visual_identity"
            ],
        )

    # ======================================================================
    # GLOBAL VALIDATION
    # ======================================================================

    if hold_count > 1:

        raise RuntimeError(
            f"'hold' animation used "
            f"{hold_count} times. "
            "Maximum is 1."
        )

    if total_duration != 45:

        raise RuntimeError(
            "Total duration must be exactly "
            f"45 seconds but is "
            f"{total_duration} seconds."
        )

    if total_visuals != 21:

        raise RuntimeError(
            "Total visuals must be exactly "
            f"21 but is {total_visuals}."
        )

    # ======================================================================
    # TOP LEVEL NORMALIZATION
    # ======================================================================

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

    script[
        "tags"
    ] = list(
        dict.fromkeys(
            script[
                "tags"
            ]
        )
    )[:12]

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
            "Vertical 9:16. "
            "No text, no logo, no watermark."
        )

    # ======================================================================
    # PIPELINE METADATA
    # ======================================================================

    script[
        "image_generation"
    ] = {

        "seed":
            seed,

        "style_lock":
            style_lock,

        "images_per_scene":
            3,

        "total_images":
            21,
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
    ].update({

        "format":
            "short_form",

        "scene_count":
            7,

        "target_duration_seconds":
            45,

        "actual_duration_seconds":
            45,

        "visuals_per_scene":
            3,

        "total_visuals":
            21,
    })

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
            "GEMINI_API_KEY environment "
            "variable is missing."
        )

    client = genai.Client(
        api_key=api_key
    )

    # Force production format.
    scene_count = 7
    target_seconds = 45

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
        "Scenes: 7"
    )

    print(
        "Visuals per scene: 3"
    )

    print(
        "TOTAL IMAGES: 21"
    )

    print(
        "Target: 45s"
    )

    print(
        topic
    )

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

The previous storyboard failed validation.

Previous error:

{last_error}

Return the COMPLETE storyboard again.

Hard requirements:

- exactly 7 scenes
- exactly 3 visuals in EVERY scene
- exactly 21 visuals total
- exactly 45 seconds
- short, specific image prompts
- each visual must represent a different part of
  the scene narration
- final scene must be the ending

Return ONLY JSON.
"""

            # --------------------------------------------------------------
            # GEMINI REQUEST
            # --------------------------------------------------------------

            response = (
                client.models.generate_content(

                    model=MODEL_NAME,

                    contents=attempt_prompt,

                    config=(
                        types.GenerateContentConfig(

                            system_instruction=
                                system_prompt,

                            response_mime_type=
                                "application/json",

                            response_json_schema=
                                response_schema,
                        )
                    ),
                )
            )

            if not response.text:

                raise RuntimeError(
                    "Gemini returned an empty "
                    "response."
                )

            script = parse_gemini_json(
                response.text
            )

            # --------------------------------------------------------------
            # METADATA
            # --------------------------------------------------------------

            script[
                "topic"
            ] = topic

            script[
                "video_structure"
            ] = {

                "format":
                    "short_form",

                "scene_count":
                    7,

                "target_duration_seconds":
                    45,

                "visuals_per_scene":
                    3,

                "total_visuals":
                    21,
            }

            # --------------------------------------------------------------
            # VALIDATION
            # --------------------------------------------------------------

            script = validate_script(
                script,
                expected_scene_count=7,
            )

            # --------------------------------------------------------------
            # SUCCESS
            # --------------------------------------------------------------

            print("=" * 80)
            print(
                "✅ SCRIPT GENERATED AND VALIDATED"
            )
            print("=" * 80)

            print(
                "Scenes: 7"
            )

            print(
                "Images: 21"
            )

            print(
                "Duration: 45s"
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
                f"{type(error).__name__}: "
                f"{error}"
            )

            print("=" * 80)

            if (
                attempt
                < MAX_GENERATION_ATTEMPTS
            ):

                # Longer delay between retries.
                # Helps with Gemini 503 capacity errors.

                retry_delay = (
                    5 * attempt
                )

                print(
                    f"⏳ Retrying in "
                    f"{retry_delay} seconds..."
                )

                time.sleep(
                    retry_delay
                )

    raise RuntimeError(
        "Gemini failed to produce a valid "
        "21-image storyboard after "
        f"{MAX_GENERATION_ATTEMPTS} attempts. "
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

        print(
            "TOPIC"
        )

        print(
            topic
        )

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

        print(
            "SCRIPT VALID"
        )

        print("=" * 100)