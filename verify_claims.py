"""
verify_claims.py
Mint-YT-Factory

Version 1.0

Scientific claim verification layer.

FLOW:

Generated Script
      ↓
Extract scene claims
      ↓
Compare against verified research
      ↓
Gemini evaluates support
      ↓
PASS / FAIL
      ↓
Only verified scripts continue
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
                "Do not treat metadata alone as "
                "evidence for detailed scientific claims."
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
# BUILD SCRIPT CLAIMS
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

        blocks.append(
            f"""
SCENE {scene_number}

Narration:
{narration}

Cited source IDs:
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

Your job is to determine whether the factual claims made in the
generated YouTube Short are actually supported by the supplied
verified research.

============================================================
ABSOLUTE RULE
============================================================

You may ONLY use the supplied research evidence.

Do NOT use:

- general knowledge
- memory
- internet knowledge
- invented evidence
- invented studies
- invented statistics

A claim is SUPPORTED only when the supplied research provides reasonable
evidence for that specific claim.

============================================================
STATUS DEFINITIONS
============================================================

supported:
The supplied research directly supports the claim.

uncertain:
The research is related but does not provide enough evidence to make
the claim confidently.

unsupported:
The supplied research does not support the claim.

contradicted:
The supplied research conflicts with the claim.

============================================================
IMPORTANT
============================================================

A source title alone is NOT enough evidence for a detailed claim.

An abstract may support a claim when the abstract clearly contains
the relevant finding.

Do not assume information that is not present.

Do not strengthen cautious research language.

For example:

Research:
"may contribute"

Claim:
"causes"

This should NOT be considered supported.

Research:
"associated with"

Claim:
"causes"

This should NOT be considered supported.

Research:
"hypothesis"

Claim:
"proven fact"

This should NOT be considered supported.

============================================================
PASS CONDITION
============================================================

The overall result is PASS only when:

1. Every important factual claim is supported.
2. No important claim is contradicted.
3. No important claim is unsupported.
4. Every claim uses only its cited source IDs.
5. The narration does not exaggerate the research.

Minor stylistic statements such as:

"That changes how we see it."

do not need research evidence.

============================================================

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

Extract the important factual claims from the narration.

For each important factual claim:

1. State the claim.
2. Identify the scene.
3. Identify the source IDs cited by that scene.
4. Decide whether the supplied evidence supports it.
5. Explain why.
6. Quote or summarize the relevant evidence.

Do NOT introduce outside information.

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

    return json.loads(
        response.text
    )


# ==========================================================================
# LOCAL SAFETY VALIDATION
# ==========================================================================

def _local_validate(
    result,
    script,
    research,
):

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

    claims = result.get(
        "claims",
        [],
    )

    unsupported = list(
        result.get(
            "unsupported_claims",
            [],
        )
    )

    warnings = list(
        result.get(
            "warnings",
            [],
        )
    )

    for claim in claims:

        if not isinstance(
            claim,
            dict,
        ):
            continue

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

            unsupported.append(
                claim.get(
                    "claim",
                    "Unknown claim",
                )
            )

            continue

        for source_id in source_ids:

            if source_id not in valid_source_ids:

                unsupported.append(
                    (
                        f"Invalid source citation "
                        f"{source_id}: "
                        f"{claim.get('claim', '')}"
                    )
                )

        if status in {
            "unsupported",
            "contradicted",
        }:

            unsupported.append(
                claim.get(
                    "claim",
                    "Unknown claim",
                )
            )

        elif status == "uncertain":

            warnings.append(
                claim.get(
                    "claim",
                    "Uncertain claim",
                )
            )

    # Deduplicate while preserving order.

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

    if unsupported:

        result[
            "overall_status"
        ] = "FAIL"

    elif warnings:

        # We treat uncertain scientific claims as a failure.
        # This prevents exaggerated research from being published.

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

        for claim in unsupported:

            print(
                f"❌ {claim}"
            )

        for warning in warnings:

            print(
                f"⚠️ {warning}"
            )

    print("=" * 80)

    return script


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