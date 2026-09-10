"""Riddles Shorts narration generator."""
from __future__ import annotations

# Keep the production implementation centralized in the existing module.
# The active repository implementation is intentionally patched at runtime by
# sitecustomize.py for the Riddles Shorts quality layer.
from . import entertainment as _base

MIN_WORDS = 60
MAX_WORDS = 95

# Runtime sitecustomize.py owns the tolerant production scene bands. These
# defaults remain compatible when the module is imported outside production.
SCENE_WORD_BUDGETS = (
    (7, 14), (9, 18), (7, 14), (7, 14), (6, 12), (3, 8), (12, 16)
)


def _clean(value):
    return _base._clean(value)


def _words(text):
    return _base._words(text)


def _normalize_phrase(text):
    import re
    return re.sub(r"[^a-z0-9]+", " ", _clean(text).lower()).strip()


def _sentence_parts(text):
    import re
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", _clean(text)) if s.strip()]


def _remove_next_topic_leak(scenes, next_topic):
    """Remove only an obvious future-topic sentence from Scenes 1-6.

    Gemini occasionally copies next_short.topic into the narration even though
    the prompt forbids it. A deterministic repair is safer than spending all
    bounded retries on a metadata/narration collision. We only remove a whole
    sentence when that sentence contains the exact normalized next topic and
    reads like a future-topic/continuation beat. If it looks like a genuine
    clue, return False so the normal regeneration guard remains active.
    """
    import re
    key = _normalize_phrase(next_topic)
    if not key:
        return False
    changed = False
    future_markers = re.compile(
        r"\b(next|coming|later|after this|afterwards|up next|another|"
        r"following|future|we(?:'ll| will) see|you(?:'ll| will) see|"
        r"stay tuned|part 2|next short|next video|tomorrow)\b", re.I
    )
    for index, scene in enumerate(scenes[:6]):
        narration = _clean(scene.get("narration", ""))
        sentences = _sentence_parts(narration)
        if not sentences:
            continue
        kept = []
        removed = False
        for sentence in sentences:
            if key in _normalize_phrase(sentence):
                if future_markers.search(sentence) or len(sentences) > 1:
                    removed = True
                    changed = True
                    continue
                # A single clue sentence containing the next topic is not safe
                # to rewrite automatically; let the normal validator regenerate.
                kept.append(sentence)
            else:
                kept.append(sentence)
        if removed:
            repaired = _clean(" ".join(kept))
            if repaired:
                scene["narration"] = repaired
                scene["subtitle_text"] = repaired
            else:
                return False
    return changed


def _validate_internal_novelty(scenes):
    import re
    all_text = " ".join(str(s.get("narration", "")) for s in scenes if isinstance(s, dict))
    if re.search(r"^(?:today(?:'s| is)? riddle|here(?:'s| is) (?:today(?:'s)? )?riddle|welcome back|hey guys|guys|listen up|okay guys|alright guys)", all_text, re.I):
        raise RuntimeError("Riddle script contains a banned generic opener.")
    grams = {}
    for index, scene in enumerate(scenes):
        words = re.findall(r"[a-z0-9']+", str(scene.get("narration", "")).lower())
        for i in range(max(0, len(words) - 3)):
            gram = tuple(words[i:i + 4])
            if len(set(gram)) < 2:
                continue
            grams.setdefault(gram, set()).add(index)
    if [g for g, v in grams.items() if len(v) >= 2]:
        raise RuntimeError("Riddle narration repeats a 4-word phrase across scenes; regenerate with a different structure.")
    if sum(str(s.get("narration", "")).count("?") for s in scenes) > 2:
        raise RuntimeError("Riddle contains too many repeated question beats.")


