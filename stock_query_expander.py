"""Semantic stock-search expansion for Mint-YT-Factory.

This module expands a failed stock-search vocabulary without changing the
media contract: Pexels and Pixabay remain the only media providers.
Gemini is used only to suggest equivalent stock-search wording; it never
creates, supplies, or selects media here.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any


MAX_EXPANDED_QUERIES = 10


def _clean(value: Any, limit: int = 100) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()[:limit]


def _json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?", "", str(text or "").strip(), flags=re.I).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise RuntimeError("Gemini returned invalid semantic stock-search JSON.")
        return json.loads(match.group(0))


def _key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required for semantic stock-search expansion.")
    return key


def _dedupe(values: list[str], existing: list[str]) -> list[str]:
    seen = {x.lower() for x in existing}
    output: list[str] = []
    for value in values:
        value = _clean(value)
        if not value or value.lower() in seen:
            continue
        if not 2 <= len(value.split()) <= 7:
            continue
        seen.add(value.lower())
        output.append(value)
    return output


def expand(directed: dict) -> dict:
    """Return the same search plan with a semantic fallback vocabulary.

    The expansion is deliberately generated only after the normal stock search
    fails. It asks Gemini for words stock libraries commonly use for the same
    visible subject/action, rather than asking for a new visual or image.
    """
    primary = [_clean(q) for q in directed.get("queries", []) if _clean(q)]
    spoken = _clean(directed.get("spoken_beat"), 700)
    brief = _clean(directed.get("casting_brief"), 500)
    must = [_clean(x, 180) for x in directed.get("must_match", []) if _clean(x)]

    from google import genai
    from google.genai import types

    prompt = f"""You are a STOCK SEARCH VOCABULARY EXPANDER.
The only allowed media providers are Pexels and Pixabay.
You must NOT generate an image, describe an AI image, or provide a media URL.

The normal stock-search vocabulary has already failed to produce an acceptable
visual. Create alternative search phrases that mean the SAME visible thing,
but use different words commonly found in stock-library titles/tags.

SPOKEN BEAT:
{spoken}
IDEAL VISIBLE SHOT:
{brief}
MUST MATCH:
{json.dumps(must, ensure_ascii=False)}
CURRENT SEARCHES:
{json.dumps(primary, ensure_ascii=False)}

RULES:
1. Preserve the actual physical subject. Do not replace it with a merely related object.
2. Preserve the action/state when one is required.
3. Use synonyms, alternate common names, singular/plural forms, stock-library terminology,
   and broader-but-still-equivalent wording.
4. Example: "single raw corn kernel" can become "raw corn grain", "corn seed close up",
   "uncooked corn kernel", "corn grain macro", "yellow corn grain".
5. Do NOT turn popcorn kernel into corn on the cob, maize field, canned corn, or generic food.
6. For invisible/internal mechanisms, search for a truthful visible proxy such as a cut-open
   object, visible steam, boiling, swelling, cracking, bursting, or the resulting object.
7. Avoid abstract terms: science, mechanism, concept, mystery, experiment, educational,
   microscopic, CGI, animation, AI, generated.
8. Keep every query 2-7 words and easy to paste into a stock search box.
9. Make every query materially different from the current searches.
10. Return only alternatives that could realistically retrieve the same visual subject.

Return ONLY JSON:
{{"alternatives":["...","..."]}}"""

    client = genai.Client(api_key=_key())
    response = client.models.generate_content(
        model="gemini-flash-lite-latest",
        contents=[prompt],
        config=types.GenerateContentConfig(temperature=0.15),
    )
    data = _json(getattr(response, "text", "") or "")
    alternatives = _dedupe(data.get("alternatives", []), primary)
    return {
        **directed,
        "queries": (primary + alternatives)[:MAX_EXPANDED_QUERIES],
        "primary_queries": primary,
        "semantic_fallback_queries": alternatives,
        "search_mode": "semantic-expanded",
    }
