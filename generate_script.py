"""
generate_script.py
Mint-YT-Factory

Version 10.1

RESEARCH-FIRST STORY + VISUAL CONTINUITY ENGINE

FIXES IN v10.0
---------------

1. Scene 7 now naturally introduces the NEXT SHORT topic.
2. The next topic is spoken only in Scene 7.
3. The next topic is NOT allowed anywhere else in the current story.
4. The current video's description is generated/validated as CURRENT-TOPIC ONLY.
5. Description validation no longer falsely rejects descriptions merely because
   the current and next topics share common words.
6. next_short remains metadata for the continuation system.
7. Scene 7 must contain a natural open-loop transition into the next topic.
8. The next topic is never presented as part of the current video's factual story.
9. Captions remain synchronized with narration.
10. Existing generate_script(topic, config, research) integration is preserved.

FIXES IN v10.1
---------------

11. Added explicit HOOK / CURIOSITY-GAP evidence-discipline guidance so
    Scene 1 and Scene 2 do not add mechanistic language, named forces,
    or comparisons the supplied evidence does not literally support.
12. generate_script() now accepts an optional extra_feedback string.
    When main.py's outer script/claim-verification cycle detects that a
    generated script failed independent claim verification on genuine
    (non-structural) scientific grounds, it passes the specific rejected
    claims back in here so the next generation attempt can avoid them.
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

MAX_TITLE_LENGTH = 70

MAX_DESCRIPTION_LENGTH = 2000

MAX_TAGS = 12

MIN_IMAGE_PROMPT_WORDS = 12

MAX_IMAGE_PROMPT_WORDS = 45

MAX_RECURRING_SUBJECTS = 15

MAX_RECURRING_OBJECTS = 20

MAX_CONTINUITY_RULES = 20


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
# STORY STRUCTURE
# ============================================================================

STORY_BEATS = """
SCENE 1 — HOOK — 0–3 seconds

Start immediately with the most surprising VERIFIED fact,
consequence, contrast, or visual situation.

Do NOT start with a question.

The first sentence must create immediate curiosity.

The viewer should feel:

"Wait... what?"

The opening should be understandable without context.


------------------------------------------------------------

SCENE 2 — CURIOSITY GAP — 3–8 seconds

Reveal the mystery, contradiction, unexpected detail,
or hidden mechanism behind the hook.

Do not repeat Scene 1.

Create a strong reason to keep watching.


------------------------------------------------------------

SCENE 3 — EXPLANATION — 8–15 seconds

Explain what is happening.

Use only verified evidence.

Make the explanation simple enough for a general audience.

Avoid sounding like a textbook.


------------------------------------------------------------

SCENE 4 — EXAMPLE — 15–22 seconds

Turn the explanation into something concrete.

Show what the mechanism or phenomenon looks like.

The visual should make the concept easier to understand.


------------------------------------------------------------

SCENE 5 — REFRAME — 22–30 seconds

Reveal the implication that changes how the viewer
understands what they just saw.

This should create an:

"Oh... so THAT is what was happening."

moment.


------------------------------------------------------------

SCENE 6 — ESCALATION — 30–38 seconds

Deliver the strongest remaining VERIFIED consequence,
observation, or perspective shift.

Increase the emotional or intellectual stakes.

Do not introduce an unrelated fact.


------------------------------------------------------------

SCENE 7 — PAYOFF + NEXT STORY HOOK — 38–45 seconds

Finish the CURRENT story first.

Then use the final sentence as a short, natural open loop
that introduces the NEXT SHORT topic.

The next topic is metadata supplied separately as:

next_short.topic

The final sentence MAY mention that topic.

The final sentence must NOT present the next topic as a
fact that belongs to the CURRENT story.

Good pattern:

"That is the strange part. But it raises an even bigger question:
[exact next topic]."

Or:

"And that leaves one question worth exploring next:
[exact next topic]."

Or:

"The story ends here, but the next mystery is:
[exact next topic]."

Do NOT say:

"Next we'll..."
"In the next video..."
"Coming next..."
"Stay tuned..."
"Watch my next video..."
"Part 2..."
"Subscribe for..."

The next topic should feel like a curiosity bridge,
not an advertisement.

The current story must still feel complete even if the viewer
never watches another Short.
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


def _safe_int(
    value,
    default=0,
):
    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
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
    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is missing."
        )

    return api_key


def _check_enum(
    value,
    allowed,
    label,
):
    if value not in allowed:
        raise RuntimeError(
            f"{label}: invalid value '{value}'. "
            f"Allowed values: {sorted(allowed)}"
        )


def _word_count(text):
    return len(
        re.findall(
            r"\b[\w'-]+\b",
            _clean(text),
        )
    )


# ============================================================================
# NEXT TOPIC HELPERS
# ============================================================================

def _topic_words(topic):
    """
    Extract meaningful words from a topic.

    This is deliberately conservative. Common words are ignored so that
    descriptions and narration are not rejected simply because both topics
    happen to contain words such as "the", "why", "how", "science", etc.
    """

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
        "should",
        "does",
        "did",
        "are",
        "was",
        "were",
        "is",
        "its",
        "it's",
        "they",
        "them",
        "than",
        "then",
        "really",
        "actually",
        "just",
        "very",
        "most",
        "more",
        "some",
        "one",
        "thing",
        "things",
        "part",
        "next",
        "story",
        "question",
        "mystery",
        "science",
        "scientific",
    }

    words = re.findall(
        r"[A-Za-z0-9'-]+",
        _clean(topic).lower(),
    )

    return [
        word
        for word in words
        if len(word) >= 4
        and word not in stop_words
    ]


def _contains_next_topic(
    text,
    next_topic,
):
    """
    Detects whether text is actually revealing the next topic.

    Exact phrase matching is the strongest signal.

    A second conservative check catches descriptions that reproduce most
    meaningful words from the next topic.

    This intentionally avoids rejecting text based on one or two shared words.
    """

    text_clean = _clean(
        text
    ).lower()

    topic_clean = _clean(
        next_topic
    ).lower()

    if not text_clean or not topic_clean:
        return False

    # Exact topic phrase.
    if topic_clean in text_clean:
        return True

    topic_words = _topic_words(
        topic_clean
    )

    if len(topic_words) < 2:
        return False

    text_words = set(
        re.findall(
            r"[A-Za-z0-9'-]+",
            text_clean,
        )
    )

    overlap = {
        word
        for word in set(topic_words)
        if word in text_words
    }

    # Require almost all meaningful words for short topics.
    if len(topic_words) <= 3:
        return len(overlap) >= len(topic_words)

    # For longer topics require at least 70% and at least 3 words.
    return (
        len(overlap) >= 3
        and
        len(overlap) / len(set(topic_words)) >= 0.70
    )


