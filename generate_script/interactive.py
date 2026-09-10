"""Narration-first Riddles Shorts generator with anti-repetition controls."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from . import entertainment as _base

MIN_WORDS = 60
MAX_WORDS = 95
SCENE_WORD_BUDGETS = ((8, 14), (10, 18), (8, 14), (8, 14), (8, 12), (5, 8), (13, 15))

# Deliberately rotate the *storytelling architecture*, not just synonyms.
# The riddle remains narration-first, but the listener should not hear the same
# seven-scene template every time.
CREATIVE_PROFILES = (
    {
        "name": "cold_open_challenge",
        "hook": "Open with a provocative claim or challenge before stating the riddle.",
        "flow": "challenge -> question -> obvious answer -> contradiction -> commitment -> countdown -> CTA",
    },
    {
        "name": "tiny_story",
        "hook": "Begin with a tiny everyday situation that naturally creates the puzzle.",
        "flow": "micro-scenario -> question -> first interpretation -> twist -> commitment -> countdown -> CTA",
    },
    {
        "name": "false_confidence",
        "hook": "Make the listener confidently expect one answer, then verbally break that assumption.",
        "flow": "confident setup -> question -> obvious answer -> assumption break -> commitment -> countdown -> CTA",
    },
    {
        "name": "word_ambush",
        "hook": "Make one ordinary word or phrase carry the hidden twist; do not rely on visual clues.",
        "flow": "intriguing phrase -> question -> literal reading -> alternate meaning -> commitment -> countdown -> CTA",
    },
    {
        "name": "impossible_choice",
        "hook": "Frame the puzzle as a choice between two tempting interpretations before revealing the trap.",
        "flow": "choice -> question -> option A -> option B / reversal -> commitment -> countdown -> CTA",
    },
    {
        "name": "reverse_logic",
        "hook": "Lead from a strange consequence backward toward the riddle instead of using a standard setup.",
        "flow": "strange consequence -> question -> expected logic -> reversal -> commitment -> countdown -> CTA",
    },
    {
        "name": "listener_test",
        "hook": "Talk directly to the listener as if testing a quick mental reflex, without generic filler.",
        "flow": "direct test -> question -> instinct -> trap -> commitment -> countdown -> CTA",
    },
    {
        "name": "mini_mystery",
        "hook": "Treat the riddle like a tiny mystery with one missing piece, not like a classic riddle recital.",
        "flow": "mystery -> question -> clue interpretation -> reveal of the trap -> commitment -> countdown -> CTA",
    },
)

GENERIC_OPENERS = re.compile(
    r"^(?:today(?:'s| is)? riddle|here(?:'s| is) (?:today(?:'s)? )?riddle|welcome back|hey guys|guys|listen up|okay guys|alright guys)",
    re.I,
)


def _feedback(extra=""):
    return (
        "RIDDLES SHORTS ONLY. This is an audio/narration-led puzzle, not a visual puzzle. "
        "The viewer must be able to solve the riddle with the phone face-down; stock visuals are atmosphere only and must never carry a required clue. "
        "Do not require a visual clue, visual inspection, on-screen text, or an object in the footage to solve the NEW riddle. "
        "A previous riddle answer may be revealed, but the NEW answer must remain locked. "
        "The ending must ask viewers to subscribe and follow for the NEW answer in the next Short; never say tomorrow, next day, or imply a fixed schedule. "
        f"Target {MIN_WORDS}-{MAX_WORDS} total spoken words, with strict scene pacing bands. Every sentence must earn its place. "
        "Every episode must feel like a different mini-game, not a synonym rewrite of the previous episode. "
        + str(extra or "")
    )


def _load_recent_history(limit=20):
    path = Path(__file__).resolve().parent.parent / "interactive_topic_history.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            return []
        return [x for x in rows[-limit:] if isinstance(x, dict)]
    except Exception:
        return []


def _profile_for(topic, number_hint=0):
    digest = hashlib.sha256(f"{topic}|{number_hint}".encode("utf-8")).digest()
    return CREATIVE_PROFILES[int.from_bytes(digest[:4], "big") % len(CREATIVE_PROFILES)]


def _normalized_words(text):
    return re.findall(r"[a-z0-9']+", str(text or "").lower())


def _validate_internal_novelty(scenes):
    """Reject scripts that sound mechanically repeated inside the same Short."""
    all_text = " ".join(str(s.get("narration", "")) for s in scenes if isinstance(s, dict))
    if GENERIC_OPENERS.search(all_text):
        raise RuntimeError("Riddle script contains a banned generic opener.")

    # Repeating the same 4-word phrase across multiple scenes is usually a sign
    # Gemini has fallen back to a template. Ignore very short function-word grams.
    grams = {}
    for index, scene in enumerate(scenes):
        words = _normalized_words(scene.get("narration", ""))
        for i in range(max(0, len(words) - 3)):
            gram = tuple(words[i:i + 4])
            if len(set(gram)) < 2:
                continue
            grams.setdefault(gram, set()).add(index)
    repeated = [gram for gram, scene_ids in grams.items() if len(scene_ids) >= 2]
    if repeated:
        raise RuntimeError("Riddle narration repeats a 4-word phrase across scenes; regenerate with a different structure.")

    # The new riddle question should be stated once, not restated in later scenes.
    question_marks = sum(str(s.get("narration", "")).count("?") for s in scenes)
    if question_marks > 2:
        raise RuntimeError("Riddle contains too many repeated question beats.")


def generate_script(topic, config, research=None, extra_feedback=""):
    from google import genai
    from google.genai import types
    import time

    topic = _base._clean(topic)
    if not topic:
        raise RuntimeError("Riddle topic is empty.")

    recent = _load_recent_history()
    number_hint = len(recent) + 1
    profile = _profile_for(topic, number_hint)
    recent_topics = [str(x.get("topic", "")).strip() for x in recent if x.get("topic")]
    recent_answers = [str(x.get("answer", "")).strip() for x in recent[-10:] if x.get("answer")]

    client = genai.Client(api_key=_base._api_key())
    recent_block = "\n".join(f"- {x}" for x in recent_topics[-12:]) or "- none available"
    answer_block = ", ".join(recent_answers[-8:]) or "none available"
    prompt = f"""RIDDLES SHORTS MODE — NARRATION FIRST.
