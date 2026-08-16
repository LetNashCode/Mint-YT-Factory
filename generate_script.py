"""
generate_script.py
Mint-YT-Factory
Version 8.1

Research-first production script generator.

FLOW:

research.py
    ↓
Verified research package
    ↓
Gemini
    ↓
45-second researched Short
    ↓
Citations attached to claims
    ↓
generate_images.py
    ↓
assemble.py
    ↓
main.py
    ↓
YouTube

IMPORTANT:
- Gemini does NOT invent research sources.
- Gemini may ONLY use sources supplied by research.py.
- Every research source must already be verified.
- Script generation FAILS if verified research is missing.
- Research references remain attached to the final script.
- next_short.topic has NO word-count limit.
- next_short.topic is the actual subject of the next video.
- New standalone topics are handled separately by topics.py.
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
# CONFIG
# ==========================================================================

MODEL_NAME = "gemini-flash-lite-latest"
MAX_GENERATION_ATTEMPTS = 4

SCENE_COUNT = 7
TARGET_SECONDS = 45

VISUALS_PER_SCENE = 2
TOTAL_VISUALS = 14

SCENE_DURATIONS = [
    3, 5, 7, 7, 8, 8, 7
]

MIN_VERIFIED_SOURCES = 2

# --------------------------------------------------------------------------
# NEXT SHORT
#
# This is NOT a word limit.
#
# It is only a safety limit to prevent Gemini from returning an enormous
# paragraph instead of a usable topic.
# --------------------------------------------------------------------------

MAX_NEXT_SHORT_CHARACTERS = 300


# ==========================================================================
# VALID VALUES
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

VALID_SOURCE_TYPE = {
    "paper",
    "journal",
    "university",
    "government",
    "research_institute",
    "textbook",
}

VALID_SOURCE_PRIORITY = {
    "primary",
    "secondary",
}

ZOOM_FACTORS = {
    "subtle": 1.06,
    "medium": 1.15,
    "strong": 1.30,
}

MOTION_SPEEDS = {
    "low": 0.5,
    "medium": 1.0,
    "high": 1.6,
}


# ==========================================================================
# STORY STRUCTURE
# ==========================================================================

BEAT_TABLE = """
1. HOOK (0-3s)
   Start with the strongest verified fact or consequence.
   Never start with a question.

2. CURIOSITY GAP (3-8s)
   Create an unanswered question based only on the verified research.

3. EXPLANATION (8-15s)
   Explain the verified mechanism simply.

4. EXAMPLE (15-22s)
   Make the verified mechanism concrete and visual.

5. REFRAME (22-30s)
   Reveal a verified implication that changes how the viewer sees the idea.

6. ESCALATION (30-38s)
   Add one final verified consequence or perspective shift.

7. ENDING + NEXT SHORT (38-45s)
   Give a satisfying insight and tease a related future Short.
