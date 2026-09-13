"""Pre-render media validation for Story Shorts.

Validates every generated visual before MoviePy starts. Still images are
normalized to RGB-compatible pixels and rejected if corrupt or unsupported.
Videos are probed with ffprobe for a usable stream.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PIL import Image

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv", ".ogv"}


def _normalize_image(path: Path) -> None:
    with Image.open(path) as image:
        image.load()
        if image.width <= 0 or image.height <= 0:
            raise RuntimeError(f"Image has invalid dimensions: {path}")
        # MoviePy/PIL can expose grayscale, palette, CMYK, or RGBA frames.
        # Normalize to RGB on disk so the render stage receives a predictable
        # HxWx3-compatible image regardless of the source format.
        if image.mode != "RGB":
            rgb = image.convert("RGB")
            tmp = path.with_name(path.name + ".rgb.tmp.jpg")
            rgb.save(tmp, format="JPEG", quality=95, optimize=True)
            os.replace(tmp, path)


def _validate_video(path: Path) -> None:
    command = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration,codec_name,pix_fmt",
        "-of", "default=noprint_wrappers=1:nokey=0", str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    values = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    if int(values.get("width", "0") or 0) <= 0 or int(values.get("height", "0") or 0) <= 0:
        raise RuntimeError(f"Video has invalid dimensions: {path}")
    if float(values.get("duration", "0") or 0) <= 0:
        raise RuntimeError(f"Video has invalid duration: {path}")


def validate_story_media(visual_paths) -> int:
    """Validate and normalize a flat list of Story visual paths."""
    paths = [Path(p) for p in (visual_paths or []) if isinstance(p, (str, os.PathLike))]
    if not paths:
        raise RuntimeError("Story media preflight received no visual files.")
    checked = 0
    for path in paths:
        if not path.is_file() or path.stat().st_size < 1024:
            raise RuntimeError(f"Story visual is missing or too small: {path}")
        suffix = path.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            _normalize_image(path)
            kind = "IMAGE"
        elif suffix in VIDEO_EXTENSIONS:
            _validate_video(path)
            kind = "VIDEO"
        else:
            raise RuntimeError(f"Unsupported Story visual extension: {path}")
        checked += 1
        print(f"   🛡️ MEDIA PREFLIGHT PASS | {kind} | {path.name}")
    print(f"🛡️ Story media preflight passed: {checked} files")
    return checked
