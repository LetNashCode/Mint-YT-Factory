"""Final quality gate for the long-form Mystery Documentary pipeline."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "artifacts" / "mystery-documentary"
MIN_DURATION = 90.0
MIN_NARRATION_WORDS = 120
MIN_NARRATION_SCENES = 4


def probe(path: Path) -> tuple[float, int, int, bool]:
    raw = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration:stream=width,height,codec_type",
            "-of", "json", str(path),
        ],
        text=True,
    )
    data = json.loads(raw)
    duration = float((data.get("format") or {}).get("duration") or 0)
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    return duration, int(video.get("width") or 0), int(video.get("height") or 0), has_audio


def main() -> None:
    video = OUT / "mystery-documentary.mp4"
    script = OUT / "script.json"
    timeline = OUT / "timeline.json"
    metadata = OUT / "metadata.json"

    for path in (video, script, timeline, metadata):
        if not path.is_file() or path.stat().st_size < 100:
            raise RuntimeError(f"Mystery quality gate: missing or invalid artifact: {path}")

    script_data = json.loads(script.read_text(encoding="utf-8"))
    timeline_data = json.loads(timeline.read_text(encoding="utf-8"))
    metadata_data = json.loads(metadata.read_text(encoding="utf-8"))

    narration = str(script_data.get("narration") or "").strip()
    words = len(re.findall(r"\b[\w'-]+\b", narration))
    scenes = [
        s for s in (timeline_data.get("scene_plan") or [])
        if isinstance(s, dict) and s.get("narration")
        and str(s.get("audio_mode") or "") in {"narration", "pause", "replay"}
    ]
    stats = timeline_data.get("narration_stats") or {}
    effect_stats = timeline_data.get("visual_effect_stats") or {}
    if not any(isinstance(s, dict) and s.get("visual_effect") for s in (timeline_data.get("scene_plan") or [])):
        raise RuntimeError("Mystery quality gate: scene plan has no visual effect instructions")
    if int(effect_stats.get("pause", 0) or 0) < 1:
        raise RuntimeError("Mystery quality gate: no pause/freeze evidence moment was rendered")
    if int(effect_stats.get("zoom_in", 0) or 0) + int(effect_stats.get("zoom_out", 0) or 0) < 1:
        raise RuntimeError("Mystery quality gate: no zoom evidence moment was rendered")

    if words < MIN_NARRATION_WORDS:
        raise RuntimeError(f"Mystery quality gate: narration has only {words} words")
    if len(scenes) < MIN_NARRATION_SCENES:
        raise RuntimeError(f"Mystery quality gate: only {len(scenes)} generated narration scenes")
    if int(stats.get("word_count", 0) or 0) < MIN_NARRATION_WORDS:
        raise RuntimeError("Mystery quality gate: narration stats do not match the required minimum")

    duration, width, height, has_audio = probe(video)
    if duration < MIN_DURATION:
        raise RuntimeError(f"Mystery quality gate: duration {duration:.2f}s is below {MIN_DURATION:.0f}s")
    if width != 1920 or height != 1080:
        raise RuntimeError(f"Mystery quality gate: expected 1920x1080, got {width}x{height}")
    if not has_audio:
        raise RuntimeError("Mystery quality gate: final documentary has no audio stream")

    if not metadata_data.get("catalog_item_id"):
        raise RuntimeError("Mystery quality gate: catalog item ID missing")
    if metadata_data.get("narration_stats", {}).get("word_count", 0) < MIN_NARRATION_WORDS:
        raise RuntimeError("Mystery quality gate: metadata reports insufficient narration")

    print(
        f"✅ Mystery Documentary quality gate passed | "
        f"{duration:.1f}s | {width}x{height} | narration={words} words | scenes={len(scenes)} | effects={effect_stats}"
    )


if __name__ == "__main__":
    main()