"""


# ==========================================================================
# RESEARCH VALIDATION
# ==========================================================================

def validate_research_package(
    research,
    topic,
):
    """
    Research is a HARD GATE.

    No verified research = no script.
    """

    if not isinstance(
        research,
        dict,
    ):

        raise RuntimeError(
            "RESEARCH GATE FAILED: "
            "research package is missing."
        )

    if research.get(
        "verified"
    ) is not True:

        raise RuntimeError(
            "RESEARCH GATE FAILED: "
            "research package is not marked VERIFIED."
        )

    if research.get(
        "status"
    ) != "VERIFIED":

        raise RuntimeError(
            "RESEARCH GATE FAILED: "
            "research status is not VERIFIED."
        )

    sources = research.get(
        "sources",
        [],
    )

    if not isinstance(
        sources,
        list,
    ):

        raise RuntimeError(
            "RESEARCH GATE FAILED: "
            "sources must be a list."
        )

    verified_sources = []

    for source in sources:

        if not isinstance(
            source,
            dict,
        ):
            continue

        if source.get(
            "verified"
        ) is not True:

            continue

        title = str(
            source.get(
                "title",
                "",
            )
        ).strip()

        authors = str(
            source.get(
                "authors",
                "",
            )
        ).strip()

        url = str(
            source.get(
                "url",
                "",
            )
        ).strip()

        if (
            title
            and authors
            and url
        ):

            verified_sources.append(
                source
            )

    if len(
        verified_sources
    ) < MIN_VERIFIED_SOURCES:

        raise RuntimeError(
            "RESEARCH GATE FAILED: "
            f"Only {len(verified_sources)} "
            "verified sources are available. "
            f"Minimum required: "
            f"{MIN_VERIFIED_SOURCES}."
        )

    research_topic = str(
        research.get(
            "topic",
            "",
        )
    ).strip()

    if research_topic:

        if (
            research_topic.lower()
            != topic.strip().lower()
        ):

            print(
                "⚠️ Research topic differs slightly "
                "from generated topic."
            )

    research[
        "sources"
    ] = verified_sources

    research[
        "source_count"
    ] = len(
        verified_sources
    )

    return research


# ==========================================================================
# RESEARCH CONTEXT
# ==========================================================================

def build_research_context(
    research,
):
    """
    Convert verified research into a strict context
    Gemini can use.

    Gemini is explicitly forbidden from creating
    additional sources.
    """

    sources = research[
        "sources"
    ]

    blocks = []

    for index, source in enumerate(
        sources,
        start=1,
    ):

        title = str(
            source.get(
                "title",
                "",
            )
        ).strip()

        authors = str(
            source.get(
                "authors",
                "",
            )
        ).strip()

        journal = str(
            source.get(
                "journal",
                "",
            )
        ).strip()

        year = source.get(
            "year",
            "",
        )

        doi = str(
            source.get(
                "doi",
                "",
            )
        ).strip()

        url = str(
            source.get(
                "url",
                "",
            )
        ).strip()

        abstract = str(
            source.get(
                "abstract",
                "",
            )
        ).strip()

        database = str(
            source.get(
                "source_database",
                "",
            )
        ).strip()

        block = f"""
VERIFIED SOURCE {index}

Title:
{title}

Authors:
{authors}

Journal / Venue:
{journal}

Year:
{year}

DOI:
{doi}

URL:
{url}

Database:
{database}

Abstract:
{abstract}
"""

        blocks.append(
            block.strip()
        )

    return "\n\n".join(
        blocks
    )


# ==========================================================================
# SYSTEM PROMPT
# ==========================================================================

def build_system_prompt(
    scene_count=SCENE_COUNT,
    target_seconds=TARGET_SECONDS,
):

    return f"""
You are an expert educational YouTube Shorts writer and visual director.

Your job is to create a scientifically responsible Short using ONLY
the VERIFIED RESEARCH SOURCES supplied by the user.

============================================================
ABSOLUTE RESEARCH RULE
============================================================

The supplied research sources are the ONLY permitted evidence.

You MUST NOT:

- invent sources
- invent studies
- invent authors
- invent statistics
- invent dates
- invent institutions
- invent URLs
- invent DOIs
- use outside knowledge as evidence
- present unsupported claims as facts
- create citations that are not supplied

Every factual scientific claim in the narration must be supported by
the supplied verified research.

If a fact cannot be supported by the supplied sources:

DO NOT INCLUDE IT.

If the research is insufficient to support the requested topic:

DO NOT fabricate an answer.

============================================================
CITATION MAPPING
============================================================

Every important factual claim must include one or more source IDs.

Use:

"source_ids": ["source_1"]

or:

"source_ids": ["source_1", "source_2"]

A source ID may ONLY refer to a supplied verified source.

Do not create source IDs that do not exist.

============================================================
FORMAT
============================================================

- Exactly {scene_count} scenes.
- Exactly {VISUALS_PER_SCENE} visuals per scene.
- Exactly {TOTAL_VISUALS} visuals total.
- Exactly {target_seconds} seconds.
- Scene durations:
  3, 5, 7, 7, 8, 8, 7 seconds.

{BEAT_TABLE}

============================================================
WRITING
============================================================

- Grade 6 reading level.
- Short punchy sentences.
- Strong opening statement.
- Never start with a question.
- No "Did you know".
- No "in this video".
- No "let's explore".
- No "today we're going to".
- No listicles.
- No countdowns.
- No Top 5.
- One connected story.
- Teach one phenomenon.

============================================================
SCIENTIFIC LANGUAGE
============================================================

Clearly distinguish:

FACT:
Supported directly by the supplied research.

