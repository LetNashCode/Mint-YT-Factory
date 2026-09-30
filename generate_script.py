"""Blueprint-led Publish Shorts generation pipeline for Mint-YT-Factory.

Stage 1: STORY BLUEPRINT
    Creates the spoken story without thinking about stock footage.

Stage 2: ENTERTAINMENT WRITER
    Receives the locked narration and translates each beat into literal,
    searchable visuals for Pexels / image generation.

The two jobs are deliberately separated so visual-search constraints cannot
make the narration dry, scientific, or unnatural.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid

from google import genai
from google.genai import types

MODEL_NAME = "gemini-flash-lite-latest"
SCENE_COUNT = 7
VISUALS_PER_SCENE = 2
SCENE_DURATIONS = [3, 5, 7, 7, 8, 8, 7]
MAX_ATTEMPTS = 5

CAMERAS = {"close_up", "medium", "wide", "macro", "top_down", "side", "aerial", "orbit"}
ANIMATIONS = {"zoom_in", "zoom_out", "pan_left", "pan_right", "rotate", "parallax", "highlight", "hold"}
PURPOSES = {"hook", "question", "explanation", "example", "mindblowing_fact", "ending"}
TONES = {"curious", "tense", "calm", "awe", "playful", "urgent", "satisfied"}
RETENTION = {"open_loop", "escalation", "payoff", "reframe", "curiosity_gap", "pattern_break", "emotional_release", "closure"}
TRANSITIONS = {"hard_cut", "whip_pan", "match_cut", "dissolve", "none"}
MUSIC_CUES = {"intro", "build", "swell", "drop", "fade_out", "none"}
IMAGE_STYLES = {"cinematic_photograph", "macro_photography", "realistic_3d_render"}

BANNED_LECTURE_PHRASES = (
    "did you know", "have you ever wondered", "today we're going to", "in this video",
    "according to scientists", "the scientific explanation is", "this phenomenon occurs because",
    "therefore", "thus", "hence", "in conclusion", "the reason is simply because",
)

JARGON = {
    "thermodynamics", "coefficient", "equilibrium", "wavelength", "viscosity", "nucleation",
    "cavitation", "electromagnetic", "differential", "oscillation", "macroscopic",
}


def _clean(value, maximum=None):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:maximum] if maximum else text


def _words(text):
    return re.findall(r"\b[\w'-]+\b", _clean(text))


def _api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY environment variable is missing.")
    return key


def _parse(text):
    text = _clean(text)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.I).strip()
        text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def _blueprint_schema():
    return {
        "type": "object",
        "properties": {
            "central_mystery": {"type": "string"},
            "viewer_question": {"type": "string"},
            "misconception_or_assumption": {"type": "string"},
            "first_reveal": {"type": "string"},
            "mechanism": {"type": "string"},
            "unexpected_consequence": {"type": "string"},
            "final_payoff": {"type": "string"},
            "emotional_effect": {"type": "string"},
        },
        "required": [
            "central_mystery", "viewer_question", "misconception_or_assumption",
            "first_reveal", "mechanism", "unexpected_consequence",
            "final_payoff", "emotional_effect",
        ],
    }


BLUEPRINT_SYSTEM = r"""
You are the STORY ARCHITECT for a high-retention YouTube Shorts channel.
Your only job is to design the underlying story before narration is written.

Do NOT write scenes, narration, visual prompts, titles, tags, CTAs, or future topics.
Do NOT think about stock footage.

For the CURRENT TOPIC, identify the one genuinely interesting mystery and construct a
single curiosity chain:
1. what strange observable behavior starts the story,
2. what question it creates in the viewer's mind,
3. what assumption the viewer may initially have,
4. the first useful reveal,
5. the simple physical mechanism,
6. the unexpected consequence or twist,
7. the final surprising payoff that changes the viewer's understanding.

The payoff must be truthful, concrete, and actually connected to the central mystery.
Avoid lists of facts. Avoid generic educational summaries. The blueprint must give the
narration writer something specific to build toward.

Return ONLY JSON matching the supplied schema.
"""


def _blueprint_prompt(topic, extra_feedback=""):
    feedback = f"\\nCHANNEL LEARNING FEEDBACK:\\n{_clean(extra_feedback, 5000)}" if extra_feedback else ""
    return f"""
CURRENT TOPIC:
{topic}

