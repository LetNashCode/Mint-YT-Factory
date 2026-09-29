"""Burn 5-word Whisper-timed documentary captions with active-word emphasis.

Each caption group contains up to five spoken words. The complete group remains on
screen while the currently spoken word becomes slightly larger, yellow, bold, and
shadowed; all other words remain white with shadow.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import whisper


BASE_SIZE = 50
ACTIVE_SIZE = 62
YELLOW = "&H0000FFFF"  # ASS BGR = yellow
WHITE = "&H00FFFFFF"
OUTLINE = "&H00101010"
SHADOW = 4


def atime(value):
    cs = max(0, int(round(float(value) * 100)))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def esc(value):
    return str(value).replace("\\", "\\\\").replace("{", "\{").replace("}", "\}")


def normalize_word(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def load_words(source: Path):
    result = whisper.load_model("base.en").transcribe(
        str(source),
        language="en",
        word_timestamps=True,
        fp16=False,
        verbose=False,
    )
    words = []
    for segment in result.get("segments", []):
        for word in segment.get("words", []):
            text = str(word.get("word", "")).strip()
            if not text:
                continue
            start = float(word.get("start", segment.get("start", 0)))
            end = float(word.get("end", segment.get("end", start + 0.2)))
            if end <= start:
                end = start + 0.15
            words.append({"text": text, "start": start, "end": end})
    return words


def group_words(words, group_size=5):
    return [words[index:index + group_size] for index in range(0, len(words), group_size)]


def styled_group(group, active_index):
    parts = []
    for index, word in enumerate(group):
        if index:
            parts.append(" ")
        if index == active_index:
            parts.append(
                "{\\fs%d\\c%s\\b1\\shad%d}%s{\\rDocumentary}"
                % (ACTIVE_SIZE, YELLOW, SHADOW, esc(word["text"]))
            )
        else:
            parts.append(
                "{\\fs%d\\c%s\\b0\\shad%d}%s{\\rDocumentary}"
                % (BASE_SIZE, WHITE, SHADOW, esc(word["text"]))
            )
    return "".join(parts)


def build_events(words):
    events = []
    for group in group_words(words, 5):
        if not group:
            continue
        group_end = max(float(group[-1]["end"]), float(group[-1]["start"]) + 0.15)
        for index, word in enumerate(group):
            start = float(word["start"])
            if index + 1 < len(group):
                end = max(start + 0.05, float(group[index + 1]["start"]))
            else:
                end = group_end
            if end <= start:
                end = start + 0.15
            events.append((start, end, styled_group(group, index)))
    return events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--keywords", required=True)
    args = parser.parse_args()

    source = Path(args.input)
    output = Path(args.output)
    audio = output.with_suffix(".wav")
    ass = output.with_suffix(".ass")

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", str(audio)],
        check=False,
    )

    # Metadata is retained for compatibility/auditability; captions are timed from
    # the actual final documentary audio, not from generated narration text.
    json.loads(Path(args.keywords).read_text(encoding="utf-8"))
    words = load_words(audio)
    events = build_events(words)

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Documentary,Arial,%d,&H00FFFFFF,&H00FFFFFF,&H00101010,&H99000000,0,0,0,0,100,100,0,0,1,3,%d,2,100,100,90,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
""" % (BASE_SIZE, SHADOW)

    ass.write_text(
        header
        + "\n".join(
            f"Dialogue: 0,{atime(start)},{atime(max(end, start + 0.15))},Documentary,,0,0,0,,{text}"
            for start, end, text in events
        )
        + "\n",
        encoding="utf-8",
    )

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(source), "-vf", f"ass={ass}", "-c:a", "copy", str(output)],
        check=True,
    )
    audio.unlink(missing_ok=True)
    ass.unlink(missing_ok=True)
    print(f"MYSTERY_DOCUMENTARY_CAPTIONS_OUTPUT={output}")
    print(f"MYSTERY_DOCUMENTARY_CAPTION_GROUP_SIZE=5")
    print(f"MYSTERY_DOCUMENTARY_CAPTION_ACTIVE_SIZE={ACTIVE_SIZE}")
    print(f"MYSTERY_DOCUMENTARY_CAPTION_BASE_SIZE={BASE_SIZE}")


if __name__ == "__main__":
    main()
