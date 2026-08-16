"""
generate_script.py
Mint-YT-Factory

Version 10.4

Research-first production script generator.

IMPORTANT:
- Gemini may ONLY use supplied verified research evidence.
- Gemini may NOT use outside knowledge.
- Gemini may NOT invent sources or evidence.
- evidence_text is authoritative.
- source_id comes only from research.py.
- research_sources are copied from research.py.
- Factual claims require citations.
- Purely stylistic scenes may contain zero citations.
- verify_claims.py remains the final claim-verification gate.
- next_short.topic has no 8-word limit.
- Scene 7 MUST verbally tease the next Short.
- The current video's description must NOT contain the next topic.
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
   Give a satisfying insight about the current topic.
   Then verbally tease the next Short.
   The next topic must NOT be hidden only in metadata.
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
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is missing."
        )

    return api_key


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

    return slug[:40] or "video"


def _check_enum(value, allowed, label):
    if value not in allowed:
        raise RuntimeError(
            f"{label}: invalid value '{value}'. "
            f"Allowed values: {sorted(allowed)}"
        )


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_style_lock(identity):
    if not isinstance(identity, dict):
        return ""

    parts = [
        _clean(identity.get("style", "")),
        _clean(identity.get("palette", "")),
        _clean(identity.get("mood_arc", "")),
    ]

    parts = [x for x in parts if x]

    if not parts:
        return ""

    return "Consistent visual identity: " + ", ".join(parts)


# ==========================================================================
# RESEARCH VALIDATION
# ==========================================================================

def validate_research_package(research, topic):

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

    sources = research.get("sources", [])

    if not isinstance(sources, list):
        raise RuntimeError(
            "RESEARCH GATE FAILED: sources must be a list."
        )

    verified_sources = []
    seen_source_ids = set()

    for index, source in enumerate(sources, start=1):

        if not isinstance(source, dict):
            continue

        if source.get("verified") is not True:
            continue

        if source.get("evidence_verified") is not True:
            continue

        if source.get("evidence_available") is not True:
            continue

        source_id = _clean(
            source.get("source_id", "")
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

        title = _clean(source.get("title", ""))
        authors = _clean(source.get("authors", ""))
        url = _clean(source.get("url", ""))
        doi = _clean(source.get("doi", ""))
        evidence = _extract_source_evidence(source)

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

        seen_source_ids.add(source_id)
        verified_sources.append(source)

    if len(verified_sources) < MIN_VERIFIED_SOURCES:
        raise RuntimeError(
            "RESEARCH GATE FAILED: "
            f"Only {len(verified_sources)} "
            "verified evidence-backed source(s) are available. "
            f"Minimum required: {MIN_VERIFIED_SOURCES}."
        )

    research_topic = _clean(
        research.get("topic", "")
    )

    if research_topic:
        if research_topic.lower() != topic.strip().lower():
            print(
                "⚠️ Research topic differs slightly from generated topic."
            )

    research["sources"] = verified_sources
    research["source_count"] = len(verified_sources)
    research["evidence_source_count"] = len(verified_sources)

    return research


# ==========================================================================
# EVIDENCE
# ==========================================================================

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


# ==========================================================================
# RESEARCH CONTEXT
# ==========================================================================

def build_research_context(research):

    blocks = []
    seen_ids = set()

    for index, source in enumerate(
        research["sources"],
        start=1,
    ):

        if not isinstance(source, dict):
            raise RuntimeError(
                f"Research source {index} is invalid."
            )

        source_id = _clean(
            source.get("source_id", "")
        )

        if not source_id:
            raise RuntimeError(
                f"Research source {index} has no source_id."
            )

        if source_id in seen_ids:
            raise RuntimeError(
                f"Duplicate research source_id detected: {source_id}"
            )

        seen_ids.add(source_id)

        evidence = _extract_source_evidence(source)

        if not evidence:
            raise RuntimeError(
                f"Research source {source_id} "
                "has no authoritative evidence_text."
            )

        block = f"""
============================================================
VERIFIED SOURCE ID: {source_id}
============================================================

IDENTITY / METADATA

Source ID:
{source_id}

Title:
{_clean(source.get("title", ""))}