Design the story blueprint for one approximately 40-second Short.
The viewer should begin with an observable mystery and finish with a satisfying mental reframe.
The final payoff should be the strongest surprising TRUE idea in the story.
Do not invent a second topic.
{feedback}
"""


def _entertainment_schema():
    scene = {
        "type": "object",
        "properties": {
            "scene": {"type": "integer"},
            "narration": {"type": "string"},
            "purpose": {"type": "string"},
            "retention_purpose": {"type": "string"},
            "emotional_tone": {"type": "string"},
        },
        "required": ["scene", "narration", "purpose", "retention_purpose", "emotional_tone"],
    }
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "category": {"type": "string"},
            "hook_type": {"type": "string"},
            "story_format": {"type": "string"},
            "payoff_type": {"type": "string"},
            "tease_type": {"type": "string"},
            "voice_style": {
                "type": "object",
                "properties": {"tone": {"type": "string"}, "pace": {"type": "string"}, "pitch": {"type": "string"}},
                "required": ["tone", "pace", "pitch"],
            },
            "scene_plan": {"type": "array", "items": scene},
        },
        "required": ["title", "tags", "category", "hook_type", "story_format", "payoff_type", "tease_type", "voice_style", "scene_plan"],
    }


def _visual_schema():
    visual = {
        "type": "object",
        "properties": {
            "segment": {"type": "integer"},
            "spoken_line": {"type": "string"},
            "visual_focus": {"type": "string"},
            "visual_action": {"type": "string"},
            "must_show": {"type": "array", "items": {"type": "string"}},
            "must_not_show": {"type": "array", "items": {"type": "string"}},
            "camera": {"type": "string"},
            "animation": {"type": "string"},
            "zoom_strength": {"type": "string"},
            "motion_intensity": {"type": "string"},
            "visual_complexity": {"type": "string"},
            "image_style": {"type": "string"},
            "lighting": {"type": "string"},
            "color_palette": {"type": "string"},
            "image_prompt": {"type": "string"},
            "visual_impact": {"type": "integer"},
        },
        "required": [
            "segment", "spoken_line", "visual_focus", "visual_action", "must_show", "must_not_show",
            "camera", "animation", "zoom_strength", "motion_intensity", "visual_complexity",
            "image_style", "lighting", "color_palette", "image_prompt", "visual_impact",
        ],
    }
    return {
        "type": "object",
        "properties": {
            "visual_identity": {
                "type": "object",
                "properties": {"style": {"type": "string"}, "palette": {"type": "string"}, "mood_arc": {"type": "string"}},
                "required": ["style", "palette", "mood_arc"],
            },
            "visual_continuity": {
                "type": "object",
                "properties": {
                    "recurring_subjects": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "type": {"type": "string"}, "appearance": {"type": "string"}, "continuity": {"type": "string"}}, "required": ["name", "type", "appearance", "continuity"]}},
                    "recurring_objects": {"type": "array", "items": {"type": "string"}},
                    "recurring_environment": {"type": "string"},
                    "continuity_rules": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["recurring_subjects", "recurring_objects", "recurring_environment", "continuity_rules"],
            },
            "thumbnail_prompt": {"type": "string"},
            "music": {"type": "object", "properties": {"search": {"type": "string"}, "arc": {"type": "string"}}, "required": ["search", "arc"]},
            "scene_plan": {"type": "array", "items": {"type": "object", "properties": {
                "scene": {"type": "integer"}, "visual_priority": {"type": "string"}, "transition": {"type": "string"},
                "music_cue": {"type": "string"}, "sfx_cue": {"type": "object", "properties": {"term": {"type": "string"}, "at_ms": {"type": "integer"}}, "required": ["term", "at_ms"]},
                "visuals": {"type": "array", "items": visual},
            }, "required": ["scene", "visual_priority", "transition", "music_cue", "sfx_cue", "visuals"]}},
        },
        "required": ["visual_identity", "visual_continuity", "thumbnail_prompt", "music", "scene_plan"],
    }


ENTERTAINMENT_SYSTEM = r"""
You are the ENTERTAINMENT WRITER for a high-retention YouTube Shorts channel.
Your job is ONLY to write the spoken story from the supplied STORY BLUEPRINT. Do not select
future topics and do not think about Pexels, stock footage, image prompts, cameras,
search queries, or what is easy to generate visually.

Write like a clever, mischievous friend showing someone a weird everyday mystery.
The viewer should feel: "Wait... seriously?!"

VOICE:
- conversational spoken English
- playful, quirky, confident and energetic
- natural rhythm: short punchy lines mixed with longer conversational lines
- vivid everyday comparisons and occasional light humor
- simple language first
- technical terms only when genuinely useful, and explain them immediately
- never sound like a textbook, documentary, classroom teacher, or AI assistant

STORY:
1. Scene 1: hit immediately with the strangest observable behavior. No greeting or setup.
2. Scene 2: make the mystery stranger and open a curiosity loop.
3. Scene 3: reveal the first piece of the explanation.
4. Scene 4: demonstrate the mechanism in an easy-to-understand way.
5. Scene 5: reveal a consequence the viewer probably did not expect.
6. Scene 6: strongest "WAIT, WHAT?" reveal, reframe, and satisfying payoff for the CURRENT topic.
7. Scene 7: finish the CURRENT topic cleanly. Production will replace this final scene with
its own single continuation bridge after the story is validated. Do not mention any future topic.

The story must be one chain of curiosity -> discovery -> escalation -> reversal -> mindblowing-but-true payoff.
Do not make a list of facts.

