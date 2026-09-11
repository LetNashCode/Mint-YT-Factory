"""Narration-first Story Shorts generator for the independent second production line."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from . import entertainment as _base

MIN_WORDS = 80
MAX_WORDS = 115
SCENE_WORD_BUDGETS = ((8,18),(8,18),(8,18),(8,18),(8,18),(8,18),(10,25))
STORY_FORMATS = (
    {"name":"rise_from_nothing","direction":"Show the person before success, the obstacle, the decisive attempt, and the consequence. Never turn it into a generic motivational speech."},
    {"name":"one_decision","direction":"Build around one decision that changed the person's direction. Delay the consequence until late in the Short."},
    {"name":"before_they_were_famous","direction":"Start with the ordinary, rejected, broke, unknown, or overlooked version of the person. Reveal the famous identity after curiosity is established."},
    {"name":"impossible_odds","direction":"Open with the apparent impossibility, then reveal how the person responded. Keep the human stakes concrete."},
    {"name":"strange_turning_point","direction":"Center the story on an unusual event, coincidence, failure, encounter, or setback that changed the person's life."},
)
GENERIC_OPENERS = re.compile(r"^(?:today|here(?:'s| is)|welcome back|hey guys|guys|listen up|okay guys|alright guys)", re.I)


def _load_recent_history(limit=30):
    path = Path(__file__).resolve().parent.parent / "story_topic_history.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        return [x for x in rows[-limit:] if isinstance(x, dict)] if isinstance(rows, list) else []
    except Exception:
        return []


def _format_for(topic, number_hint=0):
    digest = hashlib.sha256(f"{topic}|{number_hint}".encode()).digest()
    return STORY_FORMATS[int.from_bytes(digest[:4], "big") % len(STORY_FORMATS)]


def _words(text):
    return re.findall(r"\b[\w'-]+\b", str(text or ""))


def _validate_story(scenes):
    if len(scenes) != 7:
        raise RuntimeError("Story script must contain exactly 7 scenes.")
    total = sum(len(_words(s.get("narration", ""))) for s in scenes)
    if not MIN_WORDS <= total <= MAX_WORDS:
        raise RuntimeError(f"Story narration length {total} outside {MIN_WORDS}-{MAX_WORDS} words.")
    for i, (low, high) in enumerate(SCENE_WORD_BUDGETS):
        count = len(_words(scenes[i].get("narration", "")))
        if count < low or count > high:
            raise RuntimeError(f"Story Scene {i+1} has {count} words; expected {low}-{high}.")
    all_text = " ".join(str(s.get("narration", "")) for s in scenes)
    if GENERIC_OPENERS.search(all_text):
        raise RuntimeError("Story script contains a generic social-media opener.")
    if not re.search(r"\bsubscribe\b", scenes[-1].get("narration", ""), re.I):
        raise RuntimeError("Story Scene 7 must contain a subscribe CTA.")
    if not re.search(r"\bfollow\b", scenes[-1].get("narration", ""), re.I):
        raise RuntimeError("Story Scene 7 must contain a follow CTA.")


def _clean_scenes(scenes):
    for scene in scenes:
        narration = _base._clean(scene.get("narration", ""))
        narration = re.sub(r"^(?:today|welcome back|hey guys|guys),?\s+", "", narration, flags=re.I)
        scene["narration"] = narration
        scene["subtitle_text"] = narration
        scene["visual_dependency"] = "none"
        for visual in scene.get("visuals") or []:
            if isinstance(visual, dict):
                visual["spoken_line"] = narration
                visual["visual_action"] = "Support the spoken story emotionally and contextually; the narration carries the story."
                visual["visual_dependency"] = "none"
    return scenes


def generate_script(topic, config, research=None, extra_feedback=""):
    from google import genai
    from google.genai import types
    import time

    topic = _base._clean(topic)
    if not topic:
        raise RuntimeError("Story topic is empty.")
    recent = _load_recent_history()
    number_hint = len(recent) + 1
    story_format = _format_for(topic, number_hint)
    recent_topics = [str(x.get("topic", "")).strip() for x in recent if x.get("topic")]
    recent_people = [str(x.get("person", "")).strip() for x in recent if x.get("person")]
    client = genai.Client(api_key=_base._api_key())

    prompt = f"""STORY SHORTS MODE — NARRATION FIRST.

SUBJECT: {topic}
STORY FORMAT: {story_format['name']}
FORMAT DIRECTION: {story_format['direction']}

Create exactly 7 scenes for a vertical YouTube Short about this person.
The story must stand on narration alone. Stock footage/images are atmosphere and context only; viewers must never need a particular image, face, object, map, screenshot, or on-screen text to understand the story.

