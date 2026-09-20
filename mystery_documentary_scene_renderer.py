"""Scene-aware Mystery Documentary renderer.

Gemini creates a timeline; narration is synthesized only for narration/pause/replay
segments. Original segments retain source audio, preventing narration from covering
meaningful speech. The timeline is saved for auditability.
"""
from __future__ import annotations
import json, os, re, subprocess, tempfile, time
from pathlib import Path
import requests
from google import genai
from google.genai import types
from tts import synthesize_narration

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "mystery_footage_catalog.json"
OUT = ROOT / os.getenv("MYSTERY_DOCUMENTARY_OUTPUT_DIR", "artifacts/mystery-documentary")
MODEL = "gemini-flash-lite-latest"
VOICE = {"voice": {"provider": "kokoro", "voice_name": os.getenv("MINT_KOKORO_VOICE", "am_michael"), "kokoro_lang": os.getenv("MINT_KOKORO_LANG", "a"), "speed": 1.0}}


def cmd(args):
    print("$", " ".join(map(str, args)))
    subprocess.run([str(x) for x in args], check=True)


def probe(path):
    raw = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,codec_type", "-of", "json", str(path)], text=True)
    d = json.loads(raw)
    v = next((x for x in d.get("streams", []) if x.get("codec_type") == "video"), {})
    return float((d.get("format") or {}).get("duration") or 0), int(v.get("width") or 0), int(v.get("height") or 0)


def download(item, target):
    url = item.get("direct_download_url") or item.get("video_url")
    if not url:
        raise RuntimeError("No video URL")
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=180, stream=True)
    r.raise_for_status()
    if "text/html" in r.headers.get("content-type", "").lower():
        raise RuntimeError("Video URL returned HTML")
    with target.open("wb") as f:
        for chunk in r.iter_content(1024 * 1024):
            if chunk:
                f.write(chunk)


def parse_json(text):
    return json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I))


def plan(item, source, work, duration):
    frames = work / "frames"
    frames.mkdir()
    cmd(["ffmpeg", "-y", "-i", source, "-vf", "fps=1/8,scale=960:-2", "-frames:v", "30", "-q:v", "3", frames / "frame-%03d.jpg"])
    prompt = f"""Create an evidence-led editing timeline for this real-world mystery video. Duration: {duration:.2f} seconds. Return JSON with video_title, description_intro, tags, highlighted_keywords, and scene_plan. scene_plan must cover 0 to {duration:.2f} with no gaps or overlaps. Each scene: start, end, audio_mode, narration, purpose, evidence_label. audio_mode must be original, narration, pause, or replay. Use original whenever anyone may be speaking or meaningful source audio may exist; never put narration over original speech. Use narration only for clearly visual/silent explanation. Use pause for a critical moment that should freeze while it is explained. Use replay only for a short critical moment. Keep narration empty for original scenes. Do not infer guilt from body language or nervousness. Separate observations, verified facts, reported claims, theories, and limitations. Do not invent events. CASE TITLE: {item.get('title')} CASE SUMMARY: {item.get('case_summary')} FOOTAGE DESCRIPTION: {item.get('footage_description')} VERIFIED FACTS: {item.get('verified_facts', [])} OPEN QUESTIONS: {item.get('theories_or_open_questions', [])}"""
    parts = [prompt] + [types.Part.from_bytes(data=p.read_bytes(), mime_type="image/jpeg") for p in sorted(frames.glob("*.jpg"))]
    with genai.Client(api_key=os.environ["GEMINI_API_KEY"]) as client:
        result = client.models.generate_content(model=MODEL, contents=parts, config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2))
    data = parse_json(result.text)
    raw_scenes = data.get("scene_plan")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise RuntimeError("No scene plan returned")
    scenes = []
    cursor = 0.0
    for s in raw_scenes:
        start = max(cursor, float(s.get("start", cursor)))
        end = min(duration, float(s.get("end", start)))
        if end <= start:
            continue
        mode = str(s.get("audio_mode", "original")).lower()
        if mode not in {"original", "narration", "pause", "replay"}:
            mode = "original"
        scenes.append({"start": round(start, 3), "end": round(end, 3), "audio_mode": mode, "narration": str(s.get("narration", "")).strip(), "purpose": str(s.get("purpose", "")), "evidence_label": str(s.get("evidence_label", "observation"))})
        cursor = end
    if cursor < duration - 0.05:
        scenes.append({"start": round(cursor, 3), "end": round(duration, 3), "audio_mode": "original", "narration": "", "purpose": "Preserve uncovered footage", "evidence_label": "observation"})
    data["scene_plan"] = scenes
    return data


