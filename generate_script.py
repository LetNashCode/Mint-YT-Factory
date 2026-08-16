"""
generate_script.py
Mint-YT-Factory
Version 7.0

Production:
- 7 scenes
- 2 visuals per scene
- 14 images total
- 45 seconds
- next-Short teaser + subscription strategy
- research source candidates for later verification
- semantic image prompts only; no provider/technical instructions
"""

import json
import os
import random
import re
import time
import uuid

from google import genai
from google.genai import types


MODEL_NAME = "gemini-3.1-flash-lite"
MAX_GENERATION_ATTEMPTS = 4

SCENE_COUNT = 7
TARGET_SECONDS = 45
VISUALS_PER_SCENE = 2
TOTAL_VISUALS = 14

SCENE_DURATIONS = [3, 5, 7, 7, 8, 8, 7]

VALID_PURPOSE = {
    "hook", "question", "explanation", "example",
    "mindblowing_fact", "ending"
}

VALID_RETENTION_PURPOSE = {
    "open_loop", "escalation", "payoff", "reframe",
    "curiosity_gap", "pattern_break", "emotional_release", "closure"
}

VALID_SUBTITLE_STYLE = {
    "bold_center", "kinetic_word_by_word", "lower_third", "minimal_clean"
}

VALID_EMPHASIS = {"strong", "light"}

VALID_EMOTIONAL_TONE = {
    "curious", "tense", "calm", "awe",
    "playful", "urgent", "satisfied"
}

VALID_VISUAL_PRIORITY = {"hero", "supporting"}

VALID_CAMERA = {
    "close_up", "medium", "wide", "macro",
    "top_down", "side", "aerial", "orbit"
}

VALID_ANIMATION = {
    "zoom_in", "zoom_out", "pan_left", "pan_right",
    "rotate", "parallax", "highlight", "hold"
}

VALID_ZOOM_STRENGTH = {"subtle", "medium", "strong"}
VALID_MOTION_INTENSITY = {"low", "medium", "high"}
VALID_VISUAL_COMPLEXITY = {"simple", "moderate", "complex"}

VALID_IMAGE_STYLE = {
    "realistic_3d_render", "scientific_illustration",
    "cinematic_photograph", "macro_photography",
    "infographic_diagram"
}

VALID_OVERLAY_TYPE = {
    "none", "arrow", "icon", "diagram", "comparison_graphic"
}

VALID_TRANSITION = {
    "hard_cut", "whip_pan", "match_cut", "dissolve", "none"
}

VALID_MUSIC_CUE = {
    "intro", "build", "swell", "drop", "fade_out", "none"
}

VALID_CONFIDENCE = {"high", "qualitative_estimate"}

VALID_CATEGORY = {
    "space", "physics", "biology", "chemistry", "technology",
    "engineering", "earth_science", "human_body", "psychology"
}

VALID_SOURCE_TYPE = {
    "paper", "journal", "university", "government",
    "research_institute", "textbook"
}

VALID_SOURCE_PRIORITY = {"primary", "secondary"}

ZOOM_FACTORS = {
    "subtle": 1.06,
    "medium": 1.15,
    "strong": 1.30
}

MOTION_SPEEDS = {
    "low": 0.5,
    "medium": 1.0,
    "high": 1.6
}


BEAT_TABLE = """
1. HOOK (0-3s)
   Start with the most surprising fact or consequence.
   Never start with a question.

2. CURIOSITY GAP (3-8s)
   Create an unanswered question that makes the viewer need the answer.

3. EXPLANATION (8-15s)
   Explain the core mechanism simply.

4. EXAMPLE (15-22s)
   Make the mechanism concrete and visual.

5. REFRAME (22-30s)
   Reveal an implication that changes how the viewer sees the idea.

6. ESCALATION (30-38s)
   Add one final consequence or perspective shift.

7. ENDING + NEXT SHORT (38-45s)
   Give a satisfying insight and naturally tease a closely related
   next Short. The next Short is the reason to return/subscribe.
"""