def _build_next_topic_bridge(
    next_topic
):
    """
    Fallback bridge used only when Gemini fails to naturally mention the next
    topic in Scene 7.

    It is intentionally curiosity-based and does not make a factual claim
    about the next topic.
    """

    next_topic = _clean(
        next_topic
    )

    return (
        "But that leaves one bigger question: "
        f"{next_topic}."
    )


# ============================================================================
# SCIENTIFIC CLAIM SAFETY
# ============================================================================

FORBIDDEN_CLAIM_PATTERNS = [

    r"\bproves\b",
    r"\bproved\b",
    r"\bproven\b",
    r"\bproof\b",

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


def _find_claim_violations(script):

    violations = []

    scenes = script.get(
        "scene_plan",
        [],
    )

    if not isinstance(
        scenes,
        list,
    ):
        return violations

    for index, scene in enumerate(
        scenes,
        start=1,
    ):

        if not isinstance(
            scene,
            dict,
        ):
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

    violations = _find_claim_violations(
        script
    )

    if not violations:
        return

    lines = [
        "SCIENTIFIC CLAIM SAFETY CHECK FAILED.",
        "",
        "The narration contains language that may",
        "strengthen the supplied scientific evidence.",
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
        "Prefer evidence-matched wording such as:",
        "may",
        "might",
        "appears to",
        "suggests",
        "indicates",
        "is associated with",
        "researchers observed",
    ])

    raise RuntimeError(
        "\n".join(lines)
    )


# ============================================================================
# RESEARCH VALIDATION
# ============================================================================

def _extract_source_evidence(
    source
):

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

    return _clean(evidence)


def validate_research_package(
    research,
    topic,
):

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

    seen_ids = set()

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

        seen_ids.add(
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
            f"Only {len(verified_sources)} verified "
            f"evidence-backed source(s) available. "
            f"Minimum required: "
            f"{MIN_VERIFIED_SOURCES}."
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
            "⚠️ Research topic differs slightly "
            "from generated topic."
        )

    research["sources"] = (
        verified_sources
    )

    research["source_count"] = (
        len(verified_sources)
    )

    research["evidence_source_count"] = (
        len(verified_sources)
    )

    return research


# ============================================================================
# RESEARCH CONTEXT
# ============================================================================

