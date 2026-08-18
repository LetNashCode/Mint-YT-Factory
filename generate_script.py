"""
generate_script.py
Mint-YT-Factory

Research-first YouTube Shorts story generator.

PRIMARY GOAL
------------
Generate a high-retention, scientifically responsible 45-second Short
from VERIFIED research supplied by research.py.

FORMAT
------
7 scenes
45 seconds
14 visuals
2 visuals per scene

Story structure:

Scene 1  0-3s    HOOK
Scene 2  3-8s    CURIOSITY GAP
Scene 3  8-15s   EXPLANATION
Scene 4 15-22s   EXAMPLE
Scene 5 22-30s   REFRAME
Scene 6 30-38s   ESCALATION
Scene 7 38-45s   PAYOFF / ENDING

IMPORTANT DESIGN PRINCIPLES
---------------------------

1. Research is authoritative.
2. Gemini may ONLY use supplied evidence for factual claims.
3. Narration is the single source of truth for captions.
4. Scene 7 finishes the CURRENT story.
5. next_short is metadata, not part of the current narration.
6. Visuals must explain or advance the story.
7. Scientific uncertainty must never be strengthened.
8. The same visual subject must remain visually consistent.
9. The result must feel like a story, not a lecture.
10. Validation happens before production.

This file intentionally keeps the public function:

    generate_script(topic, config, research)

compatible with the existing pipeline.
"""

import json
import os
import random
import re
import time
import uuid

from google import genai
from google.genai import types


# ============================================================================
# CONFIGURATION
# ============================================================================

MODEL_NAME = "gemini-flash-lite-latest"

MAX_GENERATION_ATTEMPTS = 4

SCENE_COUNT = 7
TARGET_SECONDS = 45

VISUALS_PER_SCENE = 2
TOTAL_VISUALS = 14

SCENE_DURATIONS = [
    3,   # Hook
    5,   # Curiosity
    7,   # Explanation
    7,   # Example
    8,   # Reframe
    8,   # Escalation
    7,   # Ending
]

MIN_VERIFIED_SOURCES = 2

MAX_NEXT_SHORT_CHARACTERS = 300

MAX_TITLE_LENGTH = 70

MAX_DESCRIPTION_LENGTH = 2000

MAX_TAGS = 12


# ============================================================================
# SCIENTIFIC LANGUAGE SAFETY
# ============================================================================

# These are intentionally conservative.
#
# The purpose is NOT to decide whether a scientific statement is true.
#
# The purpose is to catch obvious language that commonly turns:
#
#   association -> causation
#   possibility -> certainty
#   indication -> proof
#   observation -> universal rule
#
# The research verifier remains authoritative.

FORBIDDEN_CLAIM_PATTERNS = [

    r"\bproves\b",
    r"\bproved\b",
    r"\bproven\b",
    r"\bproof\b",
    r"\bproof that\b",

    r"\bscientifically proven\b",
    r"\bscientifically proves\b",

    r"\bdefinitively\b",
    r"\bdefinitive proof\b",
    r"\bdefinitively proves\b",

    r"\bconfirms\b",
    r"\bconfirmed\b",
    r"\bconfirm that\b",
    r"\bconfirmed that\b",

    r"\bcauses\b",
    r"\bcaused\b",
    r"\bcaused by\b",
    r"\bcausing\b",

    r"\bresults in\b",
    r"\bresulting in\b",

    r"\bguarantees\b",
    r"\bguaranteed\b",
    r"\bguarantee\b",

    r"\bessential\b",
    r"\bessential for\b",
    r"\bessential to\b",
    r"\bis essential\b",
    r"\bare essential\b",

    r"\bmust\b",
    r"\bdefinitely\b",
    r"\bcertainly\b",

    r"\bwithout doubt\b",
    r"\bno doubt\b",

    r"\balways\b",
    r"\bnever\b",

    r"\bcompletely\b",
    r"\bperfectly\b",

    r"\bthe only reason\b",
    r"\bthe exact reason\b",
]


# ============================================================================
# VALID ENUMERATIONS
# ============================================================================

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
    "history",
    "animals",
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


# ============================================================================
# STORY BEATS
# ============================================================================

STORY_BEATS = """
SCENE 1 — HOOK — 0-3 seconds
Start immediately with the most interesting VERIFIED fact,
consequence, contrast, or visual situation.

Do NOT begin with a question.

The viewer should immediately understand:
"Something unusual is happening."

------------------------------------------------------------

SCENE 2 — CURIOSITY GAP — 3-8 seconds
Reveal the problem, mystery, contradiction, or unexpected detail.

Create a question in the viewer's mind without literally asking
a generic question.

------------------------------------------------------------

SCENE 3 — EXPLANATION — 8-15 seconds
Explain the mechanism using only verified evidence.

Keep it simple enough for a general audience.

------------------------------------------------------------

SCENE 4 — EXAMPLE — 15-22 seconds
Turn the explanation into something concrete and visual.

Show what the mechanism looks like in the real world.

------------------------------------------------------------

SCENE 5 — REFRAME — 22-30 seconds
Reveal the implication that makes the viewer reinterpret
what they just learned.

This should feel like:
"Oh — so THAT is what is really happening."

------------------------------------------------------------

SCENE 6 — ESCALATION — 30-38 seconds
Introduce the strongest remaining VERIFIED consequence,
observation, or perspective shift.

Do not add an unrelated fact.

------------------------------------------------------------

SCENE 7 — PAYOFF — 38-45 seconds
Resolve the CURRENT story.

The final sentence should feel satisfying.

The ending may leave a broader curiosity,
but it must NOT depend on mentioning the next Short.

Do NOT say:
"Next we'll look at..."
"In the next video..."
"Coming next..."
"The next mystery is..."

"""


# ============================================================================
# BASIC HELPERS
# ============================================================================

def _clean(value):
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _enum(values):
    return {
        "type": "string",
        "enum": sorted(list(values)),
    }


def _slugify(text):
    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        str(text).lower(),
    ).strip("-")

    return slug[:45] or "video"


def _get_api_key():
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is missing."
        )

    return api_key


def _check_enum(value, allowed, label):
    if value not in allowed:
        raise RuntimeError(
            f"{label}: invalid value '{value}'. "
            f"Allowed values: {sorted(allowed)}"
        )


# ============================================================================
# CLAIM SAFETY
# ============================================================================

