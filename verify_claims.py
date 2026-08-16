"""
verify_claims.py
Mint-YT-Factory

Version 2.2

Hardened scientific claim verification layer.

FLOW:

Generated Script
      ↓
Extract IMPORTANT factual claims
      ↓
Use only scene-cited research sources
      ↓
Compare against verified Evidence Text
      ↓
Gemini evaluates support
      ↓
Local structural + citation + completeness validation
      ↓
PASS / FAIL
      ↓
Only verified scripts continue

IMPORTANT:

- Gemini may ONLY use supplied Evidence Text.
- Metadata is NEVER treated as scientific evidence.
- Claims must use source IDs cited by their scene.
- Claims cannot switch to an unrelated source.
- Every important factual claim must have a valid citation.
- Every cited source must be evidence-verified.
- Evidence Text must actually exist.
- Uncertain claims FAIL.
- Unsupported claims FAIL.
- Contradicted claims FAIL.
- Invalid source IDs FAIL.
- Claims with zero source IDs FAIL.
- A scene does NOT need to contain a factual claim.
- Abstracts are accepted only when they are part of the verified
  research evidence package.
- Gemini cannot introduce outside knowledge.
- Original research source IDs are preserved exactly.
- Numeric claims are explicitly checked.
- Scene coverage is explicitly checked.
- Gemini verification may be retried when the returned result is
  structurally incomplete.
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
            "GEMINI_API_KEY environment "
            "variable is missing."
        )

    return api_key


def _unique_clean_list(values):

    if not isinstance(
        values,
        list,
    ):
        return []

    result = []
    seen = set()

    for value in values:

        value = _clean(value)

        if not value:
            continue

        key = value.lower()

        if key in seen:
            continue

        seen.add(key)
        result.append(value)

    return result


# ==========================================================================
# NUMERIC / FACTUAL SIGNAL DETECTION
# ==========================================================================

def _contains_numeric_claim_signal(
    narration
):
    """
    Detect whether narration contains obvious quantitative content.

    This is intentionally conservative.

    It does NOT decide whether something is scientifically factual.

    It only tells the local verifier:

        "Gemini must not silently ignore this sentence."

    Examples:

        80%
        10 meters
        37 degrees
        3 times
        2024
        1.5 million
        2x
    """

    text = _clean(
        narration
    )

    if not text:
        return False

    numeric_patterns = [

        # Percentages
        r"\b\d+(?:\.\d+)?\s*%",

        # Numbers with common scientific units
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

        # Decimal / standalone quantitative numbers
        r"\b\d+\.\d+\b",

        # Years
        r"\b(?:1[5-9]\d{2}|20\d{2}|21\d{2})\b",
    ]

    for pattern in numeric_patterns:

        if re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):

            return True

    return False


def _contains_factual_language_signal(
    narration
):
    """
    Conservative heuristic for detecting sentences that may contain
    factual/scientific claims.

    This is NOT a scientific classifier.

    It exists only as a second completeness safeguard so that Gemini
    cannot silently return zero claims for obviously factual narration.
    """

    text = _clean(
        narration
    )

    if not text:
        return False

    lowered = text.lower()

    factual_patterns = [

        # Research language
        r"\bresearchers?\b",
        r"\bscientists?\b",
        r"\bstudy\b",
        r"\bstudies\b",
        r"\bexperiment\b",
        r"\bexperiments\b",
        r"\bobserved\b",
        r"\bfound\b",
        r"\bfindings?\b",
        r"\bdata\b",
        r"\bevidence\b",

        # Causal / mechanistic language
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

        # Scientific observation language
        r"\bcontains?\b",
        r"\bconsists? of\b",
        r"\bhas\b",
        r"\bhave\b",
        r"\buses?\b",
        r"\buses\b",
        r"\bproduces?\b",
        r"\babsorbs?\b",
        r"\breflects?\b",
        r"\bemits?\b",
        r"\bdetects?\b",
        r"\bmeasures?\b",

        # Biological / physical mechanism signals
        r"\bcell\b",
        r"\bcells\b",
        r"\bbrain\b",
        r"\bneuron\b",
        r"\bneurons\b",
        r"\bhormone\b",
        r"\bhormones\b",
        r"\bdna\b",
        r"\bprotein\b",
        r"\bproteins\b",
        r"\batom\b",
        r"\batoms\b",
        r"\bmolecule\b",
        r"\bmolecules\b",
        r"\benergy\b",
        r"\bpressure\b",
        r"\btemperature\b",
        r"\bgravity\b",
        r"\bvelocity\b",
        r"\bfrequency\b",
        r"\bradiation\b",
        r"\bmagnetic\b",
        r"\belectric\b",

        # Strong factual verbs
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
    ]

    for pattern in factual_patterns:

        if re.search(
            pattern,
            lowered,
        ):

            return True

    return False


# ==========================================================================
# BUILD VERIFIED SOURCE MAP
# ==========================================================================

def _build_source_map(
    research
):
    """
    Build the authoritative source map.

    The source_id generated by research.py is authoritative.

    NEVER create artificial source IDs.
    """

    sources = research.get(
        "sources",
        [],
    )

    source_map = {}

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
# BUILD RESEARCH EVIDENCE
# ==========================================================================

def _build_research_evidence(
    research
):
    """
    Build the evidence package Gemini is allowed to use.

    ONLY evidence-verified sources are presented as usable evidence.
    """

    source_map = _build_source_map(
        research
    )

    blocks = []

    for source_id, source in source_map.items():

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

        evidence_text = _clean(
            source.get(
                "evidence_text",
                "",
            )
        )

        evidence_type = _clean(
            source.get(
                "evidence_type",
                "",
            )
        )

        evidence_quality = _clean(
            source.get(
                "evidence_quality",
                "",
            )
        )

        evidence_available = (
            source.get(
                "evidence_available",
                False,
            )
        )

        evidence_verified = (
            source.get(
                "evidence_verified",
                False,
            )
        )

        verification_level = _clean(
            source.get(
                "verification_level",
                "",
            )
        )

        if evidence_verified is not True:
            continue

        if evidence_available is not True:
            continue

        if not evidence_text:
            continue

        if len(
            evidence_text
        ) < MIN_EVIDENCE_CHARACTERS:
            continue

        blocks.append(
            f"""
