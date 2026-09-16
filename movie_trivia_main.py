"""Fully automatic Movie Trivia Shorts production line.

Pipeline:
1. Gemini selects a movie-trivia idea and writes the narration plus short clip queries.
2. PlayPhrase is opened in a headless browser and playable clip media is captured.
3. Kokoro generates the narration using the repository TTS engine.
4. FFmpeg builds a 9:16 Short with a hook card, movie clips, and narration.
5. The validated artifact is uploaded to YouTube when enabled.

This line is intentionally isolated from Publish Shorts and Story Shorts.
It does not use stock media or AI-generated production visuals.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

from google import genai
from google.genai import types

from tts import synthesize_narration

ROOT = Path(__file__).resolve().parent
MODEL_NAME = "gemini-flash-lite-latest"
OUTPUT_DIR = ROOT / os.getenv("MOVIE_OUTPUT_DIR", "artifacts/movie-trivia")


def run(command: list[str]) -> None:
    print("$", " ".join(str(item) for item in command))
    subprocess.run(command, check=True)


def clean_text(value: object, limit: int = 4000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text, flags=re.I).strip()
    text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def generate_episode() -> dict:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for automatic movie-trivia generation.")

    client = genai.Client(api_key=api_key)
    prompt = r"""
Create one original, factually cautious movie-trivia YouTube Short for a global English audience.
Choose a well-known movie with dialogue likely to be discoverable on PlayPhrase.me.
Avoid spoilers for major plot twists unless the narration clearly labels the spoiler.
Do not invent production facts, quotes, release dates, or actor details. Prefer widely documented,
low-risk trivia such as a memorable line's context, a practical filming detail, a recognizable
character detail, or a clearly framed interpretation. If a detail is uncertain, choose another idea.

The Short should be 35–55 seconds and use 3–5 short PlayPhrase search queries. The queries must be
short, ordinary spoken phrases likely to return a clip, not long exact quotations. The clips are
used as atmospheric dialogue moments; the narration must remain understandable without them.

Write in an energetic, conversational, curiosity-first style. Start with a strong hook. Do not say
"welcome", "today we are going to", or "did you know". End with a satisfying reveal and a brief
follow request. Return JSON only with this exact shape:
{
  "movie_title": "...",
  "video_title": "...",
  "hook": "...",
  "narration": "...",
  "clip_queries": ["...", "...", "..."],
  "description": "...",
  "tags": ["movie trivia", "film facts", "..."],
  "fact_basis": "A concise note explaining why the selected fact is safe to publish."
}
"""
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.8,
        ),
    )
    text = getattr(response, "text", "")
    if not text:
        raise RuntimeError("Gemini returned no movie-trivia episode.")
    episode = parse_json(text)

    required = ("movie_title", "video_title", "hook", "narration", "clip_queries", "description", "tags", "fact_basis")
    for key in required:
        if key not in episode:
            raise RuntimeError(f"Generated episode is missing {key!r}.")
    if not isinstance(episode["clip_queries"], list) or not episode["clip_queries"]:
        raise RuntimeError("Generated episode has no PlayPhrase queries.")
    if len(clean_text(episode["narration"]).split()) < 65:
        raise RuntimeError("Generated narration is too short for a complete Short.")
    episode["clip_queries"] = [clean_text(item, 120) for item in episode["clip_queries"][:5] if clean_text(item, 120)]
    episode["tags"] = [clean_text(item, 80) for item in episode["tags"] if clean_text(item, 80)][:12]
    print(f"🎬 Generated movie-trivia episode: {episode['movie_title']}")
    print(f"🔎 PlayPhrase queries: {episode['clip_queries']}")
    return episode


def capture_playphrase_clip(query: str, output_path: Path) -> bool:
    """Capture the first playable MP4 response from PlayPhrase's browser session.

    PlayPhrase is a browser application rather than a documented API. This adapter deliberately
    fails closed if no playable media response is observed; it never substitutes another source.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError("playwright is required for automatic PlayPhrase capture.") from error

    media_payload: dict[str, bytes | str] = {}
    search_url = f"https://www.playphrase.me/#/clip-search?language=en&q={quote(query)}"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
            viewport={"width": 1440, "height": 1000},
        )
        page = context.new_page()

        def on_response(response):
            if media_payload.get("body"):
                return
            url = response.url.lower()
            content_type = (response.headers.get("content-type") or "").lower()
            if ".mp4" in url or "video/mp4" in content_type:
                try:
                    body = response.body()
                    if len(body) > 20_000:
                        media_payload["body"] = body
                        media_payload["url"] = response.url
                except Exception:
                    pass

        page.on("response", on_response)
        print(f"🎞️ Searching PlayPhrase: {query}")
        page.goto(search_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(8_000)
        if not media_payload.get("body"):
            # Some versions expose the CDN URL only as a video element source.
            source = page.locator("video").first.get_attribute("src", timeout=5_000)
            if source and source.startswith("http"):
                try:
                    response = context.request.get(source, timeout=30_000)
                    if response.ok and len(response.body()) > 20_000:
                        media_payload["body"] = response.body()
                        media_payload["url"] = source
                except Exception:
                    pass
        browser.close()

    body = media_payload.get("body")
    if not isinstance(body, bytes):
        print(f"⚠️ No playable PlayPhrase clip captured for: {query}")
        return False
    output_path.write_bytes(body)
    print(f"✅ Captured PlayPhrase clip: {output_path.name} ({len(body)} bytes)")
    return True


def make_title_card(text: str, output: Path, duration: float = 2.5) -> None:
    # Use drawtext with a conservative escaped string; no user-provided shell interpolation is used.
    safe = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=30",
        "-t", str(duration),
        "-vf", f"drawtext=text='{safe}':fontcolor=white:fontsize=66:x=(w-text_w)/2:y=(h-text_h)/2:line_spacing=18",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output),
    ])


