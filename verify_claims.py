"""
verify_claims.py
Mint-YT-Factory
Version 3.0

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
"""

import json
import os
import re
import time

from google import genai
from google.genai import types

MODEL_NAME = "gemini-flash-lite-latest"
MAX_CLAIMS_PER_SCENE = 8
MIN_EVIDENCE_CHARACTERS = 120
MAX_VERIFICATION_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 3


def _clean(text):
    return re.sub(r"\s+", " ", str(text)).strip() if text is not None else ""


def _get_api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY environment variable is missing.")
    return key


def _contains_numeric_claim_signal(text):
    text = _clean(text)
    if not text:
        return False
    patterns = (
        r"\b\d+(?:\.\d+)?\s*%",
        r"\b\d+(?:\.\d+)?\s*(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?|meters?|metres?|kilometers?|kilometres?|centimeters?|centimetres?|millimeters?|millimetres?|grams?|kilograms?|milligrams?|degrees?|Â°|celsius|fahrenheit|kelvin|hz|khz|mhz|ghz|watts?|kw|mw|volts?|amps?|times?)\b",
        r"\b\d+(?:\.\d+)?\s*x\b",
        r"\b\d+(?:\.\d+)?\s*(?:thousand|million|billion|trillion)\b",
        r"\b\d+\.\d+\b",
        r"\b(?:1[5-9]\d{2}|20\d{2}|21\d{2})\b",
    )
    return any(re.search(p, text, re.I) for p in patterns)


def _contains_factual_language_signal(text):
    text = _clean(text).lower()
    if not text:
        return False
    patterns = (
        r"\bresearchers?\b", r"\bscientists?\b", r"\bstudy\b", r"\bstudies\b",
        r"\bexperiment(?:s)?\b", r"\bobserved\b", r"\bfound\b", r"\bfindings?\b",
        r"\bdata\b", r"\bevidence\b", r"\bcauses?\b", r"\bcaused\b", r"\bcausing\b",
        r"\bleads? to\b", r"\bresults? in\b", r"\bproduces?\b", r"\bcreates?\b",
        r"\bprevents?\b", r"\bcontrols?\b", r"\btriggers?\b", r"\bdrives?\b",
        r"\baffects?\b", r"\bincreases?\b", r"\bdecreases?\b", r"\breduces?\b",
        r"\bimproves?\b", r"\bchanges?\b", r"\bcontains?\b", r"\bconsists? of\b",
        r"\bhas\b", r"\bhave\b", r"\buses?\b", r"\babsorbs?\b", r"\breflects?\b",
        r"\bemits?\b", r"\bdetects?\b", r"\bmeasures?\b",
        r"\bcell(?:s)?\b", r"\bbrain\b", r"\bneurons?\b", r"\bhormones?\b",
        r"\bdna\b", r"\bproteins?\b", r"\batoms?\b", r"\bmolecules?\b",
        r"\benergy\b", r"\bpressure\b", r"\btemperature\b", r"\bgravity\b",
        r"\bvelocity\b", r"\bfrequency\b", r"\bradiation\b", r"\bmagnetic\b",
        r"\belectric\b", r"\bis known to\b", r"\bare known to\b",
        r"\bis caused by\b", r"\bare caused by\b", r"\bis associated with\b",
        r"\bare associated with\b", r"\bhas been shown\b", r"\bhave been shown\b",
        r"\bwas discovered\b", r"\bwere discovered\b",
    )
    return any(re.search(p, text, re.I) for p in patterns)


def _build_source_map(research):
    result = {}
    for source in research.get("sources", []) or []:
        if not isinstance(source, dict):
            continue
        sid = _clean(source.get("source_id", ""))
        if sid:
            result[sid] = source
    return result


