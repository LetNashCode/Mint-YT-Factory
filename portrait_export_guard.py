"""Final portrait export and validation guard for Mint-YT-Factory videos."""
from __future__ import annotations

import json
import re
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


def _detect_embedded_black_bars(source: Path) -> tuple[int, int, int, int] | None:
    """Detect letterbox/pillarbox borders in the source using FFmpeg cropdetect.

    A conservative threshold is used and the detected crop is accepted only when
    it removes a meaningful border while leaving a valid frame.
    """
    command = [
        "ffmpeg", "-hide_banner", "-ss", "0", "-i", str(source),
        "-t", "8", "-vf", ""cropdetect=24:16:0"", "-an", "-f", "null", "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    text = (result.stderr or "") + (result.stdout or "")
    matches = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", text)
    if not matches:
        return None

    # Use the most frequently reported crop to avoid reacting to one noisy frame.
    counts: dict[str, int] = {}
    for match in matches:
        key = ":".join(match)
        counts[key] = counts.get(key, 0) + 1
    width, height, x, y = map(int, max(counts, key=counts.get).split(":"))
    original = _probe(source)
    source_width = int(original.get("width") or 0)
    source_height = int(original.get("height") or 0)
    if not source_width or not source_height:
        return None

    removed_fraction = 1.0 - ((width * height) / float(source_width * source_height))
    # Only accept a crop when it removes a small-to-moderate border area. This
    # avoids accidentally cutting genuine scene content.
    if width <= 0 or height <= 0 or removed_fraction < 0.01 or removed_fraction > 0.30:
        return None
    if x + width > source_width or y + height > source_height:
        return None
    return width, height, x, y


def ensure_portrait_export(path: str | Path) -> Path:
    """Export a video as 2160x3840 portrait without black borders.

    Embedded letterbox/pillarbox bars are detected and cropped first. The cleaned
    source is then used for both a blurred full-canvas background and a centered
    foreground, so landscape footage fills the 9:16 canvas without black areas.
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)

    probe = _probe(source)
    width = int(probe.get("width") or 0)
    height = int(probe.get("height") or 0)
    if width <= 0 or height <= 0:
        raise RuntimeError(f"Invalid video dimensions: {width}x{height}")

    crop = _detect_embedded_black_bars(source)
    crop_filter = ""
    if crop:
        crop_w, crop_h, crop_x, crop_y = crop
        crop_filter = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"
        print(f"🧹 Removing embedded black borders with crop={crop_w}:{crop_h}:{crop_x}:{crop_y}")
    else:
        print("ℹ️ No reliable embedded black-border crop detected; preserving source frame.")

    temp = source.with_name(source.stem + ".portrait.tmp.mp4")
    filter_complex = (
        f"[0:v]{crop_filter}split=2[bgsrc][fgsrc];"
        f"[bgsrc]scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={TARGET_WIDTH}:{TARGET_HEIGHT},boxblur=30:10[background];"
        f"[fgsrc]scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"setsar=1[foreground];"
        f"[background][foreground]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"
    )
    command = [
        "ffmpeg", "-y", "-i", str(source),
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "60",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(temp),
    ]
    subprocess.run(command, check=True)
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
