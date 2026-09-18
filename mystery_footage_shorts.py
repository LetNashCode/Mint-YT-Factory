"""Create a narrated found-footage mystery Short from a curated case catalog."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from google import genai
from google.genai import types
from tts import synthesize_narration

MODEL_NAME = "gemini-flash-lite-latest"
ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "mystery_footage_catalog.json"
OUTPUT_DIR = ROOT / os.getenv("MYSTERY_FOOTAGE_OUTPUT_DIR", "artifacts/mystery-footage")
TRUE_VALUES = {"1", "true", "yes"}
REQUIRED_CASE_FIELDS = ("id", "title", "case_summary", "verified_facts", "theories_or_open_questions", "footage_description", "source_url", "video_url")


def clean(value, limit=6000):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def run(command):
    print("$", " ".join(map(str, command)))
    subprocess.run(command, check=True)


def normalize_demo_case(item):
    """Repair older auto-discovery records without inventing case facts."""
    if not (str(item.get("id", "")).startswith("youtube-") and os.getenv("MYSTERY_FOOTAGE_ALLOW_UNVERIFIED", "false").lower() in TRUE_VALUES):
        return item
    if not item.get("footage_description"):
        item["footage_description"] = "Downloaded source footage; the video frames must be inspected before narration is written."
    if not isinstance(item.get("verified_facts"), list) or not item["verified_facts"]:
        item["verified_facts"] = ["This is an automatically discovered, unverified demo candidate."]
    if not isinstance(item.get("theories_or_open_questions"), list):
        item["theories_or_open_questions"] = []
    return item


def validate_case(item):
    missing = [field for field in REQUIRED_CASE_FIELDS if not item.get(field)]
    if missing:
        raise RuntimeError(f"Catalog case {item.get('id', '<unknown>')} is missing required fields: {', '.join(missing)}")
    if "REPLACE_ME" in json.dumps(item):
        raise RuntimeError(f"Catalog case {item['id']} still contains a REPLACE_ME placeholder.")
    if not isinstance(item.get("verified_facts"), list) or not item["verified_facts"]:
        raise RuntimeError(f"Catalog case {item['id']} must contain verified facts.")
    if not isinstance(item.get("theories_or_open_questions"), list):
        raise RuntimeError(f"Catalog case {item['id']} must contain theories_or_open_questions.")
    if not item.get("rights_verified") and os.getenv("MYSTERY_FOOTAGE_ALLOW_UNVERIFIED", "false").lower() not in TRUE_VALUES:
        raise RuntimeError(f"Catalog case {item['id']} is not rights-verified; refusing to publish it.")


def load_item():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    allow = os.getenv("MYSTERY_FOOTAGE_ALLOW_UNVERIFIED", "false").lower() in TRUE_VALUES
    eligible = []
    for raw_item in data.get("items", []):
        item = normalize_demo_case(raw_item)
        if not item.get("video_url") or not item.get("source_url") or "REPLACE_ME" in json.dumps(item):
            continue
        if not allow and item.get("rights_verified") is not True:
            continue
        validate_case(item)
        eligible.append(item)
    requested = os.getenv("MYSTERY_FOOTAGE_ITEM_ID", "").strip()
    if requested:
        for item in eligible:
            if item.get("id") == requested:
                return item
        raise RuntimeError(f"No eligible curated case matches MYSTERY_FOOTAGE_ITEM_ID={requested!r}.")
    if eligible:
        return eligible[0]
    raise RuntimeError("No eligible curated found-footage case is available. Automatic discovery may have found a candidate, but it is blocked until verified facts, case-specific downloadable footage, and rights metadata are supplied.")


def parse_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise RuntimeError("Gemini returned invalid JSON.")
        return json.loads(match.group(0))


def inspect_video_frames(source, work):
    directory = work / "analysis-frames"
    directory.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-y", "-i", str(source), "-vf", "fps=1/5,scale=768:-2", "-frames:v", "8", "-q:v", "3", str(directory / "frame-%02d.jpg")])
    return [p.read_bytes() for p in sorted(directory.glob("frame-*.jpg"))]


def generate_script(item, source, work):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required.")
    frames = inspect_video_frames(source, work)
    if not frames:
        raise RuntimeError("Could not extract frames for story grounding.")
    facts = "\n".join(f"- {x}" for x in item["verified_facts"])
    theories = "\n".join(f"- {x}" for x in item["theories_or_open_questions"]) or "- None supplied"
    prompt = f"""Create a respectful documentary-style found-footage mystery Short. Inspect the supplied frames first. Write an original factual 75-110 word English narration with a strong hook, escalating curiosity, and a final question. Do not claim anything not visible. Do not invent facts. Clearly label theories and unresolved questions. Return JSON only with video_title, narration, description_intro, tags. Case: {item['title']}\nSummary: {item['case_summary']}\nFootage: {item['footage_description']}\nVerified facts:\n{facts}\nTheories:\n{theories}\nSource: {item['source_url']}"""
    contents = [prompt] + [types.Part.from_bytes(data=f, mime_type="image/jpeg") for f in frames]
    with genai.Client(api_key=key) as client:
        response = client.models.generate_content(model=MODEL_NAME, contents=contents, config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.3))
    data = parse_json(getattr(response, "text", ""))
    for field in ("video_title", "narration", "description_intro", "tags"):
        if not data.get(field):
            raise RuntimeError(f"Generated script is missing {field!r}.")
    return data


def download(item, destination):
    source_url = item["video_url"]
    host = urlparse(source_url).netloc.lower().split(":", 1)[0]
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}:
        from yt_dlp import YoutubeDL

        download_dir = destination.parent
        template = str(download_dir / "youtube-source.%(ext)s")
        options = {
            "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
            "outtmpl": template,
            "merge_output_format": "mp4",
            "noplaylist": True,
            "restrictfilenames": True,
            "remote_components": "ejs:github",
        }
        with YoutubeDL(options) as downloader:
            downloader.download([source_url])
        candidates = sorted(download_dir.glob("youtube-source.*"))
        if not candidates:
            raise RuntimeError("yt-dlp did not produce a downloadable YouTube video.")
        selected = next((path for path in candidates if path.suffix.lower() == ".mp4"), candidates[0])
        selected.replace(destination)
    else:
        response = requests.get(source_url, timeout=120, stream=True)
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
    try:
        item = load_item()
    except RuntimeError as exc:
        if os.getenv("MYSTERY_FOOTAGE_SKIP_IF_NO_ELIGIBLE", "false").lower() in TRUE_VALUES and "No eligible curated found-footage case" in str(exc):
            print(f"MYSTERY_FOOTAGE_SKIPPED={exc}")
            return
        raise
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mystery-footage-") as temp:
        work = Path(temp)
        source = work / "source.mp4"
        download(item, source)
        script = generate_script(item, source, work)
        audio = work / "narration.mp3"
        synthesize_narration(clean(script["narration"]), {"voice": {"provider": "kokoro", "voice_name": os.getenv("MINT_KOKORO_VOICE", "af_heart"), "kokoro_lang": os.getenv("MINT_KOKORO_LANG", "a"), "speed": 1.0}}, str(audio), target_duration=50.0)
        output = OUTPUT_DIR / "mystery-footage-short.mp4"
        render(source, audio, output, work)
    description = f"{script['description_intro']}\n\nCase: {item['title']}\nSource footage: {item['source_url']}\nLicense: {item.get('license', 'Not specified')}\nAttribution: {item.get('attribution', 'See source page for attribution requirements.')}\n\nThis video adds original narration and editing."
    metadata = {"video_title": script["video_title"], "catalog_item_id": item["id"], "source_url": item["source_url"], "license": item.get("license"), "rights_verified": item.get("rights_verified"), "description": description, "gemini_model": MODEL_NAME, "generated_at": int(time.time())}
    (OUTPUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    if os.getenv("MYSTERY_FOOTAGE_AUTO_UPLOAD", "false").lower() in TRUE_VALUES:
        from upload_youtube import upload_video
        config = {"upload": {"privacy_status": os.getenv("MYSTERY_FOOTAGE_PRIVACY_STATUS", "private"), "category_id": "24"}, "seo": {"hashtags": script["tags"]}}
        metadata["youtube_video_id"] = upload_video(str(output), clean(script["video_title"], 90), description, config, engagement_comment="What detail in this footage stands out to you?")
        (OUTPUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"MYSTERY_FOOTAGE_OUTPUT={output}")


if __name__ == "__main__":
    main()
