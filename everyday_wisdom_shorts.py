from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

import requests
from google import genai
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

RUN_ROOT = Path(".everyday_wisdom_runs") / str(int(time.time()))
RUN_ROOT.mkdir(parents=True, exist_ok=True)
VIDEO_DIR = RUN_ROOT / "stock"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

PEXELS_URL = "https://api.pexels.com/videos/search"
MODEL = "gemini-2.5-flash"
VOICE = os.getenv("WISDOM_KOKORO_VOICE", "af_heart")
TARGET_SECONDS = 42.0


def clean(value, limit=1000):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def client():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing")
    return genai.Client(api_key=key)


def generate_story():
    prompt = """
Create one YouTube Short for a US audience about something Americans have
heard forever but rarely stop to ask why: an old grandma saying, familiar
phrase, household rule, childhood warning, common habit, or ordinary object.

The story must uncover the documented history, practical reason, cultural
origin, or psychological reason behind it. Do not invent an origin; if the
origin is uncertain, say so naturally and give the strongest explanation.

Do not use politics, celebrities, medical advice, conspiracy, fearbait,
lists, countdowns, "Did you know?", "Today we're going to", AI references,
or a second topic. The narration must work without visuals.

Write 105-135 words, approximately 38-43 seconds, as one connected mini-story.
The first sentence must create immediate curiosity. End with a satisfying answer.

Return JSON only:
{"title":"...","topic":"...","narration":"...","search_queries":["...","...","..."]}
Search queries must be concrete things a camera can show, 3-6 words each.
"""
    c = client()
    for attempt in range(3):
        try:
            response = c.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={"temperature": 0.9, "response_mime_type": "application/json"},
            )
            data = json.loads(response.text)
            narration = clean(data.get("narration"), 3000)
            queries = [clean(x, 80) for x in data.get("search_queries", []) if clean(x, 80)]
            words = re.findall(r"\b[\w'-]+\b", narration)
            if not data.get("topic") or not narration or len(queries) < 3:
                raise RuntimeError("Incomplete story JSON")
            if not 105 <= len(words) <= 145:
                raise RuntimeError(f"Narration word count {len(words)} outside 105-145")
            return {
                "title": clean(data.get("title"), 90),
                "topic": clean(data.get("topic"), 200),
                "narration": narration,
                "search_queries": queries[:3],
            }
        except Exception as exc:
            if attempt == 2:
                raise
            print(f"Story generation retry {attempt + 1}/3: {type(exc).__name__}: {exc}")
            time.sleep(2 + attempt)
    raise RuntimeError("Story generation failed")


def synthesize(text, output):
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    pipeline = KPipeline(lang_code="a")
    words = text.split()
    chunks = [" ".join(words[i:i + 42]) for i in range(0, len(words), 42)]
    parts = []
    for index, chunk in enumerate(chunks, 1):
        print(f"TTS chunk {index}/{len(chunks)}")
        audio_parts = []
        for result in pipeline(chunk, voice=VOICE, speed=1.0, split_pattern=r"\n+"):
            audio = result[2] if isinstance(result, tuple) else result.audio
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            audio = np.asarray(audio, dtype=np.float32).reshape(-1)
            if audio.size:
                audio_parts.append(audio)
        if not audio_parts:
            raise RuntimeError(f"Kokoro returned no audio for chunk {index}")
        parts.append(np.concatenate(audio_parts))
        if index < len(chunks):
            parts.append(np.zeros(int(0.035 * 24000), dtype=np.float32))
    audio = np.concatenate(parts)
    sf.write(output, audio, 24000, subtype="PCM_16")
    duration = len(audio) / 24000.0
    if duration > TARGET_SECONDS:
        sped = output.with_name("narration_sped.wav")
        factor = min(1.12, duration / TARGET_SECONDS)
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(output), "-filter:a", f"atempo={factor:.6f}", str(sped)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        sped.replace(output)
        duration = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(output)], text=True
        ).strip())
    return duration


def search_videos(query):
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PEXELS_API_KEY is missing")
    response = requests.get(
        PEXELS_URL,
        headers={"Authorization": key},
        params={"query": query, "orientation": "portrait", "size": "medium", "per_page": 12},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("videos", [])


def download_stock(queries):
    chosen = []
    seen = set()
    for query in queries:
        for item in search_videos(query):
            vid = str(item.get("id") or "")
            if not vid or vid in seen:
                continue
            files = [f for f in item.get("video_files", []) if f.get("link")]
            if not files:
                continue
            files.sort(key=lambda f: abs((f.get("width", 0) / max(1, f.get("height", 1))) - 9 / 16))
            path = VIDEO_DIR / f"{len(chosen):02d}.mp4"
            with requests.get(files[0]["link"], stream=True, timeout=60) as dl:
                dl.raise_for_status()
                with path.open("wb") as handle:
                    for chunk in dl.iter_content(1024 * 1024):
                        if chunk:
                            handle.write(chunk)
            if path.stat().st_size < 10000:
                path.unlink(missing_ok=True)
                continue
            chosen.append(path)
            seen.add(vid)
            print(f"Stock {len(chosen)}: {query} | Pexels {vid}")
            if len(chosen) >= 6:
                return chosen
    if len(chosen) < 3:
        raise RuntimeError(f"Only {len(chosen)} usable stock videos found")
    return chosen


def _ass_time(seconds):
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    centiseconds = int(round((seconds - int(seconds)) * 100))
    whole = int(seconds) % 60
    if centiseconds >= 100:
        whole += 1
        centiseconds = 0
    return f"{hours}:{minutes:02d}:{whole:02d}.{centiseconds:02d}"


def _ass_escape(text):
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", " ")
        .strip()
    )


