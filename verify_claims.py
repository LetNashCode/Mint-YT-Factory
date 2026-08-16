"""
verify_claims.py
Mint-YT-Factory

Version 1.2

Scientific claim verification layer.

FLOW:

Generated Script
      ↓
Extract IMPORTANT factual claims
      ↓
Compare against VERIFIED research
      ↓
Gemini evaluates support
      ↓
Local citation validation
      ↓
PASS / FAIL
      ↓
Only verified scripts continue

IMPORTANT:

- Gemini may ONLY use supplied research.
- Claims must use the source IDs cited by their scene.
- Claims cannot switch to an unrelated source during verification.
- Every important factual claim must have a valid citation.
- Purely stylistic/storytelling sentences do NOT require citations.
- Uncertain claims FAIL.
- Unsupported claims FAIL.
- Contradicted claims FAIL.
- Invalid source IDs FAIL.
- Claims with zero source IDs FAIL.
- A scene does NOT need to contain a factual claim.
"""

import json
import os
import re

from google import genai
from google.genai import types


# ==========================================================================
# CONFIG
# ==========================================================================

MODEL_NAME = "gemini-flash-lite-latest"

MAX_CLAIMS_PER_SCENE = 8


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


# ==========================================================================
# BUILD RESEARCH EVIDENCE
# ==========================================================================

def _build_research_evidence(
    research
):

    sources = research.get(
        "sources",
        [],
    )

    blocks = []

    for index, source in enumerate(
        sources,
        start=1,
    ):

        source_id = (
            f"source_{index}"
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

        abstract = _clean(
            source.get(
                "abstract",
                "",
            )
        )

        if not abstract:

            abstract = (
                "NO ABSTRACT AVAILABLE. "
                "Metadata alone is NOT evidence "
                "for detailed scientific claims."
            )

        blocks.append(
            f"""
SOURCE ID: {source_id}

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

Abstract / Evidence:
{abstract}
""".strip()
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
            "unsupported_claims",
            "warnings",
        ],
    }


# ==========================================================================
# SYSTEM PROMPT
# ==========================================================================