def generate_script(topic, config, research=None, extra_feedback=""):
    """Generate a narration-first riddle while keeping next-topic ownership in Scene 7."""
    # Import the current production implementation when available. This file
    # remains a thin compatibility layer; sitecustomize applies the personality,
    # pacing and continuation policies to the live module.
    import hashlib
    import json
    import time
    from pathlib import Path
    from google import genai
    from google.genai import types
    try:
        from riddle_personality import choose_personality
    except Exception:
        choose_personality = None

    topic = _clean(topic)
    if not topic:
        raise RuntimeError("Riddle topic is empty.")
    history_path = Path(__file__).resolve().parent.parent / "interactive_topic_history.json"
    try:
        rows = json.loads(history_path.read_text(encoding="utf-8"))
        recent = [x for x in rows[-20:] if isinstance(x, dict)] if isinstance(rows, list) else []
    except Exception:
        recent = []
    number_hint = len(recent) + 1
    profile_names = ("cold_open_challenge", "tiny_story", "false_confidence", "word_ambush", "impossible_choice", "reverse_logic", "listener_test", "mini_mystery")
    profile = profile_names[int.from_bytes(hashlib.sha256(f"{topic}|{number_hint}".encode()).digest()[:4], "big") % len(profile_names)]
    recent_topics = [str(x.get("topic", "")).strip() for x in recent if x.get("topic")]
    recent_answers = [str(x.get("answer", "")).strip() for x in recent[-10:] if x.get("answer")]
    personality = choose_personality(topic, "", number_hint) if choose_personality else {"name": "dynamic", "direction": "Use a distinctive conversational performance without changing the riddle's logic.", "speed": 1.0}
    client = genai.Client(api_key=_base._api_key())
    recent_block = "\n".join(f"- {x}" for x in recent_topics[-12:]) or "- none available"
    answer_block = ", ".join(recent_answers[-8:]) or "none available"
    prompt = f"""RIDDLES SHORTS MODE — NARRATION FIRST.
CURRENT RIDDLE: {topic}
CREATIVE PROFILE: {profile}
PERSONALITY: {personality['name']}
PERFORMANCE DIRECTION: {personality['direction']}

Create exactly 7 spoken scenes. The viewer must solve the NEW riddle with the phone face-down; visuals are atmosphere only. Target {MIN_WORDS}-{MAX_WORDS} total spoken words.
SCENE BANDS: 1 7-14; 2 9-18; 3 7-14; 4 7-14; 5 6-12; 6 3-8 with a conversational 3…2…1; 7 12-16.

CRITICAL CONTINUATION RULE: next_short is metadata only. NEVER copy next_short.topic, next_short.teaser, or any future-topic wording into Scenes 1-6. Scene 7 is the only scene allowed to contain the continuation bridge. Do not mention tomorrow or a fixed schedule. The CTA must ask viewers to subscribe and follow for the answer in the next Short.

Avoid generic openers, visual-dependent clues, repeated structures, and recent conceptual neighbors.
RECENT TOPICS:
{recent_block}
RECENT ANSWERS:
{answer_block}
Return only the normal JSON schema."""

    last_error = None
    attempts = 0
    while attempts < _base.MAX_ATTEMPTS:
        try:
            retry = f"\nFix previous error: {last_error}. Change wording AND structural approach while preserving the selected personality." if last_error else ""
            response = client.models.generate_content(
                model=_base.MODEL_NAME,
                contents=prompt + retry,
                config=types.GenerateContentConfig(
                    system_instruction=_base.SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_json_schema=_base._build_schema(),
                    temperature=0.95,
                ),
            )
            raw = getattr(response, "text", None)
            if not raw:
                raise RuntimeError("Gemini returned an empty riddle script.")
            data = _base._parse(raw)
            result = _base._normalize(data, topic, enforce_word_contract=False)
            scenes = result.get("scene_plan") or []
            if len(scenes) != 7:
                raise RuntimeError("Riddle script must contain exactly 7 scenes.")

            next_short = result.get("next_short") or {}
            next_topic = _clean(next_short.get("topic"))
            if not next_topic:
                raise RuntimeError("Gemini did not provide next_short.topic.")

            # Repair obvious metadata leakage before the hard Scene 7 boundary
            # check. This preserves the quality guard while avoiding needless
            # failure when Gemini adds a clearly future-looking sentence.
            _remove_next_topic_leak(scenes, next_topic)

            # Never silently allow the exact future topic to survive in Scenes 1-6.
            next_key = _normalize_phrase(next_topic)
            for scene in scenes[:6]:
                if next_key and next_key in _normalize_phrase(scene.get("narration", "")):
                    raise RuntimeError("Next topic appeared before Scene 7.")

            total = sum(len(_words(s.get("narration", ""))) for s in scenes)
            if not MIN_WORDS <= total <= MAX_WORDS:
                raise RuntimeError(f"Riddle narration length {total} outside optimized {MIN_WORDS}-{MAX_WORDS} range.")
            for index, (low, high) in enumerate(SCENE_WORD_BUDGETS):
                count = len(_words(scenes[index].get("narration", "")))
                if count < low or count > high:
                    raise RuntimeError(f"Riddle Scene {index + 1} has {count} words; expected {low}-{high} for pacing.")

            _validate_internal_novelty(scenes)
            result["riddle_creative_profile"] = profile
            result["riddle_mechanic_policy"] = "rotating_mechanic"
            result["riddle_novelty_guard"] = "internal_phrase_and_structure"
            result["riddle_personality"] = dict(personality)
            result["riddle_personality_name"] = personality["name"]
            result["riddle_personality_direction"] = personality["direction"]
            result["riddle_personality_version"] = "v2_prompt_and_tts"
            print(f"🧩 Riddles Shorts narration validated: {total} words | profile={profile} | personality={personality['name']} | personality_prompt=ACTIVE | novelty_guard=PASS")
            return result
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            attempts += 1
            if attempts < _base.MAX_ATTEMPTS:
                print(f"⚠️ Riddle script attempt {attempts} rejected: {last_error}")
                time.sleep(2)
    raise RuntimeError(f"RIDDLE SCRIPT GENERATION FAILED after bounded retries. Last error: {last_error}")
