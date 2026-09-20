"""Place narration sentence clips only in audio-safe windows."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable


def _run(args: list[Any]) -> None:
    print("$", " ".join(map(str, args)))
    subprocess.run([str(value) for value in args], check=True)


def _duration(path: Path) -> float:
    value = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        text=True,
    ).strip()
    return max(0.0, float(value or 0.0))


def _gaps(total: float, protected: list[dict[str, float]], margin: float = 0.25) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    cursor = 0.0
    for interval in sorted(protected, key=lambda item: float(item.get("start", 0))):
        start = max(0.0, float(interval.get("start", 0)))
        end = min(total, max(start, float(interval.get("end", start))))
        if start - cursor >= margin:
            result.append((cursor, start))
        cursor = max(cursor, end)
    if total - cursor >= margin:
        result.append((cursor, total))
    return result


def _sentences(text: str) -> list[str]:
    clean = " ".join(text.split())
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", clean) if part.strip()]


def build_timed_narration(
    narration: str,
    source_duration: float,
    protected_intervals: list[dict[str, float]],
    work_dir: str | Path,
    tts: Callable[[str, str], None],
    voice_config: dict[str, Any],
) -> tuple[Path, list[dict[str, Any]]]:
    """Render sentence-level TTS into silent gaps and return a timed audio track."""
    work = Path(work_dir)
    clips = work / "narration-clips"
    clips.mkdir(parents=True, exist_ok=True)
    gaps = _gaps(source_duration, protected_intervals)
    placements: list[dict[str, Any]] = []
    gap_index = 0
    cursor = gaps[0][0] if gaps else source_duration

    for index, sentence in enumerate(_sentences(narration)):
        if gap_index >= len(gaps):
            break
        clip = clips / f"sentence-{index:04d}.mp3"
        tts(sentence, str(clip))
        clip_duration = _duration(clip)
        if clip_duration <= 0:
            continue
        while gap_index < len(gaps) and cursor + clip_duration > gaps[gap_index][1] - 0.15:
            gap_index += 1
            if gap_index < len(gaps):
                cursor = gaps[gap_index][0]
        if gap_index >= len(gaps):
            break
        start = max(cursor, gaps[gap_index][0])
        if start + clip_duration > gaps[gap_index][1]:
            break
        placements.append({"sentence": sentence, "start": round(start, 3), "end": round(start + clip_duration, 3), "file": str(clip)})
        cursor = start + clip_duration + 0.12

    output = work / "timed-narration.m4a"
    if not placements:
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo", "-t", str(source_duration), "-c:a", "aac", output])
    else:
        inputs: list[Any] = []
        filters: list[str] = []
        labels: list[str] = []
        for index, placement in enumerate(placements):
            inputs.extend(["-i", placement["file"]])
            delay = int(round(placement["start"] * 1000))
            label = f"n{index}"
            filters.append(f"[{index}:a]adelay={delay}|{delay},apad[{label}]")
            labels.append(f"[{label}]")
        filters.append("".join(labels) + f"amix=inputs={len(labels)}:duration=longest:dropout_transition=0,atrim=duration={source_duration}[mix]")
        _run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[mix]", "-c:a", "aac", "-b:a", "192k", "-t", str(source_duration), output])

    timeline = {"source_duration": source_duration, "placements": placements, "protected_intervals": protected_intervals}
    (work / "narration_timeline.json").write_text(json.dumps(timeline, indent=2, ensure_ascii=False), encoding="utf-8")
    return output, placements
