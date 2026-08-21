"""Final render validation for Mint-YT-Factory.

The upload stage is allowed to run only when the finished MP4 is actually
2160x3840 portrait, 60 fps, and encoded at the configured production bitrate.
"""

from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path


def _probe(path: str) -> dict:
    command = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,avg_frame_rate,bit_rate,codec_name,pix_fmt,color_space,color_transfer,color_primaries",
        "-of", "json",
        path,
    ]

    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )

    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError("ffprobe found no video stream.")

    return streams[0]


def _fps(stream: dict) -> float:
    value = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"
    try:
        return float(Fraction(value))
    except Exception:
        return 0.0


def validate_final_video(path: str, expected_bitrate_mbps: float = 68.0) -> dict:
    if not Path(path).is_file():
        raise RuntimeError(f"Final video not found: {path}")

    stream = _probe(path)

    width = int(stream.get("width", 0))
    height = int(stream.get("height", 0))
    fps = _fps(stream)
    codec = str(stream.get("codec_name", ""))
    pixel_format = str(stream.get("pix_fmt", ""))
    bitrate_raw = stream.get("bit_rate")
    bitrate = float(bitrate_raw) / 1_000_000 if bitrate_raw else 0.0

    print("=" * 80)
    print("🔍 FINAL VIDEO QUALITY VALIDATION")
    print("=" * 80)
    print(f"Resolution: {width}x{height}")
    print(f"FPS: {fps:.3f}")
    print(f"Codec: {codec}")
    print(f"Pixel format: {pixel_format}")
    print(f"Measured video bitrate: {bitrate:.2f} Mbps")
    print(f"Target video bitrate: {expected_bitrate_mbps:.2f} Mbps")

    errors = []

    if (width, height) != (2160, 3840):
        errors.append(f"Expected 2160x3840, got {width}x{height}")

    if abs(fps - 60.0) > 0.05:
        errors.append(f"Expected 60 fps, got {fps:.3f}")

    if codec != "h264":
        errors.append(f"Expected H.264, got {codec or 'unknown'}")

    if pixel_format != "yuv420p":
        errors.append(f"Expected yuv420p, got {pixel_format or 'unknown'}")

    # ffprobe reports average stream bitrate. Allow normal container/encoder
    # variation, but reject a render that is materially below the target.
    if bitrate and bitrate < expected_bitrate_mbps * 0.80:
        errors.append(
            f"Video bitrate is materially below target: {bitrate:.2f} Mbps"
        )

    if errors:
        print("❌ VIDEO QUALITY VALIDATION FAILED")
        for error in errors:
            print(f" - {error}")
        raise RuntimeError("Final video failed production quality validation.")

    print("✅ VIDEO QUALITY VALIDATION PASSED")
    print("=" * 80)

    return {
        "path": path,
        "width": width,
        "height": height,
        "fps": fps,
        "codec": codec,
        "pixel_format": pixel_format,
        "bitrate_mbps": bitrate,
        "target_bitrate_mbps": expected_bitrate_mbps,
    }
