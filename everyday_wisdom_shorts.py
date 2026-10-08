from __future__ import annotations

import difflib
from difflib import SequenceMatcher
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
# Keep Everyday Wisdom on the same Gemini model as Publish Shorts, but isolated to this workflow.
MODEL = "gemini-flash-lite-latest"
VOICE = os.getenv("WISDOM_KOKORO_VOICE", "af_heart")
TARGET_SECONDS = 40.0
MIN_NARRATION_WORDS = 80
MAX_NARRATION_WORDS = 95
TOPIC_HISTORY_PATH = Path("everyday_wisdom_topic_history.json")
MAX_HISTORY_FOR_PROMPT = 120
WHISPER_MODEL = os.getenv("WISDOM_WHISPER_MODEL", "tiny.en")


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

Write 80-95 words, approximately 30-38 seconds, as one connected mini-story.
Never exceed 95 words. Keep sentences concise and natural so Kokoro narration fits under 40 seconds without speeding up.
The first sentence must create immediate curiosity. End with a satisfying answer.

TITLE RULES:
- Create a curiosity-driven title for US viewers.
- Prefer 35-65 characters when natural.
- Make the familiar subject obvious while creating a reason to watch.
- Do not use "Did you know?", ALL CAPS, fake shock, misleading claims, or generic titles like "You Won't Believe This".
- Do not stuff keywords into the title.

Return JSON only:
{"title":"...","topic":"...","topic_key":"...","narration":"...","search_queries":["...","...","..."],"visual_queries":["..."]}
Search queries must be concrete things a camera can show, 3-6 words each.

VISUAL BEATS: create 16-18 ordered visual_queries, one for each roughly 2.5-second beat of the narration. Each query must depict the exact object, action, setting, or concrete visual metaphor being spoken about at that moment. Make every query materially different from the previous one. Follow the narration chronologically. Never use generic filler such as "american lifestyle", "happy family", "person thinking", "stock footage", or "everyday life". Queries must be 3-7 words each.
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
                "visual_queries": [
                    clean(x, 100) for x in data.get("visual_queries", []) if clean(x, 100)
                ][:18],
            }
            words = re.findall(r"\b[\w'-]+\b", story["narration"])
            if not story["topic"] or not story["topic_key"] or not story["narration"] or len(story["search_queries"]) < 3 or len(story["visual_queries"]) < 16:
                raise RuntimeError("Incomplete story JSON or fewer than 16 narration-aligned visual queries")
            if not MIN_NARRATION_WORDS <= len(words) <= MAX_NARRATION_WORDS:
                raise RuntimeError(f"Narration word count {len(words)} outside {MIN_NARRATION_WORDS}-{MAX_NARRATION_WORDS}")
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
    # Narration is intentionally generated short enough to fit naturally.
    # Do not time-compress speech: caption timestamps must reflect natural
    # Kokoro delivery speed.
    if duration > TARGET_SECONDS:
        raise RuntimeError(
            f"Narration synthesis exceeded 40s: {duration:.2f}s. "
            "Regenerate with a shorter narration; audio speed-up is disabled."
        )
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
    """Download one unique stock clip per narration visual beat.

    The visual_queries are ordered to match the narration. We intentionally
    download a separate source for each beat so the renderer never has to
    recycle the same clip just because the narration moved to a new idea.
    """
    chosen = []
    seen = set()
    target_duration = float(required_duration) + 1.0
    queries = [clean(q, 100) for q in queries if clean(q, 100)]
    # Gemini is allowed to return 16-18 narration-aligned beats. Do not derive
    # a rigid count from duration: a 42s narration can be covered cleanly by
    # 16 unique visuals, with the renderer distributing the time across them.
    beat_count = min(18, len(queries))
    if beat_count < 16:
        raise RuntimeError(
            f"Only {len(queries)} narration-aligned visual queries were generated; "
            "at least 16 are required"
        )

    for beat_index, query in enumerate(queries[:beat_count]):
        candidates = []
        for search_query in (query, f"{query} vertical"):
            try:
                candidates.extend(search_videos(search_query))
            except Exception as exc:
                print(f"Visual search failed for beat {beat_index + 1}: {search_query} | {exc}")
        selected = None
        for item in candidates:
            vid = str(item.get("id") or "")
            if not vid or vid in seen:
                continue
            files = [f for f in item.get("video_files", []) if f.get("link")]
            if not files:
                continue
            files.sort(
                key=lambda f: abs(
                    (f.get("width", 0) / max(1, f.get("height", 1))) - 9 / 16
                )
            )
            selected = (vid, files[0])
            break

        if selected is None:
            raise RuntimeError(
                f"No unique Pexels visual found for narration beat {beat_index + 1}: {query}"
            )

        vid, media = selected
        path = VIDEO_DIR / f"{beat_index:02d}.mp4"
        with requests.get(media["link"], stream=True, timeout=60) as dl:
            dl.raise_for_status()
            with path.open("wb") as handle:
                for chunk in dl.iter_content(1024 * 1024):
                    if chunk:
                        handle.write(chunk)

        if path.stat().st_size < 10000:
            path.unlink(missing_ok=True)
            raise RuntimeError(f"Downloaded visual is too small for beat {beat_index + 1}: {query}")

        try:
            clip_duration = video_duration(path)
        except Exception as exc:
            path.unlink(missing_ok=True)
            raise RuntimeError(
                f"Could not inspect visual for beat {beat_index + 1}: {query}"
            ) from exc

        if clip_duration < 1.0:
            path.unlink(missing_ok=True)
            raise RuntimeError(
                f"Visual is too short for beat {beat_index + 1}: {query}"
            )

        chosen.append(path)
        seen.add(vid)
        print(
            f"Visual beat {beat_index + 1}/{beat_count}: {query} | "
            f"Pexels {vid} | {clip_duration:.2f}s"
        )

    if len(chosen) < beat_count:
        raise RuntimeError(
            f"Only {len(chosen)} unique visuals downloaded; {beat_count} required"
        )

    # Keep this guard so future changes cannot silently revert to the old
    # repeated-clip timeline.
    if len({path.name for path in chosen}) != len(chosen):
        raise RuntimeError("Every narration beat must use a different visual source")

    return chosen