def build_system_prompt(
    scene_count=SCENE_COUNT,
    target_seconds=TARGET_SECONDS
):
    return f"""
You are an expert educational YouTube Shorts writer and visual director.

Create one original educational Short about the supplied topic.

HARD FORMAT:
- Exactly {scene_count} scenes.
- Exactly {VISUALS_PER_SCENE} visuals in every scene.
- Exactly {TOTAL_VISUALS} visuals total.
- Exactly {target_seconds} seconds.
- Scene durations: 3, 5, 7, 7, 8, 8, 7 seconds.

{BEAT_TABLE}

RETENTION:
- One connected story, not a list.
- Answer one curiosity gap while creating the next.
- The final scene must tease a specific, closely related next Short.
- Do not use generic "subscribe for more" language.
- The next Short should give viewers a concrete reason to return.

WRITING:
- Grade 6 reading level.
- Short, punchy sentences.
- Start with a strong statement, never a question.
- Never say "Did you know", "in this video", "let's explore", or
  "today we're going to".
- No listicles, countdowns, Top 5, or generic motivation.
- Teach one interesting phenomenon.

ACCURACY:
- Use scientifically defensible claims only.
- Do not invent statistics.
- If evidence is uncertain, use language such as "Scientists have
  proposed..." or "Researchers still debate..."
- Never turn hypotheses into facts.

BIOLOGY / CONSCIOUSNESS:
Treat consciousness, death, near-death experiences and altered states
scientifically. Never present supernatural explanations as proven.

SAFETY:
No diagnosis, treatment, medication instructions, dangerous
self-experimentation, political/religious persuasion, gore, violence,
or conspiracy theories presented as fact.

VISUALS:
- Exactly 2 visuals per scene.
- Each visual must represent a different part, action, state, detail,
  mechanism, consequence or payoff in the narration.
- The two shots should feel like consecutive documentary shots.
- Premium educational documentary style.
- Realistic science, accurate anatomy, cinematic environments, clear
  subjects and simple compositions.
- Avoid fantasy, cartoons, generic AI art, excessive glow, clutter,
  random objects, text, labels, logos and watermarks.

IMAGE PROMPTS:
- 15-35 words approximately.
- Describe ONLY what should be visible.
- Directly visualize the narration.
- One clear visual idea per prompt.
- No camera instructions.
- No lighting instructions.
- No aspect ratio instructions.
- No rendering instructions.
- No negative prompts.
- No mention of YouTube, narration, audio, subtitles, viewers, AI,
  image generation or prompt quality.

RESEARCH:
Provide 2-4 credible source candidates supporting important claims.
Prefer primary papers, peer-reviewed journals, universities, government
or research institutions.

Do not invent URLs, DOIs, titles or authors.

If unsure of a URL, leave it empty.

These are candidates and MUST be independently verified before publishing.

FINAL SCENE:
- purpose must be "ending".
- transition must be "none".
- narration must naturally contain the next-Short teaser.

Return ONLY valid JSON.
"""


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

Create the complete 45-second storyboard.

Production:
- 7 scenes
- 2 visuals per scene
- 14 visuals total

The final narration must naturally tell viewers what the next Short
will cover. Make the next topic closely related to this one.

Also provide 2-4 credible research source candidates supporting the
scientific claims. These will be verified before publication.

Keep every image_prompt short, specific and purely visual.