def _build_research_evidence(research):
    blocks = []
    for sid, source in _build_source_map(research).items():
        evidence = _clean(source.get("evidence_text", ""))
        if (
            source.get("verified") is not True
            or source.get("evidence_verified") is not True
            or source.get("evidence_available") is not True
            or len(evidence) < MIN_EVIDENCE_CHARACTERS
        ):
            continue
        blocks.append(
            f"""SOURCE ID: {sid}

TITLE:
{_clean(source.get("title",""))}

SCIENTIFIC EVIDENCE ONLY:
{evidence}

IMPORTANT: Metadata identifies the source but is NOT evidence."""
        )
    return "\n\n".join(blocks) if blocks else "NO VERIFIED SCIENTIFIC EVIDENCE AVAILABLE."


def _build_claim_context(script):
    blocks = []
    for scene in script.get("scene_plan", []) or []:
        if not isinstance(scene, dict):
            continue
        sid = scene.get("source_ids", []) or []
        if not isinstance(sid, list):
            sid = []
        sid = [str(x).strip() for x in sid if str(x).strip()]
        blocks.append(
            f"""SCENE {scene.get("scene")}

NARRATION:
{_clean(scene.get("narration",""))}

CITED SOURCE IDS:
{json.dumps(sid)}"""
        )
    return "\n\n".join(blocks)