Authors:
{_clean(source.get("authors", ""))}

Journal / Venue:
{_clean(source.get("journal", ""))}

Year:
{source.get("year", "")}

DOI:
{_clean(source.get("doi", ""))}

URL:
{_clean(source.get("url", ""))}

Database:
{_clean(source.get("source_database", ""))}

Verification Level:
{_clean(source.get("verification_level", ""))}

IMPORTANT:
Metadata identifies the source.
Metadata itself is NOT scientific evidence.

============================================================
SUPPLIED SCIENTIFIC EVIDENCE
============================================================

Evidence Available:
{source.get("evidence_available", False)}

Evidence Type:
{_clean(source.get("evidence_type", "abstract"))}

Evidence Quality:
{_clean(source.get("evidence_quality", "high"))}

Evidence Text:
{evidence}

============================================================
END SOURCE {source_id}
============================================================
"""

        blocks.append(block.strip())

    if not blocks:
        raise RuntimeError(
            "No verified research sources are available."
        )

    return "\n\n".join(blocks)


# ==========================================================================
# SYSTEM PROMPT
# ==========================================================================

def build_system_prompt(
    scene_count=SCENE_COUNT,
    target_seconds=TARGET_SECONDS,
):

    return f"""
You are an expert educational YouTube Shorts writer and visual director.

Create a scientifically responsible YouTube Short using ONLY the
VERIFIED RESEARCH EVIDENCE supplied by the user.

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
- invented mechanisms
- invented citations
- unsupported assumptions

If the evidence does not support a fact:

DO NOT INCLUDE THAT FACT.

============================================================
METADATA VS EVIDENCE
============================================================

Title, authors, journal, year, DOI and URL identify a source.

They are NOT evidence.

ONLY "SUPPLIED SCIENTIFIC EVIDENCE" may support factual claims.

============================================================
CLAIM STRENGTH
============================================================

Preserve the exact strength of the evidence.

"may" must remain "may".

"associated with" must not become "causes".

"possible" must not become "proven".

"hypothesis" must not become "fact".

Observational evidence must not become causal claims.

============================================================
SOURCE IDs
============================================================

Source IDs are supplied directly from research.py.

Use EXACTLY those IDs.

NEVER:

- create source_1/source_2
- renumber IDs
- rename IDs
- invent IDs
- replace IDs with positional IDs

For factual scenes, source_ids MUST contain the exact supporting IDs.

Purely stylistic scenes may use source_ids: [].

============================================================
WRITING
============================================================

- Grade 6 reading level.
- Short punchy sentences.
- Natural spoken narration.
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
- Do not pad with unsupported facts.

============================================================
FORMAT
============================================================

Exactly {scene_count} scenes.

Exactly {VISUALS_PER_SCENE} visuals per scene.

Exactly {TOTAL_VISUALS} visuals.

Exactly {target_seconds} seconds.

Scene durations:

3, 5, 7, 7, 8, 8, 7 seconds.

{BEAT_TABLE}

============================================================
CRITICAL NEXT-SHORT RULE
============================================================

The next Short is part of the channel's continuation strategy.

Scene 7 MUST verbally mention the next topic.

This is NOT optional.

The viewer must hear what the next Short is about.

Do NOT merely create:

- an internal next_short object
- a metadata teaser
- a description teaser

The NEXT SHORT TOPIC MUST APPEAR IN SCENE 7 NARRATION.

Example structure:

"That raises an even bigger question: how does the brain actually
combine these signals to guide the bird? That's what we'll look at
next."

The exact wording should be natural and specific to the next topic.

Do NOT say:

"Coming next."

Do NOT sound like an advertisement.

Do NOT dump the full research title unnaturally.

Make the transition feel like the natural next chapter of the story.

Scene 7 should:

1. Resolve the current story.
2. Create one curiosity gap.
3. Verbally introduce the next topic.
4. Make the viewer want the next Short.

The next topic must be researchable and specific.

next_short.topic has NO 8-word limit.

============================================================
DESCRIPTION RULE
============================================================

The current video's description is ONLY for the current video.

DO NOT mention:

- the next Short topic
- the next video's title
- the next video's subject
- a detailed description of the next video

The next topic belongs ONLY in:

