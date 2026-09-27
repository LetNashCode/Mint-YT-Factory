"""Scene-aware Mystery Documentary renderer.

Gemini creates an evidence-led timeline with narration plus restrained zoom, pause,
and replay directions. Narration is synthesized for narration/pause/replay segments. Original segments retain source audio, preventing narration from covering
meaningful speech. The timeline is saved for auditability.
"""
from __future__ import annotations
import json, os, re, subprocess, tempfile, time
from pathlib import Path
import requests
from google import genai
from google.genai import types
from tts import synthesize_narration
from mystery_audio_analysis import analyze_audio

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "mystery_footage_catalog.json"
OUT = ROOT / os.getenv("MYSTERY_DOCUMENTARY_OUTPUT_DIR", "artifacts/mystery-documentary")
MODEL = "gemini-flash-lite-latest"
VOICE = {"voice": {"provider": "kokoro", "voice_name": os.getenv("MINT_KOKORO_VOICE", "am_michael"), "kokoro_lang": os.getenv("MINT_KOKORO_LANG", "a"), "speed": 1.0}}
MIN_NARRATION_RATIO = float(os.getenv("MYSTERY_MIN_NARRATION_RATIO", "0.28"))
MIN_NARRATION_WORDS = int(os.getenv("MYSTERY_MIN_NARRATION_WORDS", "120"))
MIN_NARRATION_SCENES = int(os.getenv("MYSTERY_MIN_NARRATION_SCENES", "4"))
MAX_ZOOM = float(os.getenv("MYSTERY_MAX_ZOOM", "1.18"))


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


