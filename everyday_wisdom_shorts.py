from __future__ import annotations

import difflib
from difflib import SequenceMatcher
import json
import os
import re
import subprocess
import time
from pathlib import Path
from datetime import datetime, timezone

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
BACKGROUND_MUSIC_PATH = Path(__file__).resolve().parent / "assets" / "music" / "blade_runner_2049.mp3"
BACKGROUND_MUSIC_VOLUME = 0.10
NARRATION_VOLUME = 0.90


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


def performance_guidance():
    """Use mature, retention-rich Wisdom uploads as evidence without hard-banning topics."""
    path = Path("analytics/everyday_wisdom/videos.json")
    try:
        records = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except Exception as exc:
        print(f"Performance guidance unavailable; continuing without it: {exc}")
        return ""

    now = datetime.now(timezone.utc)
    eligible = []
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        latest = record.get("latest") or {}
        if not isinstance(latest, dict):
            continue
        retention = float(latest.get("average_view_percentage") or 0)
        published = str(record.get("published_at") or "")
        checked_at = str(latest.get("checked_at") or "")
        if retention <= 0 or not published or not checked_at:
            continue
        try:
            checked_dt = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
            if checked_dt.tzinfo is None:
                checked_dt = checked_dt.replace(tzinfo=timezone.utc)
            metric_age = (now - checked_dt.astimezone(timezone.utc)).total_seconds()
            if metric_age < 0 or metric_age > 72 * 60 * 60:
                continue
            published_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            if published_dt.tzinfo is None:
                published_dt = published_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        age_hours = (now - published_dt.astimezone(timezone.utc)).total_seconds() / 3600
        if age_hours < 24:
            continue
        eligible.append({
            "title": clean(record.get("title"), 90),
            "topic": clean(record.get("topic"), 180),
            "retention": retention,
            "views": int(latest.get("views") or 0),
            "age_hours": age_hours,
        })

    if len(eligible) < 5:
        return ""

    eligible.sort(key=lambda row: row["retention"], reverse=True)
    cohort_size = max(2, min(3, len(eligible) // 2))
    winners = eligible[:cohort_size]
    weaker = eligible[-cohort_size:]
    lines = [
        "\nHistorical channel evidence (use as creative guidance, not as a topic blacklist):",
        "Stronger retention examples:",
    ]
    lines.extend(
        f"- {row['title'] or row['topic']} ({row['retention']:.1f}% average viewed)"
        for row in winners
    )
    lines.append("Lower-retention examples to learn from:")
    lines.extend(
        f"- {row['title'] or row['topic']} ({row['retention']:.1f}% average viewed)"
        for row in weaker
    )
    lines.append(
        "Infer what may have made the stronger hooks/payoffs clearer. Do not copy these topics, "
        "do not assume low views alone mean a bad topic, and choose a genuinely new subject."
    )
    return "\n" + "\n".join(lines) + "\n"



def load_publish_topic_history():
    """Read Publish Shorts' durable topic ledger so Wisdom avoids cross-format reuse."""
    path = Path("analytics/topic_history.json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except Exception as exc:
        print(f"Publish topic history unavailable; continuing with Wisdom history only: {exc}")
        return []
    if not isinstance(payload, list):
        return []
    entries = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        value = clean(item.get("topic"), 200)
        title = clean(item.get("title"), 120)
        if value or title:
            entries.append({
                "topic": value,
                "title": title,
                "topic_key": clean(item.get("normalized"), 120),
            })
    return entries


def evaluate_story_quality(story, gemini_client=None):
    """Second-pass editorial gate using the active generation client when available."""
    narration = story.get("narration", "")
    first_person = bool(re.search(r"\b(I|I'm|I've|I'd|my|me|we|our|ours)\b", narration, re.I))
    if not first_person:
        raise RuntimeError("Narration lacks the required first-person storytelling voice")

    review_prompt = f'''
You are the independent editor for a US-culture Wisdom Shorts channel. Review this
proposed script strictly. It must feel distinct from generic viral trivia / Publish
Shorts and tell one warm first-person story about a common US phrase, family saying,
custom, or household rule.

Return JSON only:
{{"hook":1,"first_person_voice":1,"naturalness":1,"factual_caution":1,"originality":1,"progression":1,"payoff":1,"notes":"brief reason"}}
Score each numeric field from 1 to 10. Be strict. Factual_caution is high only when
claims are carefully phrased, not when a confident but unsupported origin is asserted.
Originality is high only if this is a specific familiar US saying/custom rather than
generic trivia. Reject formulaic grandma openings if the rest of the script feels
templated. The first sentence must earn attention, the story must progress, and the
ending must give a concrete answer. Do not reward length alone.

TOPIC: {story.get("topic", "")}
TITLE: {story.get("title", "")}
NARRATION: {narration}
'''
    reviewer = gemini_client or client()
    response = reviewer.models.generate_content(
        model=MODEL,
        contents=review_prompt,
        config={"temperature": 0.1, "response_mime_type": "application/json"},
    )
    review = json.loads(response.text)
    dimensions = ("hook", "first_person_voice", "naturalness", "factual_caution",
                  "originality", "progression", "payoff")
    scores = {key: float(review.get(key, 0) or 0) for key in dimensions}
    # Keep factual reliability strict, but avoid rejecting every usable draft because
    # the model-editor is subjective about individual style dimensions.
    minimum_scores = {
        "hook": 5,
        "first_person_voice": 6,
        "naturalness": 5,
        "factual_caution": 7,
        "originality": 6,
        "progression": 5,
        "payoff": 5,
    }
    failures = [
        f"{key}={scores[key]:g}"
        for key in dimensions
        if scores[key] < minimum_scores[key]
    ]
    if failures:
        raise RuntimeError(
            "Editorial quality gate failed (" + ", ".join(failures) + "): "
            + clean(review.get("notes", "No editor notes"), 300)
        )
    print("Editorial quality gate passed: " + json.dumps(scores, sort_keys=True))
    return scores

def is_duplicate_topic(candidate, history):
    # Compare against both Wisdom's own history and Publish Shorts' durable ledger.
    history = list(history) + load_publish_topic_history()
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
        "\nAlready used Wisdom topics. Do NOT create the same idea, even with different wording:\n"
        + "\n".join(f"- {item}" for item in used)
        if used
        else "\nNo previous Wisdom topics have been used yet.\n"
    )
    publish_history = load_publish_topic_history()
    publish_values = []
    for entry in publish_history:
        for key in ("topic", "title"):
            value = clean(entry.get(key), 180)
            if value and value not in publish_values:
                publish_values.append(value)
    publish_history_block = (
        "\nPublish Shorts topics to avoid reusing across formats:\n"
        + "\n".join(f"- {item}" for item in publish_values[-160:])
        if publish_values else "\nNo Publish Shorts topic ledger available.\n"
    )
    base_prompt = """
You are the dedicated WRITER for the channel format WISDOM SHORTS. This format is
deliberately separate from Publish Shorts: never write broad viral trivia, strange
science/fact reveals, sensational mystery stories, object experiments, or generic
"you won't believe this" entertainment. This channel is about familiar American
language and everyday culture: things US people actually say, grandma/grandpa
sayings, family rules, idioms, old-fashioned advice, manners, childhood warnings,
school expressions, household customs, and the ordinary reasons behind them.

Choose ONE specific, widely recognizable US phrase, saying, rule, or custom and
explain what it means, why people say it, or what its documented cultural/history/
practical origin is. Prefer topics an American viewer might have heard at home or
growing up. Avoid niche trivia and do not make up an origin. If a phrase has several
possible origins or the origin is uncertain, say that plainly and explain what is
actually supported instead of inventing a neat story.

VOICE AND POV:
Narrate in a warm, conversational FIRST-PERSON point of view, like someone telling
a friend what they grew up hearing and what they later learned. The script should
feel like a personal discovery, not a documentary narrator or listicle. A framing
like "My grandma used to say..." is one option, NOT a mandatory formula. Rotate
naturally among frames such as:
- a saying a grandparent or parent repeated;
- something the narrator heard as a kid and misunderstood;
- a phrase the narrator caught themselves using;
- a household rule that finally made sense;
- a common expression the narrator looked up after wondering why;
- a familiar piece of advice whose real explanation surprised them.
Do not claim a specific personal memory as verified fact; use the first-person
voice as a relatable storytelling frame and avoid overly detailed invented biography.
Do not start every script with "My grandma used to say". Avoid repeating the same
opening structure used by recent Wisdom scripts.

STORY SHAPE:
- 80-95 spoken words total; approximately 30-38 seconds.
- The first sentence immediately names the familiar phrase/rule and creates a
  curiosity gap or contradiction.
- Use first-person language naturally ("I", "my", "we", "our") throughout.
- Move from familiar memory/belief -> genuine question -> evidence-supported
  explanation -> satisfying takeaway.
- Hold the clearest explanation until the final third, without hiding the answer
  through fake suspense.
- End with a specific, memorable meaning or practical reason.
- Narration must work with stock footage alone and make sense without visuals.
- Use natural US conversational English, contractions, short sentences, no jargon.

ORIGINALITY:
The underlying subject must differ from every Wisdom topic and every Publish Shorts
topic supplied below. A new title, wording, example, or angle on the same underlying
idea is still a duplicate. Choose a different phrase/custom, not just a different
hook. The "topic_key" must be a concise 2-6 content-word identifier of the actual
underlying subject, not a generic label such as "grandma sayings".

DO NOT use politics, celebrities, medical advice, conspiracy, fearbait, lists,
countdowns, "Did you know?", "Today we're going to", AI references, or a second topic.
Do not present folklore as established fact. If the origin is uncertain, explicitly
qualify it in natural language.

TITLE:
Curiosity-driven for US viewers, preferably 35-65 characters when natural. Make the
phrase or custom recognizable. No ALL CAPS, fake shock, misleading claims, or
generic clickbait.

Return JSON only with this schema:
{"title":"...","topic":"...","topic_key":"...","narration":"...","search_queries":["...","...","..."],"visual_queries":["..."]}

search_queries: exactly 3 concrete stock-footage searches, 3-6 words each.
visual_queries: 16-18 ordered, distinct visual beats that follow the narration
chronologically. Each query is 3-7 words and depicts a concrete object, action,
person, or setting relevant to that spoken beat. No generic filler such as
"american lifestyle", "happy family", "person thinking", "stock footage", or
"everyday life". Do not imply visuals can prove a historical claim.
""" + history_block + publish_history_block + performance_guidance()

    max_attempts = 9
    retry_feedback = ""
    rejected_topics = []
    topic_lanes = [
        "familiar household rules and the practical reason behind them",
        "parent or grandparent advice that has a real everyday explanation",
        "American manners and small social customs people learn growing up",
        "schoolyard expressions or childhood routines, avoiding disputed phrase origins",
        "ordinary family habits around meals, guests, chores, or bedtime",
        "common American sayings whose meaning is clear even if their origin is uncertain",
        "everyday etiquette people follow without remembering who taught them",
        "a familiar childhood warning and the practical concern behind it",
        "a common phrase used in conversation, focusing on modern meaning rather than origin",
    ]
    for attempt in range(max_attempts):
        story = None
        lane = topic_lanes[attempt % len(topic_lanes)]
        try:
            # Use a fresh Gemini client per candidate attempt. Reusing a client after
            # a failed request can leave its underlying HTTP transport closed; using
            # the same live client for generation and editorial review also avoids
            # short-lived temporary clients in the review gate.
            c = client()
            response = c.models.generate_content(
                model=MODEL,
                contents=(
                    base_prompt
                    + "\n\nTOPIC LANE FOR THIS ATTEMPT: "
                    + lane
                    + "\nPrefer a concrete household custom or practical everyday explanation. "
                    + "Do not default to phrase-origin trivia. Avoid idiom etymologies and folklore "
                    + "unless the origin is well-supported; when uncertain, explain current meaning "
                    + "or practical use instead.\n"
                    + retry_feedback
                ),
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
                    f"Duplicate topic rejected across Wisdom/Publish history: {story['topic']} | key={story['topic_key']}"
                )
            story["editorial_scores"] = evaluate_story_quality(story, c)
            return story
        except Exception as exc:
            if story and (story.get("topic") or story.get("topic_key")):
                rejected = {
                    "topic": clean(story.get("topic"), 200),
                    "topic_key": clean(story.get("topic_key"), 120),
                    "title": clean(story.get("title"), 120),
                }
                if rejected not in rejected_topics:
                    rejected_topics.append(rejected)

            if attempt == max_attempts - 1:
                raise

            reason = clean(exc, 400)
            retry_feedback = (
                "\n\nRETRY CORRECTION (mandatory; the previous draft failed validation):\n"
                f"- Failure: {reason}\n"
                f"- For the next attempt, follow this topic lane: {topic_lanes[(attempt + 1) % len(topic_lanes)]}.\n"
                "- Generate a genuinely different candidate; do not rephrase any rejected subject.\n"
                "- Do not choose a phrase-origin story if a practical household custom or familiar social rule fits.\n"
                "- Aim for 88-92 spoken words so the narration safely lands inside the required 80-95 range. "
                "Count the narration words before returning JSON.\n"
                "- Keep all 3 search queries and 16-18 ordered visual queries.\n"
            )
            if rejected_topics:
                retry_feedback += (
                    "Rejected subjects that must NOT be used again (same subject with a new title still counts):\n"
                    + "\n".join(
                        f"- {item['topic']} | key: {item['topic_key']} | title: {item['title']}"
                        for item in rejected_topics[-7:]
                    )
                    + "\n"
                )
            print(
                f"Story generation retry {attempt + 1}/{max_attempts}: "
                f"{type(exc).__name__}: {exc}"
            )
            time.sleep(2 + min(attempt, 4))
    raise RuntimeError("Story generation failed after all retries")


def synthesize(text, output):
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    source = clean(text, limit=3000)
    if not source:
        raise RuntimeError("Cannot synthesize empty Everyday Wisdom narration")

    pipeline = KPipeline(lang_code="a")
    word_count = len(source.split())
    print(f"Kokoro single-pass narration | words={word_count} | voice={VOICE}")

    # Submit the complete narration once; do not split into word-count chunks
    # or insert artificial pauses between separately synthesized sections.
    audio_parts = []
    for result in pipeline(source, voice=VOICE, speed=1.0, split_pattern=r"\n+"):
        audio = result[2] if isinstance(result, tuple) else result.audio
        if audio is None:
            continue
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        if audio.size:
            audio_parts.append(audio)
    if not audio_parts:
        raise RuntimeError("Kokoro returned no audio for the complete narration")

    audio = np.concatenate(audio_parts)
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
                "scale=2160:3840:force_original_aspect_ratio=increase,"
                "crop=2160:3840,setsar=1,fps=60,format=yuv420p",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
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

WISDOM_CAPTION_EMPHASIS_WORDS = {
    "never", "always", "secret", "truth", "why", "how", "but", "because",
    "actually", "impossible", "dangerous", "mistake", "wrong", "hidden",
    "nobody", "everyone", "nothing", "everything", "first", "last", "only",
    "stop", "wait", "imagine", "remember", "suddenly", "instantly", "free",
    "dead", "death", "brain", "fear", "money", "life", "love", "real",
    "shocking", "proven", "fails", "works", "secretly", "turns", "until",
}


def _wisdom_caption_emphasized(item):
    token = _normalize_caption_token(item.get("word", ""))
    return token in WISDOM_CAPTION_EMPHASIS_WORDS or (len(token) >= 8 and token.isalpha())


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
        overrides = ""
        if _wisdom_caption_emphasized(item):
            size = 99
            angle = -4 if index % 2 == 0 else 4
            # Start at 90% scale and pop to 100% over 70 ms. The ASS
            # alignment and margins remain unchanged, preserving caption position.
            overrides = f"\\fs{size}\\frz{angle}\\fscx90\\fscy90\\t(0,70,\\fscx100\\fscy100)"
        lines.append(
            f"Dialogue: 0,{_ass_time(item['start'])},{_ass_time(item['end'])},PublishWisdom,,0,0,0,,"
            f"{{\\c{_publish_ass_color(index)}{overrides}}}{_ass_escape(item['word'])}"
        )
    ass_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Narration-synced captions created: {ass_path} | words={len(aligned_words)}")
    return ass_path

def build_audio_filter(duration):
    """Keep narration upfront while mixing the fixed, low-volume Blade Runner bed."""
    fade_out_start = max(0.0, float(duration) - 1.0)
    return (
        f"[1:a]aresample=48000,volume={NARRATION_VOLUME:.3f}[narration];"
        f"[2:a]aresample=48000,volume={BACKGROUND_MUSIC_VOLUME:.3f},"
        f"afade=t=in:st=0:d=1,"
        f"afade=t=out:st={fade_out_start:.3f}:d=1[music];"
        "[narration][music]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
    )


def render(clips, audio, output, duration, narration):
    ass_path = create_animated_captions(narration, duration, audio)
    subtitle_filter = f"subtitles='{ass_path.resolve()}'"
    visual_concat = _make_2_5_second_visual_segments(clips, duration)
    music_path = BACKGROUND_MUSIC_PATH
    if not music_path.is_file():
        raise RuntimeError(f"Everyday Wisdom background soundtrack is missing: {music_path}")
    print(
        f"Background music: {music_path.name} | volume={BACKGROUND_MUSIC_VOLUME:.0%} "
        f"| narration volume={NARRATION_VOLUME:.0%}"
    )

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(visual_concat),
            "-i", str(audio),
            "-stream_loop", "-1", "-i", str(music_path),
            "-filter_complex",
            f"[0:v]{subtitle_filter}[v];{build_audio_filter(duration)}",
            "-map", "[v]", "-map", "[a]",
            "-t", f"{duration:.3f}",
            "-r", "60",
            "-c:v", "libx264", "-preset", "veryfast",
            "-b:v", "120M", "-maxrate", "120M", "-bufsize", "240M",
            "-c:a", "aac", "-b:a", "384k",
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            str(output),
        ],
        check=True,
    )


