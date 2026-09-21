"""Fail-closed validation for the rendered Story Shorts video."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def probe(path: str) -> dict:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path
    ], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def validate(path: str, min_duration: float = 1.0) -> dict:
    if not os.path.isfile(path) or os.path.getsize(path) <= 0:
        raise RuntimeError(f"Rendered video is missing or empty: {path}")
    data = probe(path)
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        raise RuntimeError("Rendered file contains no video stream")
    duration = float((data.get("format") or {}).get("duration") or 0)
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    fps_text = str(video.get("r_frame_rate") or "0/1")
    numerator, denominator = (int(x) for x in fps_text.split("/", 1))
    fps = numerator / denominator if denominator else 0
    if duration < min_duration:
        raise RuntimeError(f"Rendered video duration is too short: {duration:.2f}s")
    if width < 1080 or height < 1920:
        raise RuntimeError(f"Rendered video resolution is too low: {width}x{height}")
    if fps < 24:
        raise RuntimeError(f"Rendered video frame rate is too low: {fps:.2f} FPS")
    if video.get("codec_name") not in {"h264", "hevc", "vp9", "av1"}:
        raise RuntimeError(f"Unsupported video codec: {video.get('codec_name')}")
    return {"path": path, "duration": round(duration, 3), "width": width, "height": height, "fps": round(fps, 3), "codec": video.get("codec_name")}


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "output/interactive/final.mp4"
    result = validate(path)
    print("FINAL_VIDEO_QUALITY_OK", json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