def render_scene(source, s, narration, out, work):
    start, end = s["start"], s["end"]
    length = max(0.1, end - start)
    mode = s["audio_mode"]
    video = work / (out.stem + ".video.mp4")
    vf = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,fps=30"
    if mode == "pause":
        vf += ",select='eq(n,0)',tpad=stop_mode=clone:stop_duration=" + str(length)
    cmd(["ffmpeg", "-y", "-ss", str(start), "-i", source, "-t", str(length), "-vf", vf, "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", video])
    if mode == "original":
        cmd(["ffmpeg", "-y", "-i", video, "-ss", str(start), "-i", source, "-t", str(length), "-map", "0:v:0", "-map", "1:a?", "-c:v", "copy", "-c:a", "aac", "-shortest", out])
    elif narration:
        cmd(["ffmpeg", "-y", "-i", video, "-i", narration, "-filter_complex", "[1:a]apad[a]", "-map", "0:v:0", "-map", "[a]", "-t", str(length), "-c:v", "copy", "-c:a", "aac", out])
    else:
        cmd(["ffmpeg", "-y", "-i", video, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", str(length), "-c:v", "copy", "-c:a", "aac", out])
    video.unlink(missing_ok=True)


def _skip_if_configured(message):
    if os.getenv("MYSTERY_FOOTAGE_SKIP_IF_NO_ELIGIBLE", "false").lower() in {"1", "true", "yes"}:
        print(message)
        return True
    return False


def main():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    requested = os.getenv("MYSTERY_FOOTAGE_ITEM_ID", "").strip()
    min_duration = float(os.getenv("MYSTERY_FOOTAGE_MIN_SOURCE_SECONDS", "90"))
    candidates = [x for x in data.get("items", []) if x.get("video_url") and x.get("source_url") and (x.get("screening") or {}).get("eligible") is True]
    if requested:
        candidates = [x for x in candidates if str(x.get("id")) == requested]
    if not candidates:
        if _skip_if_configured("MYSTERY_DOCUMENTARY_SKIPPED=no eligible case"):
            return
        raise RuntimeError("No eligible case")

    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mystery-scenes-") as td:
        work = Path(td)
        item = None
        source = None
        duration = 0.0
        width = height = 0

        # Validate every candidate's actual media before committing to a case.
        # Short or portrait footage is skipped rather than crashing the workflow.
        for index, candidate in enumerate(candidates):
            candidate_source = work / f"source-{index}.media"
            try:
                print(f"🔎 Checking mystery footage: {candidate.get('title', candidate.get('id', 'unknown'))}")
                download(candidate, candidate_source)
                candidate_duration, candidate_width, candidate_height = probe(candidate_source)
                if candidate_duration < min_duration:
                    print(f"   ⏭️ Skipping: source is {candidate_duration:.2f}s; minimum is {min_duration:.2f}s")
                    candidate_source.unlink(missing_ok=True)
                    continue
                if candidate_height > candidate_width:
                    print(f"   ⏭️ Skipping: portrait source {candidate_width}x{candidate_height}")
                    candidate_source.unlink(missing_ok=True)
                    continue
                item = candidate
                source = candidate_source
                duration, width, height = candidate_duration, candidate_width, candidate_height
                print(f"✅ Selected mystery footage: {duration:.2f}s, {width}x{height}")
                break
            except Exception as exc:
                print(f"   ⏭️ Skipping unusable candidate: {exc}")
                candidate_source.unlink(missing_ok=True)

        if item is None or source is None:
            if _skip_if_configured("MYSTERY_DOCUMENTARY_SKIPPED=no suitable source footage"):
                return
            raise RuntimeError("No eligible mystery footage met the duration/orientation requirements")

        timeline = plan(item, source, work, duration)
        (OUT / "timeline.json").write_text(json.dumps(timeline, indent=2, ensure_ascii=False), encoding="utf-8")
        parts = []
        for i, scene in enumerate(timeline["scene_plan"]):
            audio = None
            if scene["audio_mode"] in {"narration", "pause", "replay"} and scene["narration"]:
                audio = work / f"narration-{i:03d}.mp3"
                synthesize_narration(scene["narration"], VOICE, str(audio), target_duration=max(1, scene["end"] - scene["start"]))
            part = work / f"part-{i:03d}.mp4"
            render_scene(str(source), scene, str(audio) if audio else None, part, work)
            parts.append(part)
        listing = work / "concat.txt"
        listing.write_text("\n".join("file '" + p.as_posix() + "'" for p in parts) + "\n", encoding="utf-8")
        output = OUT / "mystery-documentary.mp4"
        cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", output])

    meta = {"video_title": timeline.get("video_title", item.get("title", "Mystery Documentary")), "description": timeline.get("description_intro", "") + "\n\nSource footage: " + item.get("source_url", ""), "tags": timeline.get("tags", []), "highlighted_keywords": timeline.get("highlighted_keywords", []), "catalog_item_id": item.get("id"), "source_url": item.get("source_url"), "generated_at": int(time.time())}
    (OUT / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"MYSTERY_DOCUMENTARY_OUTPUT={output}")


if __name__ == "__main__":
    main()
