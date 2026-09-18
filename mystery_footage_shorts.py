"""Create a narrated mystery-footage Short from a catalog item or auto-discovered candidate."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

import requests
from google import genai
from google.genai import types
from tts import synthesize_narration

MODEL_NAME = "gemini-flash-lite-latest"
ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "mystery_footage_catalog.json"
OUTPUT_DIR = ROOT / os.getenv("MYSTERY_FOOTAGE_OUTPUT_DIR", "artifacts/mystery-footage")


def clean(value, limit=6000):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def run(command):
    print("$", " ".join(map(str, command)))
    subprocess.run(command, check=True)


def load_item():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    allow_unverified = os.getenv("MYSTERY_FOOTAGE_ALLOW_UNVERIFIED", "false").lower() in {"1", "true", "yes"}
    eligible = [x for x in data.get("items", []) if x.get("video_url") and x.get("source_url") and (allow_unverified or x.get("rights_verified") is True) and "REPLACE_ME" not in str(x.get("video_url")) and "REPLACE_ME" not in str(x.get("source_url"))]
    requested = os.getenv("MYSTERY_FOOTAGE_ITEM_ID", "").strip()
    if requested:
        for item in eligible:
            if item.get("id") == requested:
                return item
        raise RuntimeError(f"No eligible catalog item matches MYSTERY_FOOTAGE_ITEM_ID={requested!r}.")
    if eligible:
        return eligible[0]
    if os.getenv("MYSTERY_FOOTAGE_AUTO_DISCOVER", "true").lower() in {"1", "true", "yes"}:
        from mystery_footage_discovery import discover_item
        print("No catalog footage found; asking Gemini for a search direction and discovering a candidate.")
        return discover_item()
    raise RuntimeError("No usable catalog item is available and automatic discovery is disabled.")


def parse_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise RuntimeError("Gemini returned invalid JSON.")
        return json.loads(match.group(0))


def inspect_video_frames(source: Path, work: Path) -> list[bytes]:
    """Extract representative frames from the downloaded footage."""
    frames_dir = work / "analysis-frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    pattern = frames_dir / "frame-%02d.jpg"
    run(["ffmpeg", "-y", "-i", str(source), "-vf", "fps=1/5,scale=768:-2", "-frames:v", "8", "-q:v", "3", str(pattern)])
    return [path.read_bytes() for path in sorted(frames_dir.glob("frame-*.jpg"))]


def generate_script(item, source: Path, work: Path):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required.")
    frames = inspect_video_frames(source, work)
    if not frames:
        raise RuntimeError("Could not extract frames for story grounding.")
    prompt = f"""You are writing narration ONLY AFTER inspecting the supplied video frames.
Create an original, factual, entertaining 75-110 word English YouTube Shorts narration about what is visibly happening in this footage.
The footage is the primary source. Do not invent a different story, event, location, date, identity, or mystery.
Use a strong first-second hook, escalating curiosity, concise narration, and a final question.
Describe only details supported by the frames and supplied metadata. If the footage cannot support a mystery claim, frame it as an intriguing archival scene instead.
Clearly distinguish verified facts from allegations and theories. Do not present paranormal claims as fact.
Return JSON only with video_title, narration, description_intro, tags.
Catalog title: {item.get('title')}
Catalog topic: {item.get('topic')}
Source notes: {item.get('rights_notes')}
Source URL: {item.get('source_url')}"""
    contents = [prompt]
    contents.extend(types.Part.from_bytes(data=frame, mime_type="image/jpeg") for frame in frames)
    with genai.Client(api_key=key) as client:
        response = client.models.generate_content(model=MODEL_NAME, contents=contents, config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.35))
    data = parse_json(getattr(response, "text", ""))
    for field in ("video_title", "narration", "description_intro", "tags"):
        if not data.get(field):
            raise RuntimeError(f"Generated script is missing {field!r}.")
    return data


def download(item, destination):
    response = requests.get(item["video_url"], timeout=120, stream=True)
    response.raise_for_status()
    with destination.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                handle.write(chunk)
    if destination.stat().st_size < 10000:
        raise RuntimeError("Downloaded footage is unexpectedly small.")


def render(source, audio, output, work):
    normalized = work / "normalized-source.mp4"
    run(["ffmpeg", "-y", "-i", str(source), "-t", "55", "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30", "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(normalized)])
    run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(normalized), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-t", "60", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(output)])


def main():
    item = load_item()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mystery-footage-") as temp_dir:
        work = Path(temp_dir)
        source = work / "source.mp4"
        download(item, source)
        print("Footage downloaded; inspecting frames before writing the narration.")
        script = generate_script(item, source, work)
        audio = work / "narration.mp3"
        synthesize_narration(clean(script["narration"]), {"voice": {"provider": "kokoro", "voice_name": os.getenv("MINT_KOKORO_VOICE", "af_heart"), "kokoro_lang": os.getenv("MINT_KOKORO_LANG", "a"), "speed": 1.0}}, str(audio), target_duration=50.0)
        output = OUTPUT_DIR / "mystery-footage-short.mp4"
        render(source, audio, output, work)
    description = f"{script['description_intro']}\n\nSource footage: {item['source_url']}\nLicense: {item.get('license', 'Not specified')}\nAttribution: {item.get('attribution', 'See source page for attribution requirements.')}\n\nThis video adds original narration and editing."
    metadata = {"video_title": script["video_title"], "catalog_item_id": item["id"], "source_url": item["source_url"], "license": item.get("license"), "rights_verified": item.get("rights_verified"), "description": description, "gemini_model": MODEL_NAME, "generated_at": int(time.time())}
    (OUTPUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    if os.getenv("MYSTERY_FOOTAGE_AUTO_UPLOAD", "false").lower() in {"1", "true", "yes"}:
        from upload_youtube import upload_video
        config = {"upload": {"privacy_status": os.getenv("MYSTERY_FOOTAGE_PRIVACY_STATUS", "private"), "category_id": "24"}, "seo": {"hashtags": script["tags"]}}
        metadata["youtube_video_id"] = upload_video(str(output), clean(script["video_title"], 90), description, config, engagement_comment="What do you think this footage shows?")
        (OUTPUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"MYSTERY_FOOTAGE_OUTPUT={output}")


if __name__ == "__main__":
    main()