ORIGINALITY:
- Every hook must be creatively distinct from recent channel hooks, not merely reworded.
- Rotate hook mechanisms: contradiction, challenge, impossible observation, mini-story, prediction, confession, visual mystery, counterintuitive claim, consequence-first, or pattern-break.
- Never reuse the same opening structure or first 6–8 meaningful words from a recent Short.
- Never recycle a previous topic, near-duplicate topic, or the same underlying fact with cosmetic wording changes.

PAYOFF:
- Design the strongest surprising TRUE payoff first, then build the story toward it.
- The payoff should change the viewer’s mental model or reveal an unexpectedly important consequence.
- Avoid fake sensationalism. The underlying fact must be accurate and defensible.

ENDING:
- Scene 6 must contain the complete CURRENT-topic payoff.
- Scene 7 is reserved for the production-owned ending handoff and must not repeat the current topic.
- Return tease_type only as a creative metadata label. Do not write the bridge itself and do not name a future topic.

ENTERTAINMENT RULES:
- Start with the behavior, not the topic name or a definition.
- Use personality. A playful comparison is better than sterile exposition.
- Surprise before explaining.
- Prefer "you" and everyday experiences when natural.
- Do not over-explain obvious transitions.
- Never pad the story to hit a word count.

NEVER START WITH:
"Did you know", "Have you ever wondered", "Today we're going to", "In this video",
"Let's talk about", "According to scientists".

NEVER USE LECTURE FILLER:
"therefore", "thus", "hence", "in conclusion", "the scientific explanation is",
"this phenomenon occurs because".

A metaphor is allowed when it makes the story more fun. Do NOT turn the entire narration
into metaphors. Keep the actual facts clear and natural.

Scene 6 must finish the current story. Scene 7 is an ending handoff slot controlled by the
production pipeline. Do not mention the current topic again in Scene 7 and do not invent a
second future topic.

Return ONLY JSON matching the supplied schema.
"""


VISUAL_SYSTEM = r"""
You are the VISUAL DIRECTOR for a YouTube Short.

You receive a LOCKED spoken narration created by a separate entertainment writer.
Do NOT rewrite, improve, simplify, or sanitize the narration. Your job is only to decide
what should be shown on screen for each spoken beat.

CRITICAL PRINCIPLE:
The narration can be playful or metaphorical. The visual must be literal.

RIDDLE / PUZZLE ANSWER-SPOILER LOCK:
If a riddle answer and reveal scene are supplied, the answer is forbidden from every pre-reveal shot. Before the reveal, use neutral thinking/suspense visuals only: a thinking person, puzzled expression, brainstorming, generic question context, or countdown context. Do NOT show the answer, an identifiable representation of it, or an answer-related object. The answer becomes allowed only at and after the reveal.
Translate the meaning into a real physical scene a camera could actually capture.

For every scene create EXACTLY TWO distinct shots.
Shot 1 establishes the exact physical situation.
Shot 2 advances it through a new physical action, state change, reveal, consequence,
reaction, comparison, or viewpoint. Never give two generic shots of the same object.

For every shot identify:
- spoken_line: the exact short narration beat this shot supports
- visual_focus: the main visible subject
- visual_action: what physically happens or what physical state is visible
- must_show: 3–6 concrete visible details
- must_not_show: 3–8 likely wrong/unrelated things
- image_prompt: a literal 15–40 word camera-ready description

IMPORTANT:
If the narration says something metaphorical like "the candle is digging its own grave",
do NOT create a literal grave or fantasy scene. Show the actual physical candle tunneling:
a flame burning down around the wick while the outer wax remains higher.

If an idea is invisible, show its observable physical consequence or the physical context
that demonstrates it. Do not invent microscopic characters, magical particles, abstract
science art, equations, diagrams, fake laboratory scenes, glowing symbols, or symbolic
animations unless the narration explicitly requires a real object of that kind.

SEARCHABILITY:
The visual focus and action must be specific enough to search on a stock-footage site.
Prefer concrete actions such as melting, boiling, freezing, cutting, cracking, bubbling,
spilling, sticking, rubbing, squeezing, dropping, spinning, opening, closing, expanding,
shrinking, changing color, or changing texture.

IMAGE PROMPTS:
Write as if directing a real camera operator. Literal objects, physical actions,
location/context, believable scale, realistic materials, natural lighting.
No metaphorical actions. No text, labels, logos, UI, watermarks, diagrams, arrows,
or equations unless explicitly required by the narration.

CONTINUITY:
Keep recurring subjects/objects visually consistent when they remain part of the story.
Do not introduce random people, places, food, animals, landscapes, laboratories, or props
just to make a shot interesting. Every visible element must support the spoken beat.

