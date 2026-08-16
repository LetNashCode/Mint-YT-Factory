"""
generate_script.py
Mint-YT-Factory

Version 10.1

Research-first production script generator.

FLOW:

research.py
    ↓
Verified research + evidence package
    ↓
Gemini
    ↓
45-second researched Short
    ↓
Citations attached to factual scenes
    ↓
verify_claims.py
    ↓
generate_images.py
    ↓
assemble.py
    ↓
main.py
    ↓
YouTube

IMPORTANT:

- Gemini may ONLY use supplied verified research evidence.
- Gemini may NOT use outside knowledge.
- Gemini may NOT invent sources.
- Gemini may NOT invent evidence.
- Metadata is NOT treated as evidence.
- evidence_text is the authoritative evidence field.
- Evidence must already be verified by research.py.
- Gemini may only choose source IDs from verified research.
- source_id is authoritative and comes from research.py.
- source IDs are NEVER generated from array position.
- research_sources are copied from research.py.
- Gemini does NOT generate research metadata.
- Factual claims require citations.
- Purely stylistic scenes may contain zero citations.
- verify_claims.py remains the final claim-verification gate.
- next_short.topic has no 8-word limit.
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
    3,
    5,
    7,
    7,
    8,
    8,
    7,
]

MIN_VERIFIED_SOURCES = 2

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
   Create an unanswered question based only on verified evidence.

3. EXPLANATION (8-15s)
   Explain the verified mechanism simply.

4. EXAMPLE (15-22s)
   Make the verified mechanism concrete and visual.

5. REFRAME (22-30s)
   Reveal a verified implication that changes how the viewer sees it.

6. ESCALATION (30-38s)
   Add one final verified consequence or perspective shift.

7. ENDING + NEXT SHORT (38-45s)
   Give a satisfying insight and tease the next research topic.
"""


# ==========================================================================
# HELPERS
# ==========================================================================

def _clean(text):

    if text is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(text),
    ).strip()


def _get_api_key():

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "GEMINI_API_KEY environment variable is missing."
        )

    return api_key


def _enum(values):

    return {
        "type": "string",
        "enum": list(values),
    }


def _slugify(text):

    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        str(text).lower(),
    ).strip("-")

    return slug[:40] or "video"


def _check_enum(
    value,
    allowed,
    label,
):

    if value not in allowed:

        raise RuntimeError(
            f"{label}: invalid value '{value}'."
        )


def _build_style_lock(identity):

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
        part
        for part in parts
        if part
    ]

    if not parts:
        return ""

    return (
        "Consistent visual identity: "
        + ", ".join(parts)
    )


# ==========================================================================
# RESEARCH VALIDATION
# ==========================================================================

