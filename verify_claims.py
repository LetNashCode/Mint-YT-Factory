"""
verify_claims.py
Mint-YT-Factory

Version 1.0

Post-generation scientific claim verification.

FLOW:

research.py
    ↓
verified research
    ↓
generate_script.py
    ↓
verify_claims.py
    ↓
PASS / FAIL
    ↓
YouTube pipeline

Purpose:
- Extract factual claims from the generated narration.
- Check each claim against the supplied verified research.
- Never use outside knowledge as evidence.
- Never invent citations.
- Reject unsupported claims.
- Return a structured verification report.

IMPORTANT:
This module does NOT decide whether a scientific statement is
"generally true" from Gemini's own knowledge.

It only asks:

"Is this claim supported by the supplied research?"
"""


import json
import os
import re


from google import genai
from google.genai import types


# ==========================================================================
# CONFIG
# ==========================================================================

MODEL_NAME = "gemini-3.1-flash-lite"

MAX_CLAIMS_PER_SCENE = 6


# ==========================================================================
# JSON PARSER
# ==========================================================================

def _parse_json(text):

    if not text:

        raise RuntimeError(
            "Claim verifier returned an empty response."
        )

    text = text.strip()

    # --------------------------------------------------------------
    # Direct JSON
    # --------------------------------------------------------------

    try:

        data = json.loads(text)

        if isinstance(data, dict):

            return data

    except json.JSONDecodeError:

        pass

    # --------------------------------------------------------------
    # Remove markdown fences
    # --------------------------------------------------------------

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

    # --------------------------------------------------------------
    # Extract JSON object
    # --------------------------------------------------------------

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
                "Could not parse claim verification JSON: "
                f"{error}"
            )

    raise RuntimeError(
        "Claim verifier did not return valid JSON."
    )


# ==========================================================================
# RESEARCH CONTEXT
# ==========================================================================

def build_research_context(
    research,
):

    sources = research.get(
        "sources",
        [],
    )

    if not isinstance(
        sources,
        list,
    ):

        raise RuntimeError(
            "Research sources must be a list."
        )

    blocks = []

    for index, source in enumerate(
        sources,
        start=1,
    ):

        source_id = (
            source.get(
                "source_id",
            )
            or
            f"source_{index}"
        )

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

        year = str(
            source.get(
                "year",
                "",
            )
        ).strip()

        doi = str(
            source.get(
                "doi",
                "",
            )
        ).strip()

        abstract = str(
            source.get(
                "abstract",
                "",
            )
        ).strip()

        verification = str(
            source.get(
                "verification",
                "",
            )
        ).strip()

        block = f"""
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

Verification:
{verification}
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

SYSTEM_PROMPT = """
You are a strict scientific claim verifier.

Your ONLY job is to determine whether factual claims in a generated
educational YouTube Short are supported by the supplied verified
research sources.

============================================================
ABSOLUTE RULE
============================================================

You may ONLY use the research supplied in the user prompt.

You MUST NOT use:

- your general knowledge
- information from memory
- outside websites
- outside studies
- invented evidence
- invented citations
- assumptions
- common knowledge as evidence

If the supplied research does not clearly support a claim:

mark it UNSUPPORTED.

Do NOT try to make the claim true.

============================================================
CLAIM TYPES
============================================================

Classify every extracted statement as one of:

FACT
EVIDENCE
HYPOTHESIS
OPINION
TRANSITION

Only FACT, EVIDENCE and HYPOTHESIS require research support.

OPINION and TRANSITION do not require scientific evidence.

============================================================
VERIFICATION
============================================================

A claim is:

SUPPORTED

only when the supplied research clearly supports it.

A claim is:

PARTIALLY_SUPPORTED

when the research supports the general idea but the narration
overstates, simplifies or extends the evidence.

A claim is:

UNSUPPORTED

when the supplied research does not establish the claim.

A claim is:

CONTRADICTED

when the supplied research indicates the claim is wrong.

============================================================
STRICTNESS
============================================================

Pay special attention to:

- numbers
- percentages
- dates
- measurements
- causal claims
- medical claims
- psychological claims
- statements using "causes"
- statements using "proves"
- statements using "always"
- statements using "never"
- statements using "the first"
- statements using "the only"
- statements using "scientists discovered"
- statements using "researchers found"

If the source says correlation but the narration says causation:

PARTIALLY_SUPPORTED or UNSUPPORTED.

If the source says "may", "could", "suggests" or "associated with"
but the narration presents certainty:

PARTIALLY_SUPPORTED or UNSUPPORTED.

============================================================
SOURCE IDs
============================================================

You may ONLY reference source IDs supplied in the research.

Never create a source ID.

============================================================
OUTPUT
============================================================

Return ONLY valid JSON.

The output must contain:

{
  "verified": true,
  "overall_status": "PASS",
  "claims": [
    {
      "scene": 1,
      "claim": "...",
      "claim_type": "FACT",
      "status": "SUPPORTED",
      "source_ids": ["source_1"],
      "reason": "..."
    }
  ],
  "unsupported_claims": [],
  "warnings": []
}

The overall result may be PASS only when there are no
UNSUPPORTED or CONTRADICTED factual claims.

PARTIALLY_SUPPORTED claims should produce a warning and
should normally be treated as requiring revision.
"""


# ==========================================================================
# RESPONSE SCHEMA
# ==========================================================================

def build_response_schema():

    claim = {

        "type": "object",

        "properties": {

            "scene": {
                "type": "integer",
            },

            "claim": {
                "type": "string",
            },

            "claim_type": {

                "type": "string",

                "enum": [
                    "FACT",
                    "EVIDENCE",
                    "HYPOTHESIS",
                    "OPINION",
                    "TRANSITION",
                ],
            },

            "status": {

                "type": "string",

                "enum": [
                    "SUPPORTED",
                    "PARTIALLY_SUPPORTED",
                    "UNSUPPORTED",
                    "CONTRADICTED",
                ],
            },

            "source_ids": {

                "type": "array",

                "items": {
                    "type": "string",
                },
            },

            "reason": {
                "type": "string",
            },
        },

        "required": [
            "scene",
            "claim",
            "claim_type",
            "status",
            "source_ids",
            "reason",
        ],
    }

    return {

        "type": "object",

        "properties": {

            "verified": {
                "type": "boolean",
            },

            "overall_status": {

                "type": "string",

                "enum": [
                    "PASS",
                    "FAIL",
                    "REVIEW",
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
            "verified",
            "overall_status",
            "claims",
            "unsupported_claims",
            "warnings",
        ],
    }


# ==========================================================================
# SOURCE ID VALIDATION
# ==========================================================================

def _validate_source_ids(
    report,
    research,
):

    valid_ids = set()

    for index, source in enumerate(
        research.get(
            "sources",
            [],
        ),
        start=1,
    ):

        source_id = (
            source.get(
                "source_id",
            )
            or
            f"source_{index}"
        )

        valid_ids.add(
            source_id
        )

    for claim in report.get(
        "claims",
        [],
    ):

        source_ids = claim.get(
            "source_ids",
            [],
        )

        if not isinstance(
            source_ids,
            list,
        ):

            raise RuntimeError(
                "Claim source_ids must be a list."
            )

        for source_id in source_ids:

            if source_id not in valid_ids:

                raise RuntimeError(
                    "Claim verifier referenced "
                    f"invalid source ID: {source_id}"
                )


# ==========================================================================
# HARD SAFETY CHECK
# ==========================================================================

def _apply_hard_gate(
    report,
):

    unsupported = []
    warnings = []

    for claim in report.get(
        "claims",
        [],
    ):

        status = str(
            claim.get(
                "status",
                "",
            )
        ).upper()

        claim_text = str(
            claim.get(
                "claim",
                "",
            )
        ).strip()

        claim_type = str(
            claim.get(
                "claim_type",
                "",
            )
        ).upper()

        # ----------------------------------------------------------
        # Factual claims must have sources.
        # ----------------------------------------------------------

        if claim_type in {
            "FACT",
            "EVIDENCE",
            "HYPOTHESIS",
        }:

            if not claim.get(
                "source_ids",
                [],
            ):

                unsupported.append(
                    claim_text
                )

        # ----------------------------------------------------------
        # Unsupported / contradicted claims.
        # ----------------------------------------------------------

        if status in {
            "UNSUPPORTED",
            "CONTRADICTED",
        }:

            unsupported.append(
                claim_text
            )

        # ----------------------------------------------------------
        # Partial support.
        # ----------------------------------------------------------

        if status == "PARTIALLY_SUPPORTED":

            warnings.append(
                claim_text
            )

    # Remove duplicates.

    unsupported = list(
        dict.fromkeys(
            x for x in unsupported
            if x
        )
    )

    warnings = list(
        dict.fromkeys(
            x for x in warnings
            if x
        )
    )

    report[
        "unsupported_claims"
    ] = unsupported

    report[
        "warnings"
    ] = warnings

    # --------------------------------------------------------------
    # HARD DECISION
    # --------------------------------------------------------------

    if unsupported:

        report[
            "verified"
        ] = False

        report[
            "overall_status"
        ] = "FAIL"

    elif warnings:

        report[
            "verified"
        ] = False

        report[
            "overall_status"
        ] = "REVIEW"

    else:

        report[
            "verified"
        ] = True

        report[
            "overall_status"
        ] = "PASS"

    return report


# ==========================================================================
# VERIFY SCRIPT CLAIMS
# ==========================================================================

def verify_script_claims(
    script,
    research,
):

    # ----------------------------------------------------------------------
    # Research gate
    # ----------------------------------------------------------------------

    if not isinstance(
        research,
        dict,
    ):

        raise RuntimeError(
            "Claim verification failed: "
            "research package is missing."
        )

    if research.get(
        "verified"
    ) is not True:

        raise RuntimeError(
            "Claim verification failed: "
            "research is not verified."
        )

    sources = research.get(
        "sources",
        [],
    )

    if not isinstance(
        sources,
        list,
    ) or not sources:

        raise RuntimeError(
            "Claim verification failed: "
            "no research sources available."
        )

    # ----------------------------------------------------------------------
    # Script gate
    # ----------------------------------------------------------------------

    if not isinstance(
        script,
        dict,
    ):

        raise RuntimeError(
            "Claim verification failed: "
            "script is invalid."
        )

    scenes = script.get(
        "scene_plan",
        [],
    )

    if not isinstance(
        scenes,
        list,
    ) or not scenes:

        raise RuntimeError(
            "Claim verification failed: "
            "script contains no scenes."
        )

    # ----------------------------------------------------------------------
    # API
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # Research context
    # ----------------------------------------------------------------------

    research_context = (
        build_research_context(
            research
        )
    )

    # ----------------------------------------------------------------------
    # Build narration
    # ----------------------------------------------------------------------

    scene_blocks = []

    for scene in scenes:

        scene_number = scene.get(
            "scene",
        )

        narration = str(
            scene.get(
                "narration",
                "",
            )
        ).strip()

        source_ids = scene.get(
            "source_ids",
            [],
        )

        scene_blocks.append(
            f"""