TARGET: {MIN_WORDS}-{MAX_WORDS} spoken words, naturally paced for roughly 28-38 seconds. Every line must move the story forward.
SCENE BANDS: 1={SCENE_WORD_BUDGETS[0][0]}-{SCENE_WORD_BUDGETS[0][1]}, 2={SCENE_WORD_BUDGETS[1][0]}-{SCENE_WORD_BUDGETS[1][1]}, 3={SCENE_WORD_BUDGETS[2][0]}-{SCENE_WORD_BUDGETS[2][1]}, 4={SCENE_WORD_BUDGETS[3][0]}-{SCENE_WORD_BUDGETS[3][1]}, 5={SCENE_WORD_BUDGETS[4][0]}-{SCENE_WORD_BUDGETS[4][1]}, 6={SCENE_WORD_BUDGETS[5][0]}-{SCENE_WORD_BUDGETS[5][1]}, 7={SCENE_WORD_BUDGETS[6][0]}-{SCENE_WORD_BUDGETS[6][1]}.

STORY ARC:
- Scene 1: hard hook. Start inside the most surprising moment or contradiction. Do not start with the person's name as a biography introduction unless the name itself creates curiosity.
- Scene 2: establish who the person was and what was at stake.
- Scene 3: introduce the obstacle, rejection, failure, or impossible situation.
- Scene 4: show the decision, action, encounter, or attempt that changed the trajectory.
- Scene 5: escalate. Give one concrete consequence or setback before the payoff.
- Scene 6: reveal the turning point and what it led to. Avoid a generic motivational lecture.
- Scene 7: land the emotional payoff in one or two sentences, then naturally invite viewers to subscribe and follow for another remarkable story.

FACTUALITY:
- This is a factual story about a real person. Do not invent dialogue, private thoughts, dates, locations, achievements, causes, or dramatic details.
- Do not use quotation marks unless the quote is widely established and you are confident it is authentic; paraphrase instead whenever possible.
- If a famous anecdote is disputed, omit it rather than presenting it as fact.
- Do not exaggerate "overnight success" or claim one event caused an entire career unless that is genuinely supported.
- Prefer concrete, broadly established facts over trivia.

STYLE:
- Cinematic, conversational, emotionally engaging, concise.
- Sound like someone telling a friend an unbelievable true story, not reading Wikipedia.
- Use short sentences, contrast, curiosity gaps, and specific stakes.
- No "welcome back," "today we're talking about," "in this video," or generic motivational filler.
- Do not say "wait until the end" or similar empty retention bait.
- Do not mention stock footage or visuals.
- Do not make the story dependent on captions.

RECENT PEOPLE — avoid repeating them:
{chr(10).join('- ' + x for x in recent_people[-15:]) or '- none'}
RECENT STORY SUBJECTS — avoid repeating or closely mirroring:
{chr(10).join('- ' + x for x in recent_topics[-15:]) or '- none'}

Return the normal production JSON schema. Put the person's name in the topic/title metadata where appropriate, but keep the narration story-first.
{extra_feedback}
"""

    last_error = None
    for attempt in range(_base.MAX_ATTEMPTS):
        try:
            retry = f"\nFix this validation error without changing the subject: {last_error}" if last_error else ""
            response = client.models.generate_content(
                model=_base.MODEL_NAME,
                contents=prompt + retry,
                config=types.GenerateContentConfig(
                    system_instruction=_base.SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_json_schema=_base._build_schema(),
                    temperature=0.9,
                ),
            )
            raw = getattr(response, "text", None)
            if not raw:
                raise RuntimeError("Gemini returned an empty story script.")
            data = _base._parse(raw)
            result = _base._normalize(data, topic, enforce_word_contract=False)
            scenes = _clean_scenes(result.get("scene_plan") or [])
            _validate_story(scenes)
            result["scene_plan"] = scenes
            result["story_format"] = story_format["name"]
            result["story_format_direction"] = story_format["direction"]
            result["story_visual_mode"] = "narration_atmosphere_v1"
            result["story_factuality_policy"] = "real-person-facts-no-invented-dialogue"
            result["story_word_target"] = {"min": MIN_WORDS, "max": MAX_WORDS}
            result["visual_dependency"] = "none"
            total = sum(len(_words(s.get("narration", ""))) for s in scenes)
            print(f"📖 Story Shorts narration validated: {total} words | format={story_format['name']}")
            return result
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt + 1 < _base.MAX_ATTEMPTS:
                print(f"⚠️ Story script attempt {attempt + 1} rejected: {last_error}")
                time.sleep(2)
    raise RuntimeError(f"STORY SCRIPT GENERATION FAILED after bounded retries. Last error: {last_error}")