CURRENT RIDDLE: {topic}

CREATIVE PROFILE FOR THIS EPISODE: {profile['name']}
Required hook direction: {profile['hook']}
Required story flow: {profile['flow']}
Use this profile as a structural constraint, not as wording to copy.

Create exactly 7 scenes. Return the normal production JSON schema.
The Short must work as a spoken mini-game. The narration is the product; stock media is only mood/context and must never be needed to understand or solve the riddle.
Target {MIN_WORDS}-{MAX_WORDS} total spoken words. Aim for roughly 19-30 seconds at a natural energetic pace. Do not pad for length.

SCENE PACING BANDS — these are maximum/minimum guidance, not filler targets:
- Scene 1: 8-14 words. Use the selected profile's hook architecture; if a previous answer exists, reveal it briefly and pivot.
- Scene 2: 10-18 words. State the NEW riddle clearly. Reach the actual question immediately.
- Scene 3: 8-14 words. Advance the selected profile's first interpretation or clue.
- Scene 4: 8-14 words. Deliver exactly one trap, reversal, or assumption break.
- Scene 5: 8-12 words. Force the viewer to lock in their FIRST answer.
- Scene 6: 5-8 words. Brief pressure ending with conversational 3…2…1. Never 10-to-1.
- Scene 7: 13-15 words. Preserve the NEW answer payoff gap and use a short subscribe/follow CTA for the answer in the next Short.

MECHANIC DIVERSITY:
Choose the mechanism that genuinely fits the current riddle. Rotate among wording traps, double meanings, lateral logic, expectation reversals, misconception traps, causal misdirection, category shifts, temporal ambiguity, and psychological assumptions. Do NOT default to the same mechanic just because it worked before.

LANGUAGE DIVERSITY:
Do not make every episode sound like "Can you solve this? ... Most people think ... But ... Lock in your answer ... Three, two, one." Use different sentence shapes, verbs, rhythm, and conversational framing while keeping the same retention objectives.
Do not open with a generic greeting. Do not repeat the riddle question in multiple scenes. Do not use filler.

RECENT TOPICS — avoid conceptual neighbors, not merely exact duplicates:
{recent_block}