def normalize_clip(source: Path, destination: Path, duration: float = 5.0) -> None:
    run([
        "ffmpeg", "-y", "-i", str(source), "-t", str(duration),
        "-an", "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", "30", str(destination),
    ])


def build_video(episode: dict, clip_paths: list[Path], narration_audio: Path, output: Path, work: Path) -> None:
    card = work / "hook.mp4"
    make_title_card(clean_text(episode["hook"], 180), card)
    normalized = [card]
    for index, clip in enumerate(clip_paths, start=1):
        target = work / f"normalized-{index}.mp4"
        normalize_clip(clip, target, duration=5.0)
        normalized.append(target)

    concat_file = work / "concat.txt"
    concat_file.write_text("\n".join(f"file '{path.as_posix()}'" for path in normalized), encoding="utf-8")
    joined = work / "joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(joined)])
    run([
        "ffmpeg", "-y", "-i", str(joined), "-i", str(narration_audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        "-t", "60", "-r", "30", "-c:v", "libx264", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(output),
    ])


def maybe_upload(output: Path, episode: dict) -> str | None:
    if os.getenv("MOVIE_AUTO_UPLOAD", "true").strip().lower() not in {"1", "true", "yes"}:
        print("ℹ️ MOVIE_AUTO_UPLOAD is disabled; retaining the artifact only.")
        return None
    from upload_youtube import upload_video
    config = {
        "upload": {"privacy_status": os.getenv("MOVIE_PRIVACY_STATUS", "public"), "category_id": "24"},
        "seo": {"hashtags": episode.get("tags", [])},
    }
    comment = f"What movie should we decode next? 🎬"
    return upload_video(
        str(output),
        clean_text(episode["video_title"], 90),
        clean_text(episode["description"], 1800),
        config,
        engagement_comment=comment,
    )


def main() -> None:
    if os.getenv("PLAYPHRASE_LICENSE_ACK", "").strip().lower() != "true":
        raise RuntimeError("Set PLAYPHRASE_LICENSE_ACK=true only after confirming the required clip rights.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    episode = generate_episode()
    with tempfile.TemporaryDirectory(prefix="movie-trivia-") as temp_dir:
        work = Path(temp_dir)
        clip_paths: list[Path] = []
        for index, query in enumerate(episode["clip_queries"], start=1):
            clip_path = work / f"playphrase-{index}.mp4"
            if capture_playphrase_clip(query, clip_path):
                clip_paths.append(clip_path)
            if len(clip_paths) >= 3:
                break
        if not clip_paths:
            raise RuntimeError("PlayPhrase returned no playable clips. No fallback media was used.")

        audio = work / "narration.mp3"
        tts_config = {"voice": {"provider": "kokoro", "voice_name": "af_heart", "kokoro_lang": "a", "speed": 1.0}}
        synthesize_narration(clean_text(episode["narration"], 6000), tts_config, str(audio), target_duration=48.0)
        output = OUTPUT_DIR / "movie-trivia-short.mp4"
        build_video(episode, clip_paths, audio, output, work)

    metadata = {
        "movie": episode["movie_title"],
        "video_title": episode["video_title"],
        "clip_source": "PlayPhrase browser capture",
        "clip_queries": episode["clip_queries"],
        "narration_provider": "Kokoro via tts.py",
        "gemini_model": MODEL_NAME,
        "rights_acknowledged": True,
        "fact_basis": episode["fact_basis"],
        "generated_at": int(time.time()),
    }
    (OUTPUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    video_id = maybe_upload(output, episode)
    if video_id:
        metadata["youtube_video_id"] = video_id
        (OUTPUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"MOVIE_TRIVIA_OUTPUT={output}")


if __name__ == "__main__":
    main()