def build_research_context(
    research
):

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
                f"Research source {index} "
                "has no source_id."
            )

        if source_id in seen_ids:

            raise RuntimeError(
                f"Duplicate source ID: "
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
                f"Research source "
                f"{source_id} has no evidence_text."
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

    return "\n\n".join(
        blocks
    )


# ============================================================================
# SYSTEM PROMPT
# ============================================================================

def build_system_prompt():

    return f"""
You are the lead writer and visual director for a premium
science-focused YouTube Shorts channel.

Your job is to transform VERIFIED scientific evidence into
one emotionally engaging 45-second story.

The final Short must feel like a human-created story.

It must NOT feel like:

- a textbook
- a lecture
- a list
- a countdown
- an AI-generated collection of facts


============================================================
ABSOLUTE RESEARCH RULE
============================================================

The supplied research evidence is the ONLY factual source
for the CURRENT VIDEO.

You MUST NOT use:

- model memory
- general knowledge
- outside facts
- invented statistics
- invented dates
- invented mechanisms
- invented experiments
- invented researchers
- invented institutions
- invented citations

If the evidence does not support a fact:

DO NOT SAY IT.


============================================================
EVIDENCE STRENGTH
============================================================

Preserve the exact strength of the supplied evidence.

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

preserve that uncertainty.

Never convert:

association → causation

possibility → certainty

observation → universal rule

hypothesis → fact

correlation → mechanism


============================================================
STORY
============================================================

The Short tells ONE connected story.

{STORY_BEATS}

Every scene must move the story forward.

Do not repeat the same information.

Do not introduce unrelated facts.

Do not use generic filler.


============================================================
HOOK
============================================================

Scene 1 must NOT begin with:

"Did you know..."

"Have you ever wondered..."

"Today we're going to..."

"In this video..."

Instead, begin directly with the unusual fact,
situation, consequence, or contradiction.


============================================================
HOOK AND CURIOSITY-GAP EVIDENCE DISCIPLINE
============================================================

Scenes 1 and 2 must still only state what the supplied evidence
directly supports.

Create curiosity through sentence structure, pacing, and framing —
not by adding mechanistic claims, named forces, causes, or
comparisons that are not explicitly present in the evidence text.

If the evidence does not explicitly name a mechanism or cause,
do not introduce one, even briefly, just to make the hook punchier.

A vivid but evidence-bound sentence will always pass claim
verification. A vivid but invented sentence will not.

If you are unsure whether a hook sentence is directly supported,
rewrite it to describe only the observable phenomenon itself,
without explaining why it happens, and let Scene 3 carry the
explanation.


============================================================
NARRATION
============================================================

Use natural spoken English.

Target approximately Grade 6–8 comprehension.

Use short sentences.

Avoid unnecessary technical language.

When a technical concept is essential,
explain it naturally.


============================================================
SCENE 7 NEXT-TOPIC BRIDGE
============================================================

The CURRENT story must be completed before the next topic appears.

Scene 7 should normally follow this structure:

1. Pay off the current story.
2. Add one short transition.
3. Mention next_short.topic as the final curiosity hook.

The next topic MUST be the final topic introduced in narration.

Use the exact or very lightly shortened topic supplied
in next_short.topic.

Do NOT invent a different next topic.

Do NOT discuss facts about the next topic.

Do NOT explain the next topic.

Do NOT answer the next topic.

Only introduce it as the next question/mystery.

Good:

"But that leaves one bigger question: [NEXT TOPIC]."

"And that raises an even bigger question: [NEXT TOPIC]."

"Which leaves one mystery for another story: [NEXT TOPIC]."

Bad:

"Next we'll explain [NEXT TOPIC]."

"In the next video, you'll learn [NEXT TOPIC]."

"Coming next: [NEXT TOPIC]."

"Stay tuned for [NEXT TOPIC]."

"Subscribe to find out [NEXT TOPIC]."


============================================================
CAPTIONS
============================================================

subtitle_text MUST exactly equal narration.

Narration is the single source of truth.

Never paraphrase subtitles.

Never shorten them.


============================================================
SOURCE IDS
============================================================

Use EXACT source IDs supplied by the research package.

Never invent source IDs.

Every factual CURRENT-VIDEO scene must reference one or more
supporting source IDs.

Scene 7's next-topic bridge does NOT require a source because
it is a continuation hook rather than a factual claim.

If Scene 7 contains factual claims about the CURRENT topic,
those claims still require source IDs.


============================================================
DESCRIPTION
============================================================

The description describes ONLY the CURRENT VIDEO.

The description MUST NOT:

- mention next_short
- mention the next topic
- tease the next topic
- say "next video"
- say "coming next"
- say "stay tuned"
- say "part 2"
- describe the continuation topic
- contain the exact next_short.topic

The description should explain the CURRENT topic only.

Do not use the next topic to generate the description.


============================================================
NEXT SHORT
============================================================

Create a specific researchable continuation topic that naturally
follows the CURRENT story.

It is metadata for the next video.

It MUST be mentioned naturally in the final sentence of Scene 7.

It MUST NOT appear anywhere else in the current video's narration.

It MUST NOT appear in the current description.

It MUST NOT be treated as a current-video fact.


============================================================
VISUAL STORYTELLING
============================================================

There are EXACTLY two visuals per scene.

VISUAL 1:

Establish the idea.

VISUAL 2:

Advance, reveal, demonstrate, contrast,
or reframe the idea.

The two visuals MUST NOT be duplicates.

They should feel like consecutive shots
from the same story.


============================================================
VISUAL CONTINUITY
============================================================

If the story contains a recurring:

- person
- animal
- object
- machine
- spacecraft
- cell
- structure
- environment

define it in visual_continuity.

Give it a stable visual identity.

Keep consistent:

- appearance
- proportions
- colors
- clothing
- shape
- design
- environment

unless the story explicitly requires a transformation.


============================================================
VISUAL IDENTITY
============================================================

Create ONE global visual identity for the Short.

It must include:

style
palette
mood_arc

The identity must work across all 14 images.

The images should feel like frames
from the same production.


============================================================
IMAGE PROMPTS
============================================================

Each image_prompt describes ONLY visible content.

Describe:

- subject
- action
- environment
- important objects
- spatial relationship
- visual moment

Do NOT put these inside image_prompt:

- camera instructions
- aspect ratio
- 9:16
- 16:9
- negative prompts
- text
- captions
- subtitles
- logos
- watermarks
- YouTube
- narration
- AI-generated
- camera movement


Camera belongs in:

camera

Animation belongs in:

animation

Lighting belongs in:

lighting

Palette belongs in:

color_palette


============================================================
IMAGE PROMPT LENGTH
============================================================

Image prompts should normally contain
approximately 15–35 words.

Never produce extremely short prompts.

Never create giant paragraphs.


============================================================
VISUAL DIFFERENTIATION
============================================================

For each scene:

Visual 1 should establish.

Visual 2 should change something.

Examples:

wide → close-up

subject → mechanism

before → after

surface → interior

normal → unusual

cause → visible consequence

macro → environment

Do not simply repeat the same composition.


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
        _clean(
            source.get(
                "source_id",
                "",
            )
        )
        for source in research["sources"]
        if _clean(
            source.get(
                "source_id",
                "",
            )
        )
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

{channel_config.get(
    "audience",
    "General audience"
)}


CHANNEL TONE
============================================================

{channel_config.get(
    "tone",
    "Curious, cinematic, intelligent"
)}


LANGUAGE
============================================================

{script_config.get(
    "language",
    "English"
)}


============================================================
AVAILABLE VERIFIED SOURCE IDS
============================================================

{", ".join(source_ids)}

Use ONLY these exact IDs.


============================================================
VERIFIED RESEARCH
============================================================

{research_context}


============================================================
PRODUCTION CONTRACT
============================================================

Exactly:

7 scenes

14 visuals

45 seconds

2 visuals per scene


Scene durations:

Scene 1 = 3 seconds
Scene 2 = 5 seconds
Scene 3 = 7 seconds
Scene 4 = 7 seconds
Scene 5 = 8 seconds
Scene 6 = 8 seconds
Scene 7 = 7 seconds


============================================================
STORY
============================================================

Build ONE connected story:

HOOK
→ CURIOSITY
→ EXPLANATION
→ EXAMPLE
→ REFRAME
→ ESCALATION
→ PAYOFF
→ NEXT STORY CURIOSITY HOOK


Do not write a list.

Do not write a countdown.

Do not start with a question.

Do not introduce unrelated facts.


============================================================
CURRENT VIDEO DESCRIPTION
============================================================

The description must describe ONLY:

{topic}

Do not mention the next topic.

Do not mention next_short.

Do not say what viewers will see next.

Do not use "next video", "coming next", "stay tuned",
or "part 2".


============================================================
NEXT SHORT
============================================================

Create a specific researchable continuation topic.

The next_short.topic must:

- naturally follow the CURRENT story
- be specific
- be interesting
- be researchable
- NOT be the same as the current topic

IMPORTANT:

The final sentence of Scene 7 MUST naturally mention
next_short.topic.

Do not mention next_short.topic anywhere in Scenes 1–6.

Do not mention next_short.topic in the description.

Do not explain the next topic.

Do not give factual information about the next topic.

Use it only as a curiosity bridge.

Example:

"But that leaves one bigger question: [next_short.topic]."

The exact final wording may vary naturally.


============================================================
VISUAL PRODUCTION
============================================================

Every scene has exactly two visual shots.

Shot 1 establishes the scene.

Shot 2 advances the scene.

The two prompts must be visually distinct.

Create visual continuity for recurring subjects,
objects and environments.


============================================================
CAPTIONS
============================================================

For every scene:

subtitle_text = narration

EXACTLY.


============================================================
SCIENTIFIC FIDELITY
============================================================

Only supplied evidence.

Do not add facts from memory.

Do not invent numbers.

Do not invent mechanisms.

Do not invent study details.

Do not strengthen uncertainty.

Do not convert correlation into causation.


============================================================
FINAL INTERNAL CHECK
============================================================

Before returning JSON verify:

- exactly 7 scenes
- exactly 14 visuals
- exactly 45 seconds
- exactly 2 visuals per scene
- scene durations are correct
- captions exactly match narration
- valid source IDs only
- factual scenes have citations
- no unsupported claims
- no causal overclaiming
- recurring subjects have continuity descriptions
- global visual identity exists
- visual prompts are distinct
- Scene 7 completes the current story
- Scene 7 naturally mentions next_short.topic
- next_short.topic is NOT mentioned in Scenes 1–6
- next_short.topic is NOT mentioned in description
- description describes ONLY the current topic

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

def parse_gemini_json(
    text
):

    if not text:

        raise RuntimeError(
            "Gemini returned an empty response."
        )

    text = text.strip()

    try:

        result = json.loads(
            text
        )

        if isinstance(
            result,
            dict,
        ):
            return result

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

        result = json.loads(
            cleaned
        )

        if isinstance(
            result,
            dict,
        ):
            return result

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

            result = json.loads(
                candidate
            )

            if isinstance(
                result,
                dict,
            ):
                return result

        except json.JSONDecodeError as error:

            raise RuntimeError(
                f"Failed to parse Gemini JSON: "
                f"{error}"
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

    scene["narration"] = narration

    scene["subtitle_text"] = narration

    tokens = re.findall(
        r"\b[\w'-]+\b",
        narration,
    )

    if not tokens:

        raise RuntimeError(
            f"Scene {index} narration "
            "has no usable words."
        )

    existing = scene.get(
        "caption_highlights",
        [],
    )

    if not isinstance(
        existing,
        list,
    ):
        existing = []

    lookup = {
        token.lower(): token
        for token in tokens
    }

    highlights = []

    used = set()

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

        key = word.lower()

        emphasis = _clean(
            item.get(
                "emphasis",
                "strong",
            )
        )

        if (
            key
            and key in lookup
            and key not in used
            and emphasis in VALID_EMPHASIS
        ):

            highlights.append({
                "word": lookup[key],
                "emphasis": emphasis,
            })

            used.add(
                key
            )

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

    scene["caption_highlights"] = (
        highlights[:3]
    )

    emphasis_word = _clean(
        scene.get(
            "emphasis_word",
            "",
        )
    )

    if (
        not emphasis_word
        or
        emphasis_word.lower()
        not in lookup
    ):

        emphasis_word = (
            highlights[0]["word"]
        )

    scene["emphasis_word"] = (
        emphasis_word
    )


# ============================================================================
# IMAGE PROMPT CLEANING
# ============================================================================

def _clean_image_prompt(
    visual
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
        r"\bAI generated\b",
    ]

    for pattern in forbidden:

        prompt = re.sub(
            pattern,
            "",
            prompt,
            flags=re.IGNORECASE,
        )

    return _clean(
        prompt
    )


def _validate_image_prompt_length(
    prompt,
    scene_index,
    visual_index,
):

    words = _word_count(
        prompt
    )

    if words < MIN_IMAGE_PROMPT_WORDS:

        raise RuntimeError(
            f"Scene {scene_index} visual "
            f"{visual_index} image_prompt "
            f"is too short: {words} words."
        )

    if words > MAX_IMAGE_PROMPT_WORDS:

        raise RuntimeError(
            f"Scene {scene_index} visual "
            f"{visual_index} image_prompt "
            f"is too long: {words} words."
        )


# ============================================================================
# VISUAL REPAIR
# ============================================================================

def _repair_visual(
    visual,
    scene_index,
    visual_index,
):

    if not isinstance(
        visual,
        dict,
    ):

        raise RuntimeError(
            f"Scene {scene_index} visual "
            f"{visual_index} is invalid."
        )

    visual["segment"] = (
        visual_index
    )

    defaults = {

        "camera": "medium",

        "animation": "zoom_in",

        "zoom_strength": "subtle",

        "motion_intensity": "medium",

        "visual_complexity": "moderate",

        "image_style":
            "realistic_3d_render",

        "lighting":
            "natural cinematic lighting",

        "color_palette":
            "natural cinematic tones",

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
        visual.get(
            "overlay"
        ),
        dict,
    ):

        visual["overlay"] = {
            "type": "none",
            "description": "",
        }


    overlay = visual[
        "overlay"
    ]


    if (
        overlay.get(
            "type"
        )
        not in VALID_OVERLAY_TYPE
    ):

        overlay["type"] = (
            "none"
        )


    overlay["description"] = _clean(
        overlay.get(
            "description",
            "",
        )
    )


    if (
        visual["camera"]
        not in VALID_CAMERA
    ):

        visual["camera"] = (
            "medium"
        )


    if (
        visual["animation"]
        not in VALID_ANIMATION
    ):

        visual["animation"] = (
            "zoom_in"
        )


    if (
        visual["zoom_strength"]
        not in VALID_ZOOM_STRENGTH
    ):

        visual["zoom_strength"] = (
            "subtle"
        )


    if (
        visual["motion_intensity"]
        not in VALID_MOTION_INTENSITY
    ):

        visual["motion_intensity"] = (
            "medium"
        )


    if (
        visual["visual_complexity"]
        not in VALID_VISUAL_COMPLEXITY
    ):

        visual["visual_complexity"] = (
            "moderate"
        )


    if (
        visual["image_style"]
        not in VALID_IMAGE_STYLE
    ):

        visual["image_style"] = (
            "realistic_3d_render"
        )


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


    visual["image_prompt"] = (
        _clean_image_prompt(
            visual
        )
    )


    if not visual[
        "image_prompt"
    ]:

        raise RuntimeError(
            f"Scene {scene_index} visual "
            f"{visual_index} has an empty "
            "image_prompt."
        )


    _validate_image_prompt_length(
        visual["image_prompt"],
        scene_index,
        visual_index,
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


    visual["zoom_factor"] = (
        ZOOM_FACTORS[
            visual["zoom_strength"]
        ]
    )


    visual["motion_speed"] = (
        MOTION_SPEEDS[
            visual["motion_intensity"]
        ]
    )


    visual[
        "needs_regeneration"
    ] = (
        visual["visual_impact"]
        < 5
    )


# ============================================================================
# VISUAL DURATIONS
# ============================================================================

def _allocate_visual_durations(
    scene_duration
):

    base = (
        scene_duration
        //
        VISUALS_PER_SCENE
    )

    remainder = (
        scene_duration
        %
        VISUALS_PER_SCENE
    )

    durations = [
        base
        for _ in range(
            VISUALS_PER_SCENE
        )
    ]

    for index in range(
        remainder
    ):

        durations[index] += 1

    return durations


# ============================================================================
# VISUAL CONTINUITY
# ============================================================================

def _normalize_visual_continuity(
    script
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

        if (
            not name
            or
            not appearance
        ):
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
                appearance[:600],

            "continuity":
                (
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


    environment = _clean(
        continuity.get(
            "recurring_environment",
            "",
        )
    )


    script[
        "visual_continuity"
    ] = {

        "recurring_subjects":
            normalized_subjects[
                :MAX_RECURRING_SUBJECTS
            ],

        "recurring_objects": [

            _clean(item)[:200]

            for item in objects

            if _clean(item)

        ][
            :MAX_RECURRING_OBJECTS
        ],

        "recurring_environment":
            environment[:600],

        "continuity_rules": [

            _clean(item)[:400]

            for item in rules

            if _clean(item)

        ][
            :MAX_CONTINUITY_RULES
        ],
    }


# ============================================================================
# VISUAL IDENTITY
# ============================================================================

def _normalize_visual_identity(
    script
):

    identity = script.get(
        "visual_identity",
        {},
    )

    if not isinstance(
        identity,
        dict,
    ):

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


    if not style:

        style = (
            "cinematic realistic visual storytelling "
            "with consistent subject design"
        )


    if not palette:

        palette = (
            "coherent cinematic natural color palette"
        )


    if not mood_arc:

        mood_arc = (
            "curiosity building into tension, wonder and payoff"
        )


    script[
        "visual_identity"
    ] = {

        "style":
            style[:500],

        "palette":
            palette[:300],

        "mood_arc":
            mood_arc[:300],
    }


# ============================================================================
# NEXT SHORT
# ============================================================================

def _normalize_next_short(
    script
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


    if (
        len(topic)
        >
        MAX_NEXT_SHORT_CHARACTERS
    ):

        raise RuntimeError(
            "next_short.topic exceeds "
            f"{MAX_NEXT_SHORT_CHARACTERS} "
            "characters."
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
                reason
                or
                teaser
            )[:220],

        "subscription_cta":
            (
                cta
                or
                "Follow for the next science story."
            )[:160],
    }


# ============================================================================
# NEXT TOPIC IN SCENE 7
# ============================================================================

def _ensure_next_topic_in_scene_7(
    script
):

    scenes = script.get(
        "scene_plan",
        [],
    )

    if not isinstance(
        scenes,
        list,
    ) or len(scenes) != SCENE_COUNT:

        raise RuntimeError(
            "Cannot create next-topic bridge: "
            "scene_plan is incomplete."
        )


    next_short = script.get(
        "next_short",
        {},
    )

    if not isinstance(
        next_short,
        dict,
    ):

        raise RuntimeError(
            "next_short is missing."
        )


    next_topic = _clean(
        next_short.get(
            "topic",
            "",
        )
    )

    if not next_topic:

        raise RuntimeError(
            "next_short.topic is empty."
        )


    scene_7 = scenes[SCENE_COUNT - 1]

    if not isinstance(
        scene_7,
        dict,
    ):

        raise RuntimeError(
            "Scene 7 is invalid."
        )


    narration = _clean(
        scene_7.get(
            "narration",
            "",
        )
    )


    if not narration:

        raise RuntimeError(
            "Scene 7 narration is empty."
        )


    # ------------------------------------------------------------------------
    # The next topic must appear ONLY in Scene 7.
    # ------------------------------------------------------------------------

    for index, scene in enumerate(
        scenes[:-1],
        start=1,
    ):

        if not isinstance(
            scene,
            dict,
        ):
            continue

        if _contains_next_topic(
            scene.get(
                "narration",
                "",
            ),
            next_topic,
        ):

            raise RuntimeError(
                f"Next Short topic appears in "
                f"Scene {index}. It may only appear "
                "in Scene 7."
            )


    # ------------------------------------------------------------------------
    # If Gemini already included the topic, preserve it.
    # ------------------------------------------------------------------------

    if _contains_next_topic(
        narration,
        next_topic,
    ):

        scene_7[
            "narration"
        ] = narration

        return


    # ------------------------------------------------------------------------
    # Gemini failed to mention it. Add a concise bridge.
    #
    # This is a deterministic repair rather than another API call.
    # ------------------------------------------------------------------------

    bridge = _build_next_topic_bridge(
        next_topic
    )


    # Avoid awkward double punctuation.
    narration = narration.rstrip()

    if narration[-1:] not in ".!?":
        narration += "."


    scene_7[
        "narration"
    ] = (
        f"{narration} {bridge}"
    )


# ============================================================================
# DESCRIPTION SAFETY
# ============================================================================

def _validate_description(
    script
):

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


    # ------------------------------------------------------------------------
    # The description is checked ONLY against the next topic.
    #
    # We do NOT require the description to avoid every shared word because
    # current and next topics can naturally overlap.
    # ------------------------------------------------------------------------

    next_short = script.get(
        "next_short",
        {},
    )

    if isinstance(
        next_short,
        dict,
    ):

        next_topic = _clean(
            next_short.get(
                "topic",
                "",
            )
        )

        if next_topic and _contains_next_topic(
            description,
            next_topic,
        ):

            raise RuntimeError(
                "Current description reveals the "
                "next Short topic.\n"
                f"Next topic: {next_topic}\n"
                f"Description: {description}"
            )


    # ------------------------------------------------------------------------
    # Block explicit continuation language.
    # ------------------------------------------------------------------------

    forbidden_phrases = [
        "next video",
        "next short",
        "coming next",
        "stay tuned",
        "part 2",
        "part two",
        "in the next video",
        "in the next short",
        "watch next",
        "watch the next",
        "follow for the next",
    ]


    description_lower = (
        description.lower()
    )


    for phrase in forbidden_phrases:

        if phrase in description_lower:

            raise RuntimeError(
                "Current description contains "
                f"continuation language: '{phrase}'."
            )


    script[
        "description"
    ] = description


# ============================================================================
# CURRENT TOPIC DESCRIPTION REPAIR
# ============================================================================

def _repair_description_if_needed(
    script,
    current_topic,
):

    description = _clean(
        script.get(
            "description",
            "",
        )
    )

    next_short = script.get(
        "next_short",
        {},
    )

    next_topic = ""

    if isinstance(
        next_short,
        dict,
    ):

        next_topic = _clean(
            next_short.get(
                "topic",
                "",
            )
        )


    if description:

        try:

            candidate = {
                "description":
                    description,

                "next_short":
                    {
                        "topic":
                            next_topic
                    },
            }

            _validate_description(
                candidate
            )

            return


        except RuntimeError:

            pass


    # ------------------------------------------------------------------------
    # Safe fallback.
    #
    # This guarantees that the published description is about the CURRENT
    # topic and contains no continuation information.
    # ------------------------------------------------------------------------

    current_topic = _clean(
        current_topic
    )

    script[
        "description"
    ] = (
        f"Explore the science behind {current_topic}, "
        "including the evidence, mechanism, and surprising "
        "details that make this phenomenon so fascinating."
    )


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
        verified_research[
            "sources"
        ],
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
                f"Verified source {index} "
                "has no source_id."
            )


        if source_id in seen_ids:

            raise RuntimeError(
                f"Duplicate verified source ID: "
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
                f"Verified source "
                f"{source_id} has no evidence_text."
            )


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
                _safe_int(
                    source.get(
                        "year",
                        0,
                    ),
                    0,
                ),

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
            "No verified research sources available."
        )


    script[
        "research_sources"
    ] = normalized


# ============================================================================
# SOURCE ID VALIDATION
# ============================================================================

def _validate_source_ids(
    script
):

    valid_ids = {

        _clean(
            source.get(
                "source_id",
                "",
            )
        )

        for source in script.get(
            "research_sources",
            [],
        )

        if (
            isinstance(
                source,
                dict,
            )
            and
            _clean(
                source.get(
                    "source_id",
                    "",
                )
            )
        )
    }


    if not valid_ids:

        raise RuntimeError(
            "No verified research source IDs available."
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

        source_ids = scene.get(
            "source_ids",
            [],
        )


        if not isinstance(
            source_ids,
            list,
        ):

            raise RuntimeError(
                f"Scene {index} "
                "source_ids must be a list."
            )


        cleaned = []


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


            if source_id not in cleaned:

                cleaned.append(
                    source_id
                )


        scene[
            "source_ids"
        ] = cleaned


        if not cleaned:

            purpose = scene.get(
                "purpose",
                "",
            )


            if purpose not in {
                "ending",
            }:

                raise RuntimeError(
                    f"Scene {index} contains factual/story "
                    "content but has no source_ids."
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


    scene[
        "visual_identity"
    ] = ". ".join(
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
                f"Scene {index} "
                f"missing '{key}'."
            )


    if (
        _safe_int(
            scene["scene"]
        )
        != index
    ):

        raise RuntimeError(
            f"Scene {index} "
            "has invalid scene number."
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


    scene[
        "narration"
    ] = narration


    _sync_captions_to_narration(
        scene,
        index,
    )


    duration = _safe_int(
        scene["duration"],
        -1,
    )


    expected_duration = (
        SCENE_DURATIONS[
            index - 1
        ]
    )


    if (
        duration
        != expected_duration
    ):

        raise RuntimeError(
            f"Scene {index} duration must be "
            f"{expected_duration}s."
        )


    scene[
        "duration"
    ] = duration


    pause = _safe_int(
        scene.get(
            "pause_after_ms",
            0,
        ),
        0,
    )


    scene[
        "pause_after_ms"
    ] = max(
        0,
        min(
            600,
            pause,
        ),
    )


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


    visuals = scene.get(
        "visuals",
        [],
    )


    if not isinstance(
        visuals,
        list,
    ):

        raise RuntimeError(
            f"Scene {index} visuals "
            "must be a list."
        )


    if (
        len(visuals)
        != VISUALS_PER_SCENE
    ):

        raise RuntimeError(
            f"Scene {index} must contain "
            f"{VISUALS_PER_SCENE} visuals."
        )


    visual_durations = (
        _allocate_visual_durations(
            duration
        )
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


        visual[
            "duration"
        ] = visual_durations[
            visual_index - 1
        ]


        visual_total += (
            visual["duration"]
        )


        prompts.append(
            visual[
                "image_prompt"
            ].lower().strip()
        )


    if (
        len(
            set(prompts)
        )
        != VISUALS_PER_SCENE
    ):

        raise RuntimeError(
            f"Scene {index} contains duplicate "
            "visual prompts."
        )


    if (
        visual_total
        != duration
    ):

        raise RuntimeError(
            f"Scene {index} visual durations "
            "do not match scene duration."
        )


# ============================================================================
# VISUAL CONTINUITY QUALITY CHECK
# ============================================================================

def _validate_visual_continuity_quality(
    script
):

    identity = script.get(
        "visual_identity",
        {},
    )

    if not isinstance(
        identity,
        dict,
    ):

        raise RuntimeError(
            "visual_identity must be an object."
        )


    if not _clean(
        identity.get(
            "style",
            "",
        )
    ):

        raise RuntimeError(
            "visual_identity.style is empty."
        )


    if not _clean(
        identity.get(
            "palette",
            "",
        )
    ):

        raise RuntimeError(
            "visual_identity.palette is empty."
        )


    if not _clean(
        identity.get(
            "mood_arc",
            "",
        )
    ):

        raise RuntimeError(
            "visual_identity.mood_arc is empty."
        )


    continuity = script.get(
        "visual_continuity",
        {},
    )


    if not isinstance(
        continuity,
        dict,
    ):

        raise RuntimeError(
            "visual_continuity must be an object."
        )


    subjects = continuity.get(
        "recurring_subjects",
        [],
    )


    if not isinstance(
        subjects,
        list,
    ):

        raise RuntimeError(
            "visual_continuity.recurring_subjects "
            "must be a list."
        )


    for subject in subjects:

        if not isinstance(
            subject,
            dict,
        ):
            continue


        if not _clean(
            subject.get(
                "name",
                "",
            )
        ):

            raise RuntimeError(
                "A recurring subject has no name."
            )


        if not _clean(
            subject.get(
                "appearance",
                "",
            )
        ):

            raise RuntimeError(
                "Recurring subject "
                f"'{subject.get('name', '')}' "
                "has no appearance description."
            )


        if not _clean(
            subject.get(
                "continuity",
                "",
            )
        ):

            raise RuntimeError(
                "Recurring subject "
                f"'{subject.get('name', '')}' "
                "has no continuity rule."
            )


# ============================================================================
# TOP LEVEL VALIDATION
# ============================================================================

def _validate_top_level(
    script
):

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
                f"Missing required key: "
                f"{key}"
            )


# ============================================================================
# COMPLETE VALIDATION
# ============================================================================

def validate_script(
    script,
    verified_research,
):

    if not isinstance(
        script,
        dict,
    ):

        raise RuntimeError(
            "Generated script must be "
            "a JSON object."
        )


    _validate_top_level(
        script
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


    if (
        len(scenes)
        != SCENE_COUNT
    ):

        raise RuntimeError(
            f"Expected {SCENE_COUNT} scenes, "
            f"got {len(scenes)}."
        )


    # ------------------------------------------------------------------------
    # Normalize global visual systems.
    # ------------------------------------------------------------------------

    _normalize_visual_identity(
        script
    )


    _normalize_visual_continuity(
        script
    )


    _normalize_next_short(
        script
    )


    # ------------------------------------------------------------------------
    # Make sure the next topic is actually spoken in Scene 7.
    # ------------------------------------------------------------------------

    _ensure_next_topic_in_scene_7(
        script
    )


    # ------------------------------------------------------------------------
    # Validate scenes.
    # ------------------------------------------------------------------------

    total_duration = 0

    total_visuals = 0


    for index, scene in enumerate(
        scenes,
        start=1,
    ):

        _validate_scene(
            scene,
            index,
        )


        if index == SCENE_COUNT:

            scene[
                "purpose"
            ] = "ending"

            scene[
                "transition"
            ] = "none"


        total_duration += (
            scene["duration"]
        )


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


    # ------------------------------------------------------------------------
    # Production contract.
    # ------------------------------------------------------------------------

    if (
        total_duration
        != TARGET_SECONDS
    ):

        raise RuntimeError(
            f"Total duration must be "
            f"{TARGET_SECONDS}s, "
            f"got {total_duration}s."
        )


    if (
        total_visuals
        != TOTAL_VISUALS
    ):

        raise RuntimeError(
            f"Total visuals must be "
            f"{TOTAL_VISUALS}, "
            f"got {total_visuals}."
        )


    # ------------------------------------------------------------------------
    # Research metadata.
    # ------------------------------------------------------------------------

    _normalize_research_sources(
        script,
        verified_research,
    )


    # ------------------------------------------------------------------------
    # Source validation.
    # ------------------------------------------------------------------------

    _validate_source_ids(
        script
    )


    # ------------------------------------------------------------------------
    # Scientific claim safety.
    # ------------------------------------------------------------------------

    _validate_claim_strength(
        script
    )


    # ------------------------------------------------------------------------
    # Visual continuity quality.
    # ------------------------------------------------------------------------

    _validate_visual_continuity_quality(
        script
    )


    # ------------------------------------------------------------------------
    # Description safety.
    # ------------------------------------------------------------------------

    _validate_description(
        script
    )


    # ------------------------------------------------------------------------
    # Metadata normalization.
    # ------------------------------------------------------------------------

    script[
        "title"
    ] = _clean(
        script.get(
            "title",
            "",
        )
    )[:MAX_TITLE_LENGTH]


    if not script[
        "title"
    ]:

        raise RuntimeError(
            "Video title is empty."
        )


    script[
        "description"
    ] = _clean(
        script.get(
            "description",
            "",
        )
    )[:MAX_DESCRIPTION_LENGTH]


    tags = script.get(
        "tags",
        [],
    )


    if not isinstance(
        tags,
        list,
    ):

        tags = []


    normalized_tags = []


    for tag in tags:

        tag = _clean(
            tag
        ).lower()


        if not tag:
            continue


        if tag not in normalized_tags:

            normalized_tags.append(
                tag
            )


    script[
        "tags"
    ] = normalized_tags[
        :MAX_TAGS
    ]


    category = _clean(
        script.get(
            "category",
            "",
        )
    ).lower()


    if (
        category
        not in VALID_CATEGORY
    ):

        category = "biology"


    script[
        "category"
    ] = category


    script[
        "thumbnail_prompt"
    ] = _clean(
        script.get(
            "thumbnail_prompt",
            "",
        )
    )


    # ------------------------------------------------------------------------
    # Deterministic image-generation metadata.
    # ------------------------------------------------------------------------

    existing_generation = (
        script.get(
            "image_generation",
            {},
        )
    )


    if not isinstance(
        existing_generation,
        dict,
    ):

        existing_generation = {}


    existing_seed = existing_generation.get(
        "seed"
    )


    if existing_seed is None:

        seed = random.randint(
            1,
            2_147_483_647,
        )

    else:

        seed = _safe_int(
            existing_seed,
            random.randint(
                1,
                2_147_483_647,
            ),
        )


    identity = script[
        "visual_identity"
    ]


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

        "semantic_prompts":
            True,

        "portrait_output":
            True,
    }


    # ------------------------------------------------------------------------
    # Runtime metadata.
    # ------------------------------------------------------------------------

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
            "short_form_story",

        "scene_count":
            SCENE_COUNT,

        "target_duration_seconds":
            TARGET_SECONDS,

        "actual_duration_seconds":
            total_duration,

        "visuals_per_scene":
            VISUALS_PER_SCENE,

        "total_visuals":
            total_visuals,

        "story_format":
            "hook_curiosity_explanation_example_reframe_escalation_payoff_next_topic_hook",
    }


    # ------------------------------------------------------------------------
    # Publishing state.
    # ------------------------------------------------------------------------

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

        "next_short_spoken_in_scene_7":
            True,

        "next_short_spoken_only_in_scene_7":
            True,

        "next_short_topic_in_description":
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

        "semantic_image_prompts":
            True,

        "fourteen_visuals_required":
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
    extra_feedback="",
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


    for source in research[
        "sources"
    ]:

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


    if extra_feedback:

        base_prompt += f"""

============================================================
PRIOR CLAIM VERIFICATION FEEDBACK
============================================================

A previous version of this Short passed script validation but FAILED
independent scientific claim verification. The following claims were
rejected as unsupported, uncertain, or contradicted by the supplied
evidence:

{extra_feedback}

Rewrite the story so every claim stays strictly within the wording of
the supplied evidence. Prefer softer language (may, might, is
associated with, suggests) over firm mechanistic language when the
evidence itself is not firm. Do not add causes, forces, or mechanisms
the evidence does not explicitly state, even in Scene 1 or Scene 2
hook language.
"""


    system_prompt = build_system_prompt()


    response_schema = (
        build_response_schema()
    )


    print("=" * 80)
    print("✍️ GENERATING RESEARCH-FIRST STORY")
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


    print(
        "Visual continuity: ENABLED"
    )


    print(
        "Research-first mode: ENABLED"
    )


    print(
        "Next-topic Scene 7 bridge: ENABLED"
    )


    print(
        "Current-topic-only description: ENABLED"
    )


    if extra_feedback:

        print(
            "Claim-verification retry feedback: INCLUDED"
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

            attempt_prompt = (
                base_prompt
            )


            if (
                attempt > 1
                and
                last_error
            ):

                attempt_prompt += f"""

============================================================
RETRY REQUIRED
============================================================

The previous generated storyboard failed validation.

PREVIOUS VALIDATION ERROR:

{last_error}


Generate the COMPLETE JSON again.

Do not explain the correction.

Do not return partial JSON.


============================================================
NON-NEGOTIABLE
============================================================

7 scenes.

14 visuals.

45 seconds.

Durations:

3, 5, 7, 7, 8, 8, 7.

Exactly 2 visuals per scene.

subtitle_text MUST equal narration.

Use only supplied evidence.

Use exact supplied source IDs.

Scene 7 MUST complete the current story and then
naturally mention next_short.topic as the final curiosity hook.

The next topic MUST NOT appear in Scenes 1–6.

The next topic MUST NOT appear in the description.

The description MUST describe ONLY the current topic.

Do not use:

"Next we'll..."
"In the next video..."
"Coming next..."
"Stay tuned..."
"Part 2..."
"Subscribe for..."


============================================================
VISUAL CONTINUITY
============================================================

Create a coherent visual identity.

Define recurring subjects clearly.

Define recurring objects when needed.

Define the recurring environment when relevant.

Every image must feel like it belongs
to the same Short.

Two visuals in a scene must be different
but clearly connected.


============================================================
IMAGE PROMPTS
============================================================

Each image_prompt must describe visible content.

Approximately 15–35 words.

Do not include:

camera instructions
aspect ratio
negative prompts
text
captions
subtitles
logos
watermarks
YouTube
narration


============================================================
SCIENTIFIC LANGUAGE
============================================================

Do not strengthen evidence.

Do not invent facts.

Do not invent numbers.

Do not invent mechanisms.

Do not convert association into causation.

Preserve words such as:

may
might
suggests
indicates
associated with

when supported by the research.


Return ONLY JSON.
"""


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
            # Topic belongs to the pipeline.
            # ----------------------------------------------------------------

            script[
                "topic"
            ] = topic


            # ----------------------------------------------------------------
            # Force subtitle synchronization immediately.
            # ----------------------------------------------------------------

            scenes = script.get(
                "scene_plan",
                [],
            )


            if isinstance(
                scenes,
                list,
            ):

                for scene in scenes:

                    if isinstance(
                        scene,
                        dict,
                    ):

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
            # Validate.
            # ----------------------------------------------------------------

            script = validate_script(
                script,
                research,
            )


            # ----------------------------------------------------------------
            # Final current-topic description safety repair.
            # ----------------------------------------------------------------

            _repair_description_if_needed(
                script,
                topic,
            )


            # Validate the repaired description one final time.
            _validate_description(
                script
            )


            # ----------------------------------------------------------------
            # Final next-topic verification.
            # ----------------------------------------------------------------

            final_next_topic = _clean(
                script[
                    "next_short"
                ][
                    "topic"
                ]
            )


            final_scene_7 = _clean(
                script[
                    "scene_plan"
                ][6][
                    "narration"
                ]
            )


            if not _contains_next_topic(
                final_scene_7,
                final_next_topic,
            ):

                raise RuntimeError(
                    "Scene 7 does not mention "
                    "next_short.topic."
                )


            for scene_index, scene in enumerate(
                script["scene_plan"][:6],
                start=1,
            ):

                if _contains_next_topic(
                    scene.get(
                        "narration",
                        "",
                    ),
                    final_next_topic,
                ):

                    raise RuntimeError(
                        f"next_short.topic appears "
                        f"in Scene {scene_index}. "
                        "It may only appear in Scene 7."
                    )


            if _contains_next_topic(
                script["description"],
                final_next_topic,
            ):

                raise RuntimeError(
                    "next_short.topic appears in "
                    "the current description."
                )


            # ----------------------------------------------------------------
            # Success.
            # ----------------------------------------------------------------

            print("=" * 80)
            print("✅ SHORT SCRIPT ACCEPTED")
            print("=" * 80)


            print(
                f"Scenes: "
                f"{SCENE_COUNT}"
            )


            print(
                f"Visuals: "
                f"{TOTAL_VISUALS}"
            )


            print(
                f"Duration: "
                f"{TARGET_SECONDS}s"
            )


            print(
                "Research sources: "
                f"{len(script['research_sources'])}"
            )


            cited_scenes = sum(

                1

                for scene in
                script["scene_plan"]

                if scene.get(
                    "source_ids"
                )
            )


            print(
                "Scenes with citations: "
                f"{cited_scenes}/"
                f"{SCENE_COUNT}"
            )


            continuity = script[
                "visual_continuity"
            ]


            print(
                "Recurring subjects: "
                f"{len(continuity['recurring_subjects'])}"
            )


            print(
                "Recurring objects: "
                f"{len(continuity['recurring_objects'])}"
            )


            print(
                "Environment continuity: "
                f"{'YES' if continuity['recurring_environment'] else 'NO'}"
            )


            print(
                "Visual identity: "
                "LOCKED"
            )


            print(
                "Current description: "
                "CURRENT TOPIC ONLY"
            )


            print(
                "Next Short: "
                f"{script['next_short']['topic']}"
            )


            print(
                "Next topic spoken in Scene 7: "
                "YES"
            )


            print(
                "Next topic spoken in Scenes 1–6: "
                "NO"
            )


            print(
                "Next topic in description: "
                "NO"
            )


            print(
                "Captions match narration: "
                "YES"
            )


            print(
                "Claim-strength guard: "
                "PASSED"
            )


            print(
                "Research: "
                "VERIFIED"
            )


            print(
                "14-image visual contract: "
                "PASSED"
            )


            print("=" * 80)


            return script


        except Exception as error:

            last_error = error


            print("=" * 80)


            print(
                f"❌ ATTEMPT "
                f"{attempt} FAILED"
            )


            print(
                f"{type(error).__name__}: "
                f"{error}"
            )


            print("=" * 80)


            if (
                attempt
                <
                MAX_GENERATION_ATTEMPTS
            ):

                delay = (
                    4 * attempt
                )


                print(
                    f"⏳ Retrying in "
                    f"{delay}s..."
                )


                time.sleep(
                    delay
                )


    raise RuntimeError(
        "SCRIPT GENERATION FAILED.\n\n"
        "The pipeline rejected all generated storyboards.\n\n"
        f"Last validation error:\n"
        f"{last_error}"
    )


# ============================================================================
# LOCAL TEST
# ============================================================================

if __name__ == "__main__":

    print(
        "generate_script.py "
        "v10.1 is a pipeline module."
    )

    print(
        "Run the complete pipeline "
        "through main.py."
    )
