"""
verify_claims.py
Mint-YT-Factory
Version 3.2

Hardened scientific claim verification layer.

Key hardening:
- Gemini may use ONLY scene-cited verified evidence text.
- Metadata is never evidence.
- Every scene must be reviewed.
- Every factual claim must be cited.
- Citations must be valid, usable, and scene-local.
- Numbers and causal/mechanistic language are explicitly checked.
- Unsupported / uncertain / contradicted claims always fail.
- Structural failures can be retried with explicit feedback.
- A retry never overrides a genuine scientific failure.
- Final PASS is determined locally, never by Gemini.
- Research source IDs are preserved exactly.
- No artificial source IDs are created.
- The Scene 7 "next Short" curiosity bridge is stripped before
  verification, since it is a continuation hook, not a claim about
  the current topic.
"""

import json
import os
import re
import time

from google import genai
from google.genai import types


# ==========================================================================
# CONFIG
# ==========================================================================

VERSION = "3.2"

MODEL_NAME = "gemini-flash-lite-latest"

MAX_CLAIMS_PER_SCENE = 8

MIN_EVIDENCE_CHARACTERS = 120

MAX_VERIFICATION_ATTEMPTS = 3

RETRY_DELAY_SECONDS = 3


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


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _unique_clean_list(values):
    if not isinstance(values, list):
        return []

    result = []
    seen = set()

    for value in values:
        value = _clean(value)

        if not value:
            continue

        if value.lower() in seen:
            continue

        seen.add(value.lower())
        result.append(value)

    return result


# ==========================================================================
# NEXT-TOPIC BRIDGE DETECTION
#
# Scene 7 ends with a short "next Short" curiosity bridge that is NOT a
# factual claim about the current topic (see generate_script.py's Scene 7
# rules). The claim verifier must never see that sentence, or it will
# (correctly, by its own strict rules) flag it as an unsupported claim.
#
# This mirrors the detection logic in generate_script.py's
# _contains_next_topic(), kept local here so verify_claims.py has no
# dependency on that module.
# ==========================================================================

_BRIDGE_STOPWORDS = {
    "what", "why", "how", "when", "where", "which", "does", "this", "that",
    "these", "those", "the", "and", "for", "with", "from", "into", "about",
    "your", "our", "their", "will", "can", "could", "would", "should",
    "did", "are", "was", "were", "is", "its", "it's", "they", "them",
    "than", "then", "really", "actually", "just", "very", "most", "more",
    "some", "one", "thing", "things", "part", "next", "story", "question",
    "mystery", "science", "scientific",
}


def _bridge_topic_words(topic):

    words = re.findall(
        r"[A-Za-z0-9'-]+",
        _clean(topic).lower(),
    )

    return [
        word
        for word in words
        if len(word) >= 4
        and word not in _BRIDGE_STOPWORDS
    ]