def build_response_schema():
    claim = {
        "type": "object",
        "properties": {
            "claim": {"type": "string"},
            "scene": {"type": "integer"},
            "source_ids": {"type": "array", "items": {"type": "string"}},
            "status": {"type": "string", "enum": ["supported","unsupported","uncertain","contradicted"]},
            "reason": {"type": "string"},
            "evidence": {"type": "string"},
        },
        "required": ["claim","scene","source_ids","status","reason","evidence"],
    }
    scene_review = {
        "type": "object",
        "properties": {
            "scene": {"type": "integer"},
            "factual_claims_found": {"type": "boolean"},
            "claim_count": {"type": "integer"},
            "review_note": {"type": "string"},
        },
        "required": ["scene","factual_claims_found","claim_count","review_note"],
    }
    return {
        "type": "object",
        "properties": {
            "overall_status": {"type": "string", "enum": ["PASS","FAIL"]},
            "claims": {"type": "array", "items": claim},
            "scene_reviews": {"type": "array", "items": scene_review},
            "unsupported_claims": {"type": "array", "items": {"type": "string"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["overall_status","claims","scene_reviews","unsupported_claims","warnings"],
    }


def _system_prompt():
    return """
You are a STRICT scientific fact checker.

Your ONLY job is to determine whether every important factual claim in
the supplied YouTube Short is supported by the supplied verified
scientific Evidence Text.

ABSOLUTE RULES:
- Use ONLY Evidence Text.
- Never use model memory, general knowledge, internet knowledge, or metadata.
- Metadata includes title, authors, journal, year, DOI, URL, verification level,
  evidence type, evidence quality, and source identity.
- Review the COMPLETE narration of EVERY scene.
- Extract every important factual, quantitative, causal, mechanistic,
  historical, observational, or research claim.
- Do not invent claims from purely stylistic sentences.
- Every factual claim must have at least one source ID.
- Claim source_ids MUST be a subset of the source IDs cited by that scene.
- Never borrow a source from another scene.
- Never invent or modify source IDs.
- Numbers, dates, percentages, measurements and statistics must be explicitly
  supported by the supplied Evidence Text.
- Do not convert association/correlation into causation.
- Do not convert possibility into certainty.
- Do not convert "may" into "does".
- Do not convert hypothesis into established fact.
- If evidence is related but insufficient, use uncertain.
- If evidence does not support the claim, use unsupported.
- If evidence conflicts with the claim, use contradicted.
- A PASS is allowed only if every important factual claim is supported and
  every scene has been explicitly reviewed.
- Return exactly one scene_reviews entry per script scene.
- Return ONLY valid JSON.
"""


def _verify_with_gemini(script, research, retry_feedback=""):
    client = genai.Client(api_key=_get_api_key())
    prompt = f"""
VERIFY THIS SCRIPT.

================ VERIFIED EVIDENCE ================
{_build_research_evidence(research)}

================ SCRIPT ================
{_build_claim_context(script)}

================ INSTRUCTIONS ================
For EVERY scene:
1. Read the entire narration.
2. Extract every important factual claim.
3. Check every number and causal/mechanistic statement.
4. Use ONLY Evidence Text from sources cited by that scene.
5. Return exact source IDs from that scene.
6. Create exactly one scene_reviews object.
7. If a scene is purely stylistic, return factual_claims_found=false and claim_count=0.

{retry_feedback}

Return the complete JSON result.
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
    text = getattr(response, "text", None)
    if not text:
        raise RuntimeError("Claim verifier returned an empty response.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Claim verifier returned invalid JSON: {error}") from error


def _scene_maps(script):
    scene_sources, scene_narration = {}, {}
    for scene in script.get("scene_plan", []) or []:
        if not isinstance(scene, dict):
            continue
        try:
            number = int(scene.get("scene", 0))
        except (TypeError, ValueError):
            number = 0
        ids = scene.get("source_ids", []) or []
        if not isinstance(ids, list):
            ids = []
        scene_sources[number] = {str(x).strip() for x in ids if str(x).strip()}
        scene_narration[number] = _clean(scene.get("narration", ""))
    return scene_sources, scene_narration


def _local_validate(result, script, research):
    if not isinstance(result, dict):
        raise RuntimeError("Claim verifier returned an invalid result.")

    source_map = _build_source_map(research)
    valid_ids = set(source_map)

    usable_ids = {
        sid for sid, source in source_map.items()
        if source.get("verified") is True
        and source.get("evidence_verified") is True
        and source.get("evidence_available") is True
        and len(_clean(source.get("evidence_text", ""))) >= MIN_EVIDENCE_CHARACTERS
    }

    scene_sources, scene_narration = _scene_maps(script)
    expected_scenes = set(scene_sources)

    claims = result.get("claims", [])
    reviews = result.get("scene_reviews", [])
    unsupported = [_clean(x) for x in result.get("unsupported_claims", []) or [] if _clean(x)]
    warnings = [_clean(x) for x in result.get("warnings", []) or [] if _clean(x)]

    if not isinstance(claims, list):
        unsupported.append("Verifier claims field is not an array.")
        claims = []
    if not isinstance(reviews, list):
        unsupported.append("Verifier scene_reviews field is not an array.")
        reviews = []

    claims_per_scene = {}
    normalized_claims = []

    for claim in claims:
        if not isinstance(claim, dict):
            unsupported.append("Verifier returned an invalid claim object.")
            continue

        text = _clean(claim.get("claim", ""))
        try:
            scene = int(claim.get("scene", 0))
        except (TypeError, ValueError):
            scene = 0
        status = _clean(claim.get("status", "")).lower()
        reason = _clean(claim.get("reason", ""))
        evidence = _clean(claim.get("evidence", ""))
        ids = claim.get("source_ids", []) or []
        if not isinstance(ids, list):
            ids = []
        ids = list(dict.fromkeys(str(x).strip() for x in ids if str(x).strip()))

        if not text:
            unsupported.append("Verifier returned an empty claim.")
            continue

        claims_per_scene[scene] = claims_per_scene.get(scene, 0) + 1
        if claims_per_scene[scene] > MAX_CLAIMS_PER_SCENE:
            unsupported.append(f"Scene {scene} has more than {MAX_CLAIMS_PER_SCENE} claims.")

        if scene not in scene_sources:
            unsupported.append(f"Claim references invalid scene {scene}: {text}")
            continue

        scene_ids = scene_sources[scene]
        invalid = [x for x in ids if x not in valid_ids]
        unusable = [x for x in ids if x not in usable_ids]
        wrong_scene = [x for x in ids if x not in scene_ids]

        if not ids:
            unsupported.append(f"Claim has no source citation: {text}")
        if invalid:
            unsupported.append(f"Invalid source citation {', '.join(invalid)}: {text}")
        if unusable:
            unsupported.append(f"Claim uses source(s) without verified evidence: {', '.join(unusable)}. Claim: {text}")
        if wrong_scene:
            unsupported.append(f"Claim uses source(s) not cited by scene {scene}: {', '.join(wrong_scene)}. Claim: {text}")

        if status in {"unsupported", "contradicted"}:
            unsupported.append(text)
        elif status == "uncertain":
            warnings.append(text)
        elif status != "supported":
            unsupported.append(f"Claim has invalid verification status '{status}': {text}")

        if status == "supported":
            if not reason:
                unsupported.append(f"Supported claim has no reason: {text}")
            if not evidence:
                unsupported.append(f"Supported claim has no evidence explanation: {text}")
            if not ids or invalid or unusable or wrong_scene or not reason or not evidence:
                unsupported.append(f"Supported claim failed citation/evidence requirements: {text}")
            else:
                normalized_claims.append(claim)

    reviewed = set()
    for review in reviews:
        if not isinstance(review, dict):
            unsupported.append("Verifier returned an invalid scene review.")
            continue
        try:
            scene = int(review.get("scene", 0))
        except (TypeError, ValueError):
            scene = 0
        if scene not in expected_scenes:
            unsupported.append(f"Scene review references invalid scene {scene}.")
            continue
        if scene in reviewed:
            unsupported.append(f"Scene {scene} was reviewed more than once.")
            continue
        reviewed.add(scene)

        try:
            reported = int(review.get("claim_count", 0))
        except (TypeError, ValueError):
            reported = -1
        actual = claims_per_scene.get(scene, 0)
        if reported != actual:
            unsupported.append(f"Scene {scene} review reports {reported} claims but verifier returned {actual}.")
        factual = review.get("factual_claims_found") is True
        if factual and actual == 0:
            unsupported.append(f"Scene {scene} marked factual but returned zero claims.")
        if not factual and actual > 0:
            unsupported.append(f"Scene {scene} returned claims but factual_claims_found is false.")

    missing = expected_scenes - reviewed
    if missing:
        unsupported.append("Missing scene reviews for scene(s): " + ", ".join(map(str, sorted(missing))))

    # Conservative completeness guard.
    for scene, narration in scene_narration.items():
        count = claims_per_scene.get(scene, 0)
        if _contains_numeric_claim_signal(narration) and count == 0:
            unsupported.append(f"Scene {scene} contains quantitative language but Gemini returned zero factual claims.")
        elif _contains_factual_language_signal(narration) and count == 0:
            review = next((r for r in reviews if isinstance(r, dict) and int(r.get("scene", 0) or 0) == scene), None)
            if review and review.get("factual_claims_found") is False:
                unsupported.append(f"Scene {scene} contains language that appears factual but was explicitly reviewed as zero claims.")

    if len(usable_ids) < 2:
        unsupported.append("Research package contains fewer than 2 usable evidence-verified sources.")

    # Final status is derived locally. Gemini cannot force PASS.
    unsupported = list(dict.fromkeys(x for x in unsupported if x))
    warnings = list(dict.fromkeys(x for x in warnings if x))

    result["overall_status"] = "PASS" if not unsupported and not warnings else "FAIL"
    result["claims"] = claims
    result["scene_reviews"] = reviews
    result["unsupported_claims"] = unsupported
    result["warnings"] = warnings
    return result


def _is_structural_failure(result):
    if not isinstance(result, dict):
        return True
    text = "\n".join(result.get("unsupported_claims", []) or []).lower()
    structural_markers = (
        "scene review",
        "scene reviews",
        "claim count",
        "quantitative language but gemini returned zero",
        "factual claims but no claims",
        "returned claims but factual_claims_found",
        "verifier returned an invalid",
        "missing scene reviews",
    )
    return any(marker in text for marker in structural_markers)


def _retry_feedback(result, attempt):
    problems = []
    if isinstance(result, dict):
        problems.extend(result.get("unsupported_claims", []) or [])
        problems.extend(result.get("warnings", []) or [])
    problems = [_clean(x) for x in problems if _clean(x)]
    return f"""
RETRY ATTEMPT {attempt}

The previous result failed structural completeness checks.
Correct the structural problems below while re-reading the COMPLETE script.
Do NOT change a scientifically unsupported claim to supported merely to pass.
Do NOT use outside knowledge.

PREVIOUS STRUCTURAL PROBLEMS:
{json.dumps(problems[:40], ensure_ascii=False, indent=2)}
"""


def verify_script_claims(script, research):
    if not isinstance(script, dict):
        raise RuntimeError("Claim verification received an invalid script.")
    if not isinstance(research, dict):
        raise RuntimeError("Claim verification received invalid research.")
    if research.get("verified") is not True or research.get("status") != "VERIFIED":
        raise RuntimeError("Claim verification requires verified research.")

    sources = research.get("sources", [])
    if not isinstance(sources, list) or len(sources) < 2:
        raise RuntimeError("Claim verification requires at least 2 research sources.")

    print("=" * 80)
    print("ð§ª SCIENTIFIC CLAIM VERIFICATION v3.0")
    print("=" * 80)

    last_result = None
    retry_feedback = ""

    for attempt in range(1, MAX_VERIFICATION_ATTEMPTS + 1):
        print(f"ð§  CLAIM VERIFICATION ATTEMPT {attempt}/{MAX_VERIFICATION_ATTEMPTS}")
        try:
            raw = _verify_with_gemini(script, research, retry_feedback)
            result = _local_validate(raw, script, research)
            last_result = result

            if result.get("overall_status") == "PASS":
                break

            if _is_structural_failure(result) and attempt < MAX_VERIFICATION_ATTEMPTS:
                print(f"â ï¸ Structural completeness issue. Retrying in {RETRY_DELAY_SECONDS}s...")
                retry_feedback = _retry_feedback(result, attempt + 1)
                time.sleep(RETRY_DELAY_SECONDS)
                continue

            break
        except Exception as error:
            if attempt >= MAX_VERIFICATION_ATTEMPTS:
                raise RuntimeError(
                    f"Scientific claim verification failed after {MAX_VERIFICATION_ATTEMPTS} attempts: {error}"
                ) from error
            print(f"â ï¸ Verification error: {error}")
            time.sleep(RETRY_DELAY_SECONDS)

    if last_result is None:
        raise RuntimeError("Scientific claim verification produced no result.")

    # Normalize one final time; PASS can only be produced by the local gate.
    result = _local_validate(last_result, script, research)

    script["claim_verification"] = {
        "overall_status": result.get("overall_status", "FAIL"),
        "claims": result.get("claims", []),
        "scene_reviews": result.get("scene_reviews", []),
        "unsupported_claims": result.get("unsupported_claims", []),
        "warnings": result.get("warnings", []),
        "verified": result.get("overall_status") == "PASS",
    }

    if result.get("overall_status") == "PASS":
        print("â ALL IMPORTANT CLAIMS VERIFIED")
    else:
        print("â CLAIM VERIFICATION FAILED")
        for item in result.get("unsupported_claims", []):
            print(f"  â {item}")
        for item in result.get("warnings", []):
            print(f"  â ï¸ {item}")

    print("=" * 80)
    return script


def claims_are_verified(script):
    if not isinstance(script, dict):
        return False
    verification = script.get("claim_verification", {})
    if not isinstance(verification, dict):
        return False
    return (
        verification.get("verified") is True
        and verification.get("overall_status") == "PASS"
        and isinstance(verification.get("claims"), list)
        and isinstance(verification.get("scene_reviews"), list)
        and not verification.get("unsupported_claims")
        and not verification.get("warnings")
    )


if __name__ == "__main__":
    print("verify_claims.py v3.0 is a pipeline module.")