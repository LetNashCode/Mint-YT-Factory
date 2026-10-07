from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import time
from pathlib import Path

import requests
from google import genai
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

RUN_ROOT = Path(".everyday_wisdom_runs") / str(int(time.time()))
RUN_ROOT.mkdir(parents=True, exist_ok=True)
VIDEO_DIR = RUN_ROOT / "stock"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

PEXELS_URL = "https://api.pexels.com/videos/search"
MODEL = "gemini-2.5-flash"
VOICE = os.getenv("WISDOM_KOKORO_VOICE", "af_heart")
TARGET_SECONDS = 42.0
TOPIC_HISTORY_PATH = Path("everyday_wisdom_topic_history.json")
MAX_HISTORY_FOR_PROMPT = 120


def clean(value, limit=1000):

    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def client():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing")
    return genai.Client(api_key=key)


def normalize_topic(value):
    value = re.sub(r"[^a-z0-9\s]", " ", str(value or "").lower())
    value = re.sub(
        r"\b(why|do|does|did|we|you|the|a|an|is|are|was|were|how|what|where|when|"
        r"of|to|it|people|americans|say|saying|called|call|about|behind|reason)\b",
        " ",
        value,
    )
    return " ".join(value.split())


def topic_similarity(left, right):
    left_norm = normalize_topic(left)
    right_norm = normalize_topic(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0

    left_words = set(left_norm.split())
    right_words = set(right_norm.split())
    overlap = len(left_words & right_words) / max(1, len(left_words | right_words))
    sequence = difflib.SequenceMatcher(None, left_norm, right_norm).ratio()
    return max(overlap, sequence)


def load_topic_history():
    if not TOPIC_HISTORY_PATH.exists():
        return []
    try:
        payload = json.loads(TOPIC_HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Cannot read Everyday Wisdom topic history: {exc}") from exc
    entries = payload.get("topics", []) if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        raise RuntimeError("Everyday Wisdom topic history is malformed")
    return [entry for entry in entries if isinstance(entry, dict)]


def history_strings(history):
    values = []
    for entry in history:
        for key in ("topic_key", "topic", "title"):
            value = clean(entry.get(key), 180)
            if value and value not in values:
                values.append(value)
    return values


def is_duplicate_topic(candidate, history):
    candidate_key = normalize_topic(candidate.get("topic_key"))
    candidate_topic = clean(candidate.get("topic"), 200)
    candidate_title = clean(candidate.get("title"), 120)

    for entry in history:
        old_values = [
            clean(entry.get("topic_key"), 120),
            clean(entry.get("topic"), 200),
            clean(entry.get("title"), 120),
        ]
        old_key = normalize_topic(old_values[0])
        if candidate_key and old_key and candidate_key == old_key:
            return True

        for old_value in old_values:
            if not old_value:
                continue
            if normalize_topic(candidate_topic) == normalize_topic(old_value):
                return True
            if topic_similarity(candidate_key or candidate_topic, old_value) >= 0.78:
                return True

    return False


def remember_topic(story):
    history = load_topic_history()
    entry = {
        "topic_key": clean(story.get("topic_key"), 120),
        "topic": clean(story.get("topic"), 200),
        "title": clean(story.get("title"), 120),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if is_duplicate_topic(story, history):
        raise RuntimeError(f"Topic already exists in history: {entry['topic']}")
    history.append(entry)
    TOPIC_HISTORY_PATH.write_text(
        json.dumps({"version": 1, "topics": history}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Topic history updated: {entry['topic']} | key={entry['topic_key']}")
    return entry


def generate_story():
    history = load_topic_history()
    used = history_strings(history)[-MAX_HISTORY_FOR_PROMPT:]
    history_block = (
        "\nAlready used topics. Do NOT create the same idea, even with different wording:\n"
        + "\n".join(f"- {item}" for item in used)
        if used
        else "\nNo previous topics have been used yet.\n"
    )
    base_prompt = """
Create one YouTube Short for a US audience about something Americans have
heard forever but rarely stop to ask why: an old grandma saying, familiar
phrase, household rule, childhood warning, common habit, or ordinary object.

The story must uncover the documented history, practical reason, cultural
origin, or psychological reason behind it. Do not invent an origin; if the
origin is uncertain, say so naturally and give the strongest explanation.

IMPORTANT: The topic must be genuinely different from every topic in the
provided history. Do not reuse an old topic by changing only the wording,
angle, title, or example. Choose a different underlying subject/question.

Create a short canonical "topic_key" of 2-6 content words that identifies the
underlying idea. The topic_key must make the same subject obvious even if the
title is phrased differently.

Do not use politics, celebrities, medical advice, conspiracy, fearbait,
lists, countdowns, "Did you know?", "Today we're going to", AI references,
or a second topic. The narration must work without visuals.

Write 105-135 words, approximately 38-43 seconds, as one connected mini-story.
The first sentence must create immediate curiosity. End with a satisfying answer.

TITLE RULES:
- Create a curiosity-driven title for US viewers.
- Prefer 35-65 characters when natural.
- Make the familiar subject obvious while creating a reason to watch.
- Do not use "Did you know?", ALL CAPS, fake shock, misleading claims, or generic titles like "You Won't Believe This".
- Do not stuff keywords into the title.

Return JSON only:
{"title":"...","topic":"...","topic_key":"...","narration":"...","search_queries":["...","...","..."]}
Search queries must be concrete things a camera can show, 3-6 words each.
""" + history_block

    c = client()
    for attempt in range(5):
        try:
            response = c.models.generate_content(
                model=MODEL,
                contents=base_prompt,
                config={"temperature": 0.95, "response_mime_type": "application/json"},
            )
            data = json.loads(response.text)
            story = {
                "title": clean(data.get("title"), 90),
                "topic": clean(data.get("topic"), 200),
                "topic_key": clean(data.get("topic_key"), 120),
                "narration": clean(data.get("narration"), 3000),
                "search_queries": [
                    clean(x, 80) for x in data.get("search_queries", []) if clean(x, 80)
                ][:3],
            }
            words = re.findall(r"\b[\w'-]+\b", story["narration"])
            if not story["topic"] or not story["topic_key"] or not story["narration"] or len(story["search_queries"]) < 3:
                raise RuntimeError("Incomplete story JSON")
            if not 105 <= len(words) <= 145:
                raise RuntimeError(f"Narration word count {len(words)} outside 105-145")
            if is_duplicate_topic(story, history):
                raise RuntimeError(
                    f"Duplicate topic rejected: {story['topic']} | key={story['topic_key']}"
                )
            return story
        except Exception as exc:
            if attempt == 4:
                raise
            print(f"Story generation retry {attempt + 1}/5: {type(exc).__name__}: {exc}")
            time.sleep(2 + attempt)
    raise RuntimeError("Story generation failed")


def synthesize(text, output):
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    pipeline = KPipeline(lang_code="a")
    words = text.split()
    chunks = [" ".join(words[i:i + 42]) for i in range(0, len(words), 42)]
    parts = []
    for index, chunk in enumerate(chunks, 1):
        print(f"TTS chunk {index}/{len(chunks)}")
        audio_parts = []
        for result in pipeline(chunk, voice=VOICE, speed=1.0, split_pattern=r"\n+"):
            audio = result[2] if isinstance(result, tuple) else result.audio
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            audio = np.asarray(audio, dtype=np.float32).reshape(-1)
            if audio.size:
                audio_parts.append(audio)
        if not audio_parts:
            raise RuntimeError(f"Kokoro returned no audio for chunk {index}")
        parts.append(np.concatenate(audio_parts))
        if index < len(chunks):
            parts.append(np.zeros(int(0.035 * 24000), dtype=np.float32))
    audio = np.concatenate(parts)
    sf.write(output, audio, 24000, subtype="PCM_16")
    duration = len(audio) / 24000.0
    if duration > TARGET_SECONDS:
        sped = output.with_name("narration_sped.wav")
        factor = min(1.12, duration / TARGET_SECONDS)
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(output), "-filter:a", f"atempo={factor:.6f}", str(sped)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        sped.replace(output)
        duration = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(output)], text=True
        ).strip())
    return duration


def search_videos(query):
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PEXELS_API_KEY is missing")
    response = requests.get(
        PEXELS_URL,
        headers={"Authorization": key},
        params={"query": query, "orientation": "portrait", "size": "medium", "per_page": 12},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("videos", [])


def video_duration(path):
    return float(subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    ).strip())


def download_stock(queries, required_duration):
    chosen = []
    seen = set()
    total_duration = 0.0
    target_duration = float(required_duration) + 1.0
    for query in queries:
        for item in search_videos(query):
            vid = str(item.get("id") or "")
            if not vid or vid in seen:
                continue
            files = [f for f in item.get("video_files", []) if f.get("link")]
            if not files:
                continue
            files.sort(key=lambda f: abs((f.get("width", 0) / max(1, f.get("height", 1))) - 9 / 16))
            path = VIDEO_DIR / f"{len(chosen):02d}.mp4"
            with requests.get(files[0]["link"], stream=True, timeout=60) as dl:
                dl.raise_for_status()
                with path.open("wb") as handle:
                    for chunk in dl.iter_content(1024 * 1024):
                        if chunk:
                            handle.write(chunk)
            if path.stat().st_size < 10000:
                path.unlink(missing_ok=True)
                continue
            try:
                clip_duration = video_duration(path)
            except Exception:
                path.unlink(missing_ok=True)
                continue
            if clip_duration < 1.0:
                path.unlink(missing_ok=True)
                continue

            chosen.append(path)
            total_duration += clip_duration
            seen.add(vid)
            print(
                f"Stock {len(chosen)}: {query} | Pexels {vid} | "
                f"{clip_duration:.2f}s | total={total_duration:.2f}s"
            )
            if total_duration >= target_duration:
                return chosen
            if len(chosen) >= 10:
                break
        if total_duration >= target_duration or len(chosen) >= 10:
            break

    if len(chosen) < 3 or total_duration < target_duration:
        raise RuntimeError(
            f"Insufficient stock-video duration: {total_duration:.2f}s available, "
            f"{target_duration:.2f}s required"
        )
    return chosen


def _ass_time(seconds):
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    centiseconds = int(round((seconds - int(seconds)) * 100))
    whole = int(seconds) % 60
    if centiseconds >= 100:
        whole += 1
        centiseconds = 0
    return f"{hours}:{minutes:02d}:{whole:02d}.{centiseconds:02d}"


def _ass_escape(text):
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", " ")
        .strip()
    )


def create_animated_captions(narration, duration):
    """Create isolated, narration-timed kinetic captions for Everyday Wisdom."""
    words = narration.split()
    if not words:
        raise RuntimeError("Cannot create captions from empty narration")

    groups = []
    current = []
    for word in words:
        current.append(word)
        if len(current) >= 3 or re.search(r"[.!?,;:]$", word):
            groups.append(current)
            current = []
    if current:
        groups.append(current)

    weights = [max(1, len(" ".join(group))) for group in groups]
    total_weight = float(sum(weights))
    ass_path = RUN_ROOT / "captions.ass"

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Wisdom,Arial,62,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,1,0,0,0,100,100,0,0,1,7,2,2,80,80,250,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    current_time = 0.0
    lines = [header]
    for index, (group, weight) in enumerate(zip(groups, weights)):
        start = current_time
        end = duration if index == len(groups) - 1 else current_time + duration * (weight / total_weight)
        text = _ass_escape(" ".join(group))
        events = (
            "{\\fad(90,90)\\t(0,110,\\fscx92\\fscy92)\\t(110,220,\\fscx108\\fscy108)\\t(220,300,\\fscx100\\fscy100)}"
            + text
        )
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Wisdom,,0,0,0,,{events}"
        )
        current_time = end

    ass_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Animated captions created: {ass_path} | beats={len(groups)}")
    return ass_path