Return ONLY JSON.
"""


def _enum(values):
    return {
        "type": "string",
        "enum": list(values)
    }


def build_response_schema(scene_count=SCENE_COUNT):

    visual = {
        "type": "object",

        "properties": {

            "segment": {
                "type": "integer"
            },

            "duration": {
                "type": "integer"
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
                "type": "string"
            },

            "color_palette": {
                "type": "string"
            },

            "overlay": {

                "type": "object",

                "properties": {

                    "type": _enum(
                        VALID_OVERLAY_TYPE
                    ),

                    "description": {
                        "type": "string"
                    }
                },

                "required": [
                    "type",
                    "description"
                ]
            },

            "image_prompt": {
                "type": "string"
            },

            "visual_impact": {
                "type": "integer"
            }
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
            "visual_impact"
        ]
    }

    scene = {

        "type": "object",

        "properties": {

            "scene": {
                "type": "integer"
            },

            "purpose": _enum(
                VALID_PURPOSE
            ),

            "retention_purpose": _enum(
                VALID_RETENTION_PURPOSE
            ),

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

                        "emphasis": _enum(
                            VALID_EMPHASIS
                        )
                    },

                    "required": [
                        "word",
                        "emphasis"
                    ]
                }
            },

            "subtitle_style": _enum(
                VALID_SUBTITLE_STYLE
            ),

            "emphasis_word": {
                "type": "string"
            },

            "duration": {
                "type": "integer"
            },

            "pause_after_ms": {
                "type": "integer"
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
                        "type": "string"
                    },

                    "at_ms": {
                        "type": "integer"
                    }
                },

                "required": [
                    "term",
                    "at_ms"
                ]
            },

            "music_cue": _enum(
                VALID_MUSIC_CUE
            ),

            "confidence": _enum(
                VALID_CONFIDENCE
            ),

            "visuals": {

                "type": "array",

                "items": visual
            }
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
            "visuals"
        ]
    }

    source = {

        "type": "object",

        "properties": {

            "title": {
                "type": "string"
            },

            "authors": {
                "type": "string"
            },

            "organization": {
                "type": "string"
            },

            "url": {
                "type": "string"
            },

            "source_type": _enum(
                VALID_SOURCE_TYPE
            ),

            "priority": _enum(
                VALID_SOURCE_PRIORITY
            ),

            "claim_supported": {
                "type": "string"
            }
        },

        "required": [
            "title",
            "authors",
            "organization",
            "url",
            "source_type",
            "priority",
            "claim_supported"
        ]
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
                }
            },

            "category": _enum(
                VALID_CATEGORY
            ),

            "thumbnail_prompt": {
                "type": "string"
            },

            "voice_style": {

                "type": "object",

                "properties": {

                    "tone": {
                        "type": "string"
                    },

                    "pace": _enum([
                        "slow",
                        "medium",
                        "fast"
                    ]),

                    "pitch": _enum([
                        "low",
                        "medium",
                        "high"
                    ])
                },

                "required": [
                    "tone",
                    "pace",
                    "pitch"
                ]
            },

            "music": {

                "type": "object",

                "properties": {

                    "search": {
                        "type": "string"
                    },

                    "arc": {
                        "type": "string"
                    }
                },

                "required": [
                    "search",
                    "arc"
                ]
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
                    }
                },

                "required": [
                    "style",
                    "palette",
                    "mood_arc"
                ]
            },

            "retention_self_check": {

                "type": "object",

                "properties": {

                    "weakest_scene": {
                        "type": "integer"
                    },

                    "reason": {
                        "type": "string"
                    }
                },

                "required": [
                    "weakest_scene",
                    "reason"
                ]
            },

            "next_short": {

                "type": "object",

                "properties": {

                    "topic": {
                        "type": "string"
                    },

                    "teaser": {
                        "type": "string"
                    },

                    "why_viewers_should_return": {
                        "type": "string"
                    },

                    "subscription_cta": {
                        "type": "string"
                    }
                },

                "required": [
                    "topic",
                    "teaser",
                    "why_viewers_should_return",
                    "subscription_cta"
                ]
            },

            "research_sources": {

                "type": "array",

                "items": source
            },

            "scene_plan": {

                "type": "array",

                "items": scene
            }
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
            "next_short",
            "research_sources",
            "scene_plan"
        ]
    }


def parse_gemini_json(text):

    if not text:
        raise RuntimeError(
            "Gemini returned an empty response."
        )

    text = text.strip()

    try:

        data = json.loads(text)

        if isinstance(data, dict):
            return data

    except json.JSONDecodeError:
        pass

    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned
    ).strip()

    try:

        data = json.loads(cleaned)

        if isinstance(data, dict):
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
            candidate
        )

        try:

            data = json.loads(candidate)

            if isinstance(data, dict):
                return data

        except json.JSONDecodeError as error:

            raise RuntimeError(
                f"Failed to parse Gemini JSON: {error}"
            )

    raise RuntimeError(
        "Gemini did not return valid JSON."
    )


def _check_enum(
    value,
    allowed,
    label
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
        str(text).lower()
    ).strip("-")

    return slug[:40] or "video"


def _build_style_lock(
    identity
):

    parts = [

        str(
            identity.get(
                "style",
                ""
            )
        ).strip(),

        str(
            identity.get(
                "palette",
                ""
            )
        ).strip(),

        str(
            identity.get(
                "mood_arc",
                ""
            )
        ).strip()
    ]

    parts = [
        p for p in parts if p
    ]

    if not parts:
        return ""

    return (
        "Consistent visual identity: "
        + ", ".join(parts)
    )


def _repair_caption_highlights(
    scene,
    index
):

    subtitle = str(
        scene.get(
            "subtitle_text",
            ""
        )
    ).strip()

    tokens = re.findall(
        r"\b[\w'-]+\b",
        subtitle
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

    result = []

    for item in scene.get(
        "caption_highlights",
        []
    ):

        if not isinstance(
            item,
            dict
        ):
            continue

        word = str(
            item.get(
                "word",
                ""
            )
        ).strip()

        emphasis = str(
            item.get(
                "emphasis",
                "strong"
            )
        ).strip()

        if (
            word.lower() in lookup
            and emphasis in VALID_EMPHASIS
        ):

            existing = {
                x["word"].lower()
                for x in result
            }

            if word.lower() not in existing:

                result.append({
                    "word": lookup[
                        word.lower()
                    ],
                    "emphasis": emphasis
                })

    if not result:

        word = max(
            tokens,
            key=len
        )

        result = [{
            "word": word,
            "emphasis": "strong"
        }]

    scene[
        "caption_highlights"
    ] = result[:3]


def _repair_visual(
    visual,
    scene_index,
    visual_index
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
            "soft cinematic directional lighting",

        "color_palette":
            "cinematic natural tones",

        "overlay": {
            "type": "none",
            "description": ""
        },

        "visual_impact":
            7
    }

    for key, value in defaults.items():

        visual.setdefault(
            key,
            value
        )

    if not isinstance(
        visual["overlay"],
        dict
    ):

        visual[
            "overlay"
        ] = {
            "type": "none",
            "description": ""
        }

    visual[
        "overlay"
    ].setdefault(
        "description",
        ""
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
                7
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
            impact
        )
    )

    visual[
        "image_prompt"
    ] = _clean_image_prompt(
        visual
    )

    if not visual[
        "image_prompt"
    ]:

        raise RuntimeError(
            f"Scene {scene_index} visual "
            f"{visual_index} has an empty "
            "image_prompt."
        )


def _clean_image_prompt(
    visual
):

    """
    Keep ONLY the semantic visual description.

    No camera instructions.
    No lighting instructions.
    No aspect ratio.
    No rendering instructions.
    No negative prompts.
    """

    prompt = str(
        visual.get(
            "image_prompt",
            ""
        )
    ).strip()

    prompt = prompt.replace(
        "```",
        ""
    )

    prompt = re.sub(
        r"\s+",
        " ",
        prompt
    )

    return prompt.strip()


def _allocate_visual_durations(
    scene_duration
):

    base = (
        scene_duration
        // VISUALS_PER_SCENE
    )

    remainder = (
        scene_duration
        % VISUALS_PER_SCENE
    )

    durations = [
        base
    ] * VISUALS_PER_SCENE

    for i in range(
        remainder
    ):

        durations[i] += 1

    return durations


def _add_scene_visual_compatibility(
    scene,
    identity
):

    visuals = scene.get(
        "visuals",
        []
    )

    if not visuals:
        return

    primary = visuals[0]

    scene[
        "image_prompt"
    ] = primary.get(
        "image_prompt",
        ""
    )

    scene[
        "image_style"
    ] = primary.get(
        "image_style",
        "realistic_3d_render"
    )

    scene[
        "lighting"
    ] = primary.get(
        "lighting",
        ""
    )

    scene[
        "color_palette"
    ] = primary.get(
        "color_palette",
        ""
    )

    scene[
        "camera"
    ] = primary.get(
        "camera",
        "medium"
    )

    scene[
        "visual_role"
    ] = scene.get(
        "visual_priority",
        "supporting"
    )

    scene[
        "mood"
    ] = scene.get(
        "emotional_tone",
        "curious"
    )

    scene[
        "visual_identity"
    ] = (
        f"{identity.get('style', '')}. "
        f"{identity.get('palette', '')}. "
        f"{identity.get('mood_arc', '')}"
    ).strip()


def _normalize_next_short(
    script
):

    item = script.get(
        "next_short",
        {}
    )

    if not isinstance(
        item,
        dict
    ):

        item = {}

    topic = str(
        item.get(
            "topic",
            ""
        )
    ).strip()

    teaser = str(
        item.get(
            "teaser",
            ""
        )
    ).strip()

    reason = str(
        item.get(
            "why_viewers_should_return",
            ""
        )
    ).strip()

    cta = str(
        item.get(
            "subscription_cta",
            ""
        )
    ).strip()

    if not topic:

        raise RuntimeError(
            "next_short.topic is empty."
        )

    if not teaser:

        raise RuntimeError(
            "next_short.teaser is empty."
        )

    script[
        "next_short"
    ] = {

        "topic":
            topic[:150],

        "teaser":
            teaser[:220],

        "why_viewers_should_return":
            (
                reason or teaser
            )[:220],

        "subscription_cta":
            (
                cta
                or
                "Follow the channel so you don't miss the next part."
            )[:160]
    }


def _normalize_research_sources(
    script
):

    sources = script.get(
        "research_sources",
        []
    )

    if not isinstance(
        sources,
        list
    ):

        sources = []

    normalized = []

    for source in sources[:4]:

        if not isinstance(
            source,
            dict
        ):
            continue

        title = str(
            source.get(
                "title",
                ""
            )
        ).strip()

        claim = str(
            source.get(
                "claim_supported",
                ""
            )
        ).strip()

        if not title or not claim:
            continue

        source_type = str(
            source.get(
                "source_type",
                "journal"
            )
        ).strip()

        priority = str(
            source.get(
                "priority",
                "secondary"
            )
        ).strip()

        if source_type not in VALID_SOURCE_TYPE:
            source_type = "journal"

        if priority not in VALID_SOURCE_PRIORITY:
            priority = "secondary"

        normalized.append({

            "title":
                title[:250],

            "authors":
                str(
                    source.get(
                        "authors",
                        ""
                    )
                ).strip()[:300],

            "organization":
                str(
                    source.get(
                        "organization",
                        ""
                    )
                ).strip()[:200],

            "url":
                str(
                    source.get(
                        "url",
                        ""
                    )
                ).strip()[:500],

            "source_type":
                source_type,

            "priority":
                priority,

            "claim_supported":
                claim[:500],

            "verified":
                False
        })

    script[
        "research_sources"
    ] = normalized


def validate_script(
    script,
    expected_scene_count=SCENE_COUNT
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
        "next_short",
        "research_sources",
        "scene_plan"
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
        list
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
        2_147_483_647
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
        "visuals"
    ]

    for index, scene in enumerate(
        scenes,
        start=1
    ):

        if not isinstance(
            scene,
            dict
        ):

            raise RuntimeError(
                f"Scene {index} is invalid."
            )

        for key in required_scene:

            if key not in scene:

                raise RuntimeError(
                    f"Scene {index} "
                    f"missing '{key}'."
                )

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

        _check_enum(
            scene["purpose"],
            VALID_PURPOSE,
            f"Scene {index} purpose"
        )

        _check_enum(
            scene["retention_purpose"],
            VALID_RETENTION_PURPOSE,
            f"Scene {index} retention_purpose"
        )

        _check_enum(
            scene["subtitle_style"],
            VALID_SUBTITLE_STYLE,
            f"Scene {index} subtitle_style"
        )

        _check_enum(
            scene["emotional_tone"],
            VALID_EMOTIONAL_TONE,
            f"Scene {index} emotional_tone"
        )

        _check_enum(
            scene["visual_priority"],
            VALID_VISUAL_PRIORITY,
            f"Scene {index} visual_priority"
        )

        _check_enum(
            scene["transition"],
            VALID_TRANSITION,
            f"Scene {index} transition"
        )

        _check_enum(
            scene["music_cue"],
            VALID_MUSIC_CUE,
            f"Scene {index} music_cue"
        )

        _check_enum(
            scene["confidence"],
            VALID_CONFIDENCE,
            f"Scene {index} confidence"
        )

        # --------------------------------------------------------------
        # FINAL SCENE
        # --------------------------------------------------------------

        if index == expected_scene_count:

            scene[
                "purpose"
            ] = "ending"

            scene[
                "transition"
            ] = "none"

        # --------------------------------------------------------------
        # CAPTIONS
        # --------------------------------------------------------------

        scene[
            "narration"
        ] = str(
            scene["narration"]
        ).strip()

        scene[
            "subtitle_text"
        ] = str(
            scene["subtitle_text"]
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
            index
        )

        # --------------------------------------------------------------
        # DURATION
        # --------------------------------------------------------------

        try:

            duration = int(
                scene["duration"]
            )

        except Exception:

            raise RuntimeError(
                f"Scene {index} duration "
                "is invalid."
            )

        expected_duration = (
            SCENE_DURATIONS[
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

        # --------------------------------------------------------------
        # PAUSE
        # --------------------------------------------------------------

        try:

            pause = int(
                scene.get(
                    "pause_after_ms",
                    0
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
                pause
            )
        )

        # --------------------------------------------------------------
        # SFX
        # --------------------------------------------------------------

        if not isinstance(
            scene.get(
                "sfx_cue"
            ),
            dict
        ):

            scene[
                "sfx_cue"
            ] = {
                "term": "",
                "at_ms": 0
            }

        scene[
            "sfx_cue"
        ].setdefault(
            "term",
            ""
        )

        try:

            sfx_at = int(
                scene[
                    "sfx_cue"
                ].get(
                    "at_ms",
                    0
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
            sfx_at
        )

        # --------------------------------------------------------------
        # VISUALS
        # --------------------------------------------------------------

        visuals = scene[
            "visuals"
        ]

        if not isinstance(
            visuals,
            list
        ):

            raise RuntimeError(
                f"Scene {index} visuals "
                "must be a list."
            )

        if len(visuals) != VISUALS_PER_SCENE:

            raise RuntimeError(
                f"Scene {index} must contain "
                f"exactly {VISUALS_PER_SCENE} visuals "
                f"but Gemini returned "
                f"{len(visuals)}."
            )

        durations = _allocate_visual_durations(
            duration
        )

        visual_sum = 0

        for visual_index, visual in enumerate(
            visuals,
            start=1
        ):

            if not isinstance(
                visual,
                dict
            ):

                raise RuntimeError(
                    f"Scene {index} visual "
                    f"{visual_index} is invalid."
                )

            _repair_visual(
                visual,
                index,
                visual_index
            )

            visual[
                "duration"
            ] = durations[
                visual_index - 1
            ]

            visual_sum += visual[
                "duration"
            ]

            visual[
                "zoom_factor"
            ] = ZOOM_FACTORS[
                visual[
                    "zoom_strength"
                ]
            ]

            visual[
                "motion_speed"
            ] = MOTION_SPEEDS[
                visual[
                    "motion_intensity"
                ]
            ]

            visual[
                "needs_regeneration"
            ] = (
                visual[
                    "visual_impact"
                ] < 5
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

        total_visuals += VISUALS_PER_SCENE

        _add_scene_visual_compatibility(
            scene,
            script[
                "visual_identity"
            ]
        )

    # --------------------------------------------------------------
    # GLOBAL VALIDATION
    # --------------------------------------------------------------

    if hold_count > 1:

        raise RuntimeError(
            f"'hold' animation used "
            f"{hold_count} times. "
            "Maximum is 1."
        )

    if total_duration != TARGET_SECONDS:

        raise RuntimeError(
            f"Total duration must be exactly "
            f"{TARGET_SECONDS}s but is "
            f"{total_duration}s."
        )

    if total_visuals != TOTAL_VISUALS:

        raise RuntimeError(
            f"Total visuals must be exactly "
            f"{TOTAL_VISUALS} but is "
            f"{total_visuals}."
        )

    # --------------------------------------------------------------
    # NEXT SHORT + RESEARCH
    # --------------------------------------------------------------

    _normalize_next_short(
        script
    )

    _normalize_research_sources(
        script
    )

    # --------------------------------------------------------------
    # TOP LEVEL
    # --------------------------------------------------------------

    script[
        "title"
    ] = str(
        script["title"]
    ).strip()[:60]

    script[
        "description"
    ] = str(
        script["description"]
    ).strip()

    script[
        "tags"
    ] = list(
        dict.fromkeys(
            str(tag).strip().lower()
            for tag in script["tags"]
            if str(tag).strip()
        )
    )[:12]

    category = str(
        script["category"]
    ).strip().lower()

    script[
        "category"
    ] = (
        category
        if category in VALID_CATEGORY
        else "biology"
    )

    script[
        "thumbnail_prompt"
    ] = str(
        script["thumbnail_prompt"]
    ).strip()

    # --------------------------------------------------------------
    # PIPELINE METADATA
    # --------------------------------------------------------------

    script[
        "image_generation"
    ] = {

        "seed":
            seed,

        "style_lock":
            style_lock,

        "images_per_scene":
            VISUALS_PER_SCENE,

        "total_images":
            TOTAL_VISUALS
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

    script[
        "video_structure"
    ] = {

        "format":
            "short_form",

        "scene_count":
            SCENE_COUNT,

        "target_duration_seconds":
            TARGET_SECONDS,

        "actual_duration_seconds":
            TARGET_SECONDS,

        "visuals_per_scene":
            VISUALS_PER_SCENE,

        "total_visuals":
            TOTAL_VISUALS
    }

    script[
        "publishing"
    ] = {

        "research_sources_require_verification":
            True,

        "next_short_teaser_ready":
            True,

        "subscription_strategy":
            "next_short_continuation"
    }

    return script


def generate_script(
    topic,
    config
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

    prompt = build_user_prompt(
        topic,
        config
    )

    system_prompt = build_system_prompt()

    response_schema = build_response_schema()

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
        "Visuals per scene: 2"
    )

    print(
        "TOTAL IMAGES: 14"
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
        MAX_GENERATION_ATTEMPTS + 1
    ):

        print(
            f"🧠 Gemini generation attempt "
            f"{attempt}/{MAX_GENERATION_ATTEMPTS}"
        )

        try:

            attempt_prompt = prompt

            if (
                attempt > 1
                and last_error
            ):

                attempt_prompt += f"""