EVIDENCE:
Supported by research but not necessarily absolute.

HYPOTHESIS:
Must be explicitly described as a hypothesis.

DEBATE:
Must be described as uncertain or debated.

Never convert uncertainty into certainty.

============================================================
VISUALS
============================================================

Exactly 2 visuals per scene.

Each visual must directly represent the narration.

Visual 1 establishes the idea.

Visual 2 advances or reveals the next part.

Preserve recurring subjects, objects and environments.

============================================================
IMAGE PROMPTS
============================================================

15-35 words approximately.

Describe ONLY what should be visible.

No camera instructions.
No lighting instructions.
No aspect ratio.
No rendering instructions.
No negative prompts.
No text.
No logos.
No watermarks.
No YouTube.
No narration.
No subtitles.
No viewers.
No AI.

============================================================
FINAL SCENE + NEXT SHORT
============================================================

Scene 7 is the bridge to the next Short.

The ending must:

1. Deliver a satisfying insight about the CURRENT topic.
2. Leave one natural curiosity gap.
3. Introduce a NEXT SHORT that logically continues from
   that curiosity gap.
4. Make the next topic feel like the next chapter of the story,
   not a random related subject.

The next Short topic MUST:

- Be based on the current video's final unresolved curiosity.
- Be specific enough for research.py to investigate.
- Describe the actual subject the NEXT video will research.
- Continue naturally from the current phenomenon.
- NOT simply repeat the current topic.
- NOT be a generic related topic.
- NOT be a list.
- NOT use "Top 5", "Top 10", or "Did you know".
- NOT have an 8-word limit.
- May be a full descriptive phrase or question if that makes
  the continuation clearer.

IMPORTANT:

There is NO 8-word limit for next_short.topic.

The 8-word restriction applies ONLY to independently generated
new topics by topics.py.

Example:

Current topic:
How do deep sea fish survive immense pressure

Next Short topic:
discover how deep ocean trenches drive massive cyclonic water circulation

The next_short.topic describes the actual subject that the NEXT
video will research and explain.

Do NOT shorten, paraphrase, or truncate next_short.topic merely
to make it shorter.

The next_short.topic should be research-ready.

Return ONLY valid JSON.
"""


# ==========================================================================
# USER PROMPT
# ==========================================================================

def build_user_prompt(
    topic,
    config,
    research,
):

    research_context = build_research_context(
        research
    )

    source_ids = []

    for index, source in enumerate(
        research["sources"],
        start=1,
    ):

        source_ids.append(
            f"source_{index}"
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

============================================================
VERIFIED RESEARCH
============================================================

The following sources have already passed the research verification
gate.

You MUST use only these sources.

Available source IDs:

{", ".join(source_ids)}

RESEARCH:

{research_context}

============================================================
PRODUCTION
============================================================

Create:

- 7 scenes
- 2 visuals per scene
- 14 visuals total
- 45 seconds

Scene durations:

3, 5, 7, 7, 8, 8, 7

============================================================
CRITICAL
============================================================

Every factual claim in narration must have source_ids.

Do not add unsupported facts.

Do not add new citations.

Do not invent research.

If a statement is not supported by the supplied sources, remove it.

The research_sources field in the final JSON MUST contain the supplied
verified sources exactly.

============================================================
NEXT SHORT REQUIREMENT
============================================================

The next_short.topic is NOT constrained to 8 words.

It must represent the actual subject of the NEXT video.

It must naturally continue the curiosity created by this video's ending.

The next_short.topic may be longer than 8 words when necessary.

Do NOT shorten it just to satisfy an arbitrary word limit.

Example:

discover how deep ocean trenches drive massive cyclonic water circulation

Return ONLY JSON.
"""


# ==========================================================================
# ENUM
# ==========================================================================

def _enum(values):

    return {
        "type": "string",
        "enum": list(values),
    }


# ==========================================================================
# RESPONSE SCHEMA
# ==========================================================================