def render(clips, audio, output, duration, narration):
    concat = RUN_ROOT / "concat.txt"
    concat.write_text("".join(f"file '{p.resolve()}'\n" for p in clips), encoding="utf-8")
    ass_path = create_animated_captions(narration, duration)
    subtitle_filter = f"subtitles='{ass_path.resolve()}'"
    filter_complex = (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,setsar=1,fps=30,format=yuv420p,"
        f"{subtitle_filter}[v]"
    )
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
        "-i", str(audio), "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "1:a:0",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        "-pix_fmt", "yuv420p", str(output),
    ], check=True)


def build_caption(story):
    """Build topic-specific discovery metadata for Everyday Wisdom only."""
    topic = clean(story.get("topic"), 180)
    narration = clean(story.get("narration"), 3000)
    title = clean(story.get("title"), 90)

    # Keep the title curiosity-driven but truthful. Gemini owns the creative
    # title; this only removes noisy punctuation/whitespace.
    title = re.sub(r"\s+", " ", title).strip(" .-")
    if not title:
        title = topic[:70].rstrip(" .-")
    title = title[:70].rstrip(" .-")

    # Derive searchable phrases from the actual topic rather than using a
    # generic keyword wall. These remain isolated from Publish Shorts.
    topic_terms = [
        word.lower()
        for word in re.findall(r"[A-Za-z]{3,}", topic)
        if word.lower() not in {
            "why", "does", "did", "the", "and", "for", "with",
            "from", "about", "americans", "people", "common",
        }
    ]
    topic_terms = list(dict.fromkeys(topic_terms))

    keyword_phrases = [
        topic,
        f"why {topic.lower()}",
        f"{topic.lower()} explained",
        f"meaning of {topic.lower()}",
        f"history of {topic.lower()}",
        *topic_terms,
        "everyday wisdom",
        "american life",
        "common sayings",
        "everyday history",
        "curiosity",
    ]

    tags = []
    for value in keyword_phrases:
        tag = re.sub(r"[^A-Za-z0-9 -]", "", str(value or "")).strip().lower()
        if tag and tag not in tags:
            tags.append(tag)
    tags = tags[:15]
    # YouTube enforces a total tag-character limit; keep a safety margin.
    while sum(len(tag) for tag in tags) + max(0, len(tags) - 1) > 450:
        tags.pop()

    first_sentence = re.split(r"(?<=[.!?])\s+", narration.strip())[0].strip()
    description = (
        f"{topic}. "
        f"Ever wondered why this is so common in American life? "
        f"This short explains the history, meaning, or practical reason behind it "
        f"through one simple story."
    )
    if first_sentence and len(first_sentence) <= 180:
        if first_sentence.lower() not in description.lower():
            description += f"\n\n{first_sentence}"

    description += (
        "\n\nFollow Everyday Wisdom for more familiar sayings, habits, objects, "
        "and everyday mysteries with surprisingly simple explanations."
    )

    # Keep hashtags tightly tied to this specific Short.
    hashtag_candidates = [
        "#shorts",
        "#everydaywisdom",
        "#americanlife",
        "#curiosity",
    ]
    if topic_terms:
        hashtag_candidates.append("#" + "".join(topic_terms[:2]))
    hashtags = []
    for tag in hashtag_candidates:
        tag = re.sub(r"[^A-Za-z0-9#]", "", tag).lower()
        if tag not in hashtags:
            hashtags.append(tag)
    description += "\n\n" + " ".join(hashtags[:5])

    return title, description[:2000], tags