def validate_research_package(
    research,
    topic,
):
    """
    HARD RESEARCH GATE.

    research.py is the source of truth.

    A source is accepted only when:

    - research package is VERIFIED
    - source is verified
    - source_id exists
    - source_id is unique
    - evidence_verified is True
    - evidence_available is True
    - evidence_text exists
    - title exists
    - authors exist
    - DOI exists
    - URL exists

    IMPORTANT:

    evidence_text is authoritative.

    We intentionally DO NOT fall back to abstract here.
    """

    if not isinstance(
        research,
        dict,
    ):

        raise RuntimeError(
            "RESEARCH GATE FAILED: research package is missing."
        )

    if research.get(
        "verified"
    ) is not True:

        raise RuntimeError(
            "RESEARCH GATE FAILED: research package is not VERIFIED."
        )

    if research.get(
        "status"
    ) != "VERIFIED":

        raise RuntimeError(
            "RESEARCH GATE FAILED: research status is not VERIFIED."
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
            "RESEARCH GATE FAILED: sources must be a list."
        )

    verified_sources = []

    seen_source_ids = set()

    for index, source in enumerate(
        sources,
        start=1,
    ):

        if not isinstance(
            source,
            dict,
        ):
            continue

        if source.get(
            "verified"
        ) is not True:

            continue

        if source.get(
            "evidence_verified"
        ) is not True:

            continue

        if source.get(
            "evidence_available"
        ) is not True:

            continue

        # --------------------------------------------------------------
        # AUTHORITATIVE SOURCE ID
        #
        # This MUST come from research.py.
        #
        # Never create source_1/source_2 based on position.
        # --------------------------------------------------------------

        source_id = _clean(
            source.get(
                "source_id",
                "",
            )
        )

        if not source_id:

            raise RuntimeError(
                "RESEARCH GATE FAILED: "
                f"source at position {index} has no source_id."
            )

        if source_id in seen_source_ids:

            raise RuntimeError(
                "RESEARCH GATE FAILED: "
                f"duplicate source_id '{source_id}'."
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

        seen_source_ids.add(
            source_id
        )

        verified_sources.append(
            source
        )

    if len(
        verified_sources
    ) < MIN_VERIFIED_SOURCES:

        raise RuntimeError(
            "RESEARCH GATE FAILED: "
            f"Only {len(verified_sources)} "
            "verified evidence-backed source(s) are available. "
            f"Minimum required: {MIN_VERIFIED_SOURCES}."
        )

    research_topic = _clean(
        research.get(
            "topic",
            "",
        )
    )

    if research_topic:

        if (
            research_topic.lower()
            != topic.strip().lower()
        ):

            print(
                "⚠️ Research topic differs slightly from generated topic."
            )

    research[
        "sources"
    ] = verified_sources

    research[
        "source_count"
    ] = len(
        verified_sources
    )

    research[
        "evidence_source_count"
    ] = len(
        verified_sources
    )

    return research


# ==========================================================================
# EVIDENCE EXTRACTION
# ==========================================================================

def _extract_source_evidence(
    source,
):
    """
    Extract ONLY the authoritative evidence_text.

    IMPORTANT:

    research.py is responsible for creating and verifying evidence_text.

    generate_script.py must not create, summarize, combine, or invent
    evidence.

    We deliberately do NOT fall back to:

    - abstract
    - title
    - metadata
    - evidence_summary
    - evidence_chunks

    This keeps research.py as the single source of truth.
    """

    if not isinstance(
        source,
        dict,
    ):

        return ""

    evidence = source.get(
        "evidence_text",
        "",
    )

    if not isinstance(
        evidence,
        str,
    ):

        return ""

    return _clean(
        evidence
    )


# ==========================================================================
# BUILD RESEARCH CONTEXT
# ==========================================================================

def build_research_context(
    research,
):
    """
    Build a strict evidence package for Gemini.

    IMPORTANT:

    source_id is supplied by research.py and is authoritative.

    generate_script.py MUST NOT create source IDs based on array
    position.

    Metadata is provided only for source identification.

    Scientific evidence is provided separately.

    Gemini must never treat title, DOI, journal, authors or URL
    as evidence.
    """

    sources = research[
        "sources"
    ]

    blocks = []

    seen_ids = set()

    for index, source in enumerate(
        sources,
        start=1,
    ):

        if not isinstance(
            source,
            dict,
        ):

            raise RuntimeError(
                f"Research source {index} is invalid."
            )

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
                f"Duplicate research source_id detected: "
                f"{source_id}"
            )

        seen_ids.add(
            source_id
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

        journal = _clean(
            source.get(
                "journal",
                "",
            )
        )

        year = source.get(
            "year",
            "",
        )

        doi = _clean(
            source.get(
                "doi",
                "",
            )
        )

        url = _clean(
            source.get(
                "url",
                "",
            )
        )

        database = _clean(
            source.get(
                "source_database",
                "",
            )
        )

        evidence = _extract_source_evidence(
            source
        )

        if not evidence:

            raise RuntimeError(
                f"Research source {source_id} "
                "has no authoritative evidence_text."
            )

        evidence_type = _clean(
            source.get(
                "evidence_type",
                "abstract",
            )
        )

        evidence_quality = _clean(
            source.get(
                "evidence_quality",
                "high",
            )
        )

        block = f"""
============================================================
VERIFIED SOURCE ID: {source_id}
============================================================

IDENTITY / METADATA
-------------------

Source ID:
{source_id}

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

Verification Level:
{_clean(source.get("verification_level", ""))}

Evidence Verified:
{source.get("evidence_verified", False)}

IMPORTANT:
The metadata above identifies the source.
Metadata itself is NOT scientific evidence.

============================================================
SUPPLIED SCIENTIFIC EVIDENCE
============================================================

Evidence Available:
{source.get("evidence_available", False)}

Evidence Type:
{evidence_type}

Evidence Quality:
{evidence_quality}

Evidence Text:
{evidence}

============================================================
END SOURCE {source_id}
============================================================
"""

        blocks.append(
            block.strip()
        )

    if not blocks:

        raise RuntimeError(
            "No verified research sources are available."
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
the VERIFIED RESEARCH EVIDENCE supplied by the user.

============================================================
ABSOLUTE RESEARCH RULE
============================================================

The supplied research evidence is the ONLY permitted evidence.

You MUST NOT use:

- general knowledge
- model memory
- internet knowledge
- outside scientific knowledge
- invented studies
- invented statistics
- invented dates
- invented institutions
- invented scientific mechanisms
- invented citations
- unsupported assumptions

You may use normal storytelling language, but any factual scientific
statement must be supported by the supplied evidence.

If the evidence does not support a fact:

DO NOT INCLUDE THAT FACT.

============================================================
METADATA VS EVIDENCE
============================================================

Source title, authors, journal, year, DOI and URL identify a source.

They are NOT evidence by themselves.

Only the section marked:

SUPPLIED SCIENTIFIC EVIDENCE

may be used as evidence for factual claims.

Do not infer scientific findings merely from a paper title.

============================================================
CLAIM STRENGTH
============================================================

Preserve the strength of the research.

If evidence says:

"may"

do not write:

"does."

If evidence says:

"associated with"

do not write:

"causes."

If evidence says:

"possible"

do not write:

"proven."

If evidence says:

"hypothesis"

do not write:

"fact."

If evidence is observational, do not turn it into a causal claim.

============================================================
SOURCE IDs
============================================================

The available source IDs are supplied directly by research.py.

They are authoritative.

IMPORTANT:

You MUST use the exact source IDs provided in the research
evidence package.

Do NOT:

- create source_1/source_2 yourself
- renumber source IDs
- rename source IDs
- invent source IDs
- replace authoritative IDs with positional IDs
- assume the first source is source_1
- assume the second source is source_2

A source ID may look like:

ABC123
paper_7f91
research_4d82
or another identifier.

Use exactly what is supplied.

For every scene containing factual scientific claims:

"source_ids" MUST contain the source IDs supporting those claims.

The source IDs must come ONLY from the supplied source list.

A scene containing only stylistic/storytelling language may use:

"source_ids": []

Do NOT add citations simply because a scene exists.

============================================================
IMPORTANT FACTUAL CLAIMS
============================================================

Important factual claims include statements about:

- mechanisms
- causes
- effects
- biological processes
- physical processes
- chemical processes
- measurable quantities
- scientific observations
- research findings
- relationships between variables
- dates
- numbers
- percentages
- historical facts
- scientific conclusions

Purely stylistic sentences do not require citations.

Examples:

"Here's where it gets strange."

Not a factual claim.

"But the deeper you go, the story changes."

This may be storytelling language and does not automatically require
a citation.

However:

"Pressure increases rapidly with depth."

This is factual and requires supporting evidence.

============================================================
CITATION PRECISION
============================================================

Use the smallest set of sources necessary.

If one supplied source supports a claim:

["ACTUAL_SOURCE_ID"]

Do not automatically cite all sources.

If two supplied sources are necessary:

[
    "ACTUAL_SOURCE_ID_1",
    "ACTUAL_SOURCE_ID_2"
]

Do not cite a source that does not actually support the claim.

============================================================
SOURCE METADATA
============================================================

The "research_sources" field is NOT generated from your own knowledge.

The pipeline will overwrite it with the exact verified metadata from
research.py.

Do not invent research source metadata.

Do not modify source IDs.

============================================================
FORMAT
============================================================

- Exactly {scene_count} scenes.
- Exactly {VISUALS_PER_SCENE} visuals per scene.
- Exactly {TOTAL_VISUALS} visuals total.
- Exactly {target_seconds} seconds.

Scene durations:

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
- Do not pad the script with unsupported facts.

============================================================
VISUALS
============================================================

Exactly 2 visuals per scene.

Visual 1 establishes the idea.

Visual 2 advances or reveals the next part.

Recurring subjects, objects and environments must remain visually
consistent.

============================================================
IMAGE PROMPTS
============================================================

Approximately 15-35 words.

Describe ONLY what should be visible.

Do NOT include:

- camera instructions
- lighting instructions
- aspect ratio
- negative prompts
- text
- logos
- watermarks
- YouTube
- narration
- subtitles
- viewers
- AI

============================================================
NEXT SHORT
============================================================

Scene 7 should create a natural continuation.

The ending must:

1. Deliver a satisfying insight about the current topic.
2. Leave one natural curiosity gap.
3. Introduce a next Short that logically continues that gap.
4. Make the next topic researchable.
5. Make the next topic specific.
6. Avoid simply repeating the current topic.

next_short.topic has NO 8-word limit.

It may be a full descriptive research topic.

Do not shorten it merely to make it shorter.

============================================================
OUTPUT
============================================================

Return ONLY valid JSON matching the supplied response schema.
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

        if not isinstance(
            source,
            dict,
        ):

            raise RuntimeError(
                f"Research source {index} is invalid."
            )

        source_id = _clean(
            source.get(
                "source_id",
                "",
            )
        )

        if not source_id:

            raise RuntimeError(
                f"Research source {index} "
                "does not have a source_id."
            )

        source_ids.append(
            source_id
        )

    audience = (
        config.get(
            "channel",
            {},
        ).get(
            "audience",
            "",
        )
    )

    tone = (
        config.get(
            "channel",
            {},
        ).get(
            "tone",
            "",
        )
    )

    language = (
        config.get(
            "script",
            {},
        ).get(
            "language",
            "English",
        )
    )

    return f"""
TOPIC:
{topic}

AUDIENCE:
{audience}

TONE:
{tone}

LANGUAGE:
{language}

============================================================
VERIFIED RESEARCH EVIDENCE
============================================================

The following sources have passed the research verification gate.

Available source IDs:

{", ".join(source_ids)}

IMPORTANT:

These source IDs come directly from research.py.

You MUST use these exact source IDs when citing evidence.

Do NOT:

- rename them
- create new source IDs
- replace them with source_1/source_2 unless those are the actual
  IDs supplied by research.py
- invent citations
- infer source IDs from their order

The source metadata identifies each source.

Only the supplied scientific evidence sections may be used to
support factual claims.

Do not use outside knowledge.

Do not infer facts from titles.

============================================================

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
CITATION RULE
============================================================

For each scene:

- If narration contains factual scientific claims, provide the
  supporting source IDs.
- If narration is purely stylistic, source_ids may be [].
- Never invent source IDs.
- Never cite a source that does not support the claim.
- Use the minimum necessary supporting sources.

Examples:

Factual scene:

"source_ids": ["ACTUAL_SOURCE_ID"]

Two-source claim:

"source_ids": [
    "ACTUAL_SOURCE_ID_1",
    "ACTUAL_SOURCE_ID_2"
]

Purely stylistic scene:

"source_ids": []

============================================================
RESEARCH FIDELITY
============================================================

Do NOT:

- invent facts
- invent statistics
- invent mechanisms
- strengthen uncertainty
- convert correlation into causation
- convert hypotheses into facts
- use general knowledge
- use knowledge not present in the supplied evidence

============================================================
NEXT SHORT
============================================================

next_short.topic is the actual research topic of the NEXT video.

There is NO 8-word limit.

Make it specific and research-ready.

It must naturally follow from the current video's unresolved
curiosity.

Return ONLY JSON.
"""


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
                f"Failed to parse Gemini JSON: {error}"
            )

    raise RuntimeError(
        "Gemini did not return valid JSON."
    )


# ==========================================================================
# CAPTIONS
# ==========================================================================

def _repair_caption_highlights(
    scene,
    index,
):

    subtitle = _clean(
        scene.get(
            "subtitle_text",
            "",
        )
    )

    tokens = re.findall(
        r"\b[\w'-]+\b",
        subtitle,
    )

    if not tokens:

        raise RuntimeError(
            f"Scene {index} subtitle_text contains no usable words."
        )

    lookup = {
        token.lower(): token
        for token in tokens
    }

    result = []

    existing = scene.get(
        "caption_highlights",
        [],
    )

    if not isinstance(
        existing,
        list,
    ):

        existing = []

    for item in existing:

        if not isinstance(
            item,
            dict,
        ):
            continue

        word = _clean(
            item.get(
                "word",
                "",
            )
        )

        emphasis = _clean(
            item.get(
                "emphasis",
                "strong",
            )
        )

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

    return _clean(
        prompt
    )


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

        if key not in visual:

            visual[
                key
            ] = value

    if not isinstance(
        visual.get(
            "overlay"
        ),
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
            f"Scene {scene_index} visual {visual_index} "
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

    for index in range(
        remainder
    ):

        durations[
            index
        ] += 1

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

    item = script.get(
        "next_short",
        {},
    )

    if not isinstance(
        item,
        dict,
    ):

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
            "next_short.topic is too long. "
            f"Maximum allowed is {MAX_NEXT_SHORT_CHARACTERS} characters."
        )

    if not teaser:

        raise RuntimeError(
            "next_short.teaser is empty."
        )

    script[
        "next_short"
    ] = {

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
    """
    IMPORTANT:

    Gemini does not control research_sources.

    We copy the exact verified source metadata from research.py.

    The authoritative source_id is preserved exactly.

    This prevents Gemini from inventing:

    - papers
    - authors
    - DOIs
    - URLs
    - journals
    - source IDs
    - verification information
    """

    normalized = []

    supplied_sources = (
        verified_research[
            "sources"
        ]
    )

    seen_ids = set()

    for index, source in enumerate(
        supplied_sources,
        start=1,
    ):

        if not isinstance(
            source,
            dict,
        ):

            raise RuntimeError(
                f"Verified research source {index} is invalid."
            )

        source_id = _clean(
            source.get(
                "source_id",
                "",
            )
        )

        if not source_id:

            raise RuntimeError(
                f"Verified research source {index} "
                "has no source_id."
            )

        if source_id in seen_ids:

            raise RuntimeError(
                f"Duplicate verified research source_id: "
                f"{source_id}"
            )

        seen_ids.add(
            source_id
        )

        evidence = _extract_source_evidence(
            source
        )

        if not evidence:

            raise RuntimeError(
                f"Verified source {source_id} "
                "has no evidence_text."
            )

        try:

            year = int(
                source.get(
                    "year",
                    0,
                )
                or 0
            )

        except Exception:

            year = 0

        normalized.append({

            "source_id":
                source_id,

            "title":
                _clean(
                    source.get(
                        "title",
                        "",
                    )
                )[:300],

            "authors":
                _clean(
                    source.get(
                        "authors",
                        "",
                    )
                )[:500],

            "organization":
                _clean(
                    source.get(
                        "organization",
                        "",
                    )
                )[:250],

            "journal":
                _clean(
                    source.get(
                        "journal",
                        "",
                    )
                )[:250],

            "year":
                year,

            "doi":
                _clean(
                    source.get(
                        "doi",
                        "",
                    )
                ),

            "url":
                _clean(
                    source.get(
                        "url",
                        "",
                    )
                ),

            "source_database":
                _clean(
                    source.get(
                        "source_database",
                        "",
                    )
                ),

            "source_type":
                _clean(
                    source.get(
                        "source_type",
                        "paper",
                    )
                ),

            "priority":
                _clean(
                    source.get(
                        "priority",
                        "secondary",
                    )
                ),

            "verified":
                True,

            "verification":
                (
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
            "No verified research sources could be normalized."
        )

    script[
        "research_sources"
    ] = normalized


# ==========================================================================
# SOURCE ID VALIDATION
# ==========================================================================

def _validate_source_ids(
    script,
):
    """
    Validate that every scene citation refers to an actual
    authoritative research source ID.

    Source IDs are NOT positional.

    They come directly from research.py and are preserved
    throughout the pipeline.
    """

    valid_ids = set()

    for source in script.get(
        "research_sources",
        [],
    ):

        if not isinstance(
            source,
            dict,
        ):

            continue

        source_id = _clean(
            source.get(
                "source_id",
                "",
            )
        )

        if source_id:

            valid_ids.add(
                source_id
            )

    if not valid_ids:

        raise RuntimeError(
            "No verified research source IDs are attached to script."
        )

    scenes = script.get(
        "scene_plan",
        [],
    )

    if not isinstance(
        scenes,
        list,
    ):

        raise RuntimeError(
            "scene_plan must be a list."
        )

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

        source_ids = scene.get(
            "source_ids",
            [],
        )

        if not isinstance(
            source_ids,
            list,
        ):

            raise RuntimeError(
                f"Scene {index} source_ids must be a list."
            )

        cleaned_ids = []

        for source_id in source_ids:

            source_id = _clean(
                source_id
            )

            if not source_id:

                continue

            if source_id not in valid_ids:

                raise RuntimeError(
                    f"Scene {index} references invalid "
                    f"source ID: {source_id}"
                )

            if source_id not in cleaned_ids:

                cleaned_ids.append(
                    source_id
                )

        scene[
            "source_ids"
        ] = cleaned_ids


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

            "name":
                name[:100],

            "type":
                _clean(
                    subject.get(
                        "type",
                        "",
                    )
                )[:80],

            "appearance":
                appearance[:500],

            "continuity":
                (
                    _clean(
                        subject.get(
                            "continuity",
                            "same appearance throughout",
                        )
                    )
                    or
                    "same appearance throughout"
                )[:300],
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
                _clean(x)[:200]
                for x in objects
                if _clean(x)
            ][:20],

        "recurring_environment":
            _clean(
                continuity.get(
                    "recurring_environment",
                    "",
                )
            )[:500],

        "continuity_rules":
            [
                _clean(x)[:300]
                for x in rules
                if _clean(x)
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
            f"Expected {SCENE_COUNT} scenes but got {len(scenes)}."
        )

    _normalize_visual_continuity(
        script
    )

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
                    f"Scene {index} missing '{key}'."
                )

        if int(
            scene["scene"]
        ) != index:

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

        if index == SCENE_COUNT:

            scene[
                "purpose"
            ] = "ending"

            scene[
                "transition"
            ] = "none"

        narration = _clean(
            scene["narration"]
        )

        subtitle = _clean(
            scene["subtitle_text"]
        )

        if not narration:

            raise RuntimeError(
                f"Scene {index} narration is empty."
            )

        if not subtitle:

            raise RuntimeError(
                f"Scene {index} subtitle is empty."
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

        # ------------------------------------------------------------------
        # SOURCE CITATIONS
        #
        # A scene may legitimately contain no citation if it contains
        # only stylistic/storytelling language.
        #
        # verify_claims.py is responsible for determining whether actual
        # factual claims require citations.
        # ------------------------------------------------------------------

        source_ids = scene.get(
            "source_ids",
            [],
        )

        if not isinstance(
            source_ids,
            list,
        ):

            raise RuntimeError(
                f"Scene {index} source_ids must be a list."
            )

        cleaned_source_ids = []

        for source_id in source_ids:

            source_id = _clean(
                source_id
            )

            if source_id:

                if source_id not in cleaned_source_ids:

                    cleaned_source_ids.append(
                        source_id
                    )

        scene[
            "source_ids"
        ] = cleaned_source_ids

        # ------------------------------------------------------------------
        # DURATION
        # ------------------------------------------------------------------

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
                f"Scene {index} duration must be "
                f"{expected_duration}s."
            )

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
                f"Scene {index} contains duplicate visual prompts."
            )

        if visual_sum != duration:

            raise RuntimeError(
                f"Scene {index} visual durations do not match."
            )

        total_visuals += VISUALS_PER_SCENE

        _add_scene_visual_compatibility(
            scene,
            script[
                "visual_identity"
            ],
        )

    if hold_count > 1:

        raise RuntimeError(
            "'hold' animation used more than once."
        )

    if total_duration != TARGET_SECONDS:

        raise RuntimeError(
            f"Total duration must be {TARGET_SECONDS}s."
        )

    if total_visuals != TOTAL_VISUALS:

        raise RuntimeError(
            f"Total visuals must be {TOTAL_VISUALS}."
        )

    # ----------------------------------------------------------------------
    # COPY VERIFIED RESEARCH
    # ----------------------------------------------------------------------

    _normalize_research_sources(
        script,
        verified_research,
    )

    # ----------------------------------------------------------------------
    # VALIDATE GEMINI'S CITATIONS AGAINST AUTHORITATIVE SOURCE IDs
    # ----------------------------------------------------------------------

    _validate_source_ids(
        script
    )

    # ----------------------------------------------------------------------
    # TOP LEVEL
    # ----------------------------------------------------------------------

    script[
        "title"
    ] = _clean(
        script["title"]
    )[:60]

    script[
        "description"
    ] = _clean(
        script["description"]
    )

    script[
        "tags"
    ] = list(
        dict.fromkeys(
            _clean(tag).lower()
            for tag in script["tags"]
            if _clean(tag)
        )
    )[:12]

    category = _clean(
        script[
            "category"
        ]
    ).lower()

    script[
        "category"
    ] = (
        category
        if category in VALID_CATEGORY
        else "biology"
    )

    script[
        "thumbnail_prompt"
    ] = _clean(
        script[
            "thumbnail_prompt"
        ]
    )

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

        "claim_verification_required":
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

        print(
            f"   Evidence verified: "
            f"{source.get('evidence_verified', False)}"
        )

    print("=" * 80)

    api_key = _get_api_key()

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
        f"Verified evidence sources: "
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

============================================================
RETRY NOTICE
============================================================

Previous validation error:

{last_error}

Correct the error and return the COMPLETE storyboard.

Remember:

- ONLY use supplied verified evidence_text.
- Do NOT use outside knowledge.
- Do NOT invent research.
- Do NOT invent citations.
- Do NOT invent or rename source IDs.
- Use the exact source IDs supplied by research.py.
- Metadata is not evidence.
- Factual claims need supporting source_ids.
- Purely stylistic scenes may use source_ids: [].
- Exactly 7 scenes.
- Exactly 14 visuals.
- Exactly 45 seconds.
- next_short.topic has no 8-word limit.
- Preserve the complete next_short.topic.
- Make the next topic research-ready.
- Make the next topic naturally continue the current story.

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

            # --------------------------------------------------------------
            # The topic is controlled by the pipeline, not Gemini.
            # --------------------------------------------------------------

            script[
                "topic"
            ] = topic

            # --------------------------------------------------------------
            # Validate the generated storyboard.
            # --------------------------------------------------------------

            script = validate_script(
                script,
                research,
            )

            print("=" * 80)
            print("✅ RESEARCHED SCRIPT GENERATED")
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

            cited_scenes = sum(
                1
                for scene in script["scene_plan"]
                if scene.get("source_ids")
            )

            print(
                f"Scenes with citations: "
                f"{cited_scenes}/{SCENE_COUNT}"
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
                "Citations: READY FOR CLAIM VERIFICATION"
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
                    f"⏳ Retrying in {delay}s..."
                )

                time.sleep(
                    delay
                )

    raise RuntimeError(

        "SCRIPT GENERATION FAILED.\n"
        "The pipeline refused to create a Short from "
        "unverified or insufficient research.\n\n"
        f"Last error: {last_error}"
    )


# ==========================================================================
# LOCAL TEST
# ==========================================================================

if __name__ == "__main__":

    print(
        "generate_script.py requires a VERIFIED research package."
    )

    print(
        "Run the complete pipeline through main.py."
    )