def plan(item, source, work, duration, audio_analysis):
    frames = work / "frames"
    frames.mkdir()
    cmd(["ffmpeg", "-y", "-i", source, "-vf", "fps=1/8,scale=960:-2", "-frames:v", "30", "-q:v", "3", frames / "frame-%03d.jpg"])
    factory_learning = os.getenv("MINT_FACTORY_LEARNING_CONTEXT", "").strip()
    factory_strategy = os.getenv("MINT_FACTORY_CREATIVE_STRATEGY", "").strip()
    protected_speech = audio_analysis.get("protected_intervals", []) if isinstance(audio_analysis, dict) else []
    source_transcript = audio_analysis.get("transcript", "") if isinstance(audio_analysis, dict) else ""
    prompt = f"""Create an evidence-led commentary documentary timeline for this real-world mystery video. Duration: {duration:.2f} seconds. Return JSON with video_title, description_intro, tags, highlighted_keywords, and scene_plan. scene_plan must cover 0 to {duration:.2f} with no gaps or overlaps. Each scene: start, end, audio_mode, narration, purpose, evidence_label. Add commentary_role (hook, setup, explanation, evidence, replay, theory, conclusion). Add visual_effect (normal, zoom_in, zoom_out, pause, or replay), zoom_strength, zoom_target_x, zoom_target_y, and effect_reason. audio_mode must be original, narration, pause, or replay. Use original audio ONLY inside or immediately around the supplied protected source-speech intervals. Outside those intervals, generated narration should carry the soundtrack. Narration is the primary storytelling layer and should cover at least 65% of the finished edit. Original-audio scenes should normally stay below 25% of the finished edit. There must be at least 4 narration-bearing scenes whenever the footage is long enough. Use original only when source speech or a genuinely important original sound is the point of the scene. Do not let original-audio scenes consume the entire timeline. Use pause/replay for critical evidence. Include at least one pause and one replay when the footage contains a clear moment worth explaining twice. Include at least two restrained zoom moments when there are visible details worth pointing out. Every narration scene must contain enough narration to naturally fill its planned duration at conversational speed. Target roughly 2.0-2.5 spoken words per second of narration scene, and never leave a narration scene empty. Do not infer guilt from body language or nervousness. Separate observations, verified facts, reported claims, theories, and limitations. Do not invent events. CASE TITLE: {item.get('title')} CASE SUMMARY: {item.get('case_summary')} FOOTAGE DESCRIPTION: {item.get('footage_description')} VERIFIED FACTS: {item.get('verified_facts', [])} OPEN QUESTIONS: {item.get('theories_or_open_questions', [])}

FACTORY-WIDE SELF-LEARNING CONTEXT:
{factory_learning}

CURRENT FACTORY CREATIVE EXPERIMENT:
{factory_strategy}

PROTECTED SOURCE-SPEECH INTERVALS (Whisper): {protected_speech}\nSOURCE AUDIO TRANSCRIPT: {source_transcript}\n\nUse learning only to improve structure, pacing, evidence presentation, and viewer clarity. Never copy a prior case, claim, wording, or conclusion."""
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
        effect = str(s.get("visual_effect", "normal")).lower()
        if effect not in {"normal", "zoom_in", "zoom_out", "pause", "replay"}:
            effect = "normal"
        if mode == "pause":
            effect = "pause"
        elif mode == "replay":
            effect = "replay"
        zoom_strength = min(MAX_ZOOM, max(1.0, float(s.get("zoom_strength", 1.10))))
        target_x = min(1.0, max(0.0, float(s.get("zoom_target_x", 0.5))))
        target_y = min(1.0, max(0.0, float(s.get("zoom_target_y", 0.5))))
        if effect not in {"zoom_in", "zoom_out"}:
            zoom_strength = 1.0
        scenes.append({
            "start": round(start, 3), "end": round(end, 3), "audio_mode": mode,
            "commentary_role": str(s.get("commentary_role", "explanation")).strip() or "explanation",
            "narration": str(s.get("narration", "")).strip(),
            "purpose": str(s.get("purpose", "")),
            "evidence_label": str(s.get("evidence_label", "observation")),
            "visual_effect": effect,
            "zoom_strength": round(zoom_strength, 3),
            "zoom_target_x": round(target_x, 3),
            "zoom_target_y": round(target_y, 3),
            "effect_reason": str(s.get("effect_reason", "")).strip(),
        })
        cursor = end
    if cursor < duration - 0.05:
        scenes.append({"start": round(cursor, 3), "end": round(duration, 3), "audio_mode": "original", "narration": "", "purpose": "Preserve uncovered footage", "evidence_label": "observation", "visual_effect": "normal", "zoom_strength": 1.0, "zoom_target_x": 0.5, "zoom_target_y": 0.5, "effect_reason": ""})
    data["scene_plan"] = scenes

    # Guarantee that the new documentary-editing layer is actually exercised.
    # Prefer Gemini-selected evidence moments, but provide deterministic fallbacks
    # when it returns an otherwise valid narration-only plan.
    narration_candidates = [s for s in scenes if s.get("narration") and s["audio_mode"] in {"narration", "pause", "replay"}]
    if narration_candidates:
        if not any(s.get("visual_effect") == "pause" for s in narration_candidates):
            pause_scene = max(narration_candidates, key=lambda s: float(s["end"]) - float(s["start"]))
            pause_scene["visual_effect"] = "pause"
            pause_scene["effect_reason"] = pause_scene.get("effect_reason") or "Freeze the key evidence frame while the narration explains what viewers should notice."

        if len(narration_candidates) >= 2 and not any(
            s.get("visual_effect") in {"zoom_in", "zoom_out"} for s in narration_candidates
        ):
            zoom_scene = sorted(
                narration_candidates,
                key=lambda s: float(s["end"]) - float(s["start"]),
                reverse=True,
            )[1]
            zoom_scene["visual_effect"] = "zoom_in"
            zoom_scene["zoom_strength"] = min(
                MAX_ZOOM, max(1.08, float(zoom_scene.get("zoom_strength", 1.10)))
            )
            zoom_scene["effect_reason"] = (
                zoom_scene.get("effect_reason")
                or "Slowly draw attention to the visible evidence being discussed."
            )

        if len(narration_candidates) >= 3 and not any(
            s.get("visual_effect") == "replay" for s in narration_candidates
        ):
            replay_scene = sorted(
                narration_candidates,
                key=lambda s: float(s["end"]) - float(s["start"]),
                reverse=True,
            )[2]
            replay_scene["visual_effect"] = "replay"
            replay_scene["effect_reason"] = (
                replay_scene.get("effect_reason")
                or "Replay this exact source moment so viewers can catch the detail a second time."
            )


    narration_scenes = [
        s for s in scenes
        if s["audio_mode"] in {"narration", "pause", "replay"} and s.get("narration")
    ]
    narration_seconds = sum(float(s["end"]) - float(s["start"]) for s in narration_scenes)
    narration_text = " ".join(s["narration"] for s in narration_scenes)
    narration_words = len(re.findall(r"\b[\w'-]+\b", narration_text))
    data["narration_stats"] = {
        "scene_count": len(narration_scenes),
        "seconds": round(narration_seconds, 3),
        "ratio": round(narration_seconds / duration, 3) if duration else 0.0,
        "word_count": narration_words,
    }
    narration_ratio = narration_seconds / max(duration, 1.0)
    original_seconds = sum(float(s["end"]) - float(s["start"]) for s in scenes if s["audio_mode"] == "original")
    data["audio_mix_stats"] = {"narration_ratio": round(narration_ratio, 3), "original_audio_ratio": round(original_seconds / max(duration, 1.0), 3)}
    effect_counts = {}
    for scene in scenes:
        effect = scene["visual_effect"]
        effect_counts[effect] = effect_counts.get(effect, 0) + 1
    data["visual_effect_stats"] = effect_counts
    if (
        len(narration_scenes) < min(MIN_NARRATION_SCENES, max(1, int(duration // 15)))
        or narration_seconds / max(duration, 1.0) < max(MIN_NARRATION_RATIO, 0.65)
        or narration_words < MIN_NARRATION_WORDS
    ):
        raise RuntimeError(
            "Mystery narration plan is insufficient: "
            f"scenes={len(narration_scenes)}, seconds={narration_seconds:.1f}/{duration:.1f}, "
            f"ratio={narration_seconds / max(duration, 1.0):.2%}, words={narration_words}. "
            "The documentary must contain a substantial generated narration layer."
        )
    return data


def _visual_filter(scene, length):
    effect = scene.get("visual_effect", "normal")
    base = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,fps=30"
    if effect not in {"zoom_in", "zoom_out"}:
        return base
    strength = float(scene.get("zoom_strength", 1.10))
    target_x = float(scene.get("zoom_target_x", 0.5))
    target_y = float(scene.get("zoom_target_y", 0.5))
    delta = strength - 1.0
    duration = max(length, 0.1)
    if effect == "zoom_out":
        zoom = f"{strength:.4f}-min(t/{duration:.4f},1)*{delta:.4f}"
    else:
        zoom = f"1+min(t/{duration:.4f},1)*{delta:.4f}"
    return base + f",scale=trunc(1920*({zoom})/2)*2:trunc(1080*({zoom})/2)*2,crop=1920:1080:x='(iw-1920)*{target_x:.4f}':y='(ih-1080)*{target_y:.4f}'"


def _audio_duration(path):
    if not path:
        return 0.0
    raw = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], text=True)
    return float(raw.strip() or 0.0)


def render_scene(source, s, narration, out, work):
    start, end = s["start"], s["end"]
    planned_length = max(0.1, end - start)
    mode = s["audio_mode"]
    effect = s.get("visual_effect", "normal")
    video = work / (out.stem + ".video.mp4")
    narration_duration = _audio_duration(narration) if narration else 0.0
    # Commentary drives timing. If TTS is shorter than the planned beat, trim the
    # source visual to the narration instead of padding the soundtrack with silence.
    render_length = narration_duration if narration_duration > 0 else planned_length
    render_length = max(0.1, render_length)
    vf = _visual_filter(s, render_length)
    if mode == "pause" or effect == "pause":
        vf += ",select='eq(n,0)',tpad=stop_mode=clone:stop_duration=" + str(render_length)
    source_duration = min(planned_length, render_length)
    if mode == "replay" or effect == "replay":
        vf += ",setpts=PTS/0.75"
        source_duration = min(planned_length, render_length * 0.75)
    cmd(["ffmpeg", "-y", "-ss", str(start), "-i", source, "-t", str(source_duration), "-vf", vf, "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", video])
    # If narration outlives the selected source moment, hold the final evidence frame.
    if narration_duration > source_duration + 0.05:
        hold = narration_duration - source_duration
        cmd(["ffmpeg", "-y", "-i", video, "-vf", "tpad=stop_mode=clone:stop_duration=" + str(hold), "-t", str(render_length), "-c:v", "libx264", "-pix_fmt", "yuv420p", video.with_name(video.stem + "-held.mp4")])
        video.unlink(missing_ok=True)
        video = video.with_name(video.stem + "-held.mp4")
    if mode == "original" and not narration:
        cmd(["ffmpeg", "-y", "-i", video, "-ss", str(start), "-i", source, "-t", str(render_length), "-map", "0:v:0", "-map", "1:a?", "-c:v", "copy", "-c:a", "aac", "-shortest", out])
    elif narration:
        cmd(["ffmpeg", "-y", "-i", video, "-i", narration, "-t", str(render_length), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-shortest", out])
    else:
        cmd(["ffmpeg", "-y", "-i", video, "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", str(render_length), "-c:v", "copy", "-c:a", "aac", out])
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

        print("🎧 Analyzing source speech before editorial planning...")
        audio_analysis = analyze_audio(source, work / "audio-analysis")
        (OUT / "audio_timeline.json").write_text(json.dumps(audio_analysis, indent=2, ensure_ascii=False), encoding="utf-8")
        last_plan_error = None
        timeline = None
        for attempt in range(1, 4):
            try:
                print(f"🧠 Building Mystery documentary script/timeline (attempt {attempt}/3)")
                timeline = plan(item, source, work, duration, audio_analysis)
                break
            except RuntimeError as exc:
                last_plan_error = exc
                print(f"⚠️ Mystery script/timeline rejected: {exc}")
        if timeline is None:
            raise RuntimeError(f"Could not produce a narration-rich Mystery documentary plan: {last_plan_error}")
        (OUT / "timeline.json").write_text(json.dumps(timeline, indent=2, ensure_ascii=False), encoding="utf-8")
        full_narration = " ".join(
            scene["narration"]
            for scene in timeline["scene_plan"]
            if scene.get("narration")
        ).strip()
        script_artifact = {
            "video_title": timeline.get("video_title", item.get("title", "Mystery Documentary")),
            "description_intro": timeline.get("description_intro", ""),
            "tags": timeline.get("tags", []),
            "highlighted_keywords": timeline.get("highlighted_keywords", []),
            "narration": full_narration,
            "scene_plan": timeline["scene_plan"],
            "narration_stats": timeline.get("narration_stats", {}),
            "audio_mix_stats": timeline.get("audio_mix_stats", {}),
            "visual_effect_stats": timeline.get("visual_effect_stats", {}),
            "case": {
                "id": item.get("id"),
                "title": item.get("title"),
                "summary": item.get("case_summary"),
                "verified_facts": item.get("verified_facts", []),
                "open_questions": item.get("theories_or_open_questions", []),
                "source_url": item.get("source_url"),
            },
        }
        (OUT / "script.json").write_text(json.dumps(script_artifact, indent=2, ensure_ascii=False), encoding="utf-8")
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
    meta = {
        "video_title": timeline.get("video_title", item.get("title", "Mystery Documentary")),
        "description": timeline.get("description_intro", "") + "\n\nSource footage: " + item.get("source_url", ""),
        "tags": timeline.get("tags", []),
        "highlighted_keywords": timeline.get("highlighted_keywords", []),
        "catalog_item_id": item.get("id"),
        "source_url": item.get("source_url"),
        "narration_stats": timeline.get("narration_stats", {}),
        "audio_mix_stats": timeline.get("audio_mix_stats", {}),
        "visual_effect_stats": timeline.get("visual_effect_stats", {}),
        "script_path": str(OUT / "script.json"),
        "timeline_path": str(OUT / "timeline.json"),
        "generated_at": int(time.time()),
    }
    (OUT / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    if not output.exists() or output.stat().st_size < 100_000:
        raise RuntimeError("Mystery documentary output is missing or suspiciously small")
    print(
        f"🎙️ Mystery TTS complete | narration scenes={timeline.get('narration_stats', {}).get('scene_count', 0)} "
        f"| narration words={timeline.get('narration_stats', {}).get('word_count', 0)}"
    )
    print(f"MYSTERY_DOCUMENTARY_OUTPUT={output}")


if __name__ == "__main__":
    main()
