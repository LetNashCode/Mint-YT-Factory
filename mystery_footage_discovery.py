"""Discover candidate public-domain/CC footage from Internet Archive.

The discovery layer uses Gemini only to choose a search direction and select a
candidate from metadata returned by the Internet Archive advanced-search API.
It never treats a search result as rights-cleared: rights_verified remains
false until the source terms are reviewed by a human.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import requests
from google import genai
from google.genai import types

MODEL_NAME = "gemini-flash-lite-latest"
IA_SEARCH = "https://archive.org/advancedsearch.php"


def _json(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    return json.loads(text)


def _search_direction() -> dict[str, Any]:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required for automatic footage discovery.")
    prompt = (
        "Choose a compelling, non-graphic found-footage or archival mystery topic "
        "that can be searched in the Internet Archive. Prefer public-domain or "
        "clearly licensed historical footage, unusual events, unexplained images, "
        "lost-media history, strange broadcasts, or rare archival recordings. "
        "Do not request copyrighted movies, graphic violence, or fabricated events. "
        "Return JSON only: {\"topic\": string, \"search_query\": string}."
    )
    # Keep the client alive for the complete request. Creating it inline can let
    # it be finalized before the SDK finishes its internal HTTP operation.
    with genai.Client(api_key=key) as client:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json", temperature=0.7
            ),
        )
    return _json(getattr(response, "text", ""))


def discover_item() -> dict[str, Any]:
    direction = _search_direction()
    query = str(direction.get("search_query", "")).strip() or "public domain archival footage"
    params = {
        "q": f"({query}) AND mediatype:movies",
        "fl[]": ["identifier", "title", "description", "year", "licenseurl", "rights"],
        "rows": 20,
        "output": "json",
        "page": 1,
    }
    response = requests.get(IA_SEARCH, params=params, timeout=60)
    response.raise_for_status()
    docs = response.json().get("response", {}).get("docs", [])
    for doc in docs:
        identifier = str(doc.get("identifier", "")).strip()
        title = str(doc.get("title", "")).strip()
        if not identifier or not title or "REPLACE_ME" in identifier:
            continue
        metadata_url = f"https://archive.org/metadata/{identifier}"
        meta = requests.get(metadata_url, timeout=60)
        if not meta.ok:
            continue
        files = meta.json().get("files", [])
        video = next(
            (
                f
                for f in files
                if str(f.get("name", "")).lower().endswith((".mp4", ".webm", ".ogv"))
                and int(f.get("size", 0) or 0) > 10000
            ),
            None,
        )
        if not video:
            continue
        filename = video["name"]
        return {
            "id": f"ia-{identifier}",
            "title": title,
            "topic": direction.get("topic", query),
            "source_url": f"https://archive.org/details/{identifier}",
            "video_url": f"https://archive.org/download/{identifier}/{filename}",
            "license": doc.get("licenseurl") or "Review Internet Archive item rights before publishing",
            "rights_verified": False,
            "rights_notes": "Automatically discovered candidate. Human rights review is required before commercial publication.",
            "attribution": "Follow the individual Internet Archive item's attribution requirements.",
        }
    raise RuntimeError(f"No downloadable Internet Archive footage candidate found for query: {query}")
