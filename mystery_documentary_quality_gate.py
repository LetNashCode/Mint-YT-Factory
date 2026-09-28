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


MIN_NARRATION_SILENCE_SECONDS = 1.25


def _check_unexpected_silence(path: Path, rendered_timeline: Path) -> list[float]:
    """Reject long silence inside narration; allow silence in intentional source-audio scenes."""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "silencedetect=noise=-45dB:d=0.80", "-f", "null", "-"],
        text=True, capture_output=True, check=False,
    )
    scenes = []
    try:
        data = json.loads(rendered_timeline.read_text(encoding="utf-8"))
        scenes = [s for s in data.get("scenes", []) if isinstance(s, dict)]
    except (OSError, ValueError, TypeError):
        scenes = []

    source_audio_intervals = [
        (float(s.get("start", 0) or 0), float(s.get("end", 0) or 0))
        for s in scenes
        if str(s.get("audio_mode") or "").lower() == "original"
    ]

    diagnostics = []
    silences = []
    current = None
    for line in result.stderr.splitlines():
        if "silence_start:" in line:
            try:
                current = float(line.split("silence_start:", 1)[1].strip())
            except ValueError:
                current = None
        elif "silence_end:" in line and current is not None:
            try:
                end = float(line.split("silence_end:", 1)[1].split("|", 1)[0].strip())
                duration = end - current
                if duration >= MIN_NARRATION_SILENCE_SECONDS:
                    # The final concat/codec can move a scene boundary slightly.
                    # Classify by overlap with an intentional original-audio scene
                    # rather than requiring exact containment.
                    best_overlap = 0.0
                    best_scene = None
                    for start, finish in source_audio_intervals:
                        overlap = max(0.0, min(end, finish) - max(current, start))
                        if overlap > best_overlap:
                            best_overlap = overlap
                            best_scene = (start, finish)

                    overlap_ratio = best_overlap / max(duration, 0.001)
                    allowed_source_gap = (
                        overlap_ratio >= 0.70
                        or (
                            best_overlap >= 0.75
                            and best_scene is not None
                            and current >= best_scene[0] - 0.35
                            and end <= best_scene[1] + 0.35
                        )
                    )

                    diagnostics.append({
                        "start": round(current, 3),
                        "end": round(end, 3),
                        "duration": round(duration, 3),
                        "source_overlap": round(best_overlap, 3),
                        "source_overlap_ratio": round(overlap_ratio, 3),
                        "allowed_as_source_audio": bool(allowed_source_gap),
                        "source_scene": (
                            {"start": round(best_scene[0], 3), "end": round(best_scene[1], 3)}
                            if best_scene else None
                        ),
                    })

                    if not allowed_source_gap:
                        silences.append(round(duration, 3))
            except ValueError:
                pass
            current = None

    try:
        (OUT / "silence_diagnostics.json").write_text(
            json.dumps(
                {
                    "threshold_seconds": MIN_NARRATION_SILENCE_SECONDS,
                    "source_audio_scene_count": len(source_audio_intervals),
                    "detected_gaps": diagnostics,
                    "unexpected_gaps": silences,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass

    return silences


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
    timeline_scenes = [s for s in (timeline_data.get("scene_plan") or []) if isinstance(s, dict)]
    if not timeline_scenes:
        raise RuntimeError("Mystery quality gate: scene plan is empty")
    cursor = 0.0
    for index, scene in enumerate(timeline_scenes):
        start = float(scene.get("start", 0) or 0)
        end = float(scene.get("end", 0) or 0)
        if start < cursor - 0.06 or end <= start:
            raise RuntimeError(f"Mystery quality gate: invalid/overlapping scene {index}: {start}->{end}")
        cursor = end
    if cursor < 89.5:
        raise RuntimeError(f"Mystery quality gate: scene plan only covers {cursor:.2f}s")

    stats = timeline_data.get("narration_stats") or {}
    effect_stats = timeline_data.get("visual_effect_stats") or {}
    audio_mix = timeline_data.get("audio_mix_stats") or {}
    narration_ratio = float(audio_mix.get("narration_ratio", 0) or 0)
    original_ratio = float(audio_mix.get("original_audio_ratio", 0) or 0)

    if not any(isinstance(s, dict) and s.get("visual_effect") for s in (timeline_data.get("scene_plan") or [])):
        raise RuntimeError("Mystery quality gate: scene plan has no visual effect instructions")
    if narration_ratio < 0.65:
        raise RuntimeError(f"Mystery quality gate: narration mix is only {narration_ratio:.1%}; expected at least 65%")
    if original_ratio > 0.25:
        raise RuntimeError(f"Mystery quality gate: original source audio occupies {original_ratio:.1%}; expected no more than 25%")
    if int(effect_stats.get("pause", 0) or 0) < 1:
        raise RuntimeError("Mystery quality gate: no pause/freeze evidence moment was rendered")
    if int(effect_stats.get("replay", 0) or 0) < 1:
        raise RuntimeError("Mystery quality gate: no replay of an evidence moment was rendered")
    if int(effect_stats.get("zoom_in", 0) or 0) + int(effect_stats.get("zoom_out", 0) or 0) < 2:
        raise RuntimeError("Mystery quality gate: fewer than two zoom evidence moments were rendered")

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

    rendered_scene_timeline = OUT / "rendered_scene_timeline.json"
    if not rendered_scene_timeline.is_file():
        raise RuntimeError("Mystery quality gate: rendered scene timing artifact is missing")
    long_silences = _check_unexpected_silence(video, rendered_scene_timeline)
    if long_silences:
        raise RuntimeError(f"Mystery quality gate: detected unexplained silent gaps >={MIN_NARRATION_SILENCE_SECONDS:.2f}s: {long_silences}")

    audio_timeline = OUT / "audio_timeline.json"
    if not audio_timeline.is_file():
        raise RuntimeError("Mystery quality gate: source audio analysis artifact is missing")

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