def _find_claim_violations(script):
    violations = []

    scenes = script.get(
        "scene_plan",
        [],
    )

    if not isinstance(scenes, list):
        return violations

    for index, scene in enumerate(
        scenes,
        start=1,
    ):

        if not isinstance(scene, dict):
            continue

        narration = _clean(
            scene.get(
                "narration",
                "",
            )
        )

        if not narration:
            continue

        for pattern in FORBIDDEN_CLAIM_PATTERNS:

            match = re.search(
                pattern,
                narration,
                flags=re.IGNORECASE,
            )

            if match:
                violations.append({
                    "scene": index,
                    "phrase": match.group(0),
                    "narration": narration,
                })

    return violations


def _validate_claim_strength(script):

    violations = _find_claim_violations(script)

    if not violations:
        return

    lines = [
        "SCIENTIFIC CLAIM SAFETY CHECK FAILED.",
        "",
        "The narration contains wording that may strengthen "
        "the supplied evidence.",
        "",
    ]

    for violation in violations:

        lines.append(
            f"Scene {violation['scene']}: "
            f"'{violation['phrase']}'"
        )

        lines.append(
            f"Narration: {violation['narration']}"
        )

        lines.append("")

    lines.extend([
        "Preserve the strength of the supplied evidence.",
        "",
        "Use evidence-matched language such as:",
        "- may",
        "- might",
        "- appears to",
        "- suggests",
        "- indicates",
        "- is associated with",
        "- researchers observed",
        "",
        "Do not convert association into causation.",
    ])

    raise RuntimeError(
        "\n".join(lines)
    )


# ============================================================================
# RESEARCH VALIDATION
# ============================================================================

def _extract_source_evidence(source):

    if not isinstance(source, dict):
        return ""

    evidence = source.get(
        "evidence_text",
        "",
    )

    if not isinstance(evidence, str):
        return ""

    return _clean(evidence)


def validate_research_package(
    research,
    topic,
):

    if not isinstance(research, dict):
        raise RuntimeError(
            "RESEARCH GATE FAILED: research package is missing."
        )

    if research.get("verified") is not True:
        raise RuntimeError(
            "RESEARCH GATE FAILED: research package is not VERIFIED."
        )

    if research.get("status") != "VERIFIED":
        raise RuntimeError(
            "RESEARCH GATE FAILED: research status is not VERIFIED."
        )

    sources = research.get(
        "sources",
        [],
    )

    if not isinstance(sources, list):
        raise RuntimeError(
            "RESEARCH GATE FAILED: sources must be a list."
        )

    verified_sources = []

    seen_ids = set()

    for index, source in enumerate(
        sources,
        start=1,
    ):

        if not isinstance(source, dict):
            continue

        if source.get("verified") is not True:
            continue

        if source.get("evidence_verified") is not True:
            continue

        if source.get("evidence_available") is not True:
            continue

        source_id = _clean(
            source.get(
                "source_id",
                "",
            )
        )

        if not source_id:
            raise RuntimeError(
                f"RESEARCH GATE FAILED: "
                f"source {index} has no source_id."
            )

        if source_id in seen_ids:
            raise RuntimeError(
                f"RESEARCH GATE FAILED: duplicate "
                f"source_id '{source_id}'."
            )

        title = _clean(
            source.get(
                "title",
                "",
            )
        )

        authors = _clean(
            source.get(
                "authors",
                "",
            )
        )

        url = _clean(
            source.get(
                "url",
                "",
            )
        )

        doi = _clean(
            source.get(
                "doi",
                "",
            )
        )

        evidence = _extract_source_evidence(
            source
        )

        if not title:
            continue

        if not authors:
            continue

        if not url:
            continue

        if not doi:
            continue

        if not evidence:
            continue

        seen_ids.add(source_id)

        verified_sources.append(source)

    if len(verified_sources) < MIN_VERIFIED_SOURCES:
        raise RuntimeError(
            "RESEARCH GATE FAILED: "
            f"Only {len(verified_sources)} verified evidence-backed "
            f"source(s) available. "
            f"Minimum required: {MIN_VERIFIED_SOURCES}."
        )

    research_topic = _clean(
        research.get(
            "topic",
            "",
        )
    )

    if research_topic and (
        research_topic.lower()
        != topic.strip().lower()
    ):
        print(
            "⚠️ Research topic differs slightly from generated topic."
        )

    research["sources"] = verified_sources

    research["source_count"] = len(
        verified_sources
    )

    research["evidence_source_count"] = len(
        verified_sources
    )

    return research


# ============================================================================
# RESEARCH CONTEXT
# ============================================================================

def build_research_context(research):

    blocks = []

    seen_ids = set()

    for index, source in enumerate(
        research["sources"],
        start=1,
    ):

        source_id = _clean(
            source.get(
                "source_id",
                "",
            )
        )

        if not source_id:
            raise RuntimeError(
                f"Research source {index} has no source_id."
            )

        if source_id in seen_ids:
            raise RuntimeError(
                f"Duplicate source ID: {source_id}"
            )

        seen_ids.add(source_id)

        evidence = _extract_source_evidence(
            source
        )

        if not evidence:
            raise RuntimeError(
                f"Research source {source_id} "
                "has no evidence_text."
            )

        block = f"""
============================================================
VERIFIED SOURCE: {source_id}
============================================================

SOURCE ID:
{source_id}

TITLE:
{_clean(source.get("title", ""))}

AUTHORS:
{_clean(source.get("authors", ""))}

JOURNAL:
{_clean(source.get("journal", ""))}

YEAR:
{source.get("year", "")}

DOI:
{_clean(source.get("doi", ""))}

URL:
{_clean(source.get("url", ""))}

DATABASE:
{_clean(source.get("source_database", ""))}

VERIFICATION LEVEL:
{_clean(source.get("verification_level", ""))}

------------------------------------------------------------

SUPPLIED SCIENTIFIC EVIDENCE

Evidence type:
{_clean(source.get("evidence_type", "abstract"))}

Evidence quality:
{_clean(source.get("evidence_quality", "high"))}

Evidence:

{evidence}

============================================================
END VERIFIED SOURCE {source_id}
============================================================
"""

        blocks.append(
            block.strip()
        )

    if not blocks:
        raise RuntimeError(
            "No verified research sources available."
        )

    return "\n\n".join(blocks)


# ============================================================================
# SYSTEM PROMPT
# ============================================================================