1. Scene 7 narration.
2. next_short.topic.
3. next_short.teaser.
4. next_short.why_viewers_should_return.

Do not reveal it in the current video's description.

============================================================
VISUALS
============================================================

Exactly 2 visuals per scene.

Visual 1 establishes the idea.

Visual 2 advances or reveals the next part.

Recurring subjects and environments must remain consistent.

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

    research_context = build_research_context(research)

    source_ids = []

    for index, source in enumerate(
        research["sources"],
        start=1,
    ):

        source_id = _clean(
            source.get("source_id", "")
        )

        if not source_id:
            raise RuntimeError(
                f"Research source {index} has no source_id."
            )

        source_ids.append(source_id)

    channel_config = config.get(
        "channel",
        {},
    )

    script_config = config.get(
        "script",
        {},
    )

    return f"""
TOPIC:
{topic}

AUDIENCE:
{channel_config.get("audience", "")}

TONE:
{channel_config.get("tone", "")}

LANGUAGE:
{script_config.get("language", "English")}

============================================================
VERIFIED RESEARCH EVIDENCE
============================================================

Available source IDs:

{", ".join(source_ids)}

These IDs come directly from research.py.

Use these EXACT IDs.

Do not invent or rename them.

Only supplied scientific evidence may support factual claims.

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

Durations:

3, 5, 7, 7, 8, 8, 7

============================================================
NEXT SHORT REQUIREMENT
============================================================

Scene 7 MUST actually SAY the next Short topic in the narration.

The next topic must be a natural continuation of the current story.

The viewer should understand what the next video will explore
without reading the description.

Do not merely put the next topic inside next_short.

The next topic must be spoken in Scene 7.

next_short.topic has NO 8-word limit.

============================================================
CURRENT DESCRIPTION REQUIREMENT
============================================================

The current video's description must describe ONLY the current video.

Do NOT mention or reveal:

- the next Short topic
- the next video's title
- the next video's subject
- the next video's research question

The next topic must remain outside the current description.

============================================================
CITATIONS
============================================================

Factual scientific claims require supporting source IDs.

Purely stylistic language may use [].

Never invent source IDs.

Use the minimum necessary sources.

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
- use information not present in supplied evidence

Return ONLY JSON.
"""


# ==========================================================================
# RESPONSE SCHEMA
# ==========================================================================

