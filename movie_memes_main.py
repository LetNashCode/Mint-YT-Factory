"""PlayPhrase Movie Meme Shorts pipeline.

Creates entertaining, narration-led "When..." movie meme Shorts from short
PlayPhrase dialogue clips. This is separate from Movie Trivia, Publish Shorts,
and Story Shorts.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

from google import genai
from google.genai import types
from tts import synthesize_narration

ROOT = Path(__file__).resolve().parent
MODEL_NAME = "gemini-flash-lite-latest"
OUTPUT_DIR = ROOT / os.getenv("MOVIE_MEME_OUTPUT_DIR", "artifacts/movie-memes")


def clean(value: object, limit: int = 4000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def run(command: list[str]) -> None:
    print("$", " ".join(str(x) for x in command))
    subprocess.run(command, check=True)


def parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.I).strip()
    return json.loads(re.sub(r"```$", "", text).strip())


def generate_meme() -> dict:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required.")
    prompt = r"""
Create one original, funny movie-dialogue meme for a global English YouTube Short.
The format is a relatable everyday situation beginning with 'When...' and then 3 short
movie dialogue/reaction clips assembled as a comedic imaginary conversation. Do not require
one continuous scene. Choose short, common spoken phrases likely to be searchable on
PlayPhrase.me. The clips are punchlines and atmosphere; the narration must make the joke
understandable even if a clip's exact context is unknown.

Return JSON only in this exact shape:
{
  "video_title": "short clickable title",
  "hook": "one short on-screen When... setup",
  "narration": "35-50 second narration with pauses and clear transitions; do not say welcome or did you know",
  "clip_queries": ["short phrase 1", "short phrase 2", "short phrase 3", "short phrase 4"],
  "clip_labels": ["setup label", "response label", "escalation label", "punchline label"],
  "description": "short description",
  "tags": ["movie memes", "movie dialogue", "funny shorts"]
}
Make it punchy, relatable, and easy to understand. Avoid copyrighted exact long quotes; use
ordinary short search phrases. End with 'Follow for more movie madness.'
"""
    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.95),
    )
    meme = parse_json(getattr(response, "text", ""))
    for field in ("video_title", "hook", "narration", "clip_queries", "clip_labels", "description", "tags"):
        if field not in meme:
            raise RuntimeError(f"Generated meme is missing {field!r}.")
    queries = [clean(x, 100) for x in meme["clip_queries"] if clean(x, 100)]
    if len(queries) < 3:
        raise RuntimeError("At least three PlayPhrase queries are required.")
    meme["clip_queries"] = queries[:4]
    meme["clip_labels"] = [clean(x, 100) for x in meme["clip_labels"]][:4]
    meme["tags"] = [clean(x, 80) for x in meme["tags"]][:12]
    print(f"🎭 Generated movie meme: {meme['video_title']}")
    print(f"🔎 Queries: {meme['clip_queries']}")
    return meme


def title_card(text: str, output: Path, duration: float = 2.5) -> None:
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (1080, 1920), "black")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 66)
    words = clean(text, 180).split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > 940:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    y = (1920 - len(lines) * 88) // 2
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        draw.text(((1080 - (box[2] - box[0])) // 2, y), line, fill="white", font=font)
        y += 88
    png = output.with_suffix(".png")
    image.save(png)
    run(["ffmpeg", "-y", "-loop", "1", "-i", str(png), "-t", str(duration), "-r", "30", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output)])


def normalize(source: Path, destination: Path, duration: float = 4.5) -> None:
    run(["ffmpeg", "-y", "-i", str(source), "-t", str(duration), "-an", "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30", str(destination)])


def build(meme: dict, clips: list[Path], audio: Path, output: Path, work: Path) -> None:
    parts: list[Path] = []
    hook = work / "hook.mp4"
    title_card(meme["hook"], hook)
    parts.append(hook)
    for i, clip in enumerate(clips, 1):
        target = work / f"clip-{i}.mp4"
        normalize(clip, target)
        parts.append(target)
    concat = work / "concat.txt"
    concat.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts), encoding="utf-8")
    joined = work / "joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(joined)])
    run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(joined), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-t", "55", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(output)])


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    meme = generate_meme()
    with tempfile.TemporaryDirectory(prefix="movie-meme-") as temp:
        work = Path(temp)
        from movie_trivia_runner import _capture_playphrase_clip
        clips: list[Path] = []
        for i, query in enumerate(meme["clip_queries"], 1):
            path = work / f"playphrase-{i}.mp4"
            if _capture_playphrase_clip(query, path):
                clips.append(path)
            if len(clips) >= 3:
                break
        if len(clips) < 3:
            raise RuntimeError("Fewer than three valid PlayPhrase clips were found; no unrelated fallback media was used.")
        audio = work / "narration.mp3"
        synthesize_narration(clean(meme["narration"], 6000), {"voice": {"provider": "kokoro", "voice_name": "af_heart", "kokoro_lang": "a", "speed": 1.0}}, str(audio), target_duration=42.0)
        output = OUTPUT_DIR / "movie-meme-short.mp4"
        build(meme, clips, audio, output, work)
    metadata = {"video_title": meme["video_title"], "clip_source": "PlayPhrase browser capture", "clip_queries": meme["clip_queries"], "gemini_model": MODEL_NAME, "generated_at": int(time.time())}
    (OUTPUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    if os.getenv("MOVIE_MEME_AUTO_UPLOAD", "true").lower() in {"1", "true", "yes"}:
        from upload_youtube import upload_video
        config = {"upload": {"privacy_status": os.getenv("MOVIE_MEME_PRIVACY_STATUS", "public"), "category_id": "24"}, "seo": {"hashtags": meme["tags"]}}
        video_id = upload_video(str(output), clean(meme["video_title"], 90), clean(meme["description"], 1800), config, engagement_comment="What situation should we turn into a movie meme next? 🎬")
        metadata["youtube_video_id"] = video_id
        (OUTPUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"MOVIE_MEME_OUTPUT={output}")


if __name__ == "__main__":
    main()
