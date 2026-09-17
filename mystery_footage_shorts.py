"""Create a narrated mystery-footage Short from a catalog item.

Rights verification is intentionally configurable during development. Before
real production use, populate the catalog with a real footage item and review
its usage terms.
"""
from __future__ import annotations
import json, os, re, subprocess, tempfile, time
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
    eligible = [
        x for x in data.get("items", [])
        if x.get("video_url") and x.get("source_url")
        and (allow_unverified or x.get("rights_verified") is True)
        and "REPLACE_ME" not in str(x.get("video_url"))
        and "REPLACE_ME" not in str(x.get("source_url"))
    ]
    if not eligible:
        raise RuntimeError(
            "No usable catalog item is available. Add a real item to "
            "mystery_footage_catalog.json with source_url and video_url."
        )
    requested = os.getenv("MYSTERY_FOOTAGE_ITEM_ID", "").strip()
    if requested:
        for item in eligible:
            if item.get("id") == requested:
                return item
        raise RuntimeError(f"No eligible catalog item matches MYSTERY_FOOTAGE_ITEM_ID={requested!r}.")
    return eligible[0]


def parse_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise RuntimeError("Gemini returned invalid JSON.")
        return json.loads(match.group(0))


def generate_script(item):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required.")
    prompt = f"""Create an original, factual, 75-110 word English YouTube Shorts narration about this documented mystery-footage item. Clearly distinguish verified facts from allegations and theories. Do not present paranormal claims as fact. Do not invent dates, locations, identities, or evidence. Start with a strong hook and end with a question. Return JSON only with video_title, narration, description_intro, tags.\nItem title: {item.get('title')}\nTopic: {item.get('topic')}\nSource notes: {item.get('rights_notes')}"""
    response = genai.Client(api_key=key).models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.55),
    )
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


def render(script, source, audio, output, work):
    normalized = work / "source.mp4"
    run(["ffmpeg", "-y", "-i", str(source), "-t", "55", "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30", "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(normalized)])
    run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(normalized), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-t", "60", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(output)])


def main():
    item = load_item()
    script = generate_script(item)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mystery-footage-") as temp_dir:
        work = Path(temp_dir)
        source = work / "source.mp4"
        download(item, source)
        audio = work / "narration.mp3"
        synthesize_narration(clean(script["narration"]), {"voice": {"provider": "kokoro", "voice_name": os.getenv("MINT_KOKORO_VOICE", "af_heart"), "kokoro_lang": os.getenv("MINT_KOKORO_LANG", "a"), "speed": 1.0}}, str(audio), target_duration=50.0)
        output = OUTPUT_DIR / "mystery-footage-short.mp4"
        render(script, source, audio, output, work)
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