def _system_prompt():

    return """
You are a strict scientific fact checker.

Your job is NOT to rewrite the script.

Your job is to determine whether IMPORTANT FACTUAL CLAIMS in the
generated YouTube Short are actually supported by the supplied
verified research.

============================================================
ABSOLUTE RESEARCH RULE
============================================================

You may ONLY use the supplied research evidence.

Do NOT use:

- general knowledge
- memory
- internet knowledge
- outside scientific knowledge
- invented evidence
- invented studies
- invented statistics
- information not contained in the supplied evidence

============================================================
IMPORTANT CLAIM EXTRACTION RULE
============================================================

Extract EVERY IMPORTANT FACTUAL CLAIM from the narration.

A factual claim is a statement about:

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

Do NOT create artificial claims from stylistic sentences.

For example:

"Here's where it gets interesting."

This is NOT a factual claim.

"That changes how we see the ocean."

This is NOT necessarily a factual scientific claim.

But:

"Pressure increases by about one atmosphere every ten meters."

This IS a factual claim.

The purpose is to verify the claims actually present in the
narration, NOT to force every scene to contain a claim.

============================================================
SOURCE CITATION RULE
============================================================

Each scene contains its own CITED SOURCE IDS.

For every factual claim from a scene:

- You MUST use only source IDs cited by THAT scene.
- You MUST NOT substitute another source merely because it supports
  the claim better.
- You MUST NOT add a source ID that the scene did not cite.
- You MUST NOT use a source from another scene.
- The verifier's source_ids MUST be a SUBSET of the source IDs
  cited by that scene.

If a scene cites:

["source_1", "source_2"]

and only source_1 supports the claim:

Return:

["source_1"]

If neither cited source supports the claim:

Return:

"status": "unsupported"

If the cited evidence is related but insufficient:

Return:

"status": "uncertain"

============================================================
STATUS DEFINITIONS
============================================================

supported:
The supplied evidence directly supports the claim.

uncertain:
The supplied evidence is related but does not provide enough
evidence to confidently support the claim.

unsupported:
The supplied evidence does not support the claim.

contradicted:
The supplied evidence conflicts with the claim.

============================================================
EVIDENCE STANDARD
============================================================

A source title alone is NOT evidence.

Metadata alone is NOT evidence.

An abstract may support a claim when the abstract clearly contains
the relevant finding.

Do not assume information that is not explicitly supported.

Do not strengthen cautious scientific language.

Example:

Research:
"may contribute"

Claim:
"causes"

Result:
NOT SUPPORTED.

Research:
"associated with"

Claim:
"causes"

Result:
NOT SUPPORTED.

Research:
"hypothesis"

Claim:
"proven fact"

Result:
NOT SUPPORTED.

Research:
"was observed"

Claim:
"always occurs"

Result:
NOT SUPPORTED.

Research:
"could potentially explain"

Claim:
"explains"

Result:
NOT SUPPORTED unless the supplied evidence explicitly supports
the stronger statement.

============================================================
CLAIM CITATION REQUIREMENT
============================================================

Every IMPORTANT FACTUAL CLAIM MUST have at least one source ID.

If a factual claim has zero source IDs:

FAIL it.

If a claim uses an invalid source ID:

FAIL it.

If a claim uses a source ID that was not cited by its scene:

FAIL it.

============================================================
STYLISTIC STATEMENTS
============================================================

Minor non-factual statements such as:

"That changes how we see it."

"Here's where it gets interesting."

"Nature has another surprise."

"This is where the story gets strange."

do NOT require research evidence.

A scene may therefore contain ZERO factual claims.

A scene with zero factual claims is NOT automatically a failure.

============================================================
PASS CONDITION
============================================================

The overall result may be PASS only when:

1. Every important factual claim was extracted.
2. Every important factual claim is supported.
3. No important claim is contradicted.
4. No important claim is unsupported.
5. No important claim is uncertain.
6. Every factual claim has valid source IDs.
7. Every factual claim's source IDs belong to that scene's citations.
8. The narration does not exaggerate the research.

IMPORTANT:

Do NOT fail a scene merely because it contains no factual claim.

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
VERIFIED RESEARCH
============================================================

{research_evidence}

============================================================
SCRIPT
============================================================

{claim_context}

============================================================
TASK
============================================================

Extract EVERY IMPORTANT FACTUAL CLAIM from the narration.

Do NOT invent claims.

Do NOT turn stylistic sentences into factual claims.

For each important factual claim:

1. State the claim.
2. Identify the scene.
3. Look ONLY at the source IDs cited by THAT scene.
4. Return source_ids that are a subset of that scene's cited sources.
5. Decide whether the supplied evidence supports the claim.
6. Explain why.
7. Quote or summarize the relevant supplied evidence.

IMPORTANT:

Do NOT use a source from another scene.

Do NOT introduce outside information.

Do NOT invent evidence.

Do NOT upgrade uncertainty into certainty.

If a scene contains only stylistic narration and no factual claim,
do NOT create an artificial claim for that scene.

If the scene cites source_1 and source_2, but only source_1 supports
the claim, return:

"source_ids": ["source_1"]

If neither cited source supports the claim:

"status": "unsupported"

If the evidence is insufficient:

"status": "uncertain"

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

    if not response.text:

        raise RuntimeError(
            "Claim verifier returned an empty response."
        )

    try:

        return json.loads(
            response.text
        )

    except json.JSONDecodeError as error:

        raise RuntimeError(
            f"Claim verifier returned invalid JSON: "
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

    if not isinstance(
        result,
        dict,
    ):

        raise RuntimeError(
            "Claim verifier returned "
            "an invalid result."
        )

    # ----------------------------------------------------------------------
    # VALID RESEARCH SOURCE IDS
    # ----------------------------------------------------------------------

    valid_source_ids = {

        f"source_{index}"

        for index, source in enumerate(
            research.get(
                "sources",
                [],
            ),
            start=1,
        )
    }

    # ----------------------------------------------------------------------
    # BUILD SCENE → CITED SOURCES MAP
    # ----------------------------------------------------------------------

    scene_source_map = {}

    for scene in script.get(
        "scene_plan",
        [],
    ):

        if not isinstance(
            scene,
            dict,
        ):
            continue

        scene_number = scene.get(
            "scene"
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

        scene_source_map[
            scene_number
        ] = set(
            str(source_id).strip()
            for source_id in source_ids
            if str(source_id).strip()
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

        # --------------------------------------------------------------
        # CLAIM COUNT LIMIT
        # --------------------------------------------------------------

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
        # EVERY FACTUAL CLAIM NEEDS CITATION
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
        # SOURCE IDS MUST BELONG TO THAT SCENE
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
        # CLAIM STATUS
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
        # SUPPORTED CLAIM SAFETY
        # --------------------------------------------------------------

        if status == "supported":

            if not source_ids:

                unsupported.append(
                    (
                        f"Supported claim has no evidence source: "
                        f"{claim_text}"
                    )
                )

            elif invalid_ids:

                unsupported.append(
                    (
                        f"Supported claim uses invalid evidence "
                        f"source: {claim_text}"
                    )
                )

            elif wrong_scene_sources:

                unsupported.append(
                    (
                        f"Supported claim uses evidence from "
                        f"another scene: {claim_text}"
                    )
                )

    # ----------------------------------------------------------------------
    # IMPORTANT:
    #
    # DO NOT require every scene to have a claim.
    #
    # A scene can legitimately contain:
    #
    # "And that's where the mystery deepens."
    #
    # without containing a scientific claim.
    #
    # Gemini is responsible for extracting actual factual claims.
    # ----------------------------------------------------------------------

    # No per-scene claim requirement here.

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
    # ----------------------------------------------------------------------

    if unsupported:

        result[
            "overall_status"
        ] = "FAIL"

    elif warnings:

        # Uncertain claims are not publishable.
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

    return result


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

    if research.get(
        "verified"
    ) is not True:

        raise RuntimeError(
            "Claim verification requires "
            "verified research."
        )

    print("=" * 80)
    print("🧪 SCIENTIFIC CLAIM VERIFICATION")
    print("=" * 80)

    result = _verify_with_gemini(
        script,
        research,
    )

    result = _local_validate(
        result,
        script,
        research,
    )

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
            result.get(
                "overall_status"
            ) == "PASS",
    }

    if result.get(
        "overall_status"
    ) == "PASS":

        print(
            "✅ ALL IMPORTANT CLAIMS VERIFIED"
        )

    else:

        print(
            "❌ CLAIM VERIFICATION FAILED"
        )

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

    verification = script.get(
        "claim_verification",
        {},
    )

    return (
        verification.get(
            "verified"
        ) is True
        and
        verification.get(
            "overall_status"
        ) == "PASS"
    )


# ==========================================================================
# LOCAL TEST
# ==========================================================================

if __name__ == "__main__":

    print(
        "verify_claims.py is a pipeline module."
    )

    print(
        "It is called automatically by main.py."
    )