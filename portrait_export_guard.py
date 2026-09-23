"""Final portrait export and validation guard for Mint-YT-Factory videos."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

TARGET_WIDTH = 2160
TARGET_HEIGHT = 3840


def _probe(path: Path) -> dict:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name,pix_fmt",
        "-of", "json", str(path),
    ], check=True, capture_output=True, text=True)
    streams = json.loads(result.stdout).get("streams") or []
    if not streams:
        raise RuntimeError(f"No video stream found in {path}")
    return streams[0]


def _detect_embedded_black_bars(source: Path) -> tuple[int, int, int, int] | None:
    """Detect conservative letterbox/pillarbox crops with FFmpeg cropdetect."""
    command = [
        "ffmpeg", "-hide_banner", "-ss", "0", "-i", str(source),
        "-t", "8", "-vf", "cropdetect=24:16:0", "-an", "-f", "null", "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    text = (result.stderr or "") + (result.stdout or "")
    matches = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", text)
    if not matches:
        return None

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
    if width <= 0 or height <= 0 or removed_fraction < 0.01 or removed_fraction > 0.30:
        return None
    if x + width > source_width or y + height > source_height:
        return None
    return width, height, x, y


def ensure_portrait_export(path: str | Path) -> Path:
    """Export a full-frame 2160x3840 portrait crop without blur or borders.

    Embedded black borders are removed when reliably detected. The cleaned source
    is then scaled to cover the complete 9:16 canvas and centrally cropped. This
    intentionally fills every pixel of the portrait frame, preserving the middle
    of the source rather than adding a background layer.
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)

    probe = _probe(source)
    width = int(probe.get("width") or 0)
    height = int(probe.get("height") or 0)
    if width <= 0 or height <= 0:
        raise RuntimeError(f"Invalid video dimensions: {width}x{height}")

    # Fast path: a valid portrait export is already compliant. Re-encoding every
    # run is wasteful and can fail on GitHub-hosted runners for very large 4K files.
    # The guard's job here is to enforce the final frame geometry, not to transcode
    # an already-valid master again.
    codec = str(probe.get("codec_name") or "")
    pix_fmt = str(probe.get("pix_fmt") or "")
    if width == TARGET_WIDTH and height == TARGET_HEIGHT:
        print(
            f"✅ Portrait export already compliant: {width}x{height} "
            f"{codec or 'unknown'}/{pix_fmt or 'unknown'}; skipping re-encode."
        )
        return source

    crop = _detect_embedded_black_bars(source)
    crop_filter = ""
    if crop:
        crop_w, crop_h, crop_x, crop_y = crop
        crop_filter = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"
        print(f"🧹 Removing embedded black borders: crop={crop_w}:{crop_h}:{crop_x}:{crop_y}")
    else:
        print("ℹ️ No reliable embedded black-border crop detected; preserving source frame.")

    temp = source.with_name(source.stem + ".portrait.tmp.mp4")
    # Cover-and-crop: no blurred layer, no padding, no black borders.
    filter_complex = (
        f"[0:v]{crop_filter}"
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={TARGET_WIDTH}:{TARGET_HEIGHT}:(iw-{TARGET_WIDTH})/2:(ih-{TARGET_HEIGHT})/2,"
        f"setsar=1[v]"
    )
    command = [
        "ffmpeg", "-y", "-i", str(source), "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-r", "60", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(temp),
    ]
    subprocess.run(command, check=True)
    temp.replace(source)

    final_probe = _probe(source)
    final_width = int(final_probe.get("width") or 0)
    final_height = int(final_probe.get("height") or 0)
    if final_width != TARGET_WIDTH or final_height != TARGET_HEIGHT:
        raise RuntimeError(
            f"Portrait export failed: got {final_width}x{final_height}, expected {TARGET_WIDTH}x{TARGET_HEIGHT}"
        )
    return source
