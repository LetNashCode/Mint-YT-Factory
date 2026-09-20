"""Build a full-length, source-footage-only mystery documentary.

The source clip remains the visual backbone: it is shown once in order, with
its original audio retained. Gemini creates a detailed narration plan from
sampled frames and supplied case research. The renderer extends the final
frame only when narration runs beyond the source duration; it never inserts
outside visuals.
"""
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

MODEL = "gemini-flash-lite-latest"
ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "mystery_footage_catalog.json"
OUT = ROOT / os.getenv("MYSTERY_DOCUMENTARY_OUTPUT_DIR", "artifacts/mystery-documentary")
TRUE = {"1", "true", "yes"}


def run(args):
    print("$", " ".join(map(str, args)))
    subprocess.run([str(x) for x in args], check=True)


def duration(path):
    result = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], text=True)
    return float(result.strip())


def parse_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    return json.loads(text)


def download(item, path):
    url = item.get("direct_download_url") or item.get("video_url")
    if not url:
        raise RuntimeError("No direct video URL available")
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=180, stream=True)
    response.raise_for_status()
    if "text/html" in response.headers.get("content-type", "").lower():
        raise RuntimeError("Video URL returned HTML")
    with path.open("wb") as handle:
        for chunk in response.iter_content(1024 * 1024):
            if chunk:
                handle.write(chunk)
    if path.stat().st_size < 10000:
        raise RuntimeError("Downloaded video is too small")


def frames(source, work):
    frame_dir = work / "frames"
    frame_dir.mkdir()
    run(["ffmpeg", "-y", "-i", source, "-vf", "fps=1/8,scale=960:-2", "-frames:v", "24", "-q:v", "3", frame_dir / "frame-%03d.jpg"])
    return sorted(frame_dir.glob("*.jpg"))


def make_script(item, source, work):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required")
    images = frames(source, work)
    facts = "\n".join(f"- {x}" for x in item.get("verified_facts", []))
    theories = "\n".join(f"- {x}" for x in item.get("theories_or_open_questions", []))
    prompt = f"""Create a detailed, entertaining full-length mystery documentary narration based ONLY on the supplied source footage and the case information below. Do not invent details. The documentary must explain the footage in sequence, explicitly describe what viewers are seeing, identify quiet or uneventful sections, and propose multiple clearly labeled theories while separating confirmed facts, visible observations, reported claims, and speculation. Use this structure: cold open, orientation, chronological walkthrough of the complete footage, pauses/replays to explain important moments, context and timeline, audio/visual clues, theories with evidence for and against, limitations, and conclusion. There is no word or duration limit; write as much as necessary for a complete explanation. Return JSON with: video_title, narration, description_intro, tags, highlighted_keywords. highlighted_keywords must be a list of important words or short phrases for caption emphasis.
CASE TITLE: {item.get('title')}
CASE SUMMARY: {item.get('case_summary')}
FOOTAGE DESCRIPTION: {item.get('footage_description')}
VERIFIED FACTS:\n{facts}
OPEN QUESTIONS/THEORIES:\n{theories}"""
    contents = [prompt] + [types.Part.from_bytes(data=p.read_bytes(), mime_type="image/jpeg") for p in images]
    with genai.Client(api_key=key) as client:
        response = client.models.generate_content(model=MODEL, contents=contents, config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.35))
    result = parse_json(response.text)
    for field in ("video_title", "narration", "description_intro", "tags"):
        if not result.get(field):
            raise RuntimeError(f"Missing generated field: {field}")
    return result


def render(source, narration_audio, output, work):
    source_duration = duration(source)
    narration_duration = duration(narration_audio)
    total = max(source_duration, narration_duration)
    prepared = work / "prepared-source.mp4"
    # Preserve the entire source in order. If narration is longer, hold the
    # final frame rather than inserting unrelated visuals or looping footage.
    run(["ffmpeg", "-y", "-i", source, "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,tpad=stop_mode=clone:stop_duration=" + str(max(0, total - source_duration)), "-an", "-t", str(total), "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", prepared])
    # Keep original audio audible while narration plays. The original track is
    # gently reduced rather than removed; narration is mixed over it.
    run(["ffmpeg", "-y", "-i", prepared, "-i", source, "-i", narration_audio, "-filter_complex", "[1:a]volume=0.38[original];[2:a]volume=1.0[voice];[original][voice]amix=inputs=2:duration=longest:dropout_transition=2[a]", "-map", "0:v:0", "-map", "[a]", "-t", str(total), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", output])


def main():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    candidates = [x for x in data.get("items", []) if x.get("video_url") and x.get("source_url") and (x.get("screening") or {}).get("eligible") is True]
    requested = os.getenv("MYSTERY_FOOTAGE_ITEM_ID", "").strip()
    if requested:
        candidates = [x for x in candidates if x.get("id") == requested]
    if not candidates:
        if os.getenv("MYSTERY_FOOTAGE_SKIP_IF_NO_ELIGIBLE", "false").lower() in TRUE:
            print("MYSTERY_DOCUMENTARY_SKIPPED=no eligible case")
            return
        raise RuntimeError("No eligible mystery documentary case")
    OUT.mkdir(parents=True, exist_ok=True)
    item = candidates[0]
    with tempfile.TemporaryDirectory(prefix="mystery-documentary-") as temp:
        work = Path(temp)
        source = work / "source.mp4"
        download(item, source)
        script = make_script(item, source, work)
        narration_audio = work / "narration.mp3"
        synthesize_narration(script["narration"], {"voice": {"provider": "kokoro", "voice_name": os.getenv("MINT_KOKORO_VOICE", "am_michael"), "kokoro_lang": os.getenv("MINT_KOKORO_LANG", "a"), "speed": 1.0}}, str(narration_audio))
        output = OUT / "mystery-documentary.mp4"
        render(source, narration_audio, output, work)
    metadata = {"video_title": script["video_title"], "description": script["description_intro"] + "\n\nCase: " + item["title"] + "\nSource footage: " + item["source_url"], "tags": script["tags"], "highlighted_keywords": script.get("highlighted_keywords", []), "catalog_item_id": item["id"], "source_url": item["source_url"], "generated_at": int(time.time())}
    (OUT / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    if os.getenv("MYSTERY_FOOTAGE_AUTO_UPLOAD", "false").lower() in TRUE:
        from upload_youtube import upload_video
        config = {"upload": {"privacy_status": os.getenv("MYSTERY_FOOTAGE_PRIVACY_STATUS", "private"), "category_id": "24"}, "seo": {"hashtags": script["tags"]}}
        metadata["youtube_video_id"] = upload_video(str(output), script["video_title"][:90], metadata["description"], config)
        (OUT / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"MYSTERY_DOCUMENTARY_OUTPUT={output}")


if __name__ == "__main__":
    main()
