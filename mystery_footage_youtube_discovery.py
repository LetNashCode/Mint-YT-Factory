"""Discover potentially reusable mystery footage from YouTube.

This module is deliberately conservative: it only accepts videos whose YouTube
metadata reports a Creative Commons license. It does not treat that metadata as
proof of ownership; candidates are written for the existing rights gate.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "mystery_footage_catalog.json"
API_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEO_URL = "https://www.googleapis.com/youtube/v3/videos"

QUERIES = [
    "documented unexplained CCTV mystery footage",
    "strange security camera incident documentary footage",
    "mysterious historical recording explained",
]


def clean(value: str, limit: int = 1200) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def api_get(url: str, params: dict) -> dict:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def discover() -> dict | None:
    key = os.getenv("YOUTUBE_DATA_API_KEY", "").strip()
    if not key:
        raise RuntimeError("YOUTUBE_DATA_API_KEY is required for automatic discovery.")

    for query in QUERIES:
        search = api_get(API_URL, {
            "part": "snippet",
            "q": query,
            "type": "video",
            "videoLicense": "creativeCommon",
            "maxResults": 10,
            "key": key,
        })
        ids = [item["id"]["videoId"] for item in search.get("items", [])]
        if not ids:
            continue
        details = api_get(VIDEO_URL, {
            "part": "snippet,status,contentDetails",
            "id": ",".join(ids),
            "key": key,
        })
        for video in details.get("items", []):
            snippet = video.get("snippet", {})
            status = video.get("status", {})
            if status.get("license") != "creativeCommon":
                continue
            video_id = video["id"]
            title = clean(snippet.get("title", "Untitled mystery footage"), 200)
            return {
                "id": "youtube-" + video_id,
                "title": title,
                "case_summary": "Candidate discovered automatically from YouTube; case research is pending.",
                "verified_facts": [],
                "theories_or_open_questions": [],
                "footage_description": clean(snippet.get("description", "")),
                "source_url": f"https://www.youtube.com/watch?v={video_id}",
                "video_url": f"https://www.youtube.com/watch?v={video_id}",
                "license": "YouTube Creative Commons metadata",
                "rights_verified": False,
                "rights_notes": "Creative Commons metadata is not proof that the uploader owns the footage. Requires case research and rights review.",
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            }
    return None


def main() -> None:
    candidate = discover()
    if not candidate:
        print("No Creative Commons YouTube candidate found; leaving catalog unchanged.")
        return
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    data.setdefault("items", [])
    data["items"] = [item for item in data["items"] if item.get("id") != candidate["id"]]
    data["items"].append(candidate)
    CATALOG.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Discovered candidate {candidate['id']}; it remains blocked until verified facts and rights are supplied.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"YouTube discovery failed: {exc}", file=sys.stderr)
        raise