def validate_final_video(path):
    """Fail closed unless Everyday Wisdom renders the agreed 4K/60 H.264 master."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,avg_frame_rate,codec_name,pix_fmt,bit_rate",
            "-of", "json", str(path),
        ],
        check=True, capture_output=True, text=True,
    )
    streams = json.loads(result.stdout).get("streams") or []
    if not streams:
        raise RuntimeError("Final Everyday Wisdom video has no video stream")
    stream = streams[0]
    width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
    fps_text = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"
    try:
        numerator, denominator = (int(part) for part in fps_text.split("/", 1))
        fps = numerator / denominator if denominator else 0.0
    except (TypeError, ValueError):
        fps = 0.0
    codec = str(stream.get("codec_name") or "")
    pixel_format = str(stream.get("pix_fmt") or "")
    bitrate = float(stream.get("bit_rate") or 0) / 1_000_000
    print(
        f"Final video quality: {width}x{height} | {fps:.3f} FPS | "
        f"{codec}/{pixel_format} | {bitrate:.2f} Mbps measured "
        f"(120 Mbps target)"
    )
    errors = []
    if (width, height) != (2160, 3840):
        errors.append(f"expected 2160x3840, got {width}x{height}")
    if abs(fps - 60.0) > 0.05:
        errors.append(f"expected 60 FPS, got {fps:.3f}")
    if codec != "h264":
        errors.append(f"expected H.264, got {codec or 'unknown'}")
    if pixel_format != "yuv420p":
        errors.append(f"expected yuv420p, got {pixel_format or 'unknown'}")
    if bitrate <= 0:
        errors.append("could not measure encoded video bitrate")
    if errors:
        raise RuntimeError("Everyday Wisdom video failed upload quality gate: " + "; ".join(errors))
    print("Everyday Wisdom 4K/60 H.264 upload quality gate passed.")


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
    validate_final_video(video)

    video_id = upload(video, story)

    # Save YouTube success before attempting Meta. The shared publisher records
    # per-platform status and retries Instagram/Facebook independently.
    title, description, _ = build_caption(story)
    publish_state = {
        "video_id": str(video_id),
        "uploaded": True,
        "status": "partial",
        "topic": story["topic"],
        "title": title,
        "youtube": {"status": "published", "enabled": True, "video_id": str(video_id)},
    }
    (RUN_ROOT / "publish_state.json").write_text(
        json.dumps(publish_state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    from social_publish import publish_social_reels
    social_result = publish_social_reels(str(video), title, description, {}, str(RUN_ROOT))
    print("META PUBLICATION SUMMARY: " + json.dumps(social_result, ensure_ascii=False))

    # Analytics is best-effort: never turn a successful YouTube upload into a failed run.
    try:
        os.environ["MINT_WORKFLOW_PROFILE"] = "wisdom"
        from youtube_analytics import record_upload
        record_upload(
            video_id,
            story["topic"],
            story["title"],
            str(RUN_ROOT),
            production_metadata={"workflow": "everyday_wisdom"},
        )
    except Exception as exc:
        print(f"WARNING: Everyday Wisdom analytics registration failed: {exc}")
    (RUN_ROOT / "publish.json").write_text(
        json.dumps(
            {
                "video_id": video_id,
                "topic": story["topic"],
                "uploaded": True,
                "social": social_result,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"EVERYDAY WISDOM COMPLETE: {video_id}")


if __name__ == "__main__":
    main()