def _make_2_5_second_visual_segments(clips, total_duration):
    """Build the narration-aligned 2.5s visual timeline.

    Each downloaded clip belongs to exactly one narration beat. Clips are
    consumed in order and never recycled for another beat.
    """
    if not clips:
        raise RuntimeError("No stock clips available")

    # Use every unique narration-aligned clip exactly once. The normal target
    # is ~2.5s/beat, but the final duration is distributed across the available
    # 16-18 beats so a valid 16-beat Gemini response cannot fail a 42s narration.
    segment_count = min(len(clips), max(16, min(18, int(round(float(total_duration) / 2.5)))))
    segment_duration = float(total_duration) / max(1, segment_count)

    segment_paths = []
    for index in range(segment_count):
        source = clips[index]
        segment_path = RUN_ROOT / "segments" / f"visual_{index:03d}.mp4"
        segment_path.parent.mkdir(parents=True, exist_ok=True)
        remaining = max(0.05, float(total_duration) - index * segment_duration)
        duration = min(segment_duration, remaining)

        subprocess.run(
            [
                "ffmpeg", "-y",
                "-stream_loop", "-1",
                "-i", str(source),
                "-t", f"{duration:.3f}",
                "-an",
                "-vf",
                "scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,setsar=1,fps=30,format=yuv420p",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-pix_fmt", "yuv420p",
                str(segment_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        segment_paths.append(segment_path)

    concat = RUN_ROOT / "visual_segments.txt"
    concat.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in segment_paths),
        encoding="utf-8",
    )
    return concat


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


def _publish_ass_color(index):
    colors = [
        "&H00FFFFFF",
        "&H0054D5FF",
        "&H00FFD749",
        "&H005E5AFF",
        "&H0063FF8D",
    ]
    return colors[index % len(colors)]


def _normalize_caption_token(value):
    return re.sub(r"[^a-z0-9']+", "", str(value or "").lower()).strip("'")

def _transcribe_word_timestamps(audio_path):
    """Get word-level timestamps from the final Kokoro narration audio."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("faster-whisper is required for narration-synced captions") from exc
    print(f"Caption alignment: Whisper model={WHISPER_MODEL}")
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(audio_path), language="en", word_timestamps=True,
        vad_filter=True, condition_on_previous_text=False, beam_size=5,
    )
    timed_words = []
    for segment in segments:
        for word in (segment.words or []):
            token = _normalize_caption_token(word.word)
            if token and word.end > word.start:
                timed_words.append({"word": word.word, "token": token,
                                    "start": float(word.start), "end": float(word.end)})
    print(f"Caption alignment transcription complete: {len(timed_words)} words | language={info.language}")
    return timed_words

def _align_caption_words(narration, timed_words, duration):
    """Align exact narration words to timestamps from the final audio."""
    original = [word for word in narration.split() if word.strip()]
    recognized = [item for item in timed_words if item.get("token")]
    if not original or not recognized:
        raise RuntimeError("Cannot align captions: missing narration or Whisper timestamps")
    matcher = SequenceMatcher(
        None,
        [_normalize_caption_token(word) for word in original],
        [item["token"] for item in recognized],
        autojunk=False,
    )
    anchors = [None] * len(original)
    matched = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal" or (tag == "replace" and (i2 - i1) == (j2 - j1)):
            for offset in range(i2 - i1):
                item = recognized[j1 + offset]
                anchors[i1 + offset] = (item["start"], item["end"])
                matched += 1
    minimum_match = max(1, int(len(original) * 0.70))
    if matched < minimum_match:
        raise RuntimeError(
            f"Caption/audio alignment confidence too low: matched {matched}/{len(original)} words"
        )

    for index in range(len(original)):
        if anchors[index] is not None:
            continue
        left_index = index - 1
        while left_index >= 0 and anchors[left_index] is None:
            left_index -= 1
        right_index = index + 1
        while right_index < len(original) and anchors[right_index] is None:
            right_index += 1
        start = anchors[left_index][1] if left_index >= 0 else 0.0
        end = anchors[right_index][0] if right_index < len(original) else float(duration)
        if end < start:
            end = start
        count = (right_index - left_index) if right_index < len(original) else (index - left_index + 1)
        position = (index - left_index) if left_index >= 0 else (index + 1)
        anchors[index] = (
            start + (end - start) * ((position - 1) / max(1, count)),
            start + (end - start) * (position / max(1, count)),
        )

    aligned = []
    for index, word in enumerate(original):
        start, end = anchors[index]
        start = max(0.0, min(float(duration), start))
        end = max(start + 0.015, min(float(duration), end))
        if index > 0:
            start = max(start, aligned[-1]["end"] - 0.015)
        aligned.append({"word": word, "start": start, "end": end})
    return aligned

def create_animated_captions(narration, duration, audio_path):
    aligned_words = _align_caption_words(
        narration, _transcribe_word_timestamps(audio_path), duration
    )
    ass_path = RUN_ROOT / "captions.ass"
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: PublishWisdom,Poppins ExtraBold,72,&H00FFFFFF,&H00FFFFFF,&H00111111,&H00000000,1,0,0,0,100,100,0,0,1,2,7,2,80,80,691,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for index, item in enumerate(aligned_words):
        lines.append(
            f"Dialogue: 0,{_ass_time(item['start'])},{_ass_time(item['end'])},PublishWisdom,,0,0,0,,"
            f"{{\\c{_publish_ass_color(index)}}}{_ass_escape(item['word'])}"
        )
    ass_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Narration-synced captions created: {ass_path} | words={len(aligned_words)}")
    return ass_path

def render(clips, audio, output, duration, narration):
    ass_path = create_animated_captions(narration, duration, audio)
    subtitle_filter = f"subtitles='{ass_path.resolve()}'"
    visual_concat = _make_2_5_second_visual_segments(clips, duration)

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(visual_concat),
            "-i", str(audio),
            "-filter_complex", f"[0:v]{subtitle_filter}[v]",
            "-map", "[v]", "-map", "1:a:0",
            "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            str(output),
        ],
        check=True,
    )


def build_caption(story):
    topic = clean(story.get("topic"), 180)
    narration = clean(story.get("narration"), 3000)
    title = clean(story.get("title"), 90).strip(" .-")
    if not title:
        title = topic[:70].rstrip(" .-")
    title = title[:70].rstrip(" .-")

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
    while sum(len(tag) for tag in tags) + max(0, len(tags) - 1) > 450:
        tags.pop()

    first_sentence = re.split(r"(?<=[.!?])\s+", narration.strip())[0].strip()
    description = (
        f"{topic}. Ever wondered why this is so common in American life? "
        "This short explains the history, meaning, or practical reason behind it "
        "through one simple story."
    )
    if first_sentence and len(first_sentence) <= 180:
        if first_sentence.lower() not in description.lower():
            description += f"\n\n{first_sentence}"

    description += (
        "\n\nFollow Everyday Wisdom for more familiar sayings, habits, objects, "
        "and everyday mysteries with surprisingly simple explanations."
    )

    hashtags = ["#shorts", "#everydaywisdom", "#americanlife", "#curiosity"]
    if topic_terms:
        hashtags.append("#" + "".join(topic_terms[:2]))
    description += "\n\n" + " ".join(dict.fromkeys(hashtags[:5]))

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
        raise RuntimeError(
            "YOUTUBE_TOKEN_JSON has no refresh_token; re-authorize the YouTube account"
        )

    # Explicitly refresh when needed so an expired access token never prevents
    # the upload merely because the workflow runner started with an old token.
    from google.auth.transport.requests import Request
    if credentials.expired:
        print("YouTube access token expired; refreshing with stored refresh token")
        credentials.refresh(Request())

    youtube = build("youtube", "v3", credentials=credentials)
    title, description, tags = build_caption(story)

    print(f"Uploading Everyday Wisdom Short: {title}")
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "27",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(
            str(video),
            chunksize=-1,
            resumable=True,
            mimetype="video/mp4",
        ),
    )

    response = None
    while response is None:
        status, response = request.next_chunk(num_retries=5)
        if status:
            print(f"YouTube upload progress: {int(status.progress() * 100)}%")

    video_id = response.get("id")
    if not video_id:
        raise RuntimeError(f"YouTube upload returned no video ID: {response}")

    print(f"YOUTUBE UPLOADED: https://www.youtube.com/watch?v={video_id}")
    return video_id


def main():
    print("EVERYDAY WISDOM SHORTS | isolated pipeline | START")

    story = generate_story()
    print(f"Generated topic: {story['topic']} | title={story['title']}")

    # Retire the topic before expensive media work so a failed render/upload
    # cannot cause the same topic to be selected again.
    remember_topic(story)
    (RUN_ROOT / "story.json").write_text(
        json.dumps(story, indent=2), encoding="utf-8"
    )

    audio = RUN_ROOT / "narration.wav"
    duration = synthesize(story["narration"], audio)
    if duration > TARGET_SECONDS:
        raise RuntimeError(f"Narration exceeds 40-second target after synthesis: {duration:.2f}s")
    print(f"Narration ready: {duration:.2f}s")

    clips = download_stock(story["visual_queries"], duration)
    print(f"Downloaded {len(clips)} unique narration-aligned visuals")

    video = RUN_ROOT / "final.mp4"
    render(clips, audio, video, duration, story["narration"])

    if not video.exists() or video.stat().st_size < 100000:
        raise RuntimeError("Final video was not created or is too small")

    print(f"Final video ready: {video} ({video.stat().st_size} bytes)")

    video_id = upload(video, story)
    (RUN_ROOT / "publish.json").write_text(
        json.dumps(
            {
                "video_id": video_id,
                "topic": story["topic"],
                "uploaded": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"EVERYDAY WISDOM COMPLETE: {video_id}")


if __name__ == "__main__":
    main()