Return ONLY JSON matching the supplied schema.
"""


def _call_json(client, system, prompt, schema, temperature):
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
            temperature=temperature,
        ),
    )
    text = getattr(response, "text", None)
    if not text:
        raise RuntimeError("Gemini returned an empty response.")
    return _parse(text)


def _entertainment_prompt(topic, blueprint, extra_feedback=""):
    feedback = f"\nCHANNEL LEARNING FEEDBACK:\n{_clean(extra_feedback, 5000)}" if extra_feedback else ""
    return f"""
CURRENT TOPIC:
{topic}

STORY BLUEPRINT — SOURCE OF TRUTH:
{json.dumps(blueprint, ensure_ascii=False)}

Create exactly 7 scenes with durations 3, 5, 7, 7, 8, 8, 7 seconds.
Target approximately 95–115 spoken words total.

Make the opening strong enough to stop a scroll. The first sentence should create an
immediate "wait, what?" reaction without announcing the topic like a school lesson.
Build the explanation only after curiosity has been created.

CREATIVE REQUIREMENTS:
- hook_type must identify the actual hook mechanism.
- story_format must describe the narrative mechanism, not simply "seven_scene_story".
- payoff_type must identify the actual payoff mechanism.
- tease_type must identify the ending bridge mechanism.
- Optimize for retention and shareability: the viewer should feel compelled to finish and tell someone else.

The CURRENT TOPIC is the only subject of the story.
Do not create a second story or a list of unrelated facts.
{feedback}
"""


def _critic_schema():
    return {
        "type": "object",
        "properties": {
            "overall_score": {"type": "integer"},
            "hook_score": {"type": "integer"},
            "curiosity_score": {"type": "integer"},
            "escalation_score": {"type": "integer"},
            "payoff_score": {"type": "integer"},
            "originality_score": {"type": "integer"},
            "ending_score": {"type": "integer"},
            "shareability_score": {"type": "integer"},
            "major_problem": {"type": "string"},
            "rewrite_instruction": {"type": "string"},
            "approved": {"type": "boolean"},
        },
        "required": [
            "overall_score","hook_score","curiosity_score","escalation_score",
            "payoff_score","originality_score","ending_score","shareability_score",
            "major_problem","rewrite_instruction","approved",
        ],
    }


CRITIC_SYSTEM = r"""
You are the RETENTION + VIRALITY CRITIC for a YouTube Shorts channel.
Judge a finished narration ruthlessly from the viewer's perspective.

This is not a prediction that a video will go viral. It is a pre-publish creative quality gate.

Reject scripts that:
- open generically or explain before creating curiosity
- reuse a recent hook mechanism too closely
- repeat a recent topic or underlying fact
- move from setup to explanation without escalation
- reveal the interesting answer too early
- use fake sensationalism instead of a genuinely surprising fact
- have a weak, obvious, or forgettable payoff
- end like a generic educational video
- sound like an AI, textbook, or documentary
- contain filler or repeated facts

A strong script should create an unanswered question immediately, repeatedly change the viewer's mental model,
build toward a surprising true reveal, and finish with a memorable payoff.

Score each category 0-10.
Approve only if:
overall >= 8,
hook >= 8,
curiosity >= 8,
payoff >= 8,
originality >= 8,
ending >= 7,
shareability >= 7,
and there is no major problem.

Return ONLY JSON.
"""


def _critic_script(client, topic, entertainment, recent_context):
    prompt = f"""
CURRENT TOPIC:
{topic}

RECENT CHANNEL CREATIVE MEMORY:
{_clean(recent_context, 6000)}

CANDIDATE SCRIPT:
{json.dumps(entertainment, ensure_ascii=False)}

Evaluate the candidate. Compare the hook and topic against recent memory at the IDEA level,
not just exact wording. A cosmetic rewrite of a recent hook or topic is not original.

If it fails, give one concrete rewrite instruction that targets the biggest weakness.
Do not ask for a completely different topic unless the current topic itself is duplicated.
"""
    return _call_json(client, CRITIC_SYSTEM, prompt, _critic_schema(), 0.25)


def _creative_memory_validation(topic, entertainment):
    try:
        from creative_memory import validate_candidate
        return validate_candidate(topic, entertainment)
    except Exception as exc:
        print(f"⚠️ Creative memory validation unavailable: {exc}")
        return {"ok": True}


def _recent_creative_context():
    try:
        from creative_memory import build_generation_context
        return build_generation_context()
    except Exception:
        return "Creative memory unavailable; use maximum originality and avoid generic hooks."


def _visual_prompt(topic, entertainment):
    scenes = entertainment["scene_plan"]
    lines = []
    for scene in scenes:
        lines.append(f"SCENE {scene['scene']} | PURPOSE: {scene['purpose']} | NARRATION: {scene['narration']}")
    joined = "\n".join(lines)
    return f"""
CURRENT TOPIC: {topic}

LOCKED NARRATION — DO NOT REWRITE IT:
{joined}

Create the visual plan for exactly these 7 narration scenes.
Each scene must contain exactly 2 shots.
The narration is the source of truth. Do not add new facts or new story beats.