def create_animated_captions(narration, duration):
    """Create isolated, narration-timed kinetic captions for Everyday Wisdom.

    Captions use short 2-4 word beats, a small pop/scale entrance, fade in/out,
    thick outline and bottom-safe positioning. This file belongs only to this
    workflow; Publish Shorts and Story Shorts do not use or import it.
    """
    words = narration.split()
    if not words:
        raise RuntimeError("Cannot create captions from empty narration")

    # Keep each caption readable on a phone. Break at punctuation where possible,
    # otherwise use 3-word beats.
    groups = []
    current = []
    for word in words:
        current.append(word)
        if len(current) >= 3 or re.search(r"[.!?,;:]$", word):
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    # Timing is proportional to character count, which tracks spoken duration
    # better than assigning identical time to every caption.
    weights = [max(1, len(" ".join(group))) for group in groups]
    total_weight = float(sum(weights))
    ass_path = RUN_ROOT / "captions.ass"

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Wisdom,Arial,62,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,1,0,0,0,100,100,0,0,1,7,2,2,80,80,250,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    current_time = 0.0
    lines = [header]
    for index, (group, weight) in enumerate(zip(groups, weights)):
        start = current_time
        end = duration if index == len(groups) - 1 else current_time + duration * (weight / total_weight)
        text = _ass_escape(" ".join(group))

        # Pop from 92% to 108% then settle, plus a short fade. The result is
        # animated without requiring an external caption renderer.
        events = (
            "{\\fad(90,90)\\t(0,110,\\fscx92\\fscy92)\\t(110,220,\\fscx108\\fscy108)\\t(220,300,\\fscx100\\fscy100)}"
            + text
        )
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Wisdom,,0,0,0,,{events}"
        )
        current_time = end

    ass_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Animated captions created: {ass_path} | beats={len(groups)}")
    return ass_path


def render(clips, audio, output, duration, narration):
    concat = RUN_ROOT / "concat.txt"
    concat.write_text("".join(f"file '{p.resolve()}'\n" for p in clips), encoding="utf-8")
    ass_path = create_animated_captions(narration, duration)
    filter_complex = (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,setsar=1,fps=30,format=yuv420p[v]"
    )
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
        "-i", str(audio), "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "1:a:0", "-vf", f"subtitles={ass_path}",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-pix_fmt", "yuv420p", str(output),
    ], check=True)


def build_caption(story):
    """Everyday Wisdom's isolated copy of the Publish-style metadata pattern.

    Keep this function local to this workflow so caption changes here can never
    alter Publish Shorts metadata.
    """
    topic = clean(story.get("topic"), 180)
    narration = clean(story.get("narration"), 3000)
    title = clean(story.get("title"), 90)

    first_sentence = re.split(r"(?<=[.!?])\s+", narration.strip())[0].strip()
    description = (
        f"{topic}. "
        "Here’s the everyday story, old wisdom, or simple reason hiding behind it. "
        "Watch through the payoff and follow Everyday Wisdom for more familiar things with surprising explanations."
    )
    if first_sentence and len(first_sentence) <= 180 and first_sentence.lower() not in description.lower():
        description += f"\n\n{first_sentence}"

    hashtags = ["#shorts", "#everydaywisdom", "#americanlife", "#curiosity", "#history"]
    description += "\n\n" + " ".join(hashtags)

    tags = [
        "shorts",
        "everyday wisdom",
        "american life",
        "old sayings",
        "everyday history",
        "curiosity",
        "common sayings",
        "why we say it",
    ]
    return title, description[:2000], tags


def upload(video, story):
    raw = os.getenv("YOUTUBE_TOKEN_JSON", "").strip()
    if not raw:
        raise RuntimeError("YOUTUBE_TOKEN_JSON is missing")
    credentials = Credentials.from_authorized_user_info(json.loads(raw))
    youtube = build("youtube", "v3", credentials=credentials)
    title, description, tags = build_caption(story)
    print("YouTube caption:")
    print(description)
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "27",
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(video), chunksize=-1, resumable=True, mimetype="video/mp4"),
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload: {int(status.progress() * 100)}%")
    return response["id"]


def main():
    print("EVERYDAY WISDOM SHORTS | isolated pipeline")
    story = generate_story()
    (RUN_ROOT / "story.json").write_text(json.dumps(story, indent=2), encoding="utf-8")
    audio = RUN_ROOT / "narration.wav"
    duration = synthesize(story["narration"], audio)
    clips = download_stock(story["search_queries"])
    video = RUN_ROOT / "final.mp4"
    render(clips, audio, video, min(duration, TARGET_SECONDS), story["narration"])
    if not video.exists() or video.stat().st_size < 100000:
        raise RuntimeError("Final video was not created")
    video_id = upload(video, story)
    (RUN_ROOT / "publish.json").write_text(
        json.dumps({"video_id": video_id, "topic": story["topic"], "uploaded": True}, indent=2),
        encoding="utf-8",
    )
    print(f"UPLOADED: https://www.youtube.com/watch?v={video_id}")


if __name__ == "__main__":
    main()
