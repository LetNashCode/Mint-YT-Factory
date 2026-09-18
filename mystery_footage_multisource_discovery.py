"""Discover mystery-footage candidates from non-YouTube public archives.

This module intentionally discovers candidates only. It does not claim that a
file is commercially reusable: every candidate remains rights-unverified until
reviewed by the operator.

Providers:
- Internet Archive Advanced Search + item metadata
- Wikimedia Commons MediaSearch API

The output is compatible with mystery_footage_catalog.json and includes a
stable direct-download URL whenever the provider exposes one.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "mystery_footage_catalog.json"

IA_SEARCH_URL = "https://archive.org/advancedsearch.php"
IA_METADATA_URL = "https://archive.org/metadata/{identifier}"
WIKIMEDIA_API_URL = "https://commons.wikimedia.org/w/api.php"

QUERIES = [
    "ufo footage",
    "unexplained mystery recording",
    "strange security camera footage",
    "paranormal archival film",
    "unusual historical recording",
]

VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogv", ".mov", ".mkv"}


def clean(value: Any, limit: int = 1200) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        timeout=30,
        headers={"User-Agent": "Mint-YT-Factory/1.0 footage-discovery"},
    )
    response.raise_for_status()
    return response.json()


def base_candidate(
    *,
    candidate_id: str,
    title: str,
    summary: str,
    source_url: str,
    video_url: str,
    license_name: str,
    provider: str,
    description: str = "",
    attribution: str = "",
) -> dict[str, Any]:
    return {
        "id": candidate_id,
        "title": clean(title, 200) or "Untitled mystery footage",
        "case_summary": clean(summary, 1200),
        "verified_facts": [
            f"Candidate discovered through the {provider} public archive API."
        ],
        "theories_or_open_questions": [],
        "footage_description": clean(description),
        "source_url": source_url,
        "video_url": video_url,
        "direct_download_url": video_url,
        "license": clean(license_name, 300) or "Provider metadata; review required",
        "rights_verified": False,
        "rights_notes": (
            "Discovery metadata is not proof of ownership or commercial reuse rights. "
            "The operator must review the item license, provenance, and attribution "
            "requirements before publication."
        ),
        "attribution": clean(attribution, 800),
        "discovery_provider": provider,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }


def choose_archive_video(identifier: str, files: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = []
    for item in files:
        name = str(item.get("name", ""))
        extension = Path(name).suffix.lower()
        if extension not in VIDEO_EXTENSIONS:
            continue
        if item.get("private") or item.get("source") == "original":
            # Original files are not inherently unusable, but derived/common
            # video files are generally more practical for the pipeline.
            pass
        size = int(item.get("size") or 0) if str(item.get("size", "")).isdigit() else 0
        candidates.append((extension not in {".mp4", ".webm"}, size, name))
    if not candidates:
        return None
    # Prefer MP4/WebM and avoid enormous files when a smaller playable file exists.
    candidates.sort(key=lambda row: (row[0], row[1] if row[1] else 10**18, row[2]))
    filename = candidates[0][2]
    return {
        "filename": filename,
        "url": f"https://archive.org/download/{quote(identifier)}/{quote(filename)}",
    }


def discover_internet_archive() -> dict[str, Any] | None:
    for query in QUERIES:
        result = get_json(
            IA_SEARCH_URL,
            {
                "q": f"mediatype:movies AND ({query})",
                "fl[]": ["identifier", "title", "description"],
                "rows": 10,
                "page": 1,
                "output": "json",
            },
        )
        docs = result.get("response", {}).get("docs", [])
        for doc in docs:
            identifier = clean(doc.get("identifier"), 200)
            if not identifier:
                continue
            metadata = get_json(IA_METADATA_URL.format(identifier=quote(identifier)), {})
            chosen = choose_archive_video(identifier, metadata.get("files", []))
            if not chosen:
                continue
            meta = metadata.get("metadata", {})
            title = meta.get("title") or doc.get("title") or identifier
            description = meta.get("description") or doc.get("description") or ""
            license_name = (
                meta.get("licenseurl")
                or meta.get("license")
                or "Internet Archive item metadata; review required"
            )
            return base_candidate(
                candidate_id=f"internet-archive-{identifier}",
                title=title,
                summary=(
                    "Candidate discovered from Internet Archive. The footage and "
                    "underlying event require separate factual review."
                ),
                source_url=f"https://archive.org/details/{quote(identifier)}",
                video_url=chosen["url"],
                license_name=license_name,
                provider="Internet Archive",
                description=description,
                attribution=meta.get("creator") or meta.get("contributor") or "",
            )
    return None


def discover_wikimedia() -> dict[str, Any] | None:
    for query in QUERIES:
        result = get_json(
            WIKIMEDIA_API_URL,
            {
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrsearch": f"{query} filemime:video",
                "gsrnamespace": 6,
                "gsrlimit": 10,
                "prop": "imageinfo",
                "iiprop": "url|mime|size|extmetadata",
            },
        )
        pages = result.get("query", {}).get("pages", {})
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            mime = str(info.get("mime", ""))
            url = info.get("url")
            if not url or not mime.startswith("video/"):
                continue
            extmetadata = info.get("extmetadata") or {}
            license_name = (extmetadata.get("LicenseShortName") or {}).get("value", "")
            creator = (extmetadata.get("Artist") or {}).get("value", "")
            title = page.get("title", "").removeprefix("File:")
            return base_candidate(
                candidate_id=f"wikimedia-{page.get('pageid')}",
                title=title,
                summary=(
                    "Candidate discovered from Wikimedia Commons. The footage "
                    "and event context require separate factual review."
                ),
                source_url=(
                    "https://commons.wikimedia.org/wiki/"
                    + quote(page.get("title", "").replace(" ", "_"))
                ),
                video_url=url,
                license_name=license_name or "Wikimedia Commons metadata; review required",
                provider="Wikimedia Commons",
                description=(extmetadata.get("ImageDescription") or {}).get("value", ""),
                attribution=creator,
            )
    return None


def save_candidate(candidate: dict[str, Any]) -> None:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    data.setdefault("items", [])
    data["items"] = [item for item in data["items"] if item.get("id") != candidate["id"]]
    data["items"].append(candidate)
    CATALOG.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def discover() -> dict[str, Any] | None:
    providers = [discover_internet_archive, discover_wikimedia]
    errors: list[str] = []
    for provider in providers:
        try:
            candidate = provider()
            if candidate:
                return candidate
        except Exception as exc:  # One provider should not disable the others.
            errors.append(f"{provider.__name__}: {exc}")
            print(f"Provider failed: {errors[-1]}", file=sys.stderr)
    if errors:
        print("All archive providers failed or returned no usable video.", file=sys.stderr)
    return None


def main() -> None:
    candidate = discover()
    if not candidate:
        print("No archive footage candidate found; leaving catalog unchanged.")
        return
    save_candidate(candidate)
    print(
        f"Discovered {candidate['discovery_provider']} candidate {candidate['id']}; "
        "rights remain unverified."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Multi-source footage discovery failed: {exc}", file=sys.stderr)
        raise