def build_response_schema():

    visual = {
        "type": "object",
        "properties": {
            "segment": {"type": "integer"},
            "duration": {"type": "integer"},
            "camera": _enum(VALID_CAMERA),
            "animation": _enum(VALID_ANIMATION),
            "zoom_strength": _enum(VALID_ZOOM_STRENGTH),
            "motion_intensity": _enum(VALID_MOTION_INTENSITY),
            "visual_complexity": _enum(VALID_VISUAL_COMPLEXITY),
            "image_style": _enum(VALID_IMAGE_STYLE),
            "lighting": {"type": "string"},
            "color_palette": {"type": "string"},
            "overlay": {
                "type": "object",
                "properties": {
                    "type": _enum(VALID_OVERLAY_TYPE),
                    "description": {"type": "string"},
                },
                "required": [
                    "type",
                    "description",
                ],
            },
            "image_prompt": {"type": "string"},
            "visual_impact": {"type": "integer"},
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
            "scene": {"type": "integer"},
            "purpose": _enum(VALID_PURPOSE),
            "retention_purpose": _enum(
                VALID_RETENTION_PURPOSE
            ),
            "narration": {"type": "string"},
            "source_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "subtitle_text": {"type": "string"},
            "caption_highlights": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "word": {"type": "string"},
                        "emphasis": _enum(VALID_EMPHASIS),
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
            "emphasis_word": {"type": "string"},
            "duration": {"type": "integer"},
            "pause_after_ms": {"type": "integer"},
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
                    "term": {"type": "string"},
                    "at_ms": {"type": "integer"},
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
            "source_id": {"type": "string"},
            "title": {"type": "string"},
            "authors": {"type": "string"},
            "organization": {"type": "string"},
            "journal": {"type": "string"},
            "year": {"type": "integer"},
            "doi": {"type": "string"},
            "url": {"type": "string"},
            "source_database": {"type": "string"},
            "source_type": {"type": "string"},
            "priority": {"type": "string"},
            "verified": {"type": "boolean"},
            "verification": {"type": "string"},
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
            "name": {"type": "string"},
            "type": {"type": "string"},
            "appearance": {"type": "string"},
            "continuity": {"type": "string"},
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
                "items": recurring_subject,
            },
            "recurring_objects": {
                "type": "array",
                "items": {"type": "string"},
            },
            "recurring_environment": {
                "type": "string",
            },
            "continuity_rules": {
                "type": "array",
                "items": {"type": "string"},
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
            "title": {"type": "string"},
            "description": {"type": "string"},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
            },
            "category": _enum(VALID_CATEGORY),
            "thumbnail_prompt": {"type": "string"},
            "voice_style": {
                "type": "object",
                "properties": {
                    "tone": {"type": "string"},
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
                    "search": {"type": "string"},
                    "arc": {"type": "string"},
                },
                "required": [
                    "search",
                    "arc",
                ],
            },
            "visual_identity": {
                "type": "object",
                "properties": {
                    "style": {"type": "string"},
                    "palette": {"type": "string"},
                    "mood_arc": {"type": "string"},
                },
                "required": [
                    "style",
                    "palette",
                    "mood_arc",
                ],
            },
            "visual_continuity": visual_continuity,
            "retention_self_check": {
                "type": "object",
                "properties": {
                    "weakest_scene": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": [
                    "weakest_scene",
                    "reason",
                ],
            },
            "next_short": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "teaser": {"type": "string"},
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
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
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
            candidate,
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


# ==========================================================================
# CAPTIONS
# ==========================================================================

def _repair_caption_highlights(scene, index):

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
    used = set()

    existing = scene.get(
        "caption_highlights",
        [],
    )

    if not isinstance(existing, list):
        existing = []

    for item in existing:

        if not isinstance(item, dict):
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

        key = word.lower()

        if (
            key in lookup
            and emphasis in VALID_EMPHASIS
            and key not in used
        ):

            result.append({
                "word": lookup[key],
                "emphasis": emphasis,
            })

            used.add(key)

    if not result:

        word = max(
            tokens,
            key=len,
        )

        result = [{
            "word": word,
            "emphasis": "strong",
        }]

    scene["caption_highlights"] = result[:3]


# ==========================================================================
# IMAGE PROMPT
# ==========================================================================

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

    forbidden_patterns = [
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

    for pattern in forbidden_patterns:
        prompt = re.sub(
            pattern,
            "",
            prompt,
            flags=re.IGNORECASE,
        )

    return _clean(prompt)


# ==========================================================================
# VISUAL REPAIR
# ==========================================================================

def _repair_visual(
    visual,
    scene_index,
    visual_index,
):

    visual["segment"] = visual_index

    defaults = {
        "camera": "medium",
        "animation": "zoom_in",
        "zoom_strength": "subtle",
        "motion_intensity": "medium",
        "visual_complexity": "moderate",
        "image_style": "realistic_3d_render",
        "lighting": "soft cinematic directional lighting",
        "color_palette": "cinematic natural tones",
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

    visual["overlay"].setdefault(
        "description",
        "",
    )

    if visual["overlay"].get(
        "type"
    ) not in VALID_OVERLAY_TYPE:
        visual["overlay"]["type"] = "none"

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

    impact = _safe_int(
        visual.get("visual_impact", 7),
        7,
    )

    visual["visual_impact"] = max(
        1,
        min(10, impact),
    )

    visual["lighting"] = _clean(
        visual.get("lighting", "")
    )

    visual["color_palette"] = _clean(
        visual.get("color_palette", "")
    )

    visual["image_prompt"] = _clean_image_prompt(
        visual
    )

    if not visual["image_prompt"]:
        raise RuntimeError(
            f"Scene {scene_index} visual {visual_index} "
            "has an empty image_prompt."
        )


# ==========================================================================
# VISUAL DURATIONS
# ==========================================================================

def _allocate_visual_durations(scene_duration):

    base = scene_duration // VISUALS_PER_SCENE
    remainder = scene_duration % VISUALS_PER_SCENE

    durations = [base] * VISUALS_PER_SCENE

    for index in range(remainder):
        durations[index] += 1

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

    scene["visual_identity"] = (
        f"{identity.get('style', '')}. "
        f"{identity.get('palette', '')}. "
        f"{identity.get('mood_arc', '')}"
    ).strip()


# ==========================================================================
# NEXT SHORT
# ==========================================================================

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
            "next_short.topic is too long. "
            f"Maximum allowed is {MAX_NEXT_SHORT_CHARACTERS} characters."
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
            "Follow the channel so you don't miss the next part."
        )[:160],
    }


# ==========================================================================
# NEXT SHORT SPOKEN VALIDATION
# ==========================================================================

def _validate_next_short_is_spoken(script):

    scenes = script.get(
        "scene_plan",
        [],
    )

    if not scenes:
        raise RuntimeError(
            "Cannot validate next-short narration: scene_plan is empty."
        )

    final_scene = scenes[-1]

    narration = _clean(
        final_scene.get(
            "narration",
            "",
        )
    )

    next_short = script.get(
        "next_short",
        {},
    )

    topic = _clean(
        next_short.get(
            "topic",
            "",
        )
    )

    if not narration:
        raise RuntimeError(
            "Scene 7 narration is empty."
        )

    if not topic:
        raise RuntimeError(
            "next_short.topic is empty."
        )

    # ----------------------------------------------------------------------
    # Ignore generic words that do not meaningfully identify a topic.
    # ----------------------------------------------------------------------

    stop_words = {
        "what",
        "why",
        "how",
        "when",
        "where",
        "which",
        "does",
        "do",
        "did",
        "can",
        "could",
        "would",
        "will",
        "should",
        "are",
        "is",
        "was",
        "were",
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "from",
        "your",
        "our",
        "their",
        "this",
        "that",
        "these",
        "those",
    }

    topic_tokens = [
        word.lower()
        for word in re.findall(
            r"[A-Za-z0-9'-]+",
            topic,
        )
    ]

    meaningful_topic_words = [
        word
        for word in topic_tokens
        if (
            len(word) >= 5
            and word not in stop_words
        )
    ]

    # Short topics may not contain two 5+ character words.
    if len(meaningful_topic_words) < 2:

        meaningful_topic_words = [
            word
            for word in topic_tokens
            if (
                len(word) >= 4
                and word not in stop_words
            )
        ]

    if not meaningful_topic_words:
        raise RuntimeError(
            "next_short.topic does not contain enough "
            "meaningful words for spoken validation."
        )

    # ----------------------------------------------------------------------
    # Extract words from Scene 7.
    # ----------------------------------------------------------------------

    narration_words = {
        word.lower()
        for word in re.findall(
            r"[A-Za-z0-9'-]+",
            narration,
        )
    }

    matching_words = [
        word
        for word in set(meaningful_topic_words)
        if word in narration_words
    ]

    overlap = len(matching_words)

    required_overlap = min(
        2,
        len(set(meaningful_topic_words)),
    )

    # ----------------------------------------------------------------------
    # At least two meaningful topic words must actually be spoken.
    # ----------------------------------------------------------------------

    if overlap < required_overlap:

        raise RuntimeError(
            "Scene 7 does not clearly mention the "
            "next Short topic.\n"
            f"Next topic: '{topic}'\n"
            f"Meaningful topic words: "
            f"{meaningful_topic_words}\n"
            f"Words found in Scene 7: "
            f"{matching_words}\n"
            f"Scene 7 narration: '{narration}'"
        )

    # ----------------------------------------------------------------------
    # Require a natural continuation cue.
    #
    # This prevents vague endings such as:
    #
    # "And that's the mystery."
    #
    # from passing even when topic words happen to occur naturally.
    # ----------------------------------------------------------------------

    continuation_patterns = [
        r"\bnext\b",
        r"\bnext short\b",
        r"\bnext time\b",
        r"\bwe'?ll see\b",
        r"\bwe'?ll look\b",
        r"\bwe'?ll explore\b",
        r"\bthat raises\b",
        r"\bthat leaves\b",
        r"\bthe bigger question\b",
        r"\bthe question is\b",
        r"\bbut then\b",
        r"\bwhich raises\b",
    ]

    has_continuation_cue = any(
        re.search(
            pattern,
            narration,
            flags=re.IGNORECASE,
        )
        for pattern in continuation_patterns
    )

    if not has_continuation_cue:

        raise RuntimeError(
            "Scene 7 mentions the next topic, but does not "
            "contain a clear continuation cue."
        )

    print(
        "✅ Scene 7 verbally introduces the next Short."
    )

    print(
        f"   Next topic: {topic}"
    )

    print(
        f"   Topic words spoken: "
        f"{overlap}/{required_overlap}"
    )


# ==========================================================================
# DESCRIPTION VALIDATION
# ==========================================================================

def _validate_description_does_not_contain_next_topic(script):

    description = _clean(
        script.get(
            "description",
            "",
        )
    ).lower()

    next_short = script.get(
        "next_short",
        {},
    )

    topic = _clean(
        next_short.get(
            "topic",
            "",
        )
    ).lower()

    if not description or not topic:
        return

    stop_words = {
        "what",
        "why",
        "how",
        "when",
        "where",
        "which",
        "does",
        "do",
        "did",
        "can",
        "could",
        "would",
        "will",
        "should",
        "are",
        "is",
        "was",
        "were",
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "from",
        "your",
        "our",
        "their",
        "this",
        "that",
        "these",
        "those",
    }

    topic_words = [
        word
        for word in re.findall(
            r"[A-Za-z0-9'-]+",
            topic,
        )
        if (
            len(word) >= 5
            and word not in stop_words
        )
    ]

    if len(topic_words) < 2:

        topic_words = [
            word
            for word in re.findall(
                r"[A-Za-z0-9'-]+",
                topic,
            )
            if (
                len(word) >= 4
                and word not in stop_words
            )
        ]

    if not topic_words:
        return

    description_words = set(
        re.findall(
            r"[A-Za-z0-9'-]+",
            description,
        )
    )

    meaningful_overlap = [
        word
        for word in set(topic_words)
        if word in description_words
    ]

    overlap_count = len(
        meaningful_overlap
    )

    unique_topic_words = len(
        set(topic_words)
    )

    # ----------------------------------------------------------------------
    # Only reject when the description contains a substantial portion
    # of the distinctive next-topic wording.
    #
    # Two-word topics require both words.
    # Longer topics require roughly 70% overlap.
    # ----------------------------------------------------------------------

    if unique_topic_words == 2:

        should_reject = (
            overlap_count == 2
        )

    else:

        should_reject = (
            overlap_count >= 2
            and
            overlap_count
            >= int(
                unique_topic_words * 0.7
            )
        )

    if should_reject:

        raise RuntimeError(
            "Current video's description appears to reveal "
            "the next Short topic.\n"
            f"Next topic: '{topic}'\n"
            f"Matching words: {meaningful_overlap}\n"
            f"Description: '{description}'"
        )


# ==========================================================================
# RESEARCH NORMALIZATION
# ==========================================================================

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

        if not isinstance(source, dict):
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
                f"Duplicate verified research source_id: {source_id}"
            )

        seen_ids.add(source_id)

        evidence = _extract_source_evidence(source)

        if not evidence:
            raise RuntimeError(
                f"Verified source {source_id} "
                "has no evidence_text."
            )

        normalized.append({
            "source_id": source_id,
            "title": _clean(
                source.get("title", "")
            )[:300],
            "authors": _clean(
                source.get("authors", "")
            )[:500],
            "organization": _clean(
                source.get("organization", "")
            )[:250],
            "journal": _clean(
                source.get("journal", "")
            )[:250],
            "year": _safe_int(
                source.get("year", 0),
                0,
            ),
            "doi": _clean(
                source.get("doi", "")
            ),
            "url": _clean(
                source.get("url", "")
            ),
            "source_database": _clean(
                source.get("source_database", "")
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
            "No verified research sources could be normalized."
        )

    script["research_sources"] = normalized


# ==========================================================================
# SOURCE ID VALIDATION
# ==========================================================================

def _validate_source_ids(script):

    valid_ids = set()

    for source in script.get(
        "research_sources",
        [],
    ):

        if not isinstance(source, dict):
            continue

        source_id = _clean(
            source.get(
                "source_id",
                "",
            )
        )

        if source_id:
            valid_ids.add(source_id)

    if not valid_ids:
        raise RuntimeError(
            "No verified research source IDs are attached to script."
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

        cleaned_ids = []

        for source_id in source_ids:

            source_id = _clean(source_id)

            if not source_id:
                continue

            if source_id not in valid_ids:
                raise RuntimeError(
                    f"Scene {index} references invalid "
                    f"source ID: {source_id}"
                )

            if source_id not in cleaned_ids:
                cleaned_ids.append(source_id)

        scene["source_ids"] = cleaned_ids


# ==========================================================================
# VISUAL CONTINUITY
# ==========================================================================

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
            "appearance": appearance[:500],
            "continuity": (
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
            normalized_subjects,

        "recurring_objects": [
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

        "continuity_rules": [
            _clean(x)[:300]
            for x in rules
            if _clean(x)
        ][:20],
    }


# ==========================================================================
# TOP LEVEL VALIDATION
# ==========================================================================

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


# ==========================================================================
# SCENE VALIDATION
# ==========================================================================

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

    scene["narration"] = narration
    scene["subtitle_text"] = subtitle

    _repair_caption_highlights(
        scene,
        index,
    )

    source_ids = scene.get(
        "source_ids",
        [],
    )

    if not isinstance(source_ids, list):
        raise RuntimeError(
            f"Scene {index} source_ids must be a list."
        )

    scene["source_ids"] = list(
        dict.fromkeys(
            _clean(source_id)
            for source_id in source_ids
            if _clean(source_id)
        )
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
        min(600, pause),
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

    durations = _allocate_visual_durations(
        duration
    )

    visual_sum = 0
    prompts = []

    for visual_index, visual in enumerate(
        visuals,
        start=1,
    ):

        if not isinstance(visual, dict):
            raise RuntimeError(
                f"Scene {index} visual "
                f"{visual_index} is invalid."
            )

        _repair_visual(
            visual,
            index,
            visual_index,
        )

        visual["duration"] = durations[
            visual_index - 1
        ]

        visual_sum += visual["duration"]

        visual["zoom_factor"] = ZOOM_FACTORS[
            visual["zoom_strength"]
        ]

        visual["motion_speed"] = MOTION_SPEEDS[
            visual["motion_intensity"]
        ]

        visual["needs_regeneration"] = (
            visual["visual_impact"] < 5
        )

        prompts.append(
            visual["image_prompt"]
            .lower()
            .strip()
        )

    if len(set(prompts)) != VISUALS_PER_SCENE:
        raise RuntimeError(
            f"Scene {index} contains duplicate visual prompts."
        )

    if visual_sum != duration:
        raise RuntimeError(
            f"Scene {index} visual durations do not match."
        )

    return scene


# ==========================================================================
# COMPLETE VALIDATION
# ==========================================================================

def validate_script(
    script,
    verified_research,
):

    if not isinstance(script, dict):
        raise RuntimeError(
            "Generated script must be a JSON object."
        )

    _validate_top_level(script)

    scenes = script["scene_plan"]

    if not isinstance(scenes, list):
        raise RuntimeError(
            "scene_plan must be a list."
        )

    if len(scenes) != SCENE_COUNT:
        raise RuntimeError(
            f"Expected {SCENE_COUNT} scenes but got "
            f"{len(scenes)}."
        )

    _normalize_visual_continuity(script)
    _normalize_next_short(script)

    total_duration = 0
    total_visuals = 0
    hold_count = 0

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

        if index == SCENE_COUNT:

            scene["purpose"] = "ending"
            scene["transition"] = "none"

        total_duration += scene["duration"]

        total_visuals += len(
            scene["visuals"]
        )

        for visual in scene["visuals"]:

            if visual["animation"] == "hold":
                hold_count += 1

        _add_scene_visual_compatibility(
            scene,
            script["visual_identity"],
        )

    if hold_count > 1:
        raise RuntimeError(
            "'hold' animation used more than once."
        )

    if total_duration != TARGET_SECONDS:
        raise RuntimeError(
            f"Total duration must be "
            f"{TARGET_SECONDS}s, got "
            f"{total_duration}s."
        )

    if total_visuals != TOTAL_VISUALS:
        raise RuntimeError(
            f"Total visuals must be "
            f"{TOTAL_VISUALS}, got "
            f"{total_visuals}."
        )

    # ----------------------------------------------------------------------
    # Copy authoritative research metadata.
    # ----------------------------------------------------------------------

    _normalize_research_sources(
        script,
        verified_research,
    )

    # ----------------------------------------------------------------------
    # Validate citations.
    # ----------------------------------------------------------------------

    _validate_source_ids(
        script
    )

    # ----------------------------------------------------------------------
    # CRITICAL:
    # Make sure Scene 7 actually talks about the next Short.
    # ----------------------------------------------------------------------

    _validate_next_short_is_spoken(
        script
    )

    # ----------------------------------------------------------------------
    # CRITICAL:
    # Make sure current description does not reveal next Short.
    # ----------------------------------------------------------------------

    _validate_description_does_not_contain_next_topic(
        script
    )

    # ----------------------------------------------------------------------
    # Normalize metadata.
    # ----------------------------------------------------------------------

    script["title"] = _clean(
        script["title"]
    )[:60]

    script["description"] = _clean(
        script["description"]
    )

    tags = script.get(
        "tags",
        [],
    )

    if not isinstance(tags, list):
        tags = []

    script["tags"] = list(
        dict.fromkeys(
            _clean(tag).lower()
            for tag in tags
            if _clean(tag)
        )
    )[:12]

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

    style_lock = _build_style_lock(
        script["visual_identity"]
    )

    script["image_generation"] = {
        "seed": seed,
        "style_lock": style_lock,
        "images_per_scene": VISUALS_PER_SCENE,
        "total_images": TOTAL_VISUALS,
        "visual_continuity_enabled": True,
    }

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
        "target_duration_seconds": TARGET_SECONDS,
        "actual_duration_seconds": TARGET_SECONDS,
        "visuals_per_scene": VISUALS_PER_SCENE,
        "total_visuals": TOTAL_VISUALS,
    }

    script["publishing"] = {
        "research_verified": True,
        "research_sources_require_verification": False,
        "citations_ready": True,
        "next_short_teaser_ready": True,
        "next_short_spoken_in_scene_7": True,
        "subscription_strategy": "next_short_continuation",
        "visual_continuity_enabled": True,
        "claim_verification_required": True,
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
        "Verified evidence sources: "
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

    response_schema = build_response_schema()

    print("=" * 80)
    print("✍️ GENERATING RESEARCHED SCRIPT")
    print("=" * 80)

    print(
        f"Model: {MODEL_NAME}"
    )

    print(
        "Verified evidence sources: "
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
            f"{attempt}/{MAX_GENERATION_ATTEMPTS}"
        )

        try:

            attempt_prompt = prompt

            if attempt > 1 and last_error:

                attempt_prompt += f"""

============================================================
RETRY NOTICE
============================================================

The previous storyboard failed validation.

Previous validation error:

{last_error}

Correct the error and return the COMPLETE storyboard.

CRITICAL:

Scene 7 MUST verbally mention the next Short topic.

The next topic must appear naturally in Scene 7 narration.

Do not merely put it in next_short.topic.

Do not merely put it in metadata.

Do not merely put it in the description.

The current video's description must NOT reveal the next topic.

Use exact source IDs supplied by research.py.

Only use supplied evidence.

Exactly 7 scenes.

Exactly 14 visuals.

Exactly 45 seconds.

Durations:

3, 5, 7, 7, 8, 8, 7.

Return ONLY JSON.
"""

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=attempt_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_json_schema=response_schema,
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

            # Topic is controlled by the pipeline.
            script["topic"] = topic

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
                "Next Short topic: "
                f"{script['next_short']['topic']}"
            )

            print(
                "Next Short spoken in Scene 7: YES"
            )

            print(
                "Description does not reveal next topic: YES"
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

            if attempt < MAX_GENERATION_ATTEMPTS:

                delay = 5 * attempt

                print(
                    f"⏳ Retrying in {delay}s..."
                )

                time.sleep(delay)

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