RETRY NOTICE

Previous validation error:

{last_error}

Return the COMPLETE storyboard again.

Hard requirements:

- exactly 7 scenes
- exactly 2 visuals in every scene
- exactly 14 visuals total
- exactly 45 seconds
- short semantic image prompts only
- no technical image-generation instructions
- final scene is the ending
- final scene teases the next Short
- include research source candidates

Return ONLY JSON.
"""

            response = (
                client.models.generate_content(

                    model=MODEL_NAME,

                    contents=attempt_prompt,

                    config=types.GenerateContentConfig(

                        system_instruction=
                            system_prompt,

                        response_mime_type=
                            "application/json",

                        response_json_schema=
                            response_schema
                    )
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

            script[
                "topic"
            ] = topic

            script = validate_script(
                script,
                expected_scene_count=
                    SCENE_COUNT
            )

            print("=" * 80)

            print(
                "✅ SCRIPT GENERATED AND VALIDATED"
            )

            print("=" * 80)

            print(
                "Scenes: 7"
            )

            print(
                "Images: 14"
            )

            print(
                "Duration: 45s"
            )

            print(
                f"Next Short: "
                f"{script['next_short']['topic']}"
            )

            print(
                f"Research candidates: "
                f"{len(script['research_sources'])}"
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

                delay = (
                    5 * attempt
                )

                print(
                    f"⏳ Retrying in "
                    f"{delay} seconds..."
                )

                time.sleep(
                    delay
                )

    raise RuntimeError(
        "Gemini failed to produce a valid "
        f"{TOTAL_VISUALS}-image storyboard after "
        f"{MAX_GENERATION_ATTEMPTS} attempts. "
        f"Last error: {last_error}"
    )


if __name__ == "__main__":

    import yaml

    with open(
        "config.yaml",
        "r",
        encoding="utf-8"
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

        "Why the ocean is salty"
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
            config
        )

        print(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False
            )
        )

        print("=" * 100)

        print(
            "SCRIPT VALID"
        )

        print("=" * 100)