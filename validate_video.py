"""Final render validation for Mint-YT-Factory.

The upload stage is allowed to run only when the finished MP4 is actually
2160x3840 portrait, 60 fps, and encoded at the configured 100 Mbps production bitrate.
"""

from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path


EXPECTED_WIDTH = 2160
EXPECTED_HEIGHT = 3840
EXPECTED_FPS = 60.0
EXPECTED_BITRATE_MBPS = 100.0


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


def validate_final_video(path: str, expected_bitrate_mbps: float = EXPECTED_BITRATE_MBPS) -> dict:
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

    if (width, height) != (EXPECTED_WIDTH, EXPECTED_HEIGHT):
        errors.append(f"Expected {EXPECTED_WIDTH}x{EXPECTED_HEIGHT}, got {width}x{height}")

    if abs(fps - EXPECTED_FPS) > 0.05:
        errors.append(f"Expected {EXPECTED_FPS:.0f} fps, got {fps:.3f}")

    if codec != "h264":
        errors.append(f"Expected H.264, got {codec or 'unknown'}")

    if pixel_format != "yuv420p":
        errors.append(f"Expected yuv420p, got {pixel_format or 'unknown'}")

    # ffprobe reports average stream bitrate. The encoder target is 100 Mbps;
    # allow normal encoder/content variation but reject a materially lower render.
    if bitrate <= 0:
        errors.append("Could not measure the final video bitrate")
    elif bitrate < expected_bitrate_mbps * 0.90:
        errors.append(
            f"Video bitrate is materially below 100 Mbps target: {bitrate:.2f} Mbps"
        )

    if errors:
        print("❌ VIDEO QUALITY VALIDATION FAILED")
        for error in errors:
            print(f" - {error}")
        raise RuntimeError("Final video failed production quality validation.")

    print("✅ VIDEO QUALITY VALIDATION PASSED")
    print("=" * 80)

    return {
        "ok": True,
        "path": path,
        "width": width,
        "height": height,
        "fps": fps,
        "codec": codec,
        "pixel_format": pixel_format,
        "bitrate_mbps": bitrate,
        "target_bitrate_mbps": expected_bitrate_mbps,
    }