For every shot, make the visual directly useful to understanding the spoken words.
If the line is playful, translate the underlying physical meaning rather than illustrating
the metaphor literally.

Scenes 1–6 should visually support the CURRENT topic and its payoff.
Scene 7 is a production-owned verbal handoff; keep its visuals neutral and continuity-safe.
Do not create visuals for the future/continuation topic; that topic is metadata and is handled separately.
"""


def _fallback_identity(topic):
    return {
        "style": "cinematic real-world storytelling with tactile detail",
        "palette": "natural colors with crisp believable contrast",
        "mood_arc": "curiosity, playful tension, surprise, satisfying payoff",
    }


RETired_SUBJECT_TERMS = {
    "onion", "onions",
}

def _validate_retired_subject_bleed(value, stage):
    """Hard production rule: retired subjects must never enter the current Short."""
    text = _clean(value).lower()
    for term in RETired_SUBJECT_TERMS:
        if re.search(r"\b" + re.escape(term) + r"\b", text):
            raise RuntimeError(
                f"Topic coherence gate rejected retired {term} subject bleed during {stage}."
            )
    return True


def _validate_blueprint(blueprint):

    if not isinstance(blueprint, dict):
        raise RuntimeError("Story blueprint must be an object.")
    required = (
        "central_mystery", "viewer_question", "misconception_or_assumption",
        "first_reveal", "mechanism", "unexpected_consequence",
        "final_payoff", "emotional_effect",
    )
    missing = [key for key in required if not _clean(blueprint.get(key))]
    _validate_retired_subject_bleed(json.dumps(blueprint, ensure_ascii=False), "story blueprint")
    if missing:
        raise RuntimeError("Story blueprint is missing required beats: " + ", ".join(missing))
    # A blueprint that repeats the same sentence for multiple beats is not a story
    # architecture; reject it before spending another model call on narration.
    normalized = [re.sub(r"[^a-z0-9]+", " ", _clean(blueprint[key]).lower()).strip() for key in required]
    duplicates = {value for value in normalized if value and normalized.count(value) > 1}
    if duplicates:
        raise RuntimeError("Story blueprint contains duplicate beats.")
    return True


def _validate_no_future_topic_in_story(script, topic):
    """Hard gate: Scenes 1-6 may not contain the generated continuation topic or its handoff language."""
    next_topic = _clean((script.get("next_short") or {}).get("topic"))
    next_key = re.sub(r"[^a-z0-9]+", " ", next_topic.lower()).strip()
    next_words = {w for w in re.findall(r"[a-z0-9]+", next_topic.lower()) if len(w) >= 4 and w not in {
        "why", "what", "when", "where", "how", "does", "do", "did", "the", "and", "that",
        "this", "with", "from", "into", "your", "about", "happen", "happens", "things",
    }}
    teaser_patterns = (
        r"\band\s+once\s+you\s+know\s+that\b",
        r"\bbut\s+(?:that|this)\s+(?:isn't|is\s+not)\s+the\s+only\b",
        r"\bthere(?:'s|\s+is)\s+another\b",
        r"\bone\s+mystery\s+down\b",
        r"\bnext\s+time\s+you\b",
        r"\bnext\s+(?:comes|up|is|one|mystery|question)\b",
        r"\bkeep\s+an\s+eye\s+out\s+for\s+this\s+one\b",
        r"\bif\s+that\s+surprised\s+you\b",
        r"\bokay,?\s+but\s+that\s+leaves\b",
        r"\bone\s+more\s+mystery\b",
        r"\bthe\s+same\s+(?:idea|trick)\s+(?:shows\s+up|appears)\s+in\b",
        r"\b(?:which\s+)?makes\s+you\s+wonder\s+(?:why|how|what)\b",
        r"\b(?:and\s+)?here'?s\s+(?:where|the)\s+it\s+gets\s+(?:even\s+)?stranger\b",
        r"\bup\s+next\b",
        r"\bcoming\s+next\b",
        r"\bstay\s+tuned\b",
        r"\bpart\s+2\b",
    )
    for index, scene in enumerate((script.get("scene_plan") or [])[:6], start=1):
        narration = _clean(scene.get("narration"))
        normalized = re.sub(r"[^a-z0-9]+", " ", narration.lower()).strip()
        if next_key and next_key in normalized:
            raise RuntimeError(f"Scene {index} contains the generated continuation topic: {next_topic}")
        overlap = next_words & set(re.findall(r"[a-z0-9]+", normalized))
        if len(next_words) >= 2 and len(overlap) >= 2:
            raise RuntimeError(f"Scene {index} appears to reference the generated continuation topic: {next_topic}")
        if any(re.search(pattern, narration, re.I) for pattern in teaser_patterns):
            raise RuntimeError(f"Scene {index} contains a future-topic handoff before Scene 7.")


def _validate_entertainment(script, topic):
    scenes = script.get("scene_plan")
    if not isinstance(scenes, list) or len(scenes) != 7:
        raise RuntimeError("Entertainment writer must return exactly 7 scenes.")
    total = 0
    for i, scene in enumerate(scenes):
        narration = _clean(scene.get("narration"))
        if not narration:
            raise RuntimeError(f"Entertainment scene {i+1} is empty.")
        total += len(_words(narration))
        lower = narration.lower()
        hits = [p for p in BANNED_LECTURE_PHRASES if p in lower]
        if hits:
            raise RuntimeError(f"Entertainment scene {i+1} contains lecture filler: {', '.join(hits)}")
    if total < 80 or total > 130:
        raise RuntimeError(f"Entertainment narration word count {total} is outside 80–130.")
    if _clean(scenes[0].get("narration")).lower().startswith(("did you know", "have you ever wondered", "today we're", "in this video")):
        raise RuntimeError("Entertainment hook is generic.")
    # Continuation is production-owned. The writer never selects or embeds a future topic.
    return total


def _apply_riddle_spoiler_lock(visual_plan, entertainment):
    riddle = entertainment.get("riddle") or {}
    answer = _clean(riddle.get("answer")).lower()
    reveal = int(riddle.get("answer_reveal_scene") or 0)
    terms = {t for t in re.findall(r"[a-z0-9]+", answer) if len(t) >= 3}
    if not answer or not terms or not (1 <= reveal <= SCENE_COUNT):
        return
    for scene_index, scene in enumerate(visual_plan.get("scene_plan") or [], start=1):
        if scene_index >= reveal:
            continue
        for shot_index, visual in enumerate(scene.get("visuals") or []):
            blob = " ".join([_clean(visual.get("visual_focus")), _clean(visual.get("visual_action")), _clean(visual.get("image_prompt")), " ".join(map(str, visual.get("must_show") or []))]).lower()
            if answer in blob or any(re.search(r"\b" + re.escape(t) + r"\b", blob) for t in terms):
                visual["visual_focus"] = "thinking person"
                visual["visual_action"] = "person pauses and thinks about the riddle"
                visual["must_show"] = ["thoughtful human expression", "neutral setting", "no answer object"]
                visual["must_not_show"] = list(dict.fromkeys((visual.get("must_not_show") or []) + [answer]))[:8]
                visual["image_prompt"] = "cinematic thinking person with hand on chin, considering a difficult riddle, suspenseful neutral atmosphere, realistic camera footage, no answer clue or answer object"
                print(f"🔒 Riddle answer spoiler removed from Scene {scene_index} Shot {shot_index + 1}")

def _validate_visuals(visual_plan, entertainment, topic):
    _apply_riddle_spoiler_lock(visual_plan, entertainment)
    scenes = visual_plan.get("scene_plan")
    if not isinstance(scenes, list) or len(scenes) != 7:
        raise RuntimeError("Visual director must return exactly 7 scenes.")
    locked = entertainment["scene_plan"]
    for i, scene in enumerate(scenes):
        visuals = scene.get("visuals")
        if not isinstance(visuals, list) or len(visuals) != 2:
            raise RuntimeError(f"Visual director scene {i+1} must contain exactly 2 shots.")
        narration = locked[i]["narration"].lower()
        previous_focus = ""
        for j, visual in enumerate(visuals):
            focus = _clean(visual.get("visual_focus"))
            action = _clean(visual.get("visual_action"))
            prompt = _clean(visual.get("image_prompt"))
            spoken = _clean(visual.get("spoken_line"))
            if not focus or not prompt:
                raise RuntimeError(f"Visual director scene {i+1} shot {j+1} has missing fields.")
            must_show = visual.get("must_show") or []
            must_not_show = visual.get("must_not_show") or []
            if len(must_show) < 3:
                raise RuntimeError(f"Visual director scene {i+1} shot {j+1} has fewer than 3 required visible details.")
            if len(must_not_show) < 3:
                raise RuntimeError(f"Visual director scene {i+1} shot {j+1} has fewer than 3 forbidden details.")
            # Shot 2 must advance the physical story rather than showing a second
            # static version of the same action.
            if j == 1 and previous_focus and focus.lower() == previous_focus.lower():
                raise RuntimeError(f"Visual director scene {i+1} shot 2 duplicates shot 1.")
            if j == 1:
                prev_action = _clean(visuals[0].get("visual_action")).lower()
                curr_action = action.lower()
                if prev_action and curr_action and prev_action == curr_action:
                    raise RuntimeError(f"Visual director scene {i+1} shot 2 does not advance the physical action.")
            # Repair abstract/invisible beats instead of throwing away a good story.
            if not action:
                action = "visible physical context or consequence"
                visual["visual_action"] = action
            if len(prompt.split()) < 8 or len(prompt.split()) > 60:
                visual["image_prompt"] = f"{focus}, showing {action}, literal real-world physical context matching the narration"
            if spoken:
                overlap = set(re.findall(r"[a-z]{4,}", spoken.lower())) & set(re.findall(r"[a-z]{4,}", narration))
                if len(overlap) < 2 and spoken.lower() not in narration and narration not in spoken.lower():
                    # The narrator is authoritative; bind the shot to its scene rather
                    # than rejecting the complete two-stage generation.
                    visual["spoken_line"] = narration
            previous_focus = focus
    return True


def _merge(entertainment, visual, topic):
    scenes = []
    identity = visual.get("visual_identity") or _fallback_identity(topic)
    continuity = visual.get("visual_continuity") or {
        "recurring_subjects": [], "recurring_objects": [], "recurring_environment": "",
        "continuity_rules": [],
    }
    visual_scenes = visual["scene_plan"]
    for i in range(7):
        src = entertainment["scene_plan"][i]
        vs = visual_scenes[i]
        narration = _clean(src["narration"])
        visuals = []
        durations = [SCENE_DURATIONS[i] // 2, SCENE_DURATIONS[i] - SCENE_DURATIONS[i] // 2]
        for j, raw in enumerate(vs["visuals"]):
            v = dict(raw)
            v["segment"] = j + 1
            v["duration"] = durations[j]
            v["camera"] = v.get("camera") if v.get("camera") in CAMERAS else ("close_up" if j == 0 else "medium")
            v["animation"] = v.get("animation") if v.get("animation") in ANIMATIONS else ("zoom_in" if j == 0 else "pan_right")
            v["zoom_strength"] = _clean(v.get("zoom_strength")) or "subtle"
            v["motion_intensity"] = _clean(v.get("motion_intensity")) or "medium"
            v["visual_complexity"] = _clean(v.get("visual_complexity")) or "moderate"
            v["image_style"] = v.get("image_style") if v.get("image_style") in IMAGE_STYLES else "cinematic_photograph"
            v["lighting"] = _clean(v.get("lighting")) or "natural believable lighting"
            v["color_palette"] = _clean(v.get("color_palette")) or identity.get("palette", "natural colors")
            v["spoken_line"] = _clean(v.get("spoken_line")) or narration
            v["visual_focus"] = _clean(v.get("visual_focus"))
            v["visual_action"] = _clean(v.get("visual_action"))
            v["must_show"] = [_clean(x) for x in v.get("must_show", []) if _clean(x)][:6]
            v["must_not_show"] = [_clean(x) for x in v.get("must_not_show", []) if _clean(x)][:8]
            v["image_prompt"] = _clean(v.get("image_prompt"), 900)
            v["visual_impact"] = max(1, min(10, int(v.get("visual_impact", 8) or 8)))
            v["overlay"] = {"type": "none", "description": ""}
            visuals.append(v)

        words = _words(narration)
        scenes.append({
            "scene": i + 1,
            "purpose": src.get("purpose") if src.get("purpose") in PURPOSES else ("hook" if i == 0 else "ending" if i == 6 else "explanation"),
            "retention_purpose": src.get("retention_purpose") if src.get("retention_purpose") in RETENTION else ("open_loop" if i < 2 else "payoff" if i >= 5 else "escalation"),
            "narration": narration,
            "source_ids": [],
            "subtitle_text": narration,
            "caption_highlights": [{"word": w, "emphasis": "strong"} for w in words[:3]],
            "subtitle_style": "dynamic",
            "emphasis_word": words[0] if words else "",
            "duration": SCENE_DURATIONS[i],
            "pause_after_ms": 0 if i < 6 else 250,
            "emotional_tone": src.get("emotional_tone") if src.get("emotional_tone") in TONES else ("playful" if i in (0, 3) else "curious"),
            "visual_priority": _clean(vs.get("visual_priority")) or "primary",
            "transition": vs.get("transition") if vs.get("transition") in TRANSITIONS else "hard_cut",
            "sfx_cue": vs.get("sfx_cue") if isinstance(vs.get("sfx_cue"), dict) else {"term": "none", "at_ms": 0},
            "music_cue": vs.get("music_cue") if vs.get("music_cue") in MUSIC_CUES else ("intro" if i == 0 else "fade_out" if i == 6 else "build"),
            "confidence": "high",
            "visuals": visuals,
        })

    # Continuation is intentionally empty here. main.py selects and locks the canonical
    # successor after the current story has passed its creative gates.
    next_short = {}
    return {
        "topic": topic,
        "title": _clean(entertainment.get("title"), 70) or topic[:70],
        "description": f"A quick look at {topic} and the everyday mystery behind it.",
        "tags": [_clean(x).lstrip("#") for x in entertainment.get("tags", []) if _clean(x)][:12],
        "category": _clean(entertainment.get("category")) or "science",
        "thumbnail_prompt": _clean(visual.get("thumbnail_prompt"), 700),
        "voice_style": entertainment.get("voice_style") or {"tone": "playful", "pace": "energetic", "pitch": "natural"},
        "music": visual.get("music") or {"search": "playful curious cinematic", "arc": "curiosity build to satisfying payoff"},
        "visual_identity": identity,
        "visual_continuity": continuity,
        "retention_self_check": {"weakest_scene": 4, "reason": "The story escalates from curiosity to physical explanation and payoff."},
        "story_blueprint": entertainment.get("story_blueprint") or {},
        "next_short": next_short,
        "riddle": entertainment.get("riddle") or {},
        "scene_plan": scenes,
        "publishing": {
            "research_verified": False,
            "research_sources_require_verification": False,
            "citations_ready": False,
            "claim_verification_required": False,
            "captions_match_narration": True,
            "semantic_image_prompts": True,
            "fourteen_visuals_required": True,
            "two_stage_script_generation": True,
        },
        "generated_at": int(time.time()),
        "video_id": f"{re.sub(r'[^a-z0-9]+', '-', (_clean(entertainment.get('title')) or topic).lower()).strip('-')[:40]}-{uuid.uuid4().hex[:8]}",
    }


def generate_script(topic, config, research=None, extra_feedback=""):
    """Generate a Short using independent entertainment and visual-director passes."""
    topic = _clean(topic)
    if not topic:
        raise RuntimeError("Topic is empty.")

    client = genai.Client(api_key=_api_key())
    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            # PASS 1 ---------------------------------------------------------
            # Build the story architecture before asking for narration. This separates
            # the creative reasoning from sentence generation and prevents the writer
            # from improvising a weak seven-box story.
            blueprint = _call_json(
                client,
                BLUEPRINT_SYSTEM,
                _blueprint_prompt(topic, extra_feedback),
                _blueprint_schema(),
                0.65,
            )
            _validate_blueprint(blueprint)
            print("🧭 Story blueprint pass: central mystery + escalation + payoff locked")

            # PASS 2 ---------------------------------------------------------
            # The writer receives only the current topic and its locked blueprint.
            # It has no continuation-topic field and therefore cannot author a future topic.
            entertainment = _call_json(
                client,
                ENTERTAINMENT_SYSTEM,
                _entertainment_prompt(topic, blueprint, extra_feedback),
                _entertainment_schema(),
                0.90,
            )
            entertainment["story_blueprint"] = blueprint
            word_count = _validate_entertainment(entertainment, topic)
            _validate_retired_subject_bleed(" ".join(str(s.get("narration") or "") for s in entertainment.get("scene_plan") or []), "narration")
            _validate_no_future_topic_in_story(entertainment, topic)
            print(f"🎭 Entertainment writer pass: {word_count} words")

            # Hard originality gate before spending another model call on visuals.
            memory_check = _creative_memory_validation(topic, entertainment)
            if not memory_check.get("ok", True):
                raise RuntimeError(
                    "Creative memory rejected candidate: "
                    f"topic={memory_check.get('topic_reason')} | hook={memory_check.get('hook_reason')}"
                )

            # PASS 1.5: retention/originality critic
            recent_context = _recent_creative_context()
            critique = _critic_script(client, topic, entertainment, recent_context)
            print("🧠 Creative critic: overall=%s hook=%s payoff=%s originality=%s approved=%s" % (
                critique.get("overall_score"), critique.get("hook_score"),
                critique.get("payoff_score"), critique.get("originality_score"),
                critique.get("approved")
            ))
            thresholds = {
                "overall_score": 8, "hook_score": 8, "curiosity_score": 8,
                "payoff_score": 8, "originality_score": 8, "ending_score": 7,
                "shareability_score": 7,
            }
            failed = [key for key, minimum in thresholds.items() if int(critique.get(key, 0) or 0) < minimum]
            if not bool(critique.get("approved")) or failed:
                raise RuntimeError(
                    "Creative quality gate rejected narration: "
                    + ", ".join(f"{key}<{thresholds[key]}" for key in failed)
                    + f". {critique.get('rewrite_instruction') or critique.get('major_problem') or 'Rewrite for stronger retention.'}"
                )

            # PASS 3 ---------------------------------------------------------
            # Only the finished narration crosses into the visual domain.
            visual = _call_json(
                client,
                VISUAL_SYSTEM,
                _visual_prompt(topic, entertainment),
                _visual_schema(),
                0.55,
            )
            _validate_visuals(visual, entertainment, topic)
            _validate_retired_subject_bleed(json.dumps(visual, ensure_ascii=False), "visual plan")
            print("🎬 Visual director pass: 14 narration-mapped shots")

            return _merge(entertainment, visual, topic)
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
            print(f"⚠️ Two-stage script attempt {attempt}/{MAX_ATTEMPTS} failed: {last_error}")
            if attempt < MAX_ATTEMPTS:
                time.sleep(min(8, 2 * attempt))

    raise RuntimeError(f"SCRIPT GENERATION FAILED AFTER {MAX_ATTEMPTS} TWO-STAGE ATTEMPTS. Last error: {last_error}")


if __name__ == "__main__":
    print("generate_script.py — blueprint + narration + visual director")