def build_system_prompt():

    return f"""
You are the lead writer and visual director for a premium
science-focused YouTube Shorts channel.

Your job is NOT to write a textbook.

Your job is to turn verified scientific evidence into a
45-second story that makes a viewer stop, understand something,
and want to watch another video.

============================================================
ABSOLUTE RESEARCH RULE
============================================================

The supplied research evidence is the ONLY factual source.

You MUST NOT use:

- general knowledge
- model memory
- outside facts
- internet knowledge
- invented statistics
- invented dates
- invented mechanisms
- invented experiments
- invented researchers
- invented institutions
- invented citations

If the supplied evidence does not support a fact:

DO NOT SAY IT.

Do not "fill in" missing scientific details.

============================================================
EVIDENCE STRENGTH
============================================================

Preserve the exact strength of the evidence.

If evidence says:

"may"

write:

"may"

NOT:

"will"
"does"
"always"
"proves"

If evidence says:

"is associated with"

write:

"is associated with"

NOT:

"causes"
"leads to"
"results in"

If evidence says:

"suggests"

write:

"suggests"
or another equally cautious phrase.

NOT:

"proves"
"confirms"

Never convert:

association -> causation

possibility -> certainty

observation -> universal rule

hypothesis -> fact

correlation -> mechanism

============================================================
LANGUAGE TO AVOID
============================================================

Never use unsupported:

proves
proven
proof
definitively
confirms
confirmed
causes
caused
causing
results in
guarantees
guaranteed
essential
definitely
certainly
without doubt
no doubt
always
never

Only use stronger wording when the supplied evidence itself
explicitly supports that strength.

============================================================
STORY, NOT LECTURE
============================================================

The Short must tell ONE connected story.

Do NOT create:

- Top 5
- countdowns
- lists
- unrelated facts
- "Did you know?"
- "In this video..."
- "Today we're going to..."
- generic introductions
- generic conclusions

The opening must immediately create tension, surprise,
wonder, or curiosity.

Never start with a question.

The viewer should feel that they entered an unfolding story.

============================================================
STORY ARC
============================================================

{STORY_BEATS}

============================================================
RETENTION
============================================================

Every scene must earn its place.

Avoid repeating the same idea in different words.

Each scene should do one of these:

- reveal something
- explain something
- demonstrate something
- change interpretation
- escalate consequence
- deliver payoff

The story should continuously move forward.

============================================================
SCENE 7
============================================================

Scene 7 MUST finish the CURRENT story.

Do NOT force next_short.topic into Scene 7.

Do NOT say:

"Next we'll..."
"In the next video..."
"Coming next..."
"Stay tuned for..."

The viewer should be satisfied even if they never watch another video.

============================================================
NARRATION
============================================================

Grade 6-8 reading level.

Natural spoken English.

Short sentences.

Avoid unnecessarily technical terminology.

If a technical term is essential and present in the evidence,
explain it naturally.

Do not sound like a research paper.

Do not sound like an AI assistant.

Write as an excellent human science storyteller.

============================================================
CAPTIONS
============================================================

narration is the ONLY source of truth.

subtitle_text MUST be an exact copy of narration.

Never paraphrase it.

Never shorten it.

Never phoneticize it.

Never change spelling.

============================================================
SOURCE IDS
============================================================

Use EXACT source IDs supplied by the research package.

Never invent IDs.

Never rename IDs.

Never create:

source_1
source_2

unless those exact IDs were supplied.

Every factual scene must cite the source IDs supporting it.

Purely stylistic language may use [].

============================================================
VISUAL STORYTELLING
============================================================

Exactly 2 visuals per scene.

Visual 1:
establishes the idea.

Visual 2:
advances, reveals, demonstrates, or reframes the idea.

Do not generate two visually identical shots.

The visuals should make the story understandable even without audio.

============================================================
VISUAL CONTINUITY
============================================================

If the story contains a recurring:

- person
- animal
- object
- spacecraft
- cell
- environment
- machine
- structure

define its appearance clearly in visual_continuity.

Then keep it consistent.

Do not randomly change:

- colors
- shape
- clothing
- age
- environment
- scale
- design

unless the story explicitly requires a transformation.

============================================================
IMAGE PROMPTS
============================================================

Each image_prompt should be approximately 15-35 words.

Describe ONLY what should be visible.

Do NOT include:

- camera instructions
- aspect ratio
- negative prompts
- text
- captions
- subtitles
- logos
- watermarks
- YouTube
- narration
- "AI generated"

Camera, animation, lighting and palette belong in their own fields.

============================================================
DESCRIPTION
============================================================

The description must describe ONLY the CURRENT video.

Do NOT reveal:

- next_short.topic
- next video's title
- next video's subject
- next video's research question

============================================================
NEXT SHORT
============================================================

Generate a researchable next topic that naturally follows
the current story.

It is metadata for the content pipeline.

It does NOT need to be spoken in the current Short.

The next topic should be specific enough that research.py
can independently research it.

Avoid vague topics like:

"More about this"
"Another interesting fact"
"Something surprising"

============================================================
OUTPUT
============================================================

Return ONLY valid JSON matching the supplied schema.

No markdown.

No commentary.
"""


# ============================================================================
# USER PROMPT
# ============================================================================

def build_user_prompt(
    topic,
    config,
    research,
):

    channel_config = config.get(
        "channel",
        {},
    )

    script_config = config.get(
        "script",
        {},
    )

    source_ids = [
        _clean(source.get("source_id", ""))
        for source in research["sources"]
        if _clean(source.get("source_id", ""))
    ]

    research_context = build_research_context(
        research
    )

    return f"""
CURRENT TOPIC
============================================================

{topic}

CHANNEL AUDIENCE
============================================================

{channel_config.get("audience", "General audience")}

CHANNEL TONE
============================================================

{channel_config.get("tone", "Curious, cinematic, intelligent")}

LANGUAGE
============================================================

{script_config.get("language", "English")}

============================================================
AVAILABLE VERIFIED SOURCE IDs
============================================================

{", ".join(source_ids)}

Use these EXACT IDs.

============================================================
VERIFIED RESEARCH
============================================================

{research_context}

============================================================
PRODUCTION TARGET
============================================================

Create:

7 scenes
14 visuals
45 seconds

Scene durations:

3, 5, 7, 7, 8, 8, 7

============================================================
STORY REQUIREMENT
============================================================

Create one connected story.

The Short should feel like:

HOOK
→ mystery
→ explanation
→ concrete example
→ reframe
→ escalation
→ satisfying payoff

Do not write a list.

Do not write a lecture.

Do not start with a question.

============================================================
CAPTION REQUIREMENT
============================================================

For every scene:

subtitle_text = narration

EXACTLY.

============================================================
SCIENTIFIC FIDELITY
============================================================

Only supplied evidence.

Do not add facts from memory.

Do not strengthen uncertainty.

Do not convert correlation into causation.

Do not invent mechanisms.

Do not invent numbers.

Do not invent study details.

============================================================
NEXT SHORT
============================================================

Generate a specific researchable continuation topic.

Do NOT force it into Scene 7.

Do NOT mention it in the current description.

============================================================
FINAL CHECK BEFORE JSON
============================================================

Confirm internally:

- 7 scenes
- 14 visuals
- 45 seconds
- 2 visuals per scene
- captions exactly match narration
- source IDs are valid
- every factual scene has supporting source IDs
- no unsupported claims
- no causal overclaiming
- Scene 7 completes the current story
- description does not reveal next topic

Return ONLY JSON.
"""