def build_response_schema():

    visual = {

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

    scene = {

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

            "source_ids": {

                "type": "array",

                "items": {
                    "type": "string",
                },
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

                "items": visual,
            },
        },

        "required": [

            "scene",
            "purpose",
            "retention_purpose",
            "narration",
            "source_ids",
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

    source = {

        "type": "object",

        "properties": {

            "source_id": {
                "type": "string",
            },

            "title": {
                "type": "string",
            },

            "authors": {
                "type": "string",
            },

            "organization": {
                "type": "string",
            },

            "journal": {
                "type": "string",
            },

            "year": {
                "type": "integer",
            },

            "doi": {
                "type": "string",
            },

            "url": {
                "type": "string",
            },

            "source_database": {
                "type": "string",
            },

            "source_type": {
                "type": "string",
            },

            "priority": {
                "type": "string",
            },

            "verified": {
                "type": "boolean",
            },

            "verification": {
                "type": "string",
            },
        },

        "required": [

            "source_id",
            "title",
            "authors",
            "organization",
            "journal",
            "year",
            "doi",
            "url",
            "source_database",
            "source_type",
            "priority",
            "verified",
            "verification",
        ],
    }

    recurring_subject = {

        "type": "object",

        "properties": {

            "name": {
                "type": "string",
            },

            "type": {
                "type": "string",
            },

            "appearance": {
                "type": "string",
            },

            "continuity": {
                "type": "string",
            },
        },

        "required": [
            "name",
            "type",
            "appearance",
            "continuity",
        ],
    }

    visual_continuity = {

        "type": "object",

        "properties": {

            "recurring_subjects": {

                "type": "array",

                "items":
                    recurring_subject,
            },

            "recurring_objects": {

                "type": "array",

                "items": {
                    "type": "string",
                },
            },

            "recurring_environment": {

                "type": "string",
            },

            "continuity_rules": {

                "type": "array",

                "items": {
                    "type": "string",
                },
            },
        },

        "required": [

            "recurring_subjects",
            "recurring_objects",
            "recurring_environment",
            "continuity_rules",
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

            "visual_continuity":
                visual_continuity,

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

            "next_short": {

                "type": "object",

                "properties": {

                    "topic": {
                        "type": "string",
                    },

                    "teaser": {
                        "type": "string",
                    },

                    "why_viewers_should_return": {
                        "type": "string",
                    },

                    "subscription_cta": {
                        "type": "string",
                    },
                },

                "required": [
                    "topic",
                    "teaser",
                    "why_viewers_should_return",
                    "subscription_cta",
                ],
            },

            "research_sources": {

                "type": "array",

                "items": source,
            },

            "scene_plan": {

                "type": "array",

                "items": scene,
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
            "visual_continuity",
            "retention_self_check",
            "next_short",
            "research_sources",
            "scene_plan",
        ],
    }


# ==========================================================================
# JSON PARSER
# ==========================================================================

def parse_gemini_json(
    text,
):

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

    start = cleaned.find(
        "{"
    )

    end = cleaned.rfind(
        "}"
    )

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
                f"Failed to parse Gemini JSON: "
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
            f"{label}: invalid value "
            f"'{value}'."
        )


def _slugify(
    text,
):

    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        str(text).lower(),
    ).strip("-")

    return slug[:40] or "video"


def _build_style_lock(
    identity,
):

    if not isinstance(
        identity,
        dict,
    ):
        return ""

    parts = [

        str(
            identity.get(
                "style",
                "",
            )
        ).strip(),

        str(
            identity.get(
                "palette",
                "",
            )
        ).strip(),

        str(
            identity.get(
                "mood_arc",
                "",
            )
        ).strip(),
    ]

    parts = [
        p for p in parts
        if p
    ]

    if not parts:
        return ""

    return (
        "Consistent visual identity: "
        + ", ".join(parts)
    )


# ==========================================================================
# CAPTIONS
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

    result = []

    for item in scene.get(
        "caption_highlights",
        [],
    ):

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

            if word.lower() not in {
                x["word"].lower()
                for x in result
            }:

                result.append({

                    "word":
                        lookup[
                            word.lower()
                        ],

                    "emphasis":
                        emphasis,
                })

    if not result:

        word = max(
            tokens,
            key=len,
        )

        result = [{

            "word":
                word,

            "emphasis":
                "strong",
        }]

    scene[
        "caption_highlights"
    ] = result[:3]


# ==========================================================================
# IMAGE PROMPT
# ==========================================================================

def _clean_image_prompt(
    visual,
):

    prompt = str(
        visual.get(
            "image_prompt",
            "",
        )
    ).strip()

    prompt = prompt.replace(
        "```",
        "",
    )

    prompt = re.sub(
        r"\s+",
        " ",
        prompt,
    )

    forbidden_patterns = [

        r"\baspect ratio\b",
        r"\b16:9\b",
        r"\b9:16\b",
        r"\bnegative prompt\b",
        r"\btext overlay\b",
        r"\bwatermark\b",
        r"\blogo\b",
    ]

    for pattern in forbidden_patterns:

        prompt = re.sub(
            pattern,
            "",
            prompt,
            flags=re.IGNORECASE,
        )

    prompt = re.sub(
        r"\s+",
        " ",
        prompt,
    )

    return prompt.strip()


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
            "soft cinematic directional lighting",

        "color_palette":
            "cinematic natural tones",

        "overlay": {
            "type":
                "none",

            "description":
                "",
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

        visual[
            "overlay"
        ] = {

            "type":
                "none",

            "description":
                "",
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
    ] = _clean_image_prompt(
        visual
    )

    if not visual[
        "image_prompt"
    ]:

        raise RuntimeError(
            f"Scene {scene_index} "
            f"visual {visual_index} "
            "has an empty image_prompt."
        )


# ==========================================================================
# VISUAL DURATIONS
# ==========================================================================

def _allocate_visual_durations(
    scene_duration,
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


# ==========================================================================
# SCENE COMPATIBILITY
# ==========================================================================

def _add_scene_visual_compatibility(
    scene,
    identity,
):

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

    if not isinstance(
        identity,
        dict,
    ):
        identity = {}

    scene[
        "visual_identity"
    ] = (
        f"{identity.get('style', '')}. "
        f"{identity.get('palette', '')}. "
        f"{identity.get('mood_arc', '')}"
    ).strip()


# ==========================================================================
# NEXT SHORT
# ==========================================================================

def _normalize_next_short(
    script,
):

    """
    Normalize the next Short information.

    IMPORTANT:

    next_short.topic has NO word-count limit.

    It is the actual research topic for the next video.

    A safety limit of 300 characters prevents malformed output,
    but legitimate long continuation topics are preserved exactly.
    """

    item = script.get(
        "next_short",
        {},
    )

    if not isinstance(
        item,
        dict,
    ):
        item = {}

    topic = str(
        item.get(
            "topic",
            "",
        )
    ).strip()

    teaser = str(
        item.get(
            "teaser",
            "",
        )
    ).strip()

    reason = str(
        item.get(
            "why_viewers_should_return",
            "",
        )
    ).strip()

    cta = str(
        item.get(
            "subscription_cta",
            "",
        )
    ).strip()

    if not topic:

        raise RuntimeError(
            "next_short.topic is empty."
        )

    # ----------------------------------------------------------------------
    # NO WORD LIMIT
    # ----------------------------------------------------------------------

    if len(topic) > MAX_NEXT_SHORT_CHARACTERS:

        raise RuntimeError(
            "next_short.topic is too long. "
            f"Maximum allowed is "
            f"{MAX_NEXT_SHORT_CHARACTERS} characters."
        )

    if not teaser:

        raise RuntimeError(
            "next_short.teaser is empty."
        )

    script[
        "next_short"
    ] = {

        # IMPORTANT:
        # Do NOT truncate the topic.
        "topic":
            topic,

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
            )[:160],
    }


# ==========================================================================
# RESEARCH NORMALIZATION
# ==========================================================================

def _normalize_research_sources(
    script,
    verified_research,
):

    normalized = []

    supplied_sources = (
        verified_research[
            "sources"
        ]
    )

    for index, source in enumerate(
        supplied_sources,
        start=1,
    ):

        source_id = (
            f"source_{index}"
        )

        normalized.append({

            "source_id":
                source_id,

            "title":
                str(
                    source.get(
                        "title",
                        "",
                    )
                ).strip()[:300],

            "authors":
                str(
                    source.get(
                        "authors",
                        "",
                    )
                ).strip()[:500],

            "organization":
                str(
                    source.get(
                        "organization",
                        "",
                    )
                ).strip()[:250],

            "journal":
                str(
                    source.get(
                        "journal",
                        "",
                    )
                ).strip()[:250],

            "year":
                int(
                    source.get(
                        "year",
                        0,
                    ) or 0
                ),

            "doi":
                str(
                    source.get(
                        "doi",
                        "",
                    )
                ).strip(),

            "url":
                str(
                    source.get(
                        "url",
                        "",
                    )
                ).strip(),

            "source_database":
                str(
                    source.get(
                        "source_database",
                        "",
                    )
                ).strip(),

            "source_type":
                str(
                    source.get(
                        "source_type",
                        "paper",
                    )
                ).strip(),

            "priority":
                str(
                    source.get(
                        "priority",
                        "secondary",
                    )
                ).strip(),

            "verified":
                True,

            "verification":
                str(
                    source.get(
                        "verification",
                        "Verified by research.py",
                    )
                ).strip()
                or
                "Verified by research.py",
        })

    script[
        "research_sources"
    ] = normalized


# ==========================================================================
# SOURCE ID VALIDATION
# ==========================================================================

def _validate_source_ids(
    script,
):

    valid_ids = {

        source.get(
            "source_id"
        )

        for source in script.get(
            "research_sources",
            []
        )

        if isinstance(
            source,
            dict,
        )
    }

    if not valid_ids:

        raise RuntimeError(
            "No verified research sources "
            "are attached to script."
        )

    for index, scene in enumerate(
        script.get(
            "scene_plan",
            []
        ),
        start=1,
    ):

        source_ids = scene.get(
            "source_ids",
            [],
        )

        if not isinstance(
            source_ids,
            list,
        ):

            raise RuntimeError(
                f"Scene {index} source_ids "
                "must be a list."
            )

        if not source_ids:

            raise RuntimeError(
                f"Scene {index} has no "
                "research source citation."
            )

        for source_id in source_ids:

            if source_id not in valid_ids:

                raise RuntimeError(
                    f"Scene {index} references "
                    f"invalid source ID: "
                    f"{source_id}"
                )


# ==========================================================================
# VISUAL CONTINUITY
# ==========================================================================

def _normalize_visual_continuity(
    script,
):

    continuity = script.get(
        "visual_continuity",
        {},
    )

    if not isinstance(
        continuity,
        dict,
    ):
        continuity = {}

    subjects = continuity.get(
        "recurring_subjects",
        [],
    )

    if not isinstance(
        subjects,
        list,
    ):
        subjects = []

    normalized_subjects = []

    for subject in subjects:

        if not isinstance(
            subject,
            dict,
        ):
            continue

        name = str(
            subject.get(
                "name",
                "",
            )
        ).strip()

        appearance = str(
            subject.get(
                "appearance",
                "",
            )
        ).strip()

        if not name or not appearance:
            continue

        normalized_subjects.append({

            "name":
                name[:100],

            "type":
                str(
                    subject.get(
                        "type",
                        "",
                    )
                ).strip()[:80],

            "appearance":
                appearance[:500],

            "continuity":
                str(
                    subject.get(
                        "continuity",
                        "same appearance throughout",
                    )
                ).strip()[:300],
        })

    objects = continuity.get(
        "recurring_objects",
        [],
    )

    if not isinstance(
        objects,
        list,
    ):
        objects = []

    rules = continuity.get(
        "continuity_rules",
        [],
    )

    if not isinstance(
        rules,
        list,
    ):
        rules = []

    script[
        "visual_continuity"
    ] = {

        "recurring_subjects":
            normalized_subjects,

        "recurring_objects":
            [
                str(x).strip()[:200]
                for x in objects
                if str(x).strip()
            ][:20],

        "recurring_environment":
            str(
                continuity.get(
                    "recurring_environment",
                    "",
                )
            ).strip()[:500],

        "continuity_rules":
            [
                str(x).strip()[:300]
                for x in rules
                if str(x).strip()
            ][:20],
    }


# ==========================================================================
# VALIDATION
# ==========================================================================

def validate_script(
    script,
    verified_research,
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
        "visual_continuity",
        "retention_self_check",
        "next_short",
        "research_sources",
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

    if len(scenes) != SCENE_COUNT:

        raise RuntimeError(
            f"Expected {SCENE_COUNT} scenes "
            f"but got {len(scenes)}."
        )

    _normalize_visual_continuity(
        script
    )

    # ----------------------------------------------------------------------
    # NEXT SHORT NORMALIZATION
    # ----------------------------------------------------------------------

    _normalize_next_short(
        script
    )

    total_duration = 0
    total_visuals = 0
    hold_count = 0

    seed = random.randint(
        1,
        2_147_483_647,
    )

    required_scene = [

        "scene",
        "purpose",
        "retention_purpose",
        "narration",
        "source_ids",
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

        for key in required_scene:

            if key not in scene:

                raise RuntimeError(
                    f"Scene {index} missing "
                    f"'{key}'."
                )

        if int(
            scene["scene"]
        ) != index:

            raise RuntimeError(
                f"Scene {index} has invalid "
                "scene number."
            )

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

        if index == SCENE_COUNT:

            scene[
                "purpose"
            ] = "ending"

            scene[
                "transition"
            ] = "none"

        narration = str(
            scene["narration"]
        ).strip()

        subtitle = str(
            scene["subtitle_text"]
        ).strip()

        if not narration:

            raise RuntimeError(
                f"Scene {index} narration "
                "is empty."
            )

        if not subtitle:

            raise RuntimeError(
                f"Scene {index} subtitle "
                "is empty."
            )

        scene[
            "narration"
        ] = narration

        scene[
            "subtitle_text"
        ] = subtitle

        _repair_caption_highlights(
            scene,
            index,
        )

        # --------------------------------------------------------------
        # SOURCE CITATIONS
        # --------------------------------------------------------------

        source_ids = scene.get(
            "source_ids",
            [],
        )

        if not source_ids:

            raise RuntimeError(
                f"Scene {index} contains "
                "no research citation."
            )

        # --------------------------------------------------------------
        # DURATION
        # --------------------------------------------------------------

        duration = int(
            scene["duration"]
        )

        expected_duration = (
            SCENE_DURATIONS[
                index - 1
            ]
        )

        if duration != expected_duration:

            raise RuntimeError(
                f"Scene {index} duration must "
                f"be {expected_duration}s."
            )

        total_duration += duration

        # --------------------------------------------------------------
        # PAUSE
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # SFX
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # VISUALS
        # --------------------------------------------------------------

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

        if len(visuals) != VISUALS_PER_SCENE:

            raise RuntimeError(
                f"Scene {index} must contain "
                f"{VISUALS_PER_SCENE} visuals."
            )

        durations = _allocate_visual_durations(
            duration
        )

        visual_sum = 0
        prompts = []

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
                    f"{visual_index} invalid."
                )

            _repair_visual(
                visual,
                index,
                visual_index,
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

            prompts.append(
                visual[
                    "image_prompt"
                ].lower().strip()
            )

        if len(
            set(prompts)
        ) < VISUALS_PER_SCENE:

            raise RuntimeError(
                f"Scene {index} contains "
                "duplicate visual prompts."
            )

        if visual_sum != duration:

            raise RuntimeError(
                f"Scene {index} visual "
                "durations do not match."
            )

        total_visuals += (
            VISUALS_PER_SCENE
        )

        _add_scene_visual_compatibility(
            scene,
            script[
                "visual_identity"
            ],
        )

    if hold_count > 1:

        raise RuntimeError(
            "'hold' animation used more "
            "than once."
        )

    if total_duration != TARGET_SECONDS:

        raise RuntimeError(
            f"Total duration must be "
            f"{TARGET_SECONDS}s."
        )

    if total_visuals != TOTAL_VISUALS:

        raise RuntimeError(
            f"Total visuals must be "
            f"{TOTAL_VISUALS}."
        )

    # ----------------------------------------------------------------------
    # RESEARCH IS COPIED FROM VERIFIED PACKAGE
    # ----------------------------------------------------------------------

    _normalize_research_sources(
        script,
        verified_research,
    )

    _validate_source_ids(
        script
    )

    # ----------------------------------------------------------------------
    # TOP LEVEL
    # ----------------------------------------------------------------------

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
            for tag in script[
                "tags"
            ]
            if str(tag).strip()
        )
    )[:12]

    category = str(
        script[
            "category"
        ]
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
        script[
            "thumbnail_prompt"
        ]
    ).strip()

    style_lock = _build_style_lock(
        script[
            "visual_identity"
        ]
    )

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
            TOTAL_VISUALS,

        "visual_continuity_enabled":
            True,
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
            TOTAL_VISUALS,
    }

    script[
        "publishing"
    ] = {

        "research_verified":
            True,

        "research_sources_require_verification":
            False,

        "citations_ready":
            True,

        "next_short_teaser_ready":
            True,

        "subscription_strategy":
            "next_short_continuation",

        "visual_continuity_enabled":
            True,
    }

    return script


# ==========================================================================
# GENERATE SCRIPT
# ==========================================================================

def generate_script(
    topic,
    config,
    research,
):

    # ----------------------------------------------------------------------
    # HARD RESEARCH GATE
    # ----------------------------------------------------------------------

    research = validate_research_package(
        research,
        topic,
    )

    print("=" * 80)
    print("🔬 VERIFIED RESEARCH GATE PASSED")
    print("=" * 80)

    print(
        f"Verified sources: "
        f"{len(research['sources'])}"
    )

    for index, source in enumerate(
        research["sources"],
        start=1,
    ):

        print(
            f"✅ source_{index}: "
            f"{source.get('title', '')}"
        )

    print("=" * 80)

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
        config,
        research,
    )

    system_prompt = build_system_prompt()

    response_schema = (
        build_response_schema()
    )

    print("=" * 80)
    print("✍️ GENERATING RESEARCHED SCRIPT")
    print("=" * 80)

    print(
        f"Model: {MODEL_NAME}"
    )

    print(
        f"Verified sources: "
        f"{len(research['sources'])}"
    )

    print(
        f"Scenes: {SCENE_COUNT}"
    )

    print(
        f"Images: {TOTAL_VISUALS}"
    )

    print(
        f"Duration: {TARGET_SECONDS}s"
    )

    print(
        f"Topic: {topic}"
    )

    print("=" * 80)

    last_error = None

    for attempt in range(
        1,
        MAX_GENERATION_ATTEMPTS + 1,
    ):

        print(
            f"🧠 Gemini attempt "
            f"{attempt}/"
            f"{MAX_GENERATION_ATTEMPTS}"
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

Correct the error and return the COMPLETE
storyboard.

Remember:

- ONLY use supplied verified research.
- Every scene needs source_ids.
- Never invent research.
- Never invent citations.
- Exactly 7 scenes.
- Exactly 14 visuals.
- Exactly 45 seconds.
- next_short.topic has NO 8-word limit.
- Preserve the full next_short.topic.
- Make next_short.topic the actual subject of the next video.
- Make the next topic naturally continue the current video's
  unresolved curiosity.

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
                            response_schema,
                    ),
                )
            )

            if not response.text:

                raise RuntimeError(
                    "Gemini returned an empty response."
                )

            script = parse_gemini_json(
                response.text
            )

            script[
                "topic"
            ] = topic

            script = validate_script(
                script,
                research,
            )

            print("=" * 80)
            print("✅ VERIFIED SCRIPT GENERATED")
            print("=" * 80)

            print(
                f"Scenes: {SCENE_COUNT}"
            )

            print(
                f"Images: {TOTAL_VISUALS}"
            )

            print(
                f"Duration: {TARGET_SECONDS}s"
            )

            print(
                f"Research sources: "
                f"{len(script['research_sources'])}"
            )

            print(
                f"Next Short topic: "
                f"{script['next_short']['topic']}"
            )

            print(
                f"Next Short topic words: "
                f"{len(script['next_short']['topic'].split())}"
            )

            print(
                "Research status: VERIFIED"
            )

            print(
                "Citations: READY"
            )

            print("=" * 80)

            return script

        except Exception as error:

            last_error = error

            print("=" * 80)

            print(
                f"❌ ATTEMPT {attempt} FAILED"
            )

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
                    f"{delay}s..."
                )

                time.sleep(
                    delay
                )

    raise RuntimeError(

        "SCRIPT GENERATION FAILED.\n"
        "The pipeline refused to create a "
        "Short from unverified or insufficient "
        "research.\n\n"
        f"Last error: {last_error}"
    )


# ==========================================================================
# LOCAL TEST
# ==========================================================================

if __name__ == "__main__":

    print(
        "generate_script.py requires a "
        "VERIFIED research package."
    )

    print(
        "Run the complete pipeline through main.py."
    )