RECENT ANSWERS — avoid reusing the same answer domain/object type when possible:
{answer_block}

Do not paraphrase any recent riddle. Do not reuse a recent answer if a fresh answer is possible. Prefer a different object/domain, different ambiguity, and different sentence architecture from recent episodes.
Keep every clue solvable from spoken words alone. Avoid visual-puzzle formats and phrases like "look at this", "you can see", "notice the picture", or clues that depend on footage.
Do not reveal, spell out, strongly hint at, or explain the NEW answer. Do not accidentally leak it through examples or hypothetical guesses.
Avoid generic filler: "welcome back", "today's riddle", "here's today's riddle", "stay tuned", "guys", "don't forget to like and subscribe".
{_feedback(extra_feedback)}
"""
    last_error = None
    attempts = 0
    while attempts < _base.MAX_ATTEMPTS:
        try:
            retry = (
                f"\nFix previous error: {last_error}. IMPORTANT: change the wording AND the structural approach; do not make a cosmetic rewrite."
                if last_error else ""
            )
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
            data.setdefault("next_short", {"topic": "riddle answer reveal", "teaser": "answer reveal"})
            original_boundary = _base._ensure_scene7_boundary
            original_bridge = _base._validate_natural_bridge
            _base._ensure_scene7_boundary = lambda narration, next_topic: _base._clean(narration)
            _base._validate_natural_bridge = lambda narration, next_topic: "riddle continuation"
            try:
                result = _base._normalize(data, topic, enforce_word_contract=False)
            finally:
                _base._ensure_scene7_boundary = original_boundary
                _base._validate_natural_bridge = original_bridge
            scenes = result.get("scene_plan") or []
            if len(scenes) != 7:
                raise RuntimeError("Riddle script must contain exactly 7 scenes.")
            total = sum(len(_base._words(s.get("narration", ""))) for s in scenes)
            if not MIN_WORDS <= total <= MAX_WORDS:
                raise RuntimeError(f"Riddle narration length {total} outside optimized {MIN_WORDS}-{MAX_WORDS} range.")
            for index, (low, high) in enumerate(SCENE_WORD_BUDGETS):
                count = len(_base._words(scenes[index].get("narration", "")))
                if count < low or count > high:
                    raise RuntimeError(f"Riddle Scene {index + 1} has {count} words; expected {low}-{high} for pacing.")

            previous_answer = ""
            previous_number = None
            m = re.search(r'Reveal Riddle #(\d+) answer naturally: "([^"]+)"', str(extra_feedback or ""), re.I)
            if m:
                previous_number = int(m.group(1))
                previous_answer = _base._clean(m.group(2))
                first = scenes[0]
                first_narration = _base._clean(first.get("narration", ""))
                if previous_answer.lower() not in first_narration.lower():
                    reveal_line = f"Last answer: {previous_answer}. Did you get it? "
                    first["narration"] = _base._clean(reveal_line + first_narration)
                first_narration = _base._clean(scenes[0].get("narration", ""))
                if previous_answer.lower() not in first_narration.lower():
                    raise RuntimeError(f"Previous riddle answer must be revealed in Scene 1: {previous_answer!r}")
                total = sum(len(_base._words(s.get("narration", ""))) for s in scenes)
                if total > MAX_WORDS:
                    raise RuntimeError(f"Riddle narration length {total} outside optimized {MIN_WORDS}-{MAX_WORDS} range after reveal insertion.")

            _validate_internal_novelty(scenes)
            result["riddle_creative_profile"] = profile["name"]
            result["riddle_mechanic_policy"] = "rotating_mechanic"
            result["riddle_novelty_guard"] = "internal_phrase_and_structure"
            result["riddle_recent_topic_context"] = recent_topics[-12:]
            print(
                f"🧩 Riddles Shorts narration validated: {total} words | "
                f"profile={profile['name']} | novelty_guard=PASS"
                + (f" | Riddle #{previous_number} answer revealed in Scene 1" if previous_answer else "")
            )
            return result
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            attempts += 1
            if attempts < _base.MAX_ATTEMPTS:
                print(f"⚠️ Riddle script attempt {attempts} rejected: {last_error}")
                time.sleep(2)
    raise RuntimeError(f"RIDDLE SCRIPT GENERATION FAILED after bounded retries. Last error: {last_error}")