# ============================================================================
# RESPONSE SCHEMA
# ============================================================================

def build_response_schema():

    visual_schema = {
        "type": "object",
        "properties": {

            "segment": {
                "type": "integer",
            },

            "duration": {
                "type": "integer",
            },

            "camera": _enum(VALID_CAMERA),

            "animation": _enum(VALID_ANIMATION),

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
                "items": visual_schema,
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

    source_schema = {
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

    recurring_subject_schema = {
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

    continuity_schema = {
        "type": "object",
        "properties": {

            "recurring_subjects": {
                "type": "array",
                "items": recurring_subject_schema,
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

                    "pace": _enum({
                        "slow",
                        "medium",
                        "fast",
                    }),

                    "pitch": _enum({
                        "low",
                        "medium",
                        "high",
                    }),
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

            "visual_continuity": continuity_schema,

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
                "items": source_schema,
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
            "visual_continuity",
            "retention_self_check",
            "next_short",
            "research_sources",
            "scene_plan",
        ],
    }


# ============================================================================
# JSON PARSER
# ============================================================================

def parse_gemini_json(text):

    if not text:
        raise RuntimeError(
            "Gemini returned an empty response."
        )

    text = text.strip()

    # Direct JSON.
    try:
        result = json.loads(text)

        if isinstance(result, dict):
            return result

    except json.JSONDecodeError:
        pass

    # Markdown fenced JSON.
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
        result = json.loads(cleaned)

        if isinstance(result, dict):
            return result

    except json.JSONDecodeError:
        pass

    # Extract outer JSON object.
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

            result = json.loads(candidate)

            if isinstance(result, dict):
                return result

        except json.JSONDecodeError as error:

            raise RuntimeError(
                f"Failed to parse Gemini JSON: {error}"
            )

    raise RuntimeError(
        "Gemini did not return valid JSON."
    )


# ============================================================================
# CAPTION SYNCHRONIZATION
# ============================================================================

def _sync_captions_to_narration(
    scene,
    index,
):

    narration = _clean(
        scene.get(
            "narration",
            "",
        )
    )

    if not narration:
        raise RuntimeError(
            f"Scene {index} narration is empty."
        )

    # Narration is the ONLY source of truth.
    scene["narration"] = narration
    scene["subtitle_text"] = narration

    tokens = re.findall(
        r"\b[\w'-]+\b",
        narration,
    )

    if not tokens:
        raise RuntimeError(
            f"Scene {index} narration has no usable words."
        )

    existing = scene.get(
        "caption_highlights",
        [],
    )

    if not isinstance(existing, list):
        existing = []

    lookup = {
        token.lower(): token
        for token in tokens
    }

    highlights = []
    used = set()

    for item in existing:

        if not isinstance(item, dict):
            continue

        word = _clean(
            item.get(
                "word",
                "",
            )
        )

        key = word.lower()

        emphasis = _clean(
            item.get(
                "emphasis",
                "strong",
            )
        )

        if (
            key
            and
            key in lookup
            and
            key not in used
            and
            emphasis in VALID_EMPHASIS
        ):

            highlights.append({
                "word": lookup[key],
                "emphasis": emphasis,
            })

            used.add(key)

    if not highlights:

        candidates = [
            token
            for token in tokens
            if len(token) >= 4
        ]

        if not candidates:
            candidates = tokens

        strongest = max(
            candidates,
            key=len,
        )

        highlights = [{
            "word": strongest,
            "emphasis": "strong",
        }]

    scene["caption_highlights"] = highlights[:3]


# ============================================================================
# IMAGE PROMPT CLEANING
# ============================================================================

def _clean_image_prompt(visual):

    prompt = _clean(
        visual.get(
            "image_prompt",
            "",
        )
    )

    prompt = prompt.replace(
        "```",
        "",
    )

    forbidden = [
        r"\baspect ratio\b",
        r"\b16:9\b",
        r"\b9:16\b",
        r"\bnegative prompt\b",
        r"\btext overlay\b",
        r"\bwatermark\b",
        r"\blogo\b",
        r"\bsubtitles?\b",
        r"\bnarration\b",
        r"\byoutube\b",
    ]

    for pattern in forbidden:

        prompt = re.sub(
            pattern,
            "",
            prompt,
            flags=re.IGNORECASE,
        )

    return _clean(prompt)


# ============================================================================
# VISUAL REPAIR
# ============================================================================

def _repair_visual(
    visual,
    scene_index,
    visual_index,
):

    if not isinstance(visual, dict):
        raise RuntimeError(
            f"Scene {scene_index} visual "
            f"{visual_index} is invalid."
        )

    visual["segment"] = visual_index

    defaults = {
        "camera": "medium",
        "animation": "zoom_in",
        "zoom_strength": "subtle",
        "motion_intensity": "medium",
        "visual_complexity": "moderate",
        "image_style": "realistic_3d_render",
        "lighting": "natural cinematic lighting",
        "color_palette": "natural cinematic tones",
        "overlay": {
            "type": "none",
            "description": "",
        },
        "visual_impact": 7,
    }

    for key, value in defaults.items():

        if key not in visual:
            visual[key] = value

    if not isinstance(
        visual.get("overlay"),
        dict,
    ):

        visual["overlay"] = {
            "type": "none",
            "description": "",
        }

    overlay = visual["overlay"]

    if overlay.get("type") not in VALID_OVERLAY_TYPE:
        overlay["type"] = "none"

    overlay["description"] = _clean(
        overlay.get(
            "description",
            "",
        )
    )

    if visual["camera"] not in VALID_CAMERA:
        visual["camera"] = "medium"

    if visual["animation"] not in VALID_ANIMATION:
        visual["animation"] = "zoom_in"

    if visual["zoom_strength"] not in VALID_ZOOM_STRENGTH:
        visual["zoom_strength"] = "subtle"

    if visual["motion_intensity"] not in VALID_MOTION_INTENSITY:
        visual["motion_intensity"] = "medium"

    if visual["visual_complexity"] not in VALID_VISUAL_COMPLEXITY:
        visual["visual_complexity"] = "moderate"

    if visual["image_style"] not in VALID_IMAGE_STYLE:
        visual["image_style"] = "realistic_3d_render"

    visual["lighting"] = _clean(
        visual.get(
            "lighting",
            "",
        )
    )

    visual["color_palette"] = _clean(
        visual.get(
            "color_palette",
            "",
        )
    )

    visual["image_prompt"] = _clean_image_prompt(
        visual
    )

    if not visual["image_prompt"]:
        raise RuntimeError(
            f"Scene {scene_index} visual "
            f"{visual_index} has an empty image_prompt."
        )

    impact = _safe_int(
        visual.get(
            "visual_impact",
            7,
        ),
        7,
    )

    visual["visual_impact"] = max(
        1,
        min(
            10,
            impact,
        ),
    )

    visual["zoom_factor"] = ZOOM_FACTORS[
        visual["zoom_strength"]
    ]

    visual["motion_speed"] = MOTION_SPEEDS[
        visual["motion_intensity"]
    ]

    visual["needs_regeneration"] = (
        visual["visual_impact"] < 5
    )


# ============================================================================
# VISUAL DURATIONS
# ============================================================================

def _allocate_visual_durations(scene_duration):

    base = scene_duration // VISUALS_PER_SCENE

    remainder = scene_duration % VISUALS_PER_SCENE

    durations = [
        base
        for _ in range(VISUALS_PER_SCENE)
    ]

    for index in range(remainder):
        durations[index] += 1

    return durations


# ============================================================================
# VISUAL CONTINUITY
# ============================================================================

def _normalize_visual_continuity(script):

    continuity = script.get(
        "visual_continuity",
        {},
    )

    if not isinstance(continuity, dict):
        continuity = {}

    subjects = continuity.get(
        "recurring_subjects",
        [],
    )

    if not isinstance(subjects, list):
        subjects = []

    normalized_subjects = []

    for subject in subjects:

        if not isinstance(subject, dict):
            continue

        name = _clean(
            subject.get(
                "name",
                "",
            )
        )

        appearance = _clean(
            subject.get(
                "appearance",
                "",
            )
        )

        if not name or not appearance:
            continue

        normalized_subjects.append({
            "name": name[:100],

            "type": _clean(
                subject.get(
                    "type",
                    "",
                )
            )[:80],

            "appearance": appearance[:600],

            "continuity": (
                _clean(
                    subject.get(
                        "continuity",
                        "",
                    )
                )
                or
                "Maintain the same appearance throughout the Short."
            )[:400],
        })

    objects = continuity.get(
        "recurring_objects",
        [],
    )

    if not isinstance(objects, list):
        objects = []

    rules = continuity.get(
        "continuity_rules",
        [],
    )

    if not isinstance(rules, list):
        rules = []

    script["visual_continuity"] = {
        "recurring_subjects":
            normalized_subjects[:15],

        "recurring_objects": [
            _clean(item)[:200]
            for item in objects
            if _clean(item)
        ][:20],

        "recurring_environment":
            _clean(
                continuity.get(
                    "recurring_environment",
                    "",
                )
            )[:600],

        "continuity_rules": [
            _clean(item)[:400]
            for item in rules
            if _clean(item)
        ][:20],
    }


# ============================================================================
# NEXT SHORT
# ============================================================================

def _normalize_next_short(script):

    item = script.get(
        "next_short",
        {},
    )

    if not isinstance(item, dict):
        item = {}

    topic = _clean(
        item.get(
            "topic",
            "",
        )
    )

    teaser = _clean(
        item.get(
            "teaser",
            "",
        )
    )

    reason = _clean(
        item.get(
            "why_viewers_should_return",
            "",
        )
    )

    cta = _clean(
        item.get(
            "subscription_cta",
            "",
        )
    )

    if not topic:
        raise RuntimeError(
            "next_short.topic is empty."
        )

    if len(topic) > MAX_NEXT_SHORT_CHARACTERS:
        raise RuntimeError(
            "next_short.topic exceeds "
            f"{MAX_NEXT_SHORT_CHARACTERS} characters."
        )

    if not teaser:
        raise RuntimeError(
            "next_short.teaser is empty."
        )

    script["next_short"] = {
        "topic": topic,

        "teaser": teaser[:220],

        "why_viewers_should_return": (
            reason or teaser
        )[:220],

        "subscription_cta": (
            cta
            or
            "Follow for the next science story."
        )[:160],
    }


# ============================================================================
# DESCRIPTION SAFETY
# ============================================================================

def _validate_description(script):

    description = _clean(
        script.get(
            "description",
            "",
        )
    )

    if not description:
        raise RuntimeError(
            "Video description is empty."
        )

    next_short = script.get(
        "next_short",
        {},
    )

    if not isinstance(next_short, dict):
        return

    next_topic = _clean(
        next_short.get(
            "topic",
            "",
        )
    ).lower()

    if not next_topic:
        return

    stop_words = {
        "what",
        "why",
        "how",
        "when",
        "where",
        "which",
        "does",
        "this",
        "that",
        "these",
        "those",
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
        "about",
        "your",
        "our",
        "their",
        "will",
        "can",
        "could",
        "would",
    }

    topic_words = [
        word
        for word in re.findall(
            r"[A-Za-z0-9'-]+",
            next_topic,
        )
        if (
            len(word) >= 4
            and word not in stop_words
        )
    ]

    if len(topic_words) < 2:
        return

    description_words = set(
        re.findall(
            r"[A-Za-z0-9'-]+",
            description.lower(),
        )
    )

    overlap = [
        word
        for word in set(topic_words)
        if word in description_words
    ]

    unique_count = len(set(topic_words))

    if unique_count == 2:
        reject = len(overlap) == 2
    else:
        reject = (
            len(overlap) >= 2
            and
            len(overlap) >= int(
                unique_count * 0.7
            )
        )

    if reject:
        raise RuntimeError(
            "Current description appears to reveal "
            "the next Short topic.\n"
            f"Next topic: {next_topic}\n"
            f"Matching words: {overlap}\n"
            f"Description: {description}"
        )

    script["description"] = description


# ============================================================================
# RESEARCH SOURCE NORMALIZATION
# ============================================================================

def _normalize_research_sources(
    script,
    verified_research,
):

    normalized = []

    seen_ids = set()

    for index, source in enumerate(
        verified_research["sources"],
        start=1,
    ):

        source_id = _clean(
            source.get(
                "source_id",
                "",
            )
        )

        if not source_id:
            raise RuntimeError(
                f"Verified source {index} has no source_id."
            )

        if source_id in seen_ids:
            raise RuntimeError(
                f"Duplicate verified source ID: {source_id}"
            )

        seen_ids.add(source_id)

        evidence = _extract_source_evidence(
            source
        )

        if not evidence:
            raise RuntimeError(
                f"Verified source {source_id} "
                "has no evidence_text."
            )

        normalized.append({
            "source_id": source_id,

            "title": _clean(
                source.get(
                    "title",
                    "",
                )
            )[:300],

            "authors": _clean(
                source.get(
                    "authors",
                    "",
                )
            )[:500],

            "organization": _clean(
                source.get(
                    "organization",
                    "",
                )
            )[:250],

            "journal": _clean(
                source.get(
                    "journal",
                    "",
                )
            )[:250],

            "year": _safe_int(
                source.get(
                    "year",
                    0,
                ),
                0,
            ),

            "doi": _clean(
                source.get(
                    "doi",
                    "",
                )
            ),

            "url": _clean(
                source.get(
                    "url",
                    "",
                )
            ),

            "source_database": _clean(
                source.get(
                    "source_database",
                    "",
                )
            ),

            "source_type": _clean(
                source.get(
                    "source_type",
                    "paper",
                )
            ),

            "priority": _clean(
                source.get(
                    "priority",
                    "secondary",
                )
            ),

            "verified": True,

            "verification": (
                _clean(
                    source.get(
                        "verification",
                        "",
                    )
                )
                or
                "Verified by research.py"
            ),
        })

    if not normalized:
        raise RuntimeError(
            "No verified research sources available."
        )

    script["research_sources"] = normalized


# ============================================================================
# SOURCE ID VALIDATION
# ============================================================================

def _validate_source_ids(script):

    valid_ids = {
        _clean(source.get("source_id", ""))
        for source in script.get(
            "research_sources",
            [],
        )
        if isinstance(source, dict)
        and _clean(source.get("source_id", ""))
    }

    if not valid_ids:
        raise RuntimeError(
            "No verified research source IDs available."
        )

    scenes = script.get(
        "scene_plan",
        [],
    )

    if not isinstance(scenes, list):
        raise RuntimeError(
            "scene_plan must be a list."
        )

    for index, scene in enumerate(
        scenes,
        start=1,
    ):

        source_ids = scene.get(
            "source_ids",
            [],
        )

        if not isinstance(source_ids, list):
            raise RuntimeError(
                f"Scene {index} source_ids must be a list."
            )

        cleaned = []

        for source_id in source_ids:

            source_id = _clean(source_id)

            if not source_id:
                continue

            if source_id not in valid_ids:
                raise RuntimeError(
                    f"Scene {index} references invalid "
                    f"source ID: {source_id}"
                )

            if source_id not in cleaned:
                cleaned.append(source_id)

        scene["source_ids"] = cleaned

        # Every scene except purely stylistic ending language should
        # have evidence attached.
        #
        # We deliberately do not automatically invent citations.
        if not cleaned:
            purpose = scene.get(
                "purpose",
                "",
            )

            if purpose not in {
                "ending",
            }:
                raise RuntimeError(
                    f"Scene {index} contains factual/story content "
                    "but has no source_ids."
                )


# ============================================================================
# SCENE COMPATIBILITY FIELDS
# ============================================================================

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

    scene["image_prompt"] = primary.get(
        "image_prompt",
        "",
    )

    scene["image_style"] = primary.get(
        "image_style",
        "realistic_3d_render",
    )

    scene["lighting"] = primary.get(
        "lighting",
        "",
    )

    scene["color_palette"] = primary.get(
        "color_palette",
        "",
    )

    scene["camera"] = primary.get(
        "camera",
        "medium",
    )

    scene["visual_role"] = scene.get(
        "visual_priority",
        "supporting",
    )

    scene["mood"] = scene.get(
        "emotional_tone",
        "curious",
    )

    if not isinstance(identity, dict):
        identity = {}

    style = _clean(
        identity.get(
            "style",
            "",
        )
    )

    palette = _clean(
        identity.get(
            "palette",
            "",
        )
    )

    mood_arc = _clean(
        identity.get(
            "mood_arc",
            "",
        )
    )

    scene["visual_identity"] = ". ".join(
        value
        for value in [
            style,
            palette,
            mood_arc,
        ]
        if value
    )


# ============================================================================
# SCENE VALIDATION
# ============================================================================

def _validate_scene(
    scene,
    index,
):

    required = [
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

    for key in required:

        if key not in scene:
            raise RuntimeError(
                f"Scene {index} missing '{key}'."
            )

    if _safe_int(scene["scene"]) != index:
        raise RuntimeError(
            f"Scene {index} has invalid scene number."
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

    narration = _clean(
        scene["narration"]
    )

    if not narration:
        raise RuntimeError(
            f"Scene {index} narration is empty."
        )

    scene["narration"] = narration

    # Hard caption synchronization.
    _sync_captions_to_narration(
        scene,
        index,
    )

    duration = _safe_int(
        scene["duration"],
        -1,
    )

    expected_duration = SCENE_DURATIONS[
        index - 1
    ]

    if duration != expected_duration:
        raise RuntimeError(
            f"Scene {index} duration must be "
            f"{expected_duration}s."
        )

    scene["duration"] = duration

    pause = _safe_int(
        scene.get(
            "pause_after_ms",
            0,
        ),
        0,
    )

    scene["pause_after_ms"] = max(
        0,
        min(
            600,
            pause,
        ),
    )

    if not isinstance(
        scene.get("sfx_cue"),
        dict,
    ):

        scene["sfx_cue"] = {
            "term": "",
            "at_ms": 0,
        }

    visuals = scene.get(
        "visuals",
        [],
    )

    if not isinstance(visuals, list):
        raise RuntimeError(
            f"Scene {index} visuals must be a list."
        )

    if len(visuals) != VISUALS_PER_SCENE:
        raise RuntimeError(
            f"Scene {index} must contain "
            f"{VISUALS_PER_SCENE} visuals."
        )

    visual_durations = _allocate_visual_durations(
        duration
    )

    prompts = []

    visual_total = 0

    for visual_index, visual in enumerate(
        visuals,
        start=1,
    ):

        _repair_visual(
            visual,
            index,
            visual_index,
        )

        visual["duration"] = visual_durations[
            visual_index - 1
        ]

        visual_total += visual["duration"]

        prompts.append(
            visual["image_prompt"]
            .lower()
            .strip()
        )

    if len(set(prompts)) != VISUALS_PER_SCENE:
        raise RuntimeError(
            f"Scene {index} contains duplicate visual prompts."
        )

    if visual_total != duration:
        raise RuntimeError(
            f"Scene {index} visual durations do not match "
            f"scene duration."
        )

    return scene


# ============================================================================
# TOP LEVEL VALIDATION
# ============================================================================

def _validate_top_level(script):

    required = [
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

    for key in required:

        if key not in script:
            raise RuntimeError(
                f"Missing required key: {key}"
            )


# ============================================================================
# COMPLETE VALIDATION
# ============================================================================

def validate_script(
    script,
    verified_research,
):

    if not isinstance(script, dict):
        raise RuntimeError(
            "Generated script must be a JSON object."
        )

    _validate_top_level(script)

    scenes = script.get(
        "scene_plan",
        [],
    )

    if not isinstance(scenes, list):
        raise RuntimeError(
            "scene_plan must be a list."
        )

    if len(scenes) != SCENE_COUNT:
        raise RuntimeError(
            f"Expected {SCENE_COUNT} scenes, "
            f"got {len(scenes)}."
        )

    # ------------------------------------------------------------
    # Normalize first.
    # ------------------------------------------------------------

    _normalize_visual_continuity(script)

    _normalize_next_short(script)

    # ------------------------------------------------------------
    # Validate scenes.
    # ------------------------------------------------------------

    total_duration = 0
    total_visuals = 0

    seed = random.randint(
        1,
        2_147_483_647,
    )

    for index, scene in enumerate(
        scenes,
        start=1,
    ):

        _validate_scene(
            scene,
            index,
        )

        # Scene 7 is always the ending.
        if index == SCENE_COUNT:

            scene["purpose"] = "ending"

            scene["transition"] = "none"

        total_duration += scene["duration"]

        total_visuals += len(
            scene["visuals"]
        )

        _add_scene_visual_compatibility(
            scene,
            script.get(
                "visual_identity",
                {},
            ),
        )

    if total_duration != TARGET_SECONDS:
        raise RuntimeError(
            f"Total duration must be "
            f"{TARGET_SECONDS}s, got {total_duration}s."
        )

    if total_visuals != TOTAL_VISUALS:
        raise RuntimeError(
            f"Total visuals must be "
            f"{TOTAL_VISUALS}, got {total_visuals}."
        )

    # ------------------------------------------------------------
    # Copy authoritative research metadata.
    # ------------------------------------------------------------

    _normalize_research_sources(
        script,
        verified_research,
    )

    # ------------------------------------------------------------
    # Validate source references.
    # ------------------------------------------------------------

    _validate_source_ids(script)

    # ------------------------------------------------------------
    # Scientific safety gate.
    # ------------------------------------------------------------

    _validate_claim_strength(script)

    # ------------------------------------------------------------
    # Current description must not reveal next topic.
    # ------------------------------------------------------------

    _validate_description(script)

    # ------------------------------------------------------------
    # Metadata normalization.
    # ------------------------------------------------------------

    script["title"] = _clean(
        script.get(
            "title",
            "",
        )
    )[:MAX_TITLE_LENGTH]

    if not script["title"]:
        raise RuntimeError(
            "Video title is empty."
        )

    script["description"] = _clean(
        script.get(
            "description",
            "",
        )
    )[:MAX_DESCRIPTION_LENGTH]

    tags = script.get(
        "tags",
        [],
    )

    if not isinstance(tags, list):
        tags = []

    normalized_tags = []

    for tag in tags:

        tag = _clean(tag).lower()

        if not tag:
            continue

        if tag not in normalized_tags:
            normalized_tags.append(tag)

    script["tags"] = normalized_tags[:MAX_TAGS]

    category = _clean(
        script.get(
            "category",
            "",
        )
    ).lower()

    if category not in VALID_CATEGORY:
        category = "biology"

    script["category"] = category

    script["thumbnail_prompt"] = _clean(
        script.get(
            "thumbnail_prompt",
            "",
        )
    )

    # ------------------------------------------------------------
    # Image generation configuration.
    # ------------------------------------------------------------

    identity = script.get(
        "visual_identity",
        {},
    )

    if not isinstance(identity, dict):
        identity = {}

    style_lock_parts = [
        _clean(
            identity.get(
                "style",
                "",
            )
        ),

        _clean(
            identity.get(
                "palette",
                "",
            )
        ),

        _clean(
            identity.get(
                "mood_arc",
                "",
            )
        ),
    ]

    style_lock_parts = [
        part
        for part in style_lock_parts
        if part
    ]

    style_lock = ", ".join(
        style_lock_parts
    )

    script["image_generation"] = {
        "seed": seed,
        "style_lock": style_lock,
        "images_per_scene": VISUALS_PER_SCENE,
        "total_images": TOTAL_VISUALS,
        "visual_continuity_enabled": True,
    }

    # ------------------------------------------------------------
    # Runtime metadata.
    # ------------------------------------------------------------

    script["video_id"] = (
        f"{_slugify(script['title'])}-"
        f"{uuid.uuid4().hex[:8]}"
    )

    script["generated_at"] = int(
        time.time()
    )

    script["video_structure"] = {
        "format": "short_form",

        "scene_count": SCENE_COUNT,

        "target_duration_seconds":
            TARGET_SECONDS,

        "actual_duration_seconds":
            total_duration,

        "visuals_per_scene":
            VISUALS_PER_SCENE,

        "total_visuals":
            total_visuals,
    }

    # ------------------------------------------------------------
    # Publishing state.
    # ------------------------------------------------------------

    script["publishing"] = {

        "research_verified":
            True,

        "research_sources_require_verification":
            False,

        "citations_ready":
            True,

        "next_short_teaser_ready":
            True,

        "next_short_spoken_in_scene_7":
            False,

        "subscription_strategy":
            "next_short_continuation",

        "visual_continuity_enabled":
            True,

        "claim_verification_required":
            True,

        "captions_match_narration":
            True,

        "caption_source":
            "scene.narration",

        "claim_strength_guard_enabled":
            True,
    }

    return script


# ============================================================================
# GENERATION
# ============================================================================

def generate_script(
    topic,
    config,
    research,
):

    # ------------------------------------------------------------------------
    # Research gate.
    # ------------------------------------------------------------------------

    research = validate_research_package(
        research,
        topic,
    )

    print("=" * 80)
    print("🔬 VERIFIED RESEARCH GATE PASSED")
    print("=" * 80)

    print(
        f"Verified evidence sources: "
        f"{len(research['sources'])}"
    )

    for source in research["sources"]:

        source_id = _clean(
            source.get(
                "source_id",
                "",
            )
        )

        evidence = _extract_source_evidence(
            source
        )

        print(
            f"✅ {source_id}: "
            f"{source.get('title', '')}"
        )

        print(
            f"   Evidence: "
            f"{len(evidence)} characters"
        )

    print("=" * 80)

    # ------------------------------------------------------------------------
    # Gemini.
    # ------------------------------------------------------------------------

    api_key = _get_api_key()

    client = genai.Client(
        api_key=api_key
    )

    base_prompt = build_user_prompt(
        topic,
        config,
        research,
    )

    system_prompt = build_system_prompt()

    response_schema = build_response_schema()

    print("=" * 80)
    print("✍️ GENERATING RESEARCH-FIRST SHORT")
    print("=" * 80)

    print(
        f"Model: {MODEL_NAME}"
    )

    print(
        f"Scenes: {SCENE_COUNT}"
    )

    print(
        f"Visuals: {TOTAL_VISUALS}"
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
            f"{attempt}/{MAX_GENERATION_ATTEMPTS}"
        )

        try:

            attempt_prompt = base_prompt

            if attempt > 1 and last_error:

                attempt_prompt += f"""

============================================================
RETRY REQUIRED
============================================================

The previous generation failed validation.

PREVIOUS ERROR:

{last_error}

Generate the COMPLETE JSON again.

Do not merely describe the correction.

============================================================
NON-NEGOTIABLE REQUIREMENTS
============================================================

7 scenes.

14 visuals.

45 seconds.

Durations:

3, 5, 7, 7, 8, 8, 7.

Every scene has exactly 2 visuals.

subtitle_text MUST exactly equal narration.

Use only supplied evidence.

Use exact supplied source IDs.

Scene 7 must finish the current story.

Do not force next_short.topic into Scene 7.

The current description must not reveal the next topic.

============================================================
SCIENTIFIC LANGUAGE
============================================================

Do not strengthen evidence.

Do not use unsupported:

proves
proven
proof
causes
caused
causing
results in
essential
guarantees
confirmed
confirms
definitively
definitely
certainly
always
never
without doubt
no doubt

If the evidence says "may", preserve "may".

If the evidence says "associated with", preserve
"associated with".

If the evidence says "suggests", preserve that uncertainty.

============================================================
STORY QUALITY
============================================================

Do not turn the Short into a list.

Do not repeat the same point.

Each scene must advance the story.

Scene 7 must provide a satisfying payoff.

Return ONLY JSON.
"""

            response = client.models.generate_content(

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

            response_text = getattr(
                response,
                "text",
                None,
            )

            if not response_text:
                raise RuntimeError(
                    "Gemini returned an empty response."
                )

            script = parse_gemini_json(
                response_text
            )

            # ----------------------------------------------------------------
            # Topic belongs to pipeline.
            # ----------------------------------------------------------------

            script["topic"] = topic

            # ----------------------------------------------------------------
            # Captions are forcibly derived from narration BEFORE validation.
            # ----------------------------------------------------------------

            scenes = script.get(
                "scene_plan",
                [],
            )

            if isinstance(scenes, list):

                for scene in scenes:

                    if isinstance(scene, dict):

                        narration = _clean(
                            scene.get(
                                "narration",
                                "",
                            )
                        )

                        if narration:
                            scene[
                                "subtitle_text"
                            ] = narration

            # ----------------------------------------------------------------
            # Complete validation.
            # ----------------------------------------------------------------

            script = validate_script(
                script,
                research,
            )

            # ----------------------------------------------------------------
            # Success.
            # ----------------------------------------------------------------

            print("=" * 80)
            print("✅ SHORT SCRIPT ACCEPTED")
            print("=" * 80)

            print(
                f"Scenes: {SCENE_COUNT}"
            )

            print(
                f"Visuals: {TOTAL_VISUALS}"
            )

            print(
                f"Duration: {TARGET_SECONDS}s"
            )

            print(
                "Research sources: "
                f"{len(script['research_sources'])}"
            )

            cited_scenes = sum(
                1
                for scene in script["scene_plan"]
                if scene.get("source_ids")
            )

            print(
                "Scenes with citations: "
                f"{cited_scenes}/{SCENE_COUNT}"
            )

            print(
                "Next Short: "
                f"{script['next_short']['topic']}"
            )

            print(
                "Next topic forced into Scene 7: NO"
            )

            print(
                "Captions match narration: YES"
            )

            print(
                "Claim-strength guard: PASSED"
            )

            print(
                "Research: VERIFIED"
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

            if attempt < MAX_GENERATION_ATTEMPTS:

                delay = 4 * attempt

                print(
                    f"⏳ Retrying in {delay}s..."
                )

                time.sleep(delay)

    raise RuntimeError(
        "SCRIPT GENERATION FAILED.\n\n"
        "The pipeline rejected all generated storyboards.\n\n"
        f"Last validation error:\n{last_error}"
    )


# ============================================================================
# LOCAL TEST
# ============================================================================

if __name__ == "__main__":

    print(
        "generate_script.py is a pipeline module."
    )

    print(
        "Run the complete pipeline through main.py."
    )