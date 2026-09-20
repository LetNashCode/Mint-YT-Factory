"""Build a full-length, landscape mystery documentary from approved source footage."""
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
from mystery_audio_analysis import analyze_audio
from mystery_narration_timing import build_timed_narration
from tts import synthesize_narration

MODEL = "gemini-flash-lite-latest"
ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "mystery_footage_catalog.json"
OUT = ROOT / os.getenv("MYSTERY_DOCUMENTARY_OUTPUT_DIR", "artifacts/mystery-documentary")
TRUE = {"1", "true", "yes"}
MIN_SOURCE_SECONDS = float(os.getenv("MYSTERY_FOOTAGE_MIN_SOURCE_SECONDS", "90"))


def run(args):
    print("$", " ".join(map(str, args)))
    subprocess.run([str(x) for x in args], check=True)


def probe(path):
    result = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,codec_type", "-of", "json", str(path)], text=True)
    data = json.loads(result)
    duration = float((data.get("format") or {}).get("duration") or 0)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    return duration, int(video.get("width") or 0), int(video.get("height") or 0)


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


def make_script(item, source, work, audio_timeline):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required")
    images = frames(source, work)
    facts = "\n".join(f"- {x}" for x in item.get("verified_facts", []))
    theories = "\n".join(f"- {x}" for x in item.get("theories_or_open_questions", []))
    transcript = audio_timeline.get("transcript", "") or "[No speech detected]"
    protected = json.dumps(audio_timeline.get("protected_intervals", []), ensure_ascii=False)
    prompt = f"""Create a detailed mystery documentary narration based ONLY on the supplied source footage and case information. Do not invent details. Explain the footage in sequence and separate visible observations, verified facts, reported claims, theories, and unknowns.

The original audio contains timestamped speech. Do not narrate over protected intervals. Write short, self-contained sentences because each sentence will be placed independently into available silent windows. Do not include production directions in the narration.

WHISPER TRANSCRIPT:\n{transcript}\n\nPROTECTED SPEECH INTERVALS:\n{protected}

Use: cold open, orientation, chronological walkthrough, important-moment explanations, context, clues, theories with evidence for and against, limitations, and conclusion. Return JSON with video_title, narration, description_intro, tags, highlighted_keywords.
CASE TITLE: {item.get('title')}\nCASE SUMMARY: {item.get('case_summary')}\nFOOTAGE DESCRIPTION: {item.get('footage_description')}\nVERIFIED FACTS:\n{facts}\nOPEN QUESTIONS/THEORIES:\n{theories}"""
    contents = [prompt] + [types.Part.from_bytes(data=p.read_bytes(), mime_type="image/jpeg") for p in images]
    with genai.Client(api_key=key) as client:
        response = client.models.generate_content(model=MODEL, contents=contents, config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.35))
    result = parse_json(response.text)
    for field in ("video_title", "narration", "description_intro", "tags"):
        if not result.get(field):
            raise RuntimeError(f"Missing generated field: {field}")
    return result


def _ffmpeg_volume_expression(intervals, inside_value, outside_value):
    if not intervals:
        return str(outside_value)
    clauses = []
    for interval in intervals:
        start = max(0.0, float(interval.get("start", 0.0)))
        end = max(start, float(interval.get("end", start)))
        clauses.append(f"between(t,{start:.3f},{end:.3f})")
    return f"if({'+'.join(clauses)},{inside_value},{outside_value})"


def render(source, narration_audio, output, work, audio_timeline):
    source_duration, _, _ = probe(source)
    protected = audio_timeline.get("protected_intervals", [])
    prepared = work / "prepared-source.mp4"
    run(["ffmpeg", "-y", "-i", source, "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,fps=30", "-t", str(source_duration), "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", prepared])
    original_expr = _ffmpeg_volume_expression(protected, "1.0", "0.08")
    voice_expr = _ffmpeg_volume_expression(protected, "0.0", "1.0")
    filters = f"[1:a]volume='{original_expr}':eval=frame[original];[2:a]volume='{voice_expr}':eval=frame[voice];[original][voice]amix=inputs=2:duration=longest:dropout_transition=2[a]"
    run(["ffmpeg", "-y", "-i", prepared, "-i", source, "-i", narration_audio, "-filter_complex", filters, "-map", "0:v:0", "-map", "[a]", "-t", str(source_duration), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", output])


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
        duration, width, height = probe(source)
        if duration < MIN_SOURCE_SECONDS:
            raise RuntimeError(f"Rejected short-form source footage: {duration:.1f}s; minimum is {MIN_SOURCE_SECONDS:.1f}s")
        if width and height and height > width:
            raise RuntimeError(f"Rejected portrait source footage: {width}x{height}")
        audio_timeline = analyze_audio(source, work)
        (OUT / "audio_timeline.json").write_text(json.dumps(audio_timeline, indent=2, ensure_ascii=False), encoding="utf-8")
        script = make_script(item, source, work, audio_timeline)
        voice_config = {"voice": {"provider": "kokoro", "voice_name": os.getenv("MINT_KOKORO_VOICE", "am_michael"), "kokoro_lang": os.getenv("MINT_KOKORO_LANG", "a"), "speed": 1.0}}
        def tts(text, destination):
            synthesize_narration(text, voice_config, destination)
        timed_narration, placements = build_timed_narration(script["narration"], duration, audio_timeline.get("protected_intervals", []), work, tts, voice_config)
        output = OUT / "mystery-documentary.mp4"
        render(source, timed_narration, output, work, audio_timeline)
    metadata = {"video_title": script["video_title"], "description": script["description_intro"] + "\n\nCase: " + item["title"] + "\nSource footage: " + item["source_url"], "tags": script["tags"], "highlighted_keywords": script.get("highlighted_keywords", []), "catalog_item_id": item["id"], "source_url": item["source_url"], "protected_audio_intervals": audio_timeline.get("protected_intervals", []), "narration_placements": placements, "generated_at": int(time.time())}
    if os.getenv("MYSTERY_FOOTAGE_AUTO_UPLOAD", "false").lower() in TRUE:
        from upload_youtube import upload_video
        config = {"upload": {"privacy_status": os.getenv("MYSTERY_FOOTAGE_PRIVACY_STATUS", "private"), "category_id": "24"}, "seo": {"hashtags": script["tags"]}}
        metadata["youtube_video_id"] = upload_video(str(output), script["video_title"][:90], metadata["description"], config)
    (OUT / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"MYSTERY_DOCUMENTARY_OUTPUT={output}")


if __name__ == "__main__":
    main()
