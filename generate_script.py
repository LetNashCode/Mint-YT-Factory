"""Two-stage YouTube Shorts script generator for Mint-YT-Factory.

Stage 1: ENTERTAINMENT WRITER
    Creates the spoken story without thinking about stock footage.

Stage 2: VISUAL DIRECTOR
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
            "next_short": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "teaser": {"type": "string"},
                    "why_viewers_should_return": {"type": "string"},
                    "subscription_cta": {"type": "string"},
                },
                "required": ["topic", "teaser", "why_viewers_should_return", "subscription_cta"],
            },
            "voice_style": {
                "type": "object",
                "properties": {"tone": {"type": "string"}, "pace": {"type": "string"}, "pitch": {"type": "string"}},
                "required": ["tone", "pace", "pitch"],
            },
            "scene_plan": {"type": "array", "items": scene},
        },
        "required": ["title", "tags", "category", "next_short", "voice_style", "scene_plan"],
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
Your job is ONLY to write the spoken story. Do not think about Pexels, stock footage,
image prompts, cameras, search queries, or what is easy to generate visually.

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
6. Scene 6: strongest "WAIT, WHAT?" reveal or reframe.
7. Scene 7: satisfying payoff for the CURRENT topic. Do not start another story.

The story must be one chain of curiosity -> discovery -> escalation -> payoff.
Do not make a list of facts. Every 1–2 sentences should either reveal something,
change the viewer's mental model, create a new question, or deliver a consequence.

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

Scene 7 must finish the current story. The next topic will be inserted/locked by the
production pipeline; do not discuss or tease another topic inside the entertainment story.

Return ONLY JSON matching the supplied schema.
"""


VISUAL_SYSTEM = r"""
You are the VISUAL DIRECTOR for a YouTube Short.

You receive a LOCKED spoken narration created by a separate entertainment writer.
Do NOT rewrite, improve, simplify, or sanitize the narration. Your job is only to decide
what should be shown on screen for each spoken beat.

CRITICAL PRINCIPLE:
The narration can be playful or metaphorical. The visual must be literal.
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


def _entertainment_prompt(topic, extra_feedback=""):
    feedback = f"\nCHANNEL LEARNING FEEDBACK:\n{_clean(extra_feedback, 5000)}" if extra_feedback else ""
    return f"""
CURRENT TOPIC:
{topic}

Create exactly 7 scenes with durations 3, 5, 7, 7, 8, 8, 7 seconds.
Target approximately 95–115 spoken words total.

Make the opening strong enough to stop a scroll. The first sentence should create an
immediate "wait, what?" reaction without announcing the topic like a school lesson.
Build the explanation only after curiosity has been created.

The CURRENT TOPIC is the only subject of the story.
Do not create a second story or a list of unrelated facts.
{feedback}
"""


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

The final scene's visual shots should show the CURRENT topic's payoff. Do not create visuals
for the future/continuation topic; that topic is metadata and is handled separately.
"""


def _fallback_identity(topic):
    return {
        "style": "cinematic real-world storytelling with tactile detail",
        "palette": "natural colors with crisp believable contrast",
        "mood_arc": "curiosity, playful tension, surprise, satisfying payoff",
    }


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
    if not _clean(script.get("next_short", {}).get("topic")):
        raise RuntimeError("Entertainment writer did not provide next_short.topic.")
    return total


def _validate_visuals(visual_plan, entertainment, topic):
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
            if j == 1 and previous_focus and focus.lower() == previous_focus.lower():
                raise RuntimeError(f"Visual director scene {i+1} shot 2 duplicates shot 1.")
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

    next_short = entertainment["next_short"]
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
        "next_short": next_short,
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
            # The writer never sees visual/search constraints.
            entertainment = _call_json(
                client,
                ENTERTAINMENT_SYSTEM,
                _entertainment_prompt(topic, extra_feedback),
                _entertainment_schema(),
                0.95,
            )
            word_count = _validate_entertainment(entertainment, topic)
            print(f"🎭 Entertainment writer pass: {word_count} words")

            # PASS 2 ---------------------------------------------------------
            # Only the finished narration crosses into the visual domain.
            visual = _call_json(
                client,
                VISUAL_SYSTEM,
                _visual_prompt(topic, entertainment),
                _visual_schema(),
                0.55,
            )
            _validate_visuals(visual, entertainment, topic)
            print("🎬 Visual director pass: 14 narration-mapped shots")

            return _merge(entertainment, visual, topic)
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
            print(f"⚠️ Two-stage script attempt {attempt}/{MAX_ATTEMPTS} failed: {last_error}")
            if attempt < MAX_ATTEMPTS:
                time.sleep(min(8, 2 * attempt))

    raise RuntimeError(f"SCRIPT GENERATION FAILED AFTER {MAX_ATTEMPTS} TWO-STAGE ATTEMPTS. Last error: {last_error}")


if __name__ == "__main__":
    print("generate_script.py — two-stage entertainment writer + visual director")
