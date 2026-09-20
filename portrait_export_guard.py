"""Final portrait export and validation guard for Mint-YT-Factory videos."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

TARGET_WIDTH = 2160
TARGET_HEIGHT = 3840


def _probe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,codec_name,pix_fmt",
            "-of", "json", str(path),
        ], check=True, capture_output=True, text=True,
    )
    streams = json.loads(result.stdout).get("streams") or []
    if not streams:
        raise RuntimeError(f"No video stream found in {path}")
    return streams[0]


def ensure_portrait_export(path: str | Path) -> Path:
    """Normalize a video to full-frame 9:16 and reject non-portrait output.

    The source is scaled to fit entirely inside the portrait canvas; padding is
    used instead of cropping, so landscape footage remains fully visible.
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)

    probe = _probe(source)
    width = int(probe.get("width") or 0)
    height = int(probe.get("height") or 0)
    if width <= 0 or height <= 0:
        raise RuntimeError(f"Invalid video dimensions: {width}x{height}")

    temp = source.with_name(source.stem + ".portrait.tmp.mp4")
    vf = (
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease:"
        f"force_divisible_by=2,pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black"
    )
    subprocess.run([
        "ffmpeg", "-y", "-i", str(source), "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "60",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(temp),
    ], check=True)
    temp.replace(source)

    final_probe = _probe(source)
    final_width = int(final_probe.get("width") or 0)
    final_height = int(final_probe.get("height") or 0)
    if final_width != TARGET_WIDTH or final_height != TARGET_HEIGHT:
        raise RuntimeError(
            f"Portrait export failed: got {final_width}x{final_height}, "
            f"expected {TARGET_WIDTH}x{TARGET_HEIGHT}"
        )
    return source
