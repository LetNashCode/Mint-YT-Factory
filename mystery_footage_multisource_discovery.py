"""Discover multiple mystery-footage candidates from public archives.

Discovery supplies candidate footage for editorial and technical screening.
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
    '"security camera" footage',
    '"surveillance footage" strange',
    '"caught on camera" unexplained',
    '"UFO" film footage',
    '"unexplained" "recording"',
    '"mysterious" "film"',
    '"odd" historical footage',
    '"unusual" archival footage',
]
VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogv", ".mov", ".mkv"}
MAX_NEW_CANDIDATES = int(os.getenv("MYSTERY_FOOTAGE_MAX_DISCOVERIES", "12"))

# Broad archive searches often return podcasts, interviews, news episodes, and
# compilations. Those are poor fits for a narration-led Short that must show
# meaningful source footage, so reject them before expensive screening.
REJECT_TERMS = {
    "podcast", "interview", "talk show", "episode", "full episode", "news",
    "commentary", "reaction", "gaming", "gameplay", "livestream", "live stream",
    "compilation", "top 10", "documentary", "discussion", "debunking", "analysis",
    "radio show", "webinar", "lecture", "conversation", "trailer",
}
FOOTAGE_TERMS = {
    "footage", "security camera", "surveillance", "cctv", "recording", "caught",
    "incident", "film", "archive", "ufo", "unexplained", "strange", "mysterious",
    "camera", "video evidence", "tape",
}


def clean(value: Any, limit: int = 1200) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def is_footage_candidate(title: Any, description: Any = "") -> bool:
    text = clean(f"{title} {description}", 5000).lower()
    if any(term in text for term in REJECT_TERMS):
        return False
    return any(term in text for term in FOOTAGE_TERMS)


def get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        timeout=30,
        headers={"User-Agent": "Mint-YT-Factory/1.0 footage-discovery"},
    )
    response.raise_for_status()
    return response.json()


def base_candidate(*, candidate_id: str, title: str, summary: str,
                    source_url: str, video_url: str, provider: str,
                    description: str = "") -> dict[str, Any]:
    return {
        "id": candidate_id,
        "title": clean(title, 200) or "Untitled mystery footage",
        "case_summary": clean(summary, 1200),
        "verified_facts": [f"Candidate discovered through the {provider} public archive API."],
        "theories_or_open_questions": [],
        "footage_description": clean(description),
        "source_url": source_url,
        "video_url": video_url,
        "direct_download_url": video_url,
        "discovery_provider": provider,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }


def choose_archive_video(identifier: str, files: list[dict[str, Any]]) -> dict[str, str] | None:
    candidates: list[tuple[int, int, str]] = []
    for item in files:
        name = str(item.get("name", ""))
        extension = Path(name).suffix.lower()
        if extension not in VIDEO_EXTENSIONS:
            continue
        raw_size = item.get("size")
        size = int(raw_size) if str(raw_size).isdigit() else 10**18
        candidates.append((0 if extension in {".mp4", ".webm"} else 1, size, name))
    if not candidates:
        return None
    candidates.sort()
    filename = candidates[0][2]
    return {
        "filename": filename,
        "url": f"https://archive.org/download/{quote(identifier)}/{quote(filename)}",
    }


def discover_internet_archive(limit: int) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in QUERIES:
        result = get_json(IA_SEARCH_URL, {
            "q": f"mediatype:movies AND ({query})",
            "fl[]": ["identifier", "title", "description"],
            "rows": 50,
            "page": 1,
            "output": "json",
        })
        for doc in result.get("response", {}).get("docs", []):
            identifier = clean(doc.get("identifier"), 200)
            title = doc.get("title") or identifier
            description = doc.get("description") or ""
            if not identifier or identifier in seen:
                continue
            seen.add(identifier)
            if not is_footage_candidate(title, description):
                print(f"Filtered non-footage archive item: {identifier}")
                continue
            try:
                metadata = get_json(IA_METADATA_URL.format(identifier=quote(identifier)), {})
                chosen = choose_archive_video(identifier, metadata.get("files", []))
                if not chosen:
                    continue
                meta = metadata.get("metadata", {})
                final_title = meta.get("title") or title
                final_description = meta.get("description") or description
                if not is_footage_candidate(final_title, final_description):
                    continue
                found.append(base_candidate(
                    candidate_id=f"internet-archive-{identifier}",
                    title=final_title,
                    summary="Candidate discovered from Internet Archive; the footage and event context require factual review.",
                    source_url=f"https://archive.org/details/{quote(identifier)}",
                    video_url=chosen["url"],
                    provider="Internet Archive",
                    description=final_description,
                ))
                print(f"Archive footage candidate found: {identifier}")
                if len(found) >= limit:
                    return found
            except Exception as exc:
                print(f"Skipping Internet Archive item {identifier}: {exc}", file=sys.stderr)
    return found


def discover_wikimedia(limit: int) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in QUERIES:
        result = get_json(WIKIMEDIA_API_URL, {
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": f"{query} filemime:video", "gsrnamespace": 6,
            "gsrlimit": 50, "prop": "imageinfo", "iiprop": "url|mime|size|extmetadata",
        })
        for page in (result.get("query", {}).get("pages", {}) or {}).values():
            page_id = str(page.get("pageid", ""))
            page_title = page.get("title", "")
            if not page_id or page_id in seen:
                continue
            seen.add(page_id)
            info = (page.get("imageinfo") or [{}])[0]
            url = info.get("url")
            if not url or not str(info.get("mime", "")).startswith("video/"):
                continue
            extmetadata = info.get("extmetadata") or {}
            description = (extmetadata.get("ImageDescription") or {}).get("value", "")
            title = page_title.removeprefix("File:")
            if not is_footage_candidate(title, description):
                print(f"Filtered non-footage Wikimedia item: {page_id}")
                continue
            found.append(base_candidate(
                candidate_id=f"wikimedia-{page_id}",
                title=title,
                summary="Candidate discovered from Wikimedia Commons; the footage and event context require factual review.",
                source_url="https://commons.wikimedia.org/wiki/" + quote(page_title.replace(" ", "_")),
                video_url=url,
                provider="Wikimedia Commons",
                description=description,
            ))
            print(f"Wikimedia footage candidate found: {page_id}")
            if len(found) >= limit:
                return found
    return found


def save_candidates(candidates: list[dict[str, Any]]) -> None:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    data.setdefault("items", [])
    existing = {item.get("id"): item for item in data["items"]}
    for candidate in candidates:
        old = existing.get(candidate["id"], {})
        if old.get("screening"):
            candidate["screening"] = old["screening"]
        existing[candidate["id"]] = candidate
    data["items"] = list(existing.values())
    CATALOG.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    limit = max(1, MAX_NEW_CANDIDATES)
    candidates: list[dict[str, Any]] = []
    try:
        candidates.extend(discover_internet_archive(limit))
    except Exception as exc:
        print(f"Internet Archive discovery failed: {exc}", file=sys.stderr)
    if len(candidates) < limit:
        try:
            candidates.extend(discover_wikimedia(limit - len(candidates)))
        except Exception as exc:
            print(f"Wikimedia discovery failed: {exc}", file=sys.stderr)
    if not candidates:
        print("No archive footage candidates found; leaving catalog unchanged.")
        return
    save_candidates(candidates)
    print(f"Discovered {len(candidates)} archive footage candidate(s).")


if __name__ == "__main__":
    main()