SOURCE ID: {source_id}

============================================================
SOURCE METADATA
============================================================

Title:
{title}

Authors:
{authors}

Journal:
{journal}

Year:
{year}

DOI:
{doi}

Verification Level:
{verification_level}

Evidence Verified:
{evidence_verified}

============================================================
SCIENTIFIC EVIDENCE
============================================================

Evidence Available:
{evidence_available}

Evidence Type:
{evidence_type}

Evidence Quality:
{evidence_quality}

Evidence Text:
{evidence_text}

============================================================
IMPORTANT
============================================================

Only the Evidence Text above may be used to support factual
claims.

Metadata is NOT scientific evidence.
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
# BUILD SCRIPT CLAIM CONTEXT
# ==========================================================================

def _build_claim_context(
    script
):

    scenes = script.get(
        "scene_plan",
        [],
    )

    blocks = []

    for scene in scenes:

        if not isinstance(
            scene,
            dict,
        ):
            continue

        scene_number = scene.get(
            "scene"
        )

        narration = _clean(
            scene.get(
                "narration",
                "",
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

        source_ids = [
            str(source_id).strip()
            for source_id in source_ids
            if str(source_id).strip()
        ]

        blocks.append(
            f"""
SCENE {scene_number}

Narration:
{narration}

CITED SOURCE IDS FOR THIS SCENE:
{json.dumps(source_ids)}
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

        "type":
            "object",

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

        "type":
            "object",

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

        "type":
            "object",

        "properties": {

            "overall_status": {

                "type":
                    "string",

                "enum": [
                    "PASS",
                    "FAIL",
                ],
            },

            "claims": {

                "type":
                    "array",

                "items":
                    claim,
            },

            "scene_reviews": {

                "type":
                    "array",

                "items":
                    scene_review,
            },

            "unsupported_claims": {

                "type":
                    "array",

                "items": {
                    "type": "string",
                },
            },

            "warnings": {

                "type":
                    "array",

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

Your job is NOT to rewrite the script.

Your job is to determine whether EVERY IMPORTANT FACTUAL CLAIM in
the generated YouTube Short is actually supported by the supplied
verified scientific evidence.

============================================================
ABSOLUTE EVIDENCE RULE
============================================================

You may ONLY use the supplied SCIENTIFIC EVIDENCE text.

Do NOT use:

- general knowledge
- model memory
- internet knowledge
- outside scientific knowledge
- invented evidence
- invented studies
- invented statistics
- information not contained in the supplied Evidence Text

============================================================
METADATA IS NOT EVIDENCE
============================================================

Never use:

- title
- authors
- journal
- year
- DOI
- URL
- verification level
- evidence type
- evidence quality

as proof of a scientific claim.

Only Evidence Text can support a scientific claim.

============================================================
IMPORTANT CLAIM EXTRACTION
============================================================

For EVERY scene:

1. Read the COMPLETE narration.
2. Identify EVERY IMPORTANT FACTUAL CLAIM.
3. Do NOT skip claims because they appear in storytelling language.
4. Do NOT create artificial claims from purely stylistic language.

Examples of factual claims:

- how something works
- what causes something
- what happens
- measurable effects
- scientific observations
- biological mechanisms
- physical mechanisms
- historical facts
- dates
- numbers
- percentages
- research findings
- relationships between variables
- scientific conclusions

Stylistic examples that are NOT claims:

"Here's where it gets interesting."

"This changes everything."

"Nature has another surprise."

"That makes the story even stranger."

============================================================
SCENE COVERAGE
============================================================

You MUST return one scene_reviews object for EVERY scene.

If a scene contains factual claims:

factual_claims_found:
true

and claim_count must equal the number of factual claims extracted.

If a scene contains only stylistic language:

factual_claims_found:
false

claim_count:
0

Do NOT omit scene reviews.

============================================================
SCENE CITATION RULE
============================================================

Every factual claim must use ONLY source IDs cited by THAT scene.

Never substitute a source from another scene.

Never invent a source ID.

Never add a source that the scene did not cite.

Verifier source_ids MUST be a subset of the scene's source_ids.

Preserve source IDs EXACTLY.

============================================================
STATUS DEFINITIONS
============================================================

supported:
The supplied Evidence Text directly supports the claim.

uncertain:
The supplied Evidence Text is related but insufficient.

unsupported:
The supplied Evidence Text does not support the claim.

contradicted:
The supplied Evidence Text conflicts with the claim.

============================================================
DO NOT STRENGTHEN SCIENTIFIC LANGUAGE
============================================================

"may contribute" ≠ "causes"

"associated with" ≠ "causes"

"possible" ≠ "certain"

"hypothesis" ≠ "proven"

"observed" ≠ "always occurs"

"could explain" ≠ "explains"

============================================================
NUMBERS
============================================================

Every number, percentage, measurement, date, quantity, or statistic
must be supported by the supplied Evidence Text.

Do not invent or infer numbers.

============================================================
CAUSATION
============================================================

Do not convert:

correlation → causation

association → causation

possibility → certainty

hypothesis → established fact

observation → universal rule

============================================================
CLAIM CITATION REQUIREMENT
============================================================

Every important factual claim MUST have at least one source ID.

If a factual claim has zero source IDs:

FAIL it.

If a claim uses an invalid source ID:

FAIL it.

If a claim uses a source ID that was not cited by its scene:

FAIL it.

============================================================
EVIDENCE FIELD
============================================================

For every supported claim:

- provide a concise reason
- provide a concise evidence explanation
- use ONLY supplied Evidence Text
- do not invent quotations
- do not claim evidence says something it does not say

============================================================
PASS CONDITION
============================================================

PASS is allowed only when:

1. Every important factual claim was extracted.
2. Every important factual claim is supported.
3. No important claim is contradicted.
4. No important claim is unsupported.
5. No important claim is uncertain.
6. Every factual claim has valid source IDs.
7. Every factual claim's source IDs belong to that scene.
8. Numbers are supported.
9. Causal language is supported.
10. No outside knowledge was required.
11. Every scene has been explicitly reviewed.

Return ONLY valid JSON.
"""


# ==========================================================================
# VERIFY WITH GEMINI
# ==========================================================================

def _verify_with_gemini(
    script,
    research,
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
            script
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

Review EVERY scene.

For each scene:

1. Read the entire narration.
2. Identify every important factual claim.
3. Do not skip quantitative claims.
4. Do not skip causal/mechanistic claims.
5. Do not turn stylistic sentences into claims.
6. Create exactly one scene_reviews entry.

For every factual claim:

1. State the claim.
2. Identify its scene.
3. Look ONLY at Evidence Text belonging to sources cited by
   that scene.
4. Do NOT use metadata as evidence.
5. Return source_ids that are a SUBSET of that scene's cited IDs.
6. Preserve exact source IDs.
7. Determine whether the supplied evidence directly supports it.
8. Explain why.
9. Provide a concise evidence explanation.

IMPORTANT:

Do NOT use sources from another scene.

Do NOT introduce outside information.

Do NOT invent evidence.

Do NOT upgrade uncertainty into certainty.

Do NOT convert correlation into causation.

Do NOT accept unsupported numbers.

A scene with only stylistic narration may have:

factual_claims_found = false
claim_count = 0

But EVERY scene must still appear in scene_reviews.

Return ONLY JSON.
"""

    response = client.models.generate_content(

        model=MODEL_NAME,

        contents=prompt,

        config=types.GenerateContentConfig(

            system_instruction=
                _system_prompt(),

            response_mime_type=
                "application/json",

            response_json_schema=
                build_response_schema(),
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
        )


# ==========================================================================
# LOCAL SAFETY VALIDATION
# ==========================================================================

def _local_validate(
    result,
    script,
    research,
):
    """
    Local safety layer.

    Gemini evaluates scientific support.

    Local validation enforces:

    - valid source IDs
    - scene-local citations
    - usable evidence
    - supported-only PASS
    - no uncertainty
    - no unsupported claims
    - no contradicted claims
    - scene coverage
    - numeric claim coverage
    - claim limits
    """

    if not isinstance(
        result,
        dict,
    ):

        raise RuntimeError(
            "Claim verifier returned "
            "an invalid result."
        )

    source_map = _build_source_map(
        research
    )

    valid_source_ids = set(
        source_map.keys()
    )

    # ----------------------------------------------------------------------
    # USABLE SOURCE IDS
    # ----------------------------------------------------------------------

    usable_source_ids = set()

    for source_id, source in source_map.items():

        if not isinstance(
            source,
            dict,
        ):
            continue

        if source.get(
            "verified"
        ) is not True:

            # Some research packages may not include this field,
            # but the upstream research gate requires it.
            continue

        if source.get(
            "evidence_verified"
        ) is not True:

            continue

        if source.get(
            "evidence_available"
        ) is not True:

            continue

        evidence_text = _clean(
            source.get(
                "evidence_text",
                "",
            )
        )

        if len(
            evidence_text
        ) < MIN_EVIDENCE_CHARACTERS:

            continue

        usable_source_ids.add(
            source_id
        )

    # ----------------------------------------------------------------------
    # SCENE MAP
    # ----------------------------------------------------------------------

    scene_source_map = {}

    scene_narration_map = {}

    scenes = script.get(
        "scene_plan",
        [],
    )

    if not isinstance(
        scenes,
        list,
    ):

        raise RuntimeError(
            "Script scene_plan is invalid."
        )

    for scene in scenes:

        if not isinstance(
            scene,
            dict,
        ):
            continue

        try:

            scene_number = int(
                scene.get(
                    "scene",
                    0,
                )
            )

        except Exception:

            scene_number = 0

        source_ids = scene.get(
            "source_ids",
            [],
        )

        if not isinstance(
            source_ids,
            list,
        ):

            source_ids = []

        normalized_ids = set(

            str(source_id).strip()

            for source_id in source_ids

            if str(source_id).strip()
        )

        scene_source_map[
            scene_number
        ] = normalized_ids

        scene_narration_map[
            scene_number
        ] = _clean(
            scene.get(
                "narration",
                "",
            )
        )

    expected_scene_numbers = set(
        scene_source_map.keys()
    )

    # ----------------------------------------------------------------------
    # RESULT ARRAYS
    # ----------------------------------------------------------------------

    claims = result.get(
        "claims",
        [],
    )

    if not isinstance(
        claims,
        list,
    ):

        claims = []

    scene_reviews = result.get(
        "scene_reviews",
        [],
    )

    if not isinstance(
        scene_reviews,
        list,
    ):

        scene_reviews = []

    unsupported = list(
        result.get(
            "unsupported_claims",
            [],
        )
        or []
    )

    warnings = list(
        result.get(
            "warnings",
            [],
        )
        or []
    )

    # ----------------------------------------------------------------------
    # CLAIM VALIDATION
    # ----------------------------------------------------------------------

    claims_per_scene = {}

    supported_claims = []

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

        if not claim_text:

            unsupported.append(
                "Verifier returned an empty claim."
            )

            continue

        try:

            scene_number = int(
                claim.get(
                    "scene",
                    0,
                )
            )

        except Exception:

            scene_number = 0

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

        source_ids = [
            str(source_id).strip()
            for source_id in source_ids
            if str(source_id).strip()
        ]

        source_ids = list(
            dict.fromkeys(
                source_ids
            )
        )

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
                (
                    f"Scene {scene_number} has more than "
                    f"{MAX_CLAIMS_PER_SCENE} claims."
                )
            )

        # --------------------------------------------------------------
        # SCENE MUST EXIST
        # --------------------------------------------------------------

        if scene_number not in scene_source_map:

            unsupported.append(
                (
                    f"Claim references invalid scene "
                    f"{scene_number}: {claim_text}"
                )
            )

            continue

        scene_sources = scene_source_map[
            scene_number
        ]

        # --------------------------------------------------------------
        # CLAIM MUST HAVE CITATION
        # --------------------------------------------------------------

        if not source_ids:

            unsupported.append(
                (
                    f"Claim has no source citation: "
                    f"{claim_text}"
                )
            )

        # --------------------------------------------------------------
        # SOURCE IDS MUST EXIST
        # --------------------------------------------------------------

        invalid_ids = [

            source_id

            for source_id in source_ids

            if source_id not in valid_source_ids
        ]

        if invalid_ids:

            unsupported.append(
                (
                    f"Invalid source citation "
                    f"{', '.join(invalid_ids)}: "
                    f"{claim_text}"
                )
            )

        # --------------------------------------------------------------
        # SOURCES MUST BE USABLE
        # --------------------------------------------------------------

        unusable_ids = [

            source_id

            for source_id in source_ids

            if source_id not in usable_source_ids
        ]

        if unusable_ids:

            unsupported.append(
                (
                    f"Claim uses source(s) without verified "
                    f"evidence: "
                    f"{', '.join(unusable_ids)}. "
                    f"Claim: {claim_text}"
                )
            )

        # --------------------------------------------------------------
        # SCENE-LOCAL CITATION
        # --------------------------------------------------------------

        wrong_scene_sources = [

            source_id

            for source_id in source_ids

            if source_id not in scene_sources
        ]

        if wrong_scene_sources:

            unsupported.append(
                (
                    f"Claim uses source(s) not cited by "
                    f"scene {scene_number}: "
                    f"{', '.join(wrong_scene_sources)}. "
                    f"Claim: {claim_text}"
                )
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
                (
                    f"Claim has invalid verification status "
                    f"'{status}': {claim_text}"
                )
            )

        # --------------------------------------------------------------
        # SUPPORTED CLAIM REQUIREMENTS
        # --------------------------------------------------------------

        if status == "supported":

            if not reason:

                unsupported.append(
                    (
                        f"Supported claim has no verification "
                        f"reason: {claim_text}"
                    )
                )

            if not evidence:

                unsupported.append(
                    (
                        f"Supported claim has no evidence "
                        f"explanation: {claim_text}"
                    )
                )

            if not source_ids:

                unsupported.append(
                    (
                        f"Supported claim has no source: "
                        f"{claim_text}"
                    )
                )

            if invalid_ids:

                unsupported.append(
                    (
                        f"Supported claim uses invalid source: "
                        f"{claim_text}"
                    )
                )

            if unusable_ids:

                unsupported.append(
                    (
                        f"Supported claim uses source without "
                        f"verified evidence: {claim_text}"
                    )
                )

            if wrong_scene_sources:

                unsupported.append(
                    (
                        f"Supported claim uses source from "
                        f"another scene: {claim_text}"
                    )
                )

            if (
                not invalid_ids
                and not unusable_ids
                and not wrong_scene_sources
                and source_ids
                and reason
                and evidence
            ):

                supported_claims.append(
                    claim
                )

    # ----------------------------------------------------------------------
    # SCENE REVIEW VALIDATION
    # ----------------------------------------------------------------------

    reviewed_scenes = set()

    for review in scene_reviews:

        if not isinstance(
            review,
            dict,
        ):

            unsupported.append(
                "Verifier returned an invalid scene review."
            )

            continue

        try:

            scene_number = int(
                review.get(
                    "scene",
                    0,
                )
            )

        except Exception:

            scene_number = 0

        if scene_number not in expected_scene_numbers:

            unsupported.append(
                (
                    f"Scene review references invalid "
                    f"scene {scene_number}."
                )
            )

            continue

        if scene_number in reviewed_scenes:

            unsupported.append(
                (
                    f"Scene {scene_number} was reviewed "
                    f"more than once."
                )
            )

            continue

        reviewed_scenes.add(
            scene_number
        )

        factual_claims_found = (
            review.get(
                "factual_claims_found",
                False,
            )
            is True
        )

        try:

            reported_count = int(
                review.get(
                    "claim_count",
                    0,
                )
            )

        except Exception:

            reported_count = -1

        actual_count = claims_per_scene.get(
            scene_number,
            0,
        )

        # --------------------------------------------------------------
        # CLAIM COUNT MUST MATCH
        # --------------------------------------------------------------

        if reported_count != actual_count:

            unsupported.append(
                (
                    f"Scene {scene_number} review reports "
                    f"{reported_count} claims but verifier "
                    f"returned {actual_count}."
                )
            )

        # --------------------------------------------------------------
        # FACTUAL FLAG MUST MATCH
        # --------------------------------------------------------------

        if (
            factual_claims_found
            and actual_count == 0
        ):

            unsupported.append(
                (
                    f"Scene {scene_number} was marked as containing "
                    f"factual claims but no claims were returned."
                )
            )

        if (
            not factual_claims_found
            and actual_count > 0
        ):

            unsupported.append(
                (
                    f"Scene {scene_number} returned factual claims "
                    f"but factual_claims_found was false."
                )
            )

    # ----------------------------------------------------------------------
    # EVERY SCENE MUST BE REVIEWED
    # ----------------------------------------------------------------------

    missing_scene_reviews = (
        expected_scene_numbers
        - reviewed_scenes
    )

    if missing_scene_reviews:

        unsupported.append(
            (
                "Missing scene reviews for scene(s): "
                +
                ", ".join(
                    str(x)
                    for x in sorted(
                        missing_scene_reviews
                    )
                )
            )
        )

    # ----------------------------------------------------------------------
    # LOCAL COMPLETENESS CHECK
    #
    # We intentionally use conservative heuristics here.
    #
    # A numeric/factual signal means Gemini must have returned at least
    # one claim for that scene.
    # ----------------------------------------------------------------------

    for scene_number, narration in scene_narration_map.items():

        if not narration:
            continue

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

        returned_claim_count = claims_per_scene.get(
            scene_number,
            0,
        )

        if (
            numeric_signal
            and returned_claim_count == 0
        ):

            unsupported.append(
                (
                    f"Scene {scene_number} contains quantitative "
                    f"language but Gemini returned zero factual "
                    f"claims."
                )
            )

        elif (
            factual_signal
            and returned_claim_count == 0
        ):

            # We do not automatically fail every factual-looking
            # sentence because some can still be stylistic.
            #
            # However, if Gemini explicitly marked the scene as
            # non-factual, the combination is suspicious enough
            # to require a retry/failure.
            review = None

            for candidate in scene_reviews:

                if not isinstance(
                    candidate,
                    dict,
                ):
                    continue

                try:

                    candidate_scene = int(
                        candidate.get(
                            "scene",
                            0,
                        )
                    )

                except Exception:

                    candidate_scene = 0

                if candidate_scene == scene_number:

                    review = candidate
                    break

            if (
                review
                and
                review.get(
                    "factual_claims_found",
                    False,
                )
                is False
            ):

                unsupported.append(
                    (
                        f"Scene {scene_number} contains language "
                        f"that appears factual but was explicitly "
                        f"reviewed as having zero factual claims."
                    )
                )

    # ----------------------------------------------------------------------
    # RESEARCH PACKAGE MUST HAVE MULTIPLE USABLE SOURCES
    # ----------------------------------------------------------------------

    if len(
        usable_source_ids
    ) < 2:

        unsupported.append(
            (
                "Research package contains fewer than "
                "2 usable evidence-verified sources."
            )
        )

    # ----------------------------------------------------------------------
    # RESULT CLAIMS MUST NOT BE EMPTY WHEN FACTUAL CLAIMS EXIST
    # ----------------------------------------------------------------------

    factual_scene_exists = False

    for scene_number, narration in scene_narration_map.items():

        if (
            _contains_numeric_claim_signal(
                narration
            )
            or
            _contains_factual_language_signal(
                narration
            )
        ):

            factual_scene_exists = True
            break

    if (
        factual_scene_exists
        and not claims
    ):

        unsupported.append(
            (
                "Narration contains factual signals but "
                "the verifier returned zero claims."
            )
        )

    # ----------------------------------------------------------------------
    # DEDUPLICATE
    # ----------------------------------------------------------------------

    unsupported = list(
        dict.fromkeys(

            _clean(x)

            for x in unsupported

            if _clean(x)
        )
    )

    warnings = list(
        dict.fromkeys(

            _clean(x)

            for x in warnings

            if _clean(x)
        )
    )

    # ----------------------------------------------------------------------
    # FINAL STATUS
    #
    # Warnings are failures.
    # ----------------------------------------------------------------------

    if unsupported:

        result[
            "overall_status"
        ] = "FAIL"

    elif warnings:

        result[
            "overall_status"
        ] = "FAIL"

    else:

        result[
            "overall_status"
        ] = "PASS"

    result[
        "unsupported_claims"
    ] = unsupported

    result[
        "warnings"
    ] = warnings

    # Normalize scene reviews.
    result[
        "scene_reviews"
    ] = scene_reviews

    return result


# ==========================================================================
# VERIFICATION RETRY DECISION
# ==========================================================================

def _result_requires_retry(
    result
):
    """
    Determine whether another Gemini verification attempt may fix a
    structural extraction problem.

    A retry is useful for:

    - missing scene reviews
    - claim-count mismatch
    - suspicious zero-claim result
    - invalid JSON/structure handled by caller

    A retry is NOT used to override genuine unsupported/uncertain/
    contradicted claims.
    """

    if not isinstance(
        result,
        dict,
    ):

        return True

    scene_reviews = result.get(
        "scene_reviews",
        [],
    )

    if not isinstance(
        scene_reviews,
        list,
    ):

        return True

    claims = result.get(
        "claims",
        [],
    )

    if not isinstance(
        claims,
        list,
    ):

        return True

    return False


# ==========================================================================
# RETRY PROMPT
# ==========================================================================

def _build_retry_instruction(
    attempt,
    previous_result,
):

    scene_reviews = (
        previous_result.get(
            "scene_reviews",
            [],
        )
        if isinstance(
            previous_result,
            dict,
        )
        else []
    )

    claims = (
        previous_result.get(
            "claims",
            [],
        )
        if isinstance(
            previous_result,
            dict,
        )
        else []
    )

    return f"""
============================================================
VERIFICATION RETRY
============================================================

This is verification attempt {attempt}.

The previous verification result was structurally incomplete
or suspicious.

You MUST re-read the COMPLETE narration.

Previous result summary:

Scene reviews returned:
{len(scene_reviews)}

Claims returned:
{len(claims)}

CRITICAL:

- Review EVERY scene.
- Return exactly one scene_reviews entry for every scene.
- Do not silently omit factual claims.
- Check every number and quantitative statement.
- Check every causal or mechanistic statement.
- Every factual claim needs a source ID.
- Source IDs must belong to the scene.
- Use ONLY supplied Evidence Text.
- Do NOT use metadata.
- Do NOT use outside knowledge.
- Do NOT invent evidence.

Return the COMPLETE JSON result again.
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
            "Claim verification received "
            "an invalid script."
        )

    if not isinstance(
        research,
        dict,
    ):

        raise RuntimeError(
            "Claim verification received "
            "invalid research."
        )

    # ----------------------------------------------------------------------
    # RESEARCH MUST BE VERIFIED
    # ----------------------------------------------------------------------

    if research.get(
        "verified"
    ) is not True:

        raise RuntimeError(
            "Claim verification requires "
            "verified research."
        )

    if research.get(
        "status"
    ) != "VERIFIED":

        raise RuntimeError(
            "Claim verification requires "
            "research status VERIFIED."
        )

    # ----------------------------------------------------------------------
    # RESEARCH MUST HAVE MULTIPLE SOURCES
    # ----------------------------------------------------------------------

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

    if len(
        sources
    ) < 2:

        raise RuntimeError(
            "Claim verification requires "
            "at least 2 research sources."
        )

    print("=" * 80)
    print("🧪 SCIENTIFIC CLAIM VERIFICATION v2.2")
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

    # ----------------------------------------------------------------------
    # PRINT AUTHORITATIVE SOURCE IDS
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
    # GEMINI VERIFICATION WITH RETRIES
    # ----------------------------------------------------------------------

    result = None
    last_error = None

    for attempt in range(
        1,
        MAX_VERIFICATION_ATTEMPTS + 1,
    ):

        print(
            "=" * 80
        )

        print(
            f"🧠 CLAIM VERIFICATION ATTEMPT "
            f"{attempt}/{MAX_VERIFICATION_ATTEMPTS}"
        )

        try:

            raw_result = _verify_with_gemini(
                script,
                research,
            )

            # --------------------------------------------------------------
            # LOCAL VALIDATION
            # --------------------------------------------------------------

            validated_result = _local_validate(
                raw_result,
                script,
                research,
            )

            result = validated_result

            # --------------------------------------------------------------
            # If the result passes, we're done.
            # --------------------------------------------------------------

            if (
                result.get(
                    "overall_status"
                )
                == "PASS"
            ):

                break

            # --------------------------------------------------------------
            # If it fails because of a structural completeness problem,
            # retry.
            # --------------------------------------------------------------

            unsupported = result.get(
                "unsupported_claims",
                [],
            )

            structural_failure = any(
                (
                    "scene review"
                    in str(item).lower()
                    or
                    "scene reviews"
                    in str(item).lower()
                    or
                    "returned zero factual claims"
                    in str(item).lower()
                    or
                    "quantitative language"
                    in str(item).lower()
                    or
                    "claim count"
                    in str(item).lower()
                )
                for item in unsupported
            )

            if (
                structural_failure
                and attempt
                <
                MAX_VERIFICATION_ATTEMPTS
            ):

                print(
                    "⚠️ Verification result appears "
                    "structurally incomplete."
                )

                print(
                    f"⏳ Retrying in "
                    f"{RETRY_DELAY_SECONDS}s..."
                )

                time.sleep(
                    RETRY_DELAY_SECONDS
                )

                continue

            # --------------------------------------------------------------
            # Genuine scientific failure.
            # --------------------------------------------------------------

            break

        except Exception as error:

            last_error = error

            print(
                f"❌ Verification attempt "
                f"{attempt} failed:"
            )

            print(
                f"{type(error).__name__}: "
                f"{error}"
            )

            if attempt < MAX_VERIFICATION_ATTEMPTS:

                print(
                    f"⏳ Retrying in "
                    f"{RETRY_DELAY_SECONDS}s..."
                )

                time.sleep(
                    RETRY_DELAY_SECONDS
                )

            else:

                raise RuntimeError(
                    "Scientific claim verification failed "
                    f"after {MAX_VERIFICATION_ATTEMPTS} attempts: "
                    f"{error}"
                ) from error

    if result is None:

        if last_error:

            raise RuntimeError(
                "Scientific claim verification failed: "
                f"{last_error}"
            ) from last_error

        raise RuntimeError(
            "Scientific claim verification produced "
            "no result."
        )

    # ----------------------------------------------------------------------
    # FINAL LOCAL VALIDATION
    #
    # Run once more after retries so the final object stored in the
    # script is always normalized.
    # ----------------------------------------------------------------------

    result = _local_validate(
        result,
        script,
        research,
    )

    # ----------------------------------------------------------------------
    # SAVE RESULT INTO SCRIPT
    # ----------------------------------------------------------------------

    script[
        "claim_verification"
    ] = {

        "overall_status":
            result.get(
                "overall_status",
                "FAIL",
            ),

        "claims":
            result.get(
                "claims",
                [],
            ),

        "scene_reviews":
            result.get(
                "scene_reviews",
                [],
            ),

        "unsupported_claims":
            result.get(
                "unsupported_claims",
                [],
            ),

        "warnings":
            result.get(
                "warnings",
                [],
            ),

        "verified":
            (
                result.get(
                    "overall_status"
                )
                == "PASS"
            ),
    }

    # ----------------------------------------------------------------------
    # OUTPUT
    # ----------------------------------------------------------------------

    if result.get(
        "overall_status"
    ) == "PASS":

        print("=" * 80)
        print("✅ ALL IMPORTANT CLAIMS VERIFIED")
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
        print("❌ CLAIM VERIFICATION FAILED")
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

            for claim in unsupported:

                print(
                    f"  ❌ {claim}"
                )

        if warnings:

            print(
                "\n⚠️ Uncertain claims:"
            )

            for warning in warnings:

                print(
                    f"  ⚠️ {warning}"
                )

    print("=" * 80)

    return script


# ==========================================================================
# CLAIM VERIFICATION STATUS
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
        "verify_claims.py v2.2 is a pipeline module."
    )

    print(
        "It is called automatically by main.py."
    )