def _contains_next_topic(
    text,
    next_topic,
):

    text_clean = _clean(text).lower()
    topic_clean = _clean(next_topic).lower()

    if not text_clean or not topic_clean:
        return False

    if topic_clean in text_clean:
        return True

    topic_words = _bridge_topic_words(
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

    if len(topic_words) <= 3:
        return len(overlap) >= len(topic_words)

    return (
        len(overlap) >= 3
        and
        len(overlap) / len(set(topic_words)) >= 0.70
    )


def _split_sentences(text):

    text = _clean(text)

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    return [
        part.strip()
        for part in parts
        if part.strip()
    ]


def _strip_next_topic_bridge(
    narration,
    next_topic,
):
    """
    Remove the next-Short curiosity-bridge sentence(s) from narration
    before it is sent to the claim verifier or scanned for factual
    language signals.

    generate_script.py guarantees the bridge only ever appears in Scene 7,
    as the final sentence(s), and never in Scenes 1-6 or the description.
    Stripping any matching sentence from any scene's narration is
    therefore safe and has no effect on scenes that don't contain it.
    """

    next_topic = _clean(
        next_topic
    )

    if not next_topic:
        return narration

    sentences = _split_sentences(
        narration
    )

    if not sentences:
        return narration

    kept = [
        sentence
        for sentence in sentences
        if not _contains_next_topic(
            sentence,
            next_topic,
        )
    ]

    stripped = " ".join(
        kept
    ).strip()

    return stripped if stripped else narration


# ==========================================================================
# NUMERIC CLAIM SIGNAL
# ==========================================================================

def _contains_numeric_claim_signal(text):
    """
    Detect obvious quantitative language.

    This does NOT determine whether something is factual.

    It only ensures Gemini cannot silently ignore obvious numbers.
    """

    text = _clean(text)

    if not text:
        return False

    patterns = (

        # Percentages
        r"\b\d+(?:\.\d+)?\s*%",

        # Scientific / physical units
        r"\b\d+(?:\.\d+)?\s*"
        r"(?:"
        r"seconds?|minutes?|hours?|days?|weeks?|months?|years?|"
        r"meters?|metres?|kilometers?|kilometres?|"
        r"centimeters?|centimetres?|millimeters?|millimetres?|"
        r"grams?|kilograms?|milligrams?|"
        r"degrees?|°|"
        r"celsius|fahrenheit|kelvin|"
        r"hz|khz|mhz|ghz|"
        r"watts?|kw|mw|"
        r"volts?|amps?|"
        r"times?"
        r")\b",

        # Multipliers
        r"\b\d+(?:\.\d+)?\s*x\b",

        # Large quantities
        r"\b\d+(?:\.\d+)?\s*"
        r"(?:thousand|million|billion|trillion)\b",

        # Decimal numbers
        r"\b\d+\.\d+\b",

        # Years
        r"\b(?:1[5-9]\d{2}|20\d{2}|21\d{2})\b",
    )

    return any(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        for pattern in patterns
    )


# ==========================================================================
# FACTUAL LANGUAGE SIGNAL
# ==========================================================================

def _contains_factual_language_signal(text):
    """
    Conservative safeguard.

    This does NOT classify a sentence scientifically.

    It only detects language that strongly suggests a factual claim
    may exist and therefore requires careful Gemini review.
    """

    text = _clean(text).lower()

    if not text:
        return False

    patterns = (

        # Research
        r"\bresearchers?\b",
        r"\bscientists?\b",
        r"\bstudy\b",
        r"\bstudies\b",
        r"\bexperiment(?:s)?\b",
        r"\bobserved\b",
        r"\bfound\b",
        r"\bfindings?\b",
        r"\bdata\b",
        r"\bevidence\b",

        # Causation
        r"\bcauses?\b",
        r"\bcaused\b",
        r"\bcausing\b",
        r"\bleads? to\b",
        r"\bresults? in\b",
        r"\bproduces?\b",
        r"\bcreates?\b",
        r"\bprevents?\b",
        r"\bcontrols?\b",
        r"\btriggers?\b",
        r"\bdrives?\b",
        r"\baffects?\b",
        r"\bincreases?\b",
        r"\bdecreases?\b",
        r"\breduces?\b",
        r"\bimproves?\b",
        r"\bchanges?\b",

        # Mechanisms
        r"\bcontains?\b",
        r"\bconsists? of\b",
        r"\bhas\b",
        r"\bhave\b",
        r"\buses?\b",
        r"\babsorbs?\b",
        r"\breflects?\b",
        r"\bemits?\b",
        r"\bdetects?\b",
        r"\bmeasures?\b",

        # Biology / physics
        r"\bcells?\b",
        r"\bbrain\b",
        r"\bneurons?\b",
        r"\bhormones?\b",
        r"\bdna\b",
        r"\bproteins?\b",
        r"\batoms?\b",
        r"\bmolecules?\b",
        r"\benergy\b",
        r"\bpressure\b",
        r"\btemperature\b",
        r"\bgravity\b",
        r"\bvelocity\b",
        r"\bfrequency\b",
        r"\bradiation\b",
        r"\bmagnetic\b",
        r"\belectric\b",

        # Strong factual phrasing
        r"\bis known to\b",
        r"\bare known to\b",
        r"\bis caused by\b",
        r"\bare caused by\b",
        r"\bis associated with\b",
        r"\bare associated with\b",
        r"\bhas been shown\b",
        r"\bhave been shown\b",
        r"\bwas discovered\b",
        r"\bwere discovered\b",
    )

    return any(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
        for pattern in patterns
    )


# ==========================================================================
# SOURCE MAP
# ==========================================================================

def _build_source_map(research):
    source_map = {}

    sources = research.get(
        "sources",
        [],
    )

    if not isinstance(
        sources,
        list,
    ):
        return source_map

    for source in sources:

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

        if not source_id:
            continue

        source_map[
            source_id
        ] = source

    return source_map


# ==========================================================================
# VERIFIED RESEARCH EVIDENCE
# ==========================================================================

def _build_research_evidence(research):
    """
    Gemini receives ONLY usable scientific evidence.

    Metadata may identify the source, but it cannot be used as evidence.
    """

    blocks = []

    source_map = _build_source_map(
        research
    )

    for source_id, source in source_map.items():

        evidence = _clean(
            source.get(
                "evidence_text",
                "",
            )
        )

        if (
            source.get(
                "verified"
            ) is not True
        ):
            continue

        if (
            source.get(
                "evidence_verified"
            ) is not True
        ):
            continue

        if (
            source.get(
                "evidence_available"
            ) is not True
        ):
            continue

        if len(evidence) < (
            MIN_EVIDENCE_CHARACTERS
        ):
            continue

        blocks.append(
            f"""
SOURCE ID: {source_id}

============================================================
SOURCE IDENTIFICATION
============================================================

Title:
{_clean(source.get("title", ""))}

============================================================
SCIENTIFIC EVIDENCE
============================================================

{evidence}

============================================================
EVIDENCE RULE
============================================================

Only the scientific evidence text above may support claims.

Source metadata is NOT scientific evidence.
""".strip()
        )

    if not blocks:
        return (
            "NO VERIFIED SCIENTIFIC EVIDENCE AVAILABLE."
        )

    return "\n\n".join(
        blocks
    )


# ==========================================================================
# SCRIPT CLAIM CONTEXT
# ==========================================================================

def _build_claim_context(script, next_topic=""):
    """
    Build the per-scene narration/citation context sent to Gemini.

    The Scene 7 next-topic bridge sentence is stripped out here so the
    verifier never sees it and cannot flag it as an unsupported claim.
    """

    blocks = []

    scenes = script.get(
        "scene_plan",
        [],
    )

    if not isinstance(
        scenes,
        list,
    ):
        return ""

    for scene in scenes:

        if not isinstance(
            scene,
            dict,
        ):
            continue

        source_ids = scene.get(
            "source_ids",
            [],
        )

        if not isinstance(
            source_ids,
            list,
        ):
            source_ids = []

        source_ids = [
            str(source_id).strip()
            for source_id in source_ids
            if str(source_id).strip()
        ]

        narration = _clean(
            scene.get(
                "narration",
                "",
            )
        )

        reviewable_narration = _strip_next_topic_bridge(
            narration,
            next_topic,
        )

        blocks.append(
            f"""
SCENE {scene.get("scene")}

NARRATION:
{reviewable_narration}

CITED SOURCE IDS:
{json.dumps(source_ids, ensure_ascii=False)}
""".strip()
        )

    return "\n\n".join(
        blocks
    )


# ==========================================================================
# RESPONSE SCHEMA
# ==========================================================================

def build_response_schema():

    claim = {
        "type": "object",
        "properties": {
            "claim": {
                "type": "string",
            },
            "scene": {
                "type": "integer",
            },
            "source_ids": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
            "status": {
                "type": "string",
                "enum": [
                    "supported",
                    "unsupported",
                    "uncertain",
                    "contradicted",
                ],
            },
            "reason": {
                "type": "string",
            },
            "evidence": {
                "type": "string",
            },
        },
        "required": [
            "claim",
            "scene",
            "source_ids",
            "status",
            "reason",
            "evidence",
        ],
    }

    scene_review = {
        "type": "object",
        "properties": {
            "scene": {
                "type": "integer",
            },
            "factual_claims_found": {
                "type": "boolean",
            },
            "claim_count": {
                "type": "integer",
            },
            "review_note": {
                "type": "string",
            },
        },
        "required": [
            "scene",
            "factual_claims_found",
            "claim_count",
            "review_note",
        ],
    }

    return {
        "type": "object",
        "properties": {
            "overall_status": {
                "type": "string",
                "enum": [
                    "PASS",
                    "FAIL",
                ],
            },
            "claims": {
                "type": "array",
                "items": claim,
            },
            "scene_reviews": {
                "type": "array",
                "items": scene_review,
            },
            "unsupported_claims": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
            "warnings": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
        },
        "required": [
            "overall_status",
            "claims",
            "scene_reviews",
            "unsupported_claims",
            "warnings",
        ],
    }


# ==========================================================================
# SYSTEM PROMPT
# ==========================================================================

def _system_prompt():

    return """
You are a STRICT scientific fact checker.

Your ONLY task is to determine whether every IMPORTANT FACTUAL CLAIM
in the supplied YouTube Short is supported by the supplied verified
scientific Evidence Text.

============================================================
ABSOLUTE EVIDENCE RULE
============================================================

You may ONLY use the supplied Scientific Evidence text.

Do NOT use:

- model memory
- general knowledge
- internet knowledge
- outside scientific knowledge
- invented evidence
- invented studies
- invented statistics
- assumptions

============================================================
METADATA IS NOT EVIDENCE
============================================================

Never use the following as scientific evidence:

- title
- authors
- journal
- year
- DOI
- URL
- source identity
- verification level

Only the actual Evidence Text can support a factual claim.

============================================================
NEXT-SHORT BRIDGE SENTENCES
============================================================

Some scripts originally end with a short forward-looking sentence
that introduces the topic of the NEXT Short (for example: "But that
leaves one bigger question: ...").

These bridge sentences are curiosity hooks about a DIFFERENT,
future video. They are NOT factual claims about the current topic.

The narration you are given has already had this bridge sentence
removed. If any trace of it still appears, do NOT extract it as a
claim and do NOT count it against scene completeness. Treat it as
stylistic, not factual.

============================================================
EVERY SCENE MUST BE REVIEWED
============================================================

Read the COMPLETE narration of every scene.

Return exactly ONE scene_reviews object for every script scene.

Never omit a scene.

============================================================
CLAIM EXTRACTION
============================================================

Identify EVERY IMPORTANT factual claim.

Include:

- scientific facts
- biological facts
- physical facts
- mechanisms
- causes
- effects
- observations
- research findings
- measurements
- numbers
- percentages
- dates
- statistics
- historical factual statements
- relationships between variables

Do NOT create claims from purely stylistic language.

Examples of stylistic language:

"Here's where it gets strange."

"Nature has another surprise."

"This changes everything."

============================================================
SCENE-LOCAL CITATION
============================================================

Every factual claim must use ONLY source IDs cited by that scene.

The claim's source_ids MUST be a subset of the scene's source_ids.

Never:

- borrow a source from another scene
- invent a source ID
- modify a source ID
- substitute another source

Preserve source IDs exactly.

============================================================
CLAIM STATUS
============================================================

supported:

The supplied Evidence Text directly supports the claim.

uncertain:

The Evidence Text is related but insufficient to establish the claim.

unsupported:

The Evidence Text does not support the claim.

contradicted:

The Evidence Text conflicts with the claim.

============================================================
SCIENTIFIC LANGUAGE
============================================================

Do NOT strengthen evidence.

"may contribute" does NOT mean "causes".

"associated with" does NOT mean "causes".

"possible" does NOT mean "certain".

"hypothesis" does NOT mean "proven".

"observed" does NOT mean "always happens".

"could explain" does NOT mean "explains".

============================================================
NUMBERS
============================================================

Every:

- number
- percentage
- date
- measurement
- quantity
- statistic
- multiplier

must be explicitly supported by the supplied Evidence Text.

Never infer or invent a number.

============================================================
CAUSATION
============================================================

Do NOT convert:

correlation → causation

association → causation

possibility → certainty

hypothesis → established fact

observation → universal rule

============================================================
PASS CONDITION
============================================================

PASS is allowed only when:

1. Every important factual claim was extracted.
2. Every important factual claim is supported.
3. No important claim is unsupported.
4. No important claim is uncertain.
5. No important claim is contradicted.
6. Every factual claim has at least one source ID.
7. Every source ID belongs to that scene.
8. Every source ID is valid.
9. Every source has verified evidence.
10. Numbers are supported.
11. Causal language is supported.
12. Every scene has been explicitly reviewed.

Return ONLY valid JSON.
"""


# ==========================================================================
# GEMINI VERIFICATION
# ==========================================================================

def _verify_with_gemini(
    script,
    research,
    retry_feedback="",
    next_topic="",
):

    client = genai.Client(
        api_key=_get_api_key()
    )

    research_evidence = (
        _build_research_evidence(
            research
        )
    )

    claim_context = (
        _build_claim_context(
            script,
            next_topic,
        )
    )

    prompt = f"""
VERIFY THIS SCRIPT.

============================================================
VERIFIED SCIENTIFIC EVIDENCE
============================================================

{research_evidence}

============================================================
SCRIPT
============================================================

{claim_context}

============================================================
TASK
============================================================

For EVERY scene:

1. Read the complete narration.
2. Identify every important factual claim.
3. Check every number and quantitative statement.
4. Check every causal or mechanistic statement.
5. Use ONLY Evidence Text from sources cited by that scene.
6. Return only exact source IDs cited by that scene.
7. Create exactly one scene_reviews object.
8. If a scene contains no factual claims, return:
   factual_claims_found = false
   claim_count = 0

For every factual claim:

- state the claim
- identify its scene
- provide exact scene-local source IDs
- classify the claim
- explain the decision
- provide a concise evidence explanation

Do NOT use metadata as evidence.

Do NOT use outside knowledge.

Do NOT invent evidence.

Do NOT strengthen scientific language.

Do NOT convert correlation into causation.

Do NOT convert possibility into certainty.

{retry_feedback}

Return the COMPLETE JSON result.
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_system_prompt(),
            response_mime_type="application/json",
            response_json_schema=build_response_schema(),
        ),
    )

    response_text = getattr(
        response,
        "text",
        None,
    )

    if not response_text:
        raise RuntimeError(
            "Claim verifier returned an empty response."
        )

    try:
        return json.loads(
            response_text
        )

    except json.JSONDecodeError as error:

        raise RuntimeError(
            "Claim verifier returned invalid JSON: "
            f"{error}"
        ) from error


# ==========================================================================
# SCENE MAPS
# ==========================================================================

def _scene_maps(script, next_topic=""):
    """
    Build per-scene source-ID and narration lookups.

    scene_narration uses the bridge-stripped narration so the
    conservative numeric/factual-language completeness checks below
    don't misfire on the Scene 7 curiosity bridge.
    """

    scene_sources = {}
    scene_narration = {}

    scenes = script.get(
        "scene_plan",
        [],
    )

    if not isinstance(
        scenes,
        list,
    ):
        return scene_sources, scene_narration

    for scene in scenes:

        if not isinstance(
            scene,
            dict,
        ):
            continue

        scene_number = _safe_int(
            scene.get(
                "scene",
                0,
            )
        )

        source_ids = scene.get(
            "source_ids",
            [],
        )

        if not isinstance(
            source_ids,
            list,
        ):
            source_ids = []

        scene_sources[
            scene_number
        ] = {
            str(source_id).strip()
            for source_id in source_ids
            if str(source_id).strip()
        }

        narration = _clean(
            scene.get(
                "narration",
                "",
            )
        )

        scene_narration[
            scene_number
        ] = _strip_next_topic_bridge(
            narration,
            next_topic,
        )

    return scene_sources, scene_narration


# ==========================================================================
# LOCAL VALIDATION
# ==========================================================================

def _local_validate(
    result,
    script,
    research,
    next_topic="",
):

    if not isinstance(
        result,
        dict,
    ):
        raise RuntimeError(
            "Claim verifier returned an invalid result."
        )

    source_map = _build_source_map(
        research
    )

    valid_source_ids = set(
        source_map.keys()
    )

    usable_source_ids = set()

    for source_id, source in source_map.items():

        if not isinstance(
            source,
            dict,
        ):
            continue

        evidence = _clean(
            source.get(
                "evidence_text",
                "",
            )
        )

        if (
            source.get(
                "verified"
            ) is True
            and
            source.get(
                "evidence_verified"
            ) is True
            and
            source.get(
                "evidence_available"
            ) is True
            and
            len(evidence)
            >= MIN_EVIDENCE_CHARACTERS
        ):

            usable_source_ids.add(
                source_id
            )

    scene_sources, scene_narration = (
        _scene_maps(script, next_topic)
    )

    expected_scenes = set(
        scene_sources.keys()
    )

    claims = result.get(
        "claims",
        [],
    )

    reviews = result.get(
        "scene_reviews",
        [],
    )

    unsupported = _unique_clean_list(
        result.get(
            "unsupported_claims",
            [],
        )
    )

    warnings = _unique_clean_list(
        result.get(
            "warnings",
            [],
        )
    )

    if not isinstance(
        claims,
        list,
    ):

        unsupported.append(
            "Verifier claims field is not an array."
        )

        claims = []

    if not isinstance(
        reviews,
        list,
    ):

        unsupported.append(
            "Verifier scene_reviews field is not an array."
        )

        reviews = []

    claims_per_scene = {}

    # ----------------------------------------------------------------------
    # CLAIM VALIDATION
    # ----------------------------------------------------------------------

    for claim in claims:

        if not isinstance(
            claim,
            dict,
        ):

            unsupported.append(
                "Verifier returned an invalid claim object."
            )

            continue

        claim_text = _clean(
            claim.get(
                "claim",
                "",
            )
        )

        scene_number = _safe_int(
            claim.get(
                "scene",
                0,
            )
        )

        status = _clean(
            claim.get(
                "status",
                "",
            )
        ).lower()

        reason = _clean(
            claim.get(
                "reason",
                "",
            )
        )

        evidence = _clean(
            claim.get(
                "evidence",
                "",
            )
        )

        source_ids = claim.get(
            "source_ids",
            [],
        )

        if not isinstance(
            source_ids,
            list,
        ):
            source_ids = []

        source_ids = list(
            dict.fromkeys(
                str(source_id).strip()
                for source_id in source_ids
                if str(source_id).strip()
            )
        )

        if not claim_text:

            unsupported.append(
                "Verifier returned an empty claim."
            )

            continue

        claims_per_scene[
            scene_number
        ] = (
            claims_per_scene.get(
                scene_number,
                0,
            )
            + 1
        )

        if (
            claims_per_scene[
                scene_number
            ]
            > MAX_CLAIMS_PER_SCENE
        ):

            unsupported.append(
                f"Scene {scene_number} has more than "
                f"{MAX_CLAIMS_PER_SCENE} claims."
            )

        # --------------------------------------------------------------
        # VALID SCENE
        # --------------------------------------------------------------

        if scene_number not in scene_sources:

            unsupported.append(
                f"Claim references invalid scene "
                f"{scene_number}: {claim_text}"
            )

            continue

        scene_source_ids = scene_sources[
            scene_number
        ]

        # --------------------------------------------------------------
        # CITATION REQUIRED
        # --------------------------------------------------------------

        if not source_ids:

            unsupported.append(
                f"Claim has no source citation: "
                f"{claim_text}"
            )

        # --------------------------------------------------------------
        # SOURCE VALIDITY
        # --------------------------------------------------------------

        invalid_ids = [
            source_id
            for source_id in source_ids
            if source_id not in valid_source_ids
        ]

        if invalid_ids:

            unsupported.append(
                f"Invalid source citation "
                f"{', '.join(invalid_ids)}: "
                f"{claim_text}"
            )

        # --------------------------------------------------------------
        # SOURCE MUST HAVE VERIFIED EVIDENCE
        # --------------------------------------------------------------

        unusable_ids = [
            source_id
            for source_id in source_ids
            if source_id not in usable_source_ids
        ]

        if unusable_ids:

            unsupported.append(
                f"Claim uses source(s) without verified "
                f"evidence: "
                f"{', '.join(unusable_ids)}. "
                f"Claim: {claim_text}"
            )

        # --------------------------------------------------------------
        # SCENE LOCALITY
        # --------------------------------------------------------------

        wrong_scene_ids = [
            source_id
            for source_id in source_ids
            if source_id not in scene_source_ids
        ]

        if wrong_scene_ids:

            unsupported.append(
                f"Claim uses source(s) not cited by "
                f"scene {scene_number}: "
                f"{', '.join(wrong_scene_ids)}. "
                f"Claim: {claim_text}"
            )

        # --------------------------------------------------------------
        # STATUS
        # --------------------------------------------------------------

        if status in {
            "unsupported",
            "contradicted",
        }:

            unsupported.append(
                claim_text
            )

        elif status == "uncertain":

            warnings.append(
                claim_text
            )

        elif status != "supported":

            unsupported.append(
                f"Claim has invalid verification status "
                f"'{status}': {claim_text}"
            )

        # --------------------------------------------------------------
        # SUPPORTED CLAIM REQUIREMENTS
        # --------------------------------------------------------------

        if status == "supported":

            if not reason:

                unsupported.append(
                    f"Supported claim has no verification "
                    f"reason: {claim_text}"
                )

            if not evidence:

                unsupported.append(
                    f"Supported claim has no evidence "
                    f"explanation: {claim_text}"
                )

            if (
                not source_ids
                or invalid_ids
                or unusable_ids
                or wrong_scene_ids
                or not reason
                or not evidence
            ):

                unsupported.append(
                    f"Supported claim failed citation/evidence "
                    f"requirements: {claim_text}"
                )

    # ----------------------------------------------------------------------
    # SCENE REVIEW VALIDATION
    # ----------------------------------------------------------------------

    reviewed_scenes = set()

    for review in reviews:

        if not isinstance(
            review,
            dict,
        ):

            unsupported.append(
                "Verifier returned an invalid scene review."
            )

            continue

        scene_number = _safe_int(
            review.get(
                "scene",
                0,
            )
        )

        if scene_number not in expected_scenes:

            unsupported.append(
                f"Scene review references invalid "
                f"scene {scene_number}."
            )

            continue

        if scene_number in reviewed_scenes:

            unsupported.append(
                f"Scene {scene_number} was reviewed more than once."
            )

            continue

        reviewed_scenes.add(
            scene_number
        )

        reported_count = _safe_int(
            review.get(
                "claim_count",
                0,
            ),
            default=-1,
        )

        actual_count = claims_per_scene.get(
            scene_number,
            0,
        )

        if reported_count != actual_count:

            unsupported.append(
                f"Scene {scene_number} review reports "
                f"{reported_count} claims but verifier "
                f"returned {actual_count}."
            )

        factual_claims_found = (
            review.get(
                "factual_claims_found",
                False,
            )
            is True
        )

        if (
            factual_claims_found
            and actual_count == 0
        ):

            unsupported.append(
                f"Scene {scene_number} was marked factual "
                f"but returned zero claims."
            )

        if (
            not factual_claims_found
            and actual_count > 0
        ):

            unsupported.append(
                f"Scene {scene_number} returned claims "
                f"but factual_claims_found is false."
            )

    # ----------------------------------------------------------------------
    # EVERY SCENE MUST BE REVIEWED
    # ----------------------------------------------------------------------

    missing_reviews = (
        expected_scenes
        - reviewed_scenes
    )

    if missing_reviews:

        unsupported.append(
            "Missing scene reviews for scene(s): "
            + ", ".join(
                str(scene)
                for scene in sorted(
                    missing_reviews
                )
            )
        )

    # ----------------------------------------------------------------------
    # CONSERVATIVE COMPLETENESS CHECK
    # ----------------------------------------------------------------------

    for scene_number, narration in (
        scene_narration.items()
    ):

        if not narration:
            continue

        claim_count = claims_per_scene.get(
            scene_number,
            0,
        )

        numeric_signal = (
            _contains_numeric_claim_signal(
                narration
            )
        )

        factual_signal = (
            _contains_factual_language_signal(
                narration
            )
        )

        if (
            numeric_signal
            and claim_count == 0
        ):

            unsupported.append(
                f"Scene {scene_number} contains "
                f"quantitative language but Gemini "
                f"returned zero factual claims."
            )

        elif (
            factual_signal
            and claim_count == 0
        ):

            scene_review = None

            for review in reviews:

                if not isinstance(
                    review,
                    dict,
                ):
                    continue

                if (
                    _safe_int(
                        review.get(
                            "scene",
                            0,
                        )
                    )
                    == scene_number
                ):

                    scene_review = review
                    break

            if (
                scene_review
                and
                scene_review.get(
                    "factual_claims_found",
                    False,
                )
                is False
            ):

                unsupported.append(
                    f"Scene {scene_number} contains language "
                    f"that appears factual but was explicitly "
                    f"reviewed as zero claims."
                )

    # ----------------------------------------------------------------------
    # MINIMUM RESEARCH EVIDENCE
    # ----------------------------------------------------------------------

    if len(
        usable_source_ids
    ) < 2:

        unsupported.append(
            "Research package contains fewer than "
            "2 usable evidence-verified sources."
        )

    # ----------------------------------------------------------------------
    # DEDUPLICATE
    # ----------------------------------------------------------------------

    unsupported = _unique_clean_list(
        unsupported
    )

    warnings = _unique_clean_list(
        warnings
    )

    # ----------------------------------------------------------------------
    # FINAL STATUS
    #
    # Gemini's overall_status is ignored.
    #
    # Local validation is authoritative.
    # ----------------------------------------------------------------------

    if unsupported or warnings:

        result["overall_status"] = "FAIL"

    else:

        result["overall_status"] = "PASS"

    result["claims"] = claims
    result["scene_reviews"] = reviews
    result["unsupported_claims"] = unsupported
    result["warnings"] = warnings

    return result


# ==========================================================================
# STRUCTURAL FAILURE DETECTION
# ==========================================================================

def _is_structural_failure(result):

    if not isinstance(
        result,
        dict,
    ):
        return True

    problems = []

    problems.extend(
        result.get(
            "unsupported_claims",
            [],
        )
        or []
    )

    problems_text = "\n".join(
        _clean(problem).lower()
        for problem in problems
    )

    structural_markers = (
        "scene review",
        "scene reviews",
        "claim count",
        "quantitative language but gemini returned zero",
        "factual claims but returned zero",
        "returned claims but factual_claims_found",
        "verifier returned an invalid",
        "missing scene reviews",
        "returned an empty claim",
    )

    return any(
        marker in problems_text
        for marker in structural_markers
    )


# ==========================================================================
# RETRY FEEDBACK
# ==========================================================================

def _build_retry_feedback(
    result,
    attempt,
):

    problems = []

    if isinstance(
        result,
        dict,
    ):

        problems.extend(
            result.get(
                "unsupported_claims",
                [],
            )
            or []
        )

        problems.extend(
            result.get(
                "warnings",
                [],
            )
            or []
        )

    problems = _unique_clean_list(
        problems
    )

    return f"""
============================================================
VERIFICATION RETRY
============================================================

This is verification attempt {attempt}.

The previous result failed structural completeness checks.

You MUST re-read the COMPLETE narration.

Correct the structural problems below.

IMPORTANT:

Do NOT change a scientifically unsupported claim into a supported
claim merely to make the result pass.

Do NOT use outside knowledge.

Do NOT use metadata as evidence.

Do NOT borrow sources from another scene.

Do NOT invent source IDs.

Previous problems:

{json.dumps(
    problems[:40],
    ensure_ascii=False,
    indent=2,
)}

Remember:

- Every scene must have exactly one scene_reviews entry.
- Every factual claim must be extracted.
- Every factual claim must have scene-local source IDs.
- Numbers must be checked.
- Causal language must be checked.
- Evidence must come only from supplied Evidence Text.

Return the COMPLETE JSON result.
"""


# ==========================================================================
# PUBLIC API
# ==========================================================================

def verify_script_claims(
    script,
    research,
):

    if not isinstance(
        script,
        dict,
    ):

        raise RuntimeError(
            "Claim verification received an invalid script."
        )

    if not isinstance(
        research,
        dict,
    ):

        raise RuntimeError(
            "Claim verification received invalid research."
        )

    # ----------------------------------------------------------------------
    # RESEARCH STATUS
    # ----------------------------------------------------------------------

    if (
        research.get(
            "verified"
        )
        is not True
    ):

        raise RuntimeError(
            "Claim verification requires verified research."
        )

    if (
        research.get(
            "status"
        )
        != "VERIFIED"
    ):

        raise RuntimeError(
            "Claim verification requires research status VERIFIED."
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
            "Research sources are invalid."
        )

    if len(sources) < 2:

        raise RuntimeError(
            "Claim verification requires at least 2 research sources."
        )

    # ----------------------------------------------------------------------
    # NEXT-TOPIC BRIDGE (excluded from verification below)
    # ----------------------------------------------------------------------

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

    print("=" * 80)
    print(
        f"🧪 SCIENTIFIC CLAIM VERIFICATION v{VERSION}"
    )
    print("=" * 80)

    print(
        f"Research sources: {len(sources)}"
    )

    print(
        "Evidence policy: VERIFIED EVIDENCE TEXT ONLY"
    )

    print(
        "Citation policy: SCENE-LOCAL SOURCES ONLY"
    )

    print(
        "Completeness policy: EVERY SCENE REVIEWED"
    )

    print(
        "Numeric claim policy: EXPLICITLY CHECKED"
    )

    print(
        "Next-topic bridge policy: EXCLUDED FROM VERIFICATION"
    )

    # ----------------------------------------------------------------------
    # AUTHORITATIVE SOURCE IDS
    # ----------------------------------------------------------------------

    source_map = _build_source_map(
        research
    )

    print(
        f"Authoritative source IDs: "
        f"{len(source_map)}"
    )

    for source_id in source_map:

        print(
            f"  🔗 {source_id}"
        )

    # ----------------------------------------------------------------------
    # GEMINI VERIFICATION
    # ----------------------------------------------------------------------

    last_result = None

    retry_feedback = ""

    for attempt in range(
        1,
        MAX_VERIFICATION_ATTEMPTS + 1,
    ):

        print("=" * 80)

        print(
            f"🧠 CLAIM VERIFICATION ATTEMPT "
            f"{attempt}/{MAX_VERIFICATION_ATTEMPTS}"
        )

        try:

            raw_result = _verify_with_gemini(
                script,
                research,
                retry_feedback,
                next_topic,
            )

            result = _local_validate(
                raw_result,
                script,
                research,
                next_topic,
            )

            last_result = result

            # --------------------------------------------------------------
            # SUCCESS
            # --------------------------------------------------------------

            if (
                result.get(
                    "overall_status"
                )
                == "PASS"
            ):

                break

            # --------------------------------------------------------------
            # STRUCTURAL FAILURE
            #
            # Retry only structural problems.
            # Genuine scientific failures are not retried.
            # --------------------------------------------------------------

            if (
                _is_structural_failure(
                    result
                )
                and
                attempt
                < MAX_VERIFICATION_ATTEMPTS
            ):

                print(
                    "⚠️ Structural completeness issue detected."
                )

                print(
                    f"⏳ Retrying in "
                    f"{RETRY_DELAY_SECONDS}s..."
                )

                retry_feedback = (
                    _build_retry_feedback(
                        result,
                        attempt + 1,
                    )
                )

                time.sleep(
                    RETRY_DELAY_SECONDS
                )

                continue

            # --------------------------------------------------------------
            # GENUINE SCIENTIFIC FAILURE
            # --------------------------------------------------------------

            break

        except Exception as error:

            print(
                f"❌ Verification attempt "
                f"{attempt} failed:"
            )

            print(
                f"{type(error).__name__}: {error}"
            )

            if (
                attempt
                >= MAX_VERIFICATION_ATTEMPTS
            ):

                raise RuntimeError(
                    "Scientific claim verification failed "
                    f"after {MAX_VERIFICATION_ATTEMPTS} attempts: "
                    f"{error}"
                ) from error

            print(
                f"⏳ Retrying in "
                f"{RETRY_DELAY_SECONDS}s..."
            )

            time.sleep(
                RETRY_DELAY_SECONDS
            )

    if last_result is None:

        raise RuntimeError(
            "Scientific claim verification produced no result."
        )

    # ----------------------------------------------------------------------
    # FINAL LOCAL GATE
    #
    # This is intentionally run again.
    #
    # Gemini NEVER controls PASS/FAIL.
    # ----------------------------------------------------------------------

    result = _local_validate(
        last_result,
        script,
        research,
        next_topic,
    )

    # ----------------------------------------------------------------------
    # STORE VERIFICATION
    # ----------------------------------------------------------------------

    script[
        "claim_verification"
    ] = {
        "overall_status": result.get(
            "overall_status",
            "FAIL",
        ),
        "claims": result.get(
            "claims",
            [],
        ),
        "scene_reviews": result.get(
            "scene_reviews",
            [],
        ),
        "unsupported_claims": result.get(
            "unsupported_claims",
            [],
        ),
        "warnings": result.get(
            "warnings",
            [],
        ),
        "verified": (
            result.get(
                "overall_status"
            )
            == "PASS"
        ),
    }

    # ----------------------------------------------------------------------
    # OUTPUT
    # ----------------------------------------------------------------------

    if (
        result.get(
            "overall_status"
        )
        == "PASS"
    ):

        print("=" * 80)
        print(
            "✅ ALL IMPORTANT CLAIMS VERIFIED"
        )
        print("=" * 80)

        print(
            f"Verified claims: "
            f"{len(result.get('claims', []))}"
        )

        print(
            f"Scenes reviewed: "
            f"{len(result.get('scene_reviews', []))}"
        )

        print(
            "Numeric claim checks: ENABLED"
        )

        print(
            "Scene-local citations: VERIFIED"
        )

        print(
            "Evidence-only verification: VERIFIED"
        )

    else:

        print("=" * 80)
        print(
            "❌ CLAIM VERIFICATION FAILED"
        )
        print("=" * 80)

        unsupported = result.get(
            "unsupported_claims",
            [],
        )

        warnings = result.get(
            "warnings",
            [],
        )

        if unsupported:

            print(
                "\n❌ Unsupported / invalid claims:"
            )

            for item in unsupported:

                print(
                    f"  ❌ {item}"
                )

        if warnings:

            print(
                "\n⚠️ Uncertain claims:"
            )

            for item in warnings:

                print(
                    f"  ⚠️ {item}"
                )

    print("=" * 80)

    return script


# ==========================================================================
# VERIFICATION STATUS
# ==========================================================================

def claims_are_verified(
    script,
):

    if not isinstance(
        script,
        dict,
    ):

        return False

    verification = script.get(
        "claim_verification",
        {},
    )

    if not isinstance(
        verification,
        dict,
    ):

        return False

    return (
        verification.get(
            "verified"
        )
        is True
        and
        verification.get(
            "overall_status"
        )
        == "PASS"
        and
        isinstance(
            verification.get(
                "claims",
                [],
            ),
            list,
        )
        and
        isinstance(
            verification.get(
                "scene_reviews",
                [],
            ),
            list,
        )
        and
        not verification.get(
            "unsupported_claims",
            [],
        )
        and
        not verification.get(
            "warnings",
            [],
        )
    )


# ==========================================================================
# LOCAL TEST
# ==========================================================================

if __name__ == "__main__":

    print(
        f"verify_claims.py v{VERSION} "
        "is a pipeline module."
    )

    print(
        "It is called automatically by main.py."
    )
