"""Create a narrated mystery video while preserving the complete source frame."""
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
HISTORY_FILE = ROOT / "mystery_footage_history.json"
TRUE_VALUES = {"1", "true", "yes"}
REQUIRED_CASE_FIELDS = ("id", "title", "case_summary", "verified_facts", "theories_or_open_questions", "footage_description", "source_url", "video_url")


def clean(value, limit=6000):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def run(command):
    print("$", " ".join(map(str, command)))
    subprocess.run(command, check=True)


def validate_case(item):
    missing = [f for f in REQUIRED_CASE_FIELDS if f not in item or item[f] is None or (not isinstance(item[f], list) and not item[f])]
    if missing:
        raise RuntimeError(f"Catalog case {item.get('id', '<unknown>')} is missing: {', '.join(missing)}")
    if "REPLACE_ME" in json.dumps(item):
        raise RuntimeError(f"Catalog case {item['id']} contains REPLACE_ME.")
    if not isinstance(item.get("verified_facts"), list) or not item["verified_facts"]:
        raise RuntimeError(f"Catalog case {item['id']} has no verified facts.")
    if not isinstance(item.get("theories_or_open_questions"), list):
        raise RuntimeError(f"Catalog case {item['id']} has invalid theories_or_open_questions.")


def load_history():
    if not HISTORY_FILE.exists():
        return {"version": 1, "used": []}
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"version": 1, "used": []}
    except json.JSONDecodeError:
        return {"version": 1, "used": []}


def save_history(history):
    HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")


def source_key(item):
    return clean(item.get("direct_download_url") or item.get("video_url") or item.get("source_url"), 2000)


def load_items():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    require_screening = os.getenv("MYSTERY_FOOTAGE_REQUIRE_STORY_SCREEN", "true").lower() in TRUE_VALUES
    history = load_history()
    used = {str(x.get("source_key")) for x in history.get("used", []) if isinstance(x, dict)}
    eligible = []
    for item in data.get("items", []):
        if not item.get("video_url") or not item.get("source_url") or "REPLACE_ME" in json.dumps(item):
            continue
        if require_screening and (item.get("screening") or {}).get("eligible") is not True:
            continue
        validate_case(item)
        if source_key(item) in used:
            print(f"Skipping previously used footage: {item.get('id')}")
            continue
        eligible.append(item)
    requested = os.getenv("MYSTERY_FOOTAGE_ITEM_ID", "").strip()
    if requested:
        eligible = [x for x in eligible if x.get("id") == requested]
    return eligible


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
        raise RuntimeError("No frames extracted.")
    facts = "\n".join(f"- {x}" for x in item["verified_facts"])
    theories = "\n".join(f"- {x}" for x in item["theories_or_open_questions"]) or "- None supplied"
    prompt = f"""Create a respectful documentary-style mystery video narration. Inspect the supplied frames first. Write an original factual 75-110 word English narration with a strong hook, escalating curiosity, and a final question. Do not invent facts or claim anything not visible. Clearly label theories and unresolved questions. Return JSON only with video_title, narration, description_intro, tags. Case: {item['title']}\nSummary: {item['case_summary']}\nFootage: {item['footage_description']}\nVerified facts:\n{facts}\nTheories:\n{theories}"""
    contents = [prompt] + [types.Part.from_bytes(data=f, mime_type="image/jpeg") for f in frames]
    with genai.Client(api_key=key) as client:
        response = client.models.generate_content(model=MODEL_NAME, contents=contents, config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.3))
    result = parse_json(getattr(response, "text", ""))
    for field in ("video_title", "narration", "description_intro", "tags"):
        if not result.get(field):
            raise RuntimeError(f"Generated script is missing {field}.")
    return result


def download(item, destination):
    source_url = item.get("direct_download_url") or item.get("video_url")
    if not source_url:
        raise RuntimeError("Candidate has no downloadable source URL.")
    host = urlparse(source_url).netloc.lower().split(":", 1)[0]
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}:
        raise RuntimeError("YouTube footage is disabled.")
    response = requests.get(source_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=120, stream=True)
    response.raise_for_status()
    if "text/html" in response.headers.get("content-type", "").lower():
        raise RuntimeError("Source URL returned HTML instead of media.")
    with destination.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                handle.write(chunk)
    if not destination.exists() or destination.stat().st_size < 10000:
        raise RuntimeError("Downloaded footage is unexpectedly small.")


def render(source, audio, output, work):
    # Keep the entire source video visible. No center crop and no forced portrait conversion.
    normalized = work / "normalized-source.mp4"
    run(["ffmpeg", "-y", "-i", str(source), "-t", "55", "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30", "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(normalized)])
    run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(normalized), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-t", "60", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(output)])


def record_used(item, script, output):
    history = load_history()
    history.setdefault("used", []).append({"catalog_item_id": item.get("id"), "source_key": source_key(item), "source_url": item.get("source_url"), "video_title": script.get("video_title"), "output": str(output), "used_at": int(time.time())})
    save_history(history)


def main():
    items = load_items()
    if not items:
        message = "No unused eligible curated found-footage case is available."
        if os.getenv("MYSTERY_FOOTAGE_SKIP_IF_NO_ELIGIBLE", "false").lower() in TRUE_VALUES:
            print(f"MYSTERY_FOOTAGE_SKIPPED={message}")
            return
        raise RuntimeError(message)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    last_error = None
    for index, item in enumerate(items, start=1):
        print(f"Trying mystery footage candidate {index}/{len(items)}: {item.get('id')}")
        try:
            with tempfile.TemporaryDirectory(prefix="mystery-footage-") as temp:
                work = Path(temp)
                source = work / "source.mp4"
                download(item, source)
                script = generate_script(item, source, work)
                audio = work / "narration.mp3"
                synthesize_narration(clean(script["narration"]), {"voice": {"provider": "kokoro", "voice_name": os.getenv("MINT_KOKORO_VOICE", "af_heart"), "kokoro_lang": os.getenv("MINT_KOKORO_LANG", "a"), "speed": 1.0}}, str(audio), target_duration=50.0)
                output = OUTPUT_DIR / "mystery-footage-short.mp4"
                render(source, audio, output, work)
            description = f"{script['description_intro']}\n\nCase: {item['title']}\nSource footage: {item['source_url']}\n\nThis video adds original narration and editing."
            metadata = {"video_title": script["video_title"], "catalog_item_id": item["id"], "source_url": item["source_url"], "description": description, "gemini_model": MODEL_NAME, "generated_at": int(time.time())}
            (OUTPUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
            record_used(item, script, output)
            if os.getenv("MYSTERY_FOOTAGE_AUTO_UPLOAD", "false").lower() in TRUE_VALUES:
                from upload_youtube import upload_video
                config = {"upload": {"privacy_status": os.getenv("MYSTERY_FOOTAGE_PRIVACY_STATUS", "private"), "category_id": "24"}, "seo": {"hashtags": script["tags"]}}
                metadata["youtube_video_id"] = upload_video(str(output), clean(script["video_title"], 90), description, config, engagement_comment="What detail in this footage stands out to you?")
                (OUTPUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"MYSTERY_FOOTAGE_OUTPUT={output}")
            return
        except Exception as exc:
            last_error = exc
            print(f"Candidate {item.get('id')} failed: {type(exc).__name__}: {exc}")
            print("Trying the next eligible candidate.")
    raise RuntimeError(f"All eligible mystery footage candidates failed. Last error: {last_error}")


if __name__ == "__main__":
    main()
