"""Analyze mystery-footage audio and produce timestamped speech/safety intervals.

The analysis is intentionally conservative: when Whisper detects speech, the
interval is padded before and after so generated narration can avoid covering
original dialogue. The resulting JSON is also useful to the scene planner.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_PADDING_SECONDS = float(os.getenv("MYSTERY_SPEECH_PADDING_SECONDS", "0.75"))
DEFAULT_MODEL = os.getenv("MYSTERY_WHISPER_MODEL", "tiny")


def _run(args: list[Any]) -> None:
    subprocess.run([str(value) for value in args], check=True)


def _extract_audio(source: Path, wav_path: Path) -> None:
    _run([
        "ffmpeg", "-y", "-i", source,
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        wav_path,
    ])


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[dict[str, float]]:
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [{"start": round(start, 3), "end": round(end, 3)} for start, end in merged]


def analyze_audio(source: str | Path, work_dir: str | Path) -> dict[str, Any]:
    """Return Whisper segments, padded protected intervals, and transcript text."""
    source_path = Path(source)
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    wav_path = work / "mystery-audio-16khz.wav"
    _extract_audio(source_path, wav_path)

    try:
        import whisper
    except ImportError as exc:
        raise RuntimeError(
            "Whisper is required for mystery audio analysis. Install openai-whisper."
        ) from exc

    model = whisper.load_model(DEFAULT_MODEL)
    result = model.transcribe(
        str(wav_path),
        fp16=False,
        verbose=False,
        temperature=0,
        condition_on_previous_text=False,
    )

    segments: list[dict[str, Any]] = []
    raw_intervals: list[tuple[float, float]] = []
    for segment in result.get("segments", []):
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", start))
        text = " ".join(str(segment.get("text", "")).split())
        if end <= start:
            continue
        segments.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "text": text,
        })
        raw_intervals.append((
            max(0.0, start - DEFAULT_PADDING_SECONDS),
            end + DEFAULT_PADDING_SECONDS,
        ))

    protected = _merge_intervals(raw_intervals)
    analysis = {
        "source": str(source_path),
        "model": DEFAULT_MODEL,
        "padding_seconds": DEFAULT_PADDING_SECONDS,
        "transcript": " ".join(item["text"] for item in segments).strip(),
        "segments": segments,
        "protected_intervals": protected,
        "narration_policy": (
            "Do not place generated narration inside protected_intervals. "
            "Preserve original speech and leave a short breathing gap around it."
        ),
    }
    (work / "audio_timeline.json").write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return analysis