SCENE {scene_number}

Narration:
{narration}

Existing source IDs:
{json.dumps(source_ids)}
""".strip()
        )

    narration_context = "\n\n".join(
        scene_blocks
    )

    # ----------------------------------------------------------------------
    # Prompt
    # ----------------------------------------------------------------------

    prompt = f"""
VERIFY THIS EDUCATIONAL SHORT.

TOPIC:
{script.get("topic", "")}

============================================================
VERIFIED RESEARCH
============================================================

{research_context}

============================================================
GENERATED NARRATION
============================================================

{narration_context}

============================================================
TASK
============================================================

Extract the factual/scientific claims from every scene.

Check each claim ONLY against the supplied research.

Do not use external knowledge.

Do not assume something is true merely because it sounds plausible.

Check source_ids carefully.

A factual claim without adequate research support must fail.

Return ONLY JSON.
"""

    # ----------------------------------------------------------------------
    # Gemini
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🔬 VERIFYING GENERATED CLAIMS")
    print("=" * 80)

    response = client.models.generate_content(

        model=MODEL_NAME,

        contents=prompt,

        config=types.GenerateContentConfig(

            system_instruction=
                SYSTEM_PROMPT,

            response_mime_type=
                "application/json",

            response_json_schema=
                build_response_schema(),
        ),
    )

    if not response.text:

        raise RuntimeError(
            "Claim verifier returned no response."
        )

    report = _parse_json(
        response.text
    )

    # ----------------------------------------------------------------------
    # Validate source references
    # ----------------------------------------------------------------------

    _validate_source_ids(
        report,
        research,
    )

    # ----------------------------------------------------------------------
    # Apply deterministic hard gate
    # ----------------------------------------------------------------------

    report = _apply_hard_gate(
        report
    )

    # ----------------------------------------------------------------------
    # Attach report
    # ----------------------------------------------------------------------

    script[
        "claim_verification"
    ] = report

    # ----------------------------------------------------------------------
    # Output
    # ----------------------------------------------------------------------

    print("=" * 80)

    if report[
        "overall_status"
    ] == "PASS":

        print(
            "✅ CLAIM VERIFICATION PASSED"
        )

    elif report[
        "overall_status"
    ] == "REVIEW":

        print(
            "⚠️ CLAIM VERIFICATION NEEDS REVIEW"
        )

    else:

        print(
            "❌ CLAIM VERIFICATION FAILED"
        )

    print(
        f"Claims checked: "
        f"{len(report.get('claims', []))}"
    )

    print(
        f"Unsupported claims: "
        f"{len(report.get('unsupported_claims', []))}"
    )

    print(
        f"Warnings: "
        f"{len(report.get('warnings', []))}"
    )

    print("=" * 80)

    return script


# ==========================================================================
# CONVENIENCE FUNCTION
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
        )
        is True
        and
        verification.get(
            "overall_status"
        )
        == "PASS"
    )


# ==========================================================================
# LOCAL TEST
# ==========================================================================

if __name__ == "__main__":

    print(
        "verify_claims.py is a pipeline module."
    )

    print(
        "It verifies generated narration against "
        "the research package supplied by research.py."
    )