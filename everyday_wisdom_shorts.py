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


def render(clips, audio, output, duration):
    concat = RUN_ROOT / "concat.txt"
    concat.write_text("".join(f"file '{p.resolve()}'\n" for p in clips), encoding="utf-8")
    filter_complex = (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,setsar=1,fps=30,format=yuv420p[v]"
    )
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
        "-i", str(audio), "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "1:a:0", "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-pix_fmt", "yuv420p", str(output),
    ], check=True)


def upload(video, story):
    raw = os.getenv("YOUTUBE_TOKEN_JSON", "").strip()
    if not raw:
        raise RuntimeError("YOUTUBE_TOKEN_JSON is missing")
    credentials = Credentials.from_authorized_user_info(json.loads(raw))
    youtube = build("youtube", "v3", credentials=credentials)
    description = (
        f"{story['topic']}\n\n"
        "Everyday sayings, familiar habits, and the stories hiding behind them.\n\n"
        "#shorts #americanlife #sayings #history #curiosity"
    )
    body = {
        "snippet": {
            "title": clean(story["title"], 90),
            "description": description,
            "tags": ["shorts", "american life", "sayings", "history", "curiosity"],
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
    render(clips, audio, video, min(duration, TARGET_SECONDS))
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