def upload(video, story):
    raw = os.getenv("YOUTUBE_TOKEN_JSON", "").strip()
    if not raw:
        raise RuntimeError("YOUTUBE_TOKEN_JSON is missing")
    try:
        token_info = json.loads(raw)
        credentials = Credentials.from_authorized_user_info(token_info)
    except Exception as exc:
        raise RuntimeError(f"Invalid YOUTUBE_TOKEN_JSON: {exc}") from exc
    if not credentials.refresh_token:
        raise RuntimeError("YOUTUBE_TOKEN_JSON has no refresh_token; re-authorize the YouTube account")
    youtube = build("youtube", "v3", credentials=credentials)
    title, description, tags = build_caption(story)
    print("YouTube caption:")
    print(description)
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "27",
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(video), chunksize=-1, resumable=True, mimetype="video/mp4"),
    )
    response = None
    while response is None:
        status, response = request.next_chunk(num_retries=5)
        if status:
            print(f"Upload: {int(status.progress() * 100)}%")
    return response["id"]


def main():
    print("EVERYDAY WISDOM SHORTS | isolated pipeline")
    story = generate_story()
    remember_topic(story)
    (RUN_ROOT / "story.json").write_text(json.dumps(story, indent=2), encoding="utf-8")
    audio = RUN_ROOT / "narration.wav"
    duration = synthesize(story["narration"], audio)
    clips = download_stock(story["search_queries"], min(duration, TARGET_SECONDS))
    video = RUN_ROOT / "final.mp4"
    render(clips, audio, video, min(duration, TARGET_SECONDS), story["narration"])
    if not video.exists() or video.stat().st_size < 100000:
        raise RuntimeError("Final video was not created")
    video_id = upload(video, story)
    (RUN_ROOT / "publish.json").write_text(
        json.dumps({"video_id": video_id, "topic": story["topic"], "uploaded": True}, indent=2),
        encoding="utf-8",
    )
    print(f"UPLOADED: https://www.youtube.com/watch?v={video_id}")


if __name__ == "__main__":
    main()
