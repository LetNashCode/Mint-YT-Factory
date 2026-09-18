"""Screen discovered mystery footage before it enters the production queue.

The screener checks that a candidate is downloadable and technically usable,
then optionally asks Gemini to assess hook potential from sampled frames. It
never grants copyright clearance or validates the underlying story.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "mystery_footage_catalog.json"
MODEL_NAME = "gemini-flash-lite-latest"
TRUE_VALUES = {"1", "true", "yes"}
MIN_BYTES = 10_000
MIN_SECONDS = 3.0
MAX_DOWNLOAD_BYTES = 300 * 1024 * 1024


def enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name, str(default).lower()).lower()
    return value in TRUE_VALUES


def run(command: list[str]) -> str:
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def download(url: str, destination: Path) -> None:
    response = requests.get(
        url,
        timeout=120,
        stream=True,
        headers={"User-Agent": "Mint-YT-Factory/1.0 footage-screening"},
    )
    response.raise_for_status()
    content_length = int(response.headers.get("content-length", "0") or 0)
    if content_length > MAX_DOWNLOAD_BYTES:
        raise RuntimeError("source file exceeds screening size limit")
    total = 0
    with destination.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise RuntimeError("source file exceeded screening size limit")
            handle.write(chunk)
    if total < MIN_BYTES:
        raise RuntimeError("downloaded file is unexpectedly small")


def media_probe(source: Path) -> dict[str, Any]:
    raw = run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=width,height,codec_type",
        "-of", "json", str(source),
    ])
    data = json.loads(raw)
    fmt = data.get("format", {})
    streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    if not streams:
        raise RuntimeError("no video stream found")
    stream = streams[0]
    duration = float(fmt.get("duration") or 0)
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    if duration < MIN_SECONDS or width < 240 or height < 180:
        raise RuntimeError("video is too short or too small for production")
    return {
        "duration_seconds": round(duration, 2),
        "width": width,
        "height": height,
        "size_bytes": int(float(fmt.get("size") or source.stat().st_size)),
    }


def sample_frames(source: Path, directory: Path) -> list[bytes]:
    directory.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-i", str(source), "-vf", "fps=1/5,scale=768:-2",
        "-frames:v", "6", "-q:v", "4", str(directory / "frame-%02d.jpg"),
    ])
    return [path.read_bytes() for path in sorted(directory.glob("frame-*.jpg"))]


def assess_story(candidate: dict[str, Any], frames: list[bytes]) -> dict[str, Any]:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key or not frames:
        return {
            "story_score": 0,
            "hook_score": 0,
            "screening_status": "technical-only",
            "screening_notes": "Gemini assessment skipped; manual story review required.",
        }
    prompt = f"""Assess this found-footage candidate for a factual mystery Short.
Return JSON only with integer hook_score 0-10, story_score 0-10, usable_visuals
true/false, and a short screening_notes string. Judge only what the frames and
metadata support. Do not decide copyright status and do not invent the event.
A high score requires a visually understandable, unusual moment that can be
explained without sensational claims.
Title: {candidate.get('title')}
Description: {candidate.get('footage_description')}
Source: {candidate.get('source_url')}"""
    contents = [prompt] + [types.Part.from_bytes(data=frame, mime_type="image/jpeg") for frame in frames]
    with genai.Client(api_key=key) as client:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
        )
    try:
        result = json.loads(getattr(response, "text", "{}"))
    except json.JSONDecodeError:
        result = {}
    hook = max(0, min(10, int(result.get("hook_score", 0) or 0)))
    story = max(0, min(10, int(result.get("story_score", 0) or 0)))
    return {
        "hook_score": hook,
        "story_score": story,
        "usable_visuals": bool(result.get("usable_visuals", False)),
        "screening_status": "gemini-reviewed",
        "screening_notes": str(result.get("screening_notes", ""))[:1000],
    }


def screen_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    source_url = candidate.get("video_url") or candidate.get("direct_download_url")
    if not source_url:
        raise RuntimeError("candidate has no video URL")
    with tempfile.TemporaryDirectory(prefix="mystery-screen-") as temp:
        work = Path(temp)
        source = work / "source"
        download(source_url, source)
        technical = media_probe(source)
        frames = sample_frames(source, work / "frames")
        assessment = assess_story(candidate, frames)
    screened = dict(candidate)
    screened["screening"] = {
        **technical,
        **assessment,
        "screened_at": datetime.now(timezone.utc).isoformat(),
    }
    # Technical validity is mandatory. Gemini scores are used as a gate only
    # when explicitly enabled, so a missing/limited API does not corrupt data.
    minimum_score = int(os.getenv("MYSTERY_FOOTAGE_MIN_STORY_SCORE", "6"))
    if enabled("MYSTERY_FOOTAGE_REQUIRE_STORY_SCREEN", True):
        screening = screened["screening"]
        screened["screening"]["eligible"] = bool(
            screening.get("screening_status") == "gemini-reviewed"
            and screening.get("usable_visuals") is True
            and screening.get("hook_score", 0) >= minimum_score
            and screening.get("story_score", 0) >= minimum_score
        )
    else:
        screened["screening"]["eligible"] = True
    return screened


def main() -> None:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    items = data.setdefault("items", [])
    changed = False
    for index, item in enumerate(items):
        if item.get("screening", {}).get("eligible") is True:
            continue
        try:
            items[index] = screen_candidate(item)
            changed = True
            print(f"Screened {item.get('id')}: eligible={items[index]['screening'].get('eligible')}")
        except Exception as exc:
            item["screening"] = {
                "eligible": False,
                "screening_status": "failed",
                "screening_notes": str(exc)[:1000],
                "screened_at": datetime.now(timezone.utc).isoformat(),
            }
            changed = True
            print(f"Screening failed for {item.get('id')}: {exc}")
    if changed:
        CATALOG.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
