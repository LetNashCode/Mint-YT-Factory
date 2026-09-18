"""Discover candidate public-domain/CC footage from Internet Archive.

Gemini chooses a search direction, then the discovery layer searches Internet
Archive metadata. Search results are never treated as rights-cleared.
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
FALLBACK_QUERIES = [
    "public domain historical footage",
    "public domain archival film",
    "unusual historical event footage",
    "strange archival recording",
    "unexplained historical footage",
]


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
    with genai.Client(api_key=key) as client:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json", temperature=0.7
            ),
        )
    return _json(getattr(response, "text", ""))


def _find_video(query: str) -> dict[str, Any] | None:
    params = {
        "q": f"({query}) AND mediatype:movies",
        "fl[]": ["identifier", "title", "description", "year", "licenseurl", "rights"],
        "rows": 50,
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
        try:
            meta = requests.get(
                f"https://archive.org/metadata/{identifier}", timeout=60
            )
            meta.raise_for_status()
            files = meta.json().get("files", [])
        except (requests.RequestException, ValueError):
            continue
        video = next(
            (
                f
                for f in files
                if str(f.get("name", "")).lower().endswith((".mp4", ".webm", ".ogv"))
                and _file_size(f) > 10000
            ),
            None,
        )
        if not video:
            continue
        filename = str(video["name"])
        return {
            "id": f"ia-{identifier}",
            "title": title,
            "topic": query,
            "source_url": f"https://archive.org/details/{identifier}",
            "video_url": f"https://archive.org/download/{identifier}/{filename}",
            "license": doc.get("licenseurl") or "Review Internet Archive item rights before publishing",
            "rights_verified": False,
            "rights_notes": "Automatically discovered candidate. Human rights review is required before commercial publication.",
            "attribution": "Follow the individual Internet Archive item's attribution requirements.",
        }
    return None


def _file_size(file_entry: dict[str, Any]) -> int:
    try:
        return int(file_entry.get("size", 0) or 0)
    except (TypeError, ValueError):
        return 0


def discover_item() -> dict[str, Any]:
    direction = _search_direction()
    requested = str(direction.get("search_query", "")).strip()
    queries: list[str] = []
    if requested:
        queries.append(requested)
    queries.extend(q for q in FALLBACK_QUERIES if q.lower() != requested.lower())

    for query in queries:
        print(f"Searching Internet Archive for: {query}")
        try:
            item = _find_video(query)
        except requests.RequestException as exc:
            print(f"Internet Archive search failed for {query!r}: {exc}")
            continue
        if item:
            item["topic"] = direction.get("topic") or query
            return item

    raise RuntimeError(
        "No downloadable Internet Archive footage candidate found after trying "
        f"{len(queries)} search queries. Last query: {queries[-1] if queries else 'none'}"
    )
