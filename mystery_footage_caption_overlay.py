"""Burn timed one-word captions onto a rendered mystery-footage Short."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import whisper


def ass_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    centiseconds = int(round(seconds * 100))
    h, remainder = divmod(centiseconds, 360000)
    m, remainder = divmod(remainder, 6000)
    s, cs = divmod(remainder, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def escape(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    source = Path(args.input)
    output = Path(args.output)
    audio_probe = output.with_suffix(".caption-audio.wav")
    ass_path = output.with_suffix(".ass")
    subprocess.run(["ffmpeg", "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", str(audio_probe)], check=True)

    model = whisper.load_model("base.en")
    result = model.transcribe(str(audio_probe), language="en", word_timestamps=True, fp16=False, verbose=False)
    events = []
    for segment in result.get("segments", []):
        for word in segment.get("words", []):
            text = str(word.get("word", "")).strip()
            if not text:
                continue
            start = float(word.get("start", segment.get("start", 0)))
            end = float(word.get("end", segment.get("end", start + 0.2)))
            if end <= start:
                end = start + 0.15
            events.append((start, end, escape(text)))

    header = """[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: OneWord,Poppins,92,&H00FFFFFF,&H00FFFFFF,&H00111111,&H99000000,1,0,0,0,100,100,0,0,1,5,4,5,60,60,560,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
    ass_path.write_text(header + "\n".join(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},OneWord,,0,0,0,,{word}" for s, e, word in events) + "\n", encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-i", str(source), "-vf", f"ass={ass_path}", "-c:a", "copy", str(output)], check=True)
    audio_probe.unlink(missing_ok=True)
    ass_path.unlink(missing_ok=True)
    print(f"MYSTERY_FOOTAGE_CAPTIONS_OUTPUT={output}")


if __name__ == "__main__":
    main()
