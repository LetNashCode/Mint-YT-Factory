"""Entertainment-first Short storyboard generator for Mint-YT-Factory.

Research is intentionally NOT used in this stage.
The goal is to make the generated Short fun, visual, conversational and
high-retention first. A research/verification layer can be added later.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
import uuid

from google import genai
from google.genai import types

MODEL_NAME = "gemini-flash-lite-latest"
SCENE_COUNT = 7
VISUALS_PER_SCENE = 2
TOTAL_VISUALS = 14
TARGET_SECONDS = 45
SCENE_DURATIONS = [3, 5, 7, 7, 8, 8, 7]
MAX_ATTEMPTS = 4

CAMERAS = {"close_up", "medium", "wide", "macro", "top_down", "side", "aerial", "orbit"}
ANIMATIONS = {"zoom_in", "zoom_out", "pan_left", "pan_right", "rotate", "parallax", "highlight", "hold"}
PURPOSES = {"hook", "question", "explanation", "example", "mindblowing_fact", "ending"}
TONES = {"curious", "tense", "calm", "awe", "playful", "urgent", "satisfied"}
RETENTION = {"open_loop", "escalation", "payoff", "reframe", "curiosity_gap", "pattern_break", "emotional_release", "closure"}
TRANSITIONS = {"hard_cut", "whip_pan", "match_cut", "dissolve", "none"}
MUSIC_CUES = {"intro", "build", "swell", "drop", "fade_out", "none"}


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _words(text):
    return re.findall(r"\b[\w'-]+\b", _clean(text))


def _api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY environment variable is missing.")
    return key


def _fallback_visual(scene_text, shot, previous=""):
    """Deterministic visual fallback; narration remains the source of truth."""
    subject = scene_text.rstrip(".!?")
    if shot == 1:
        return f"A recognizable real-world scene literally showing {subject}, with the main subject clearly visible and a concrete physical action."
    return f"A different close physical view of {subject}, revealing a new detail or visible consequence while remaining in the same real-world setting."


def _build_system_prompt():
    return """
You are the entertainment writer and visual director for Wonder Minute.
Create ONE highly engaging 35–45 second YouTube Short about the supplied topic.

THIS IS NOT A RESEARCH PASS.
Do not behave like an academic researcher. Do not write citations, papers,
source lists, scientific disclaimers, or textbook explanations.
The topic is the creative starting point. Use ordinary, broadly understood
knowledge only when needed to make the story coherent; do not invent precise
statistics, study names, quotes, experiments, or fake evidence.

PRIMARY GOAL:
Make the viewer think: "Wait... WHAT?"

VOICE:
- conversational
- playful
- curious
- slightly quirky
- confident
- simple spoken English
- short punchy sentences
- sounds like a great human storyteller, not an AI assistant
- explain technical ideas using everyday comparisons
- prefer concrete words over jargon

ABSOLUTELY AVOID:
- "Did you know"
- "Have you ever wondered"
- "Today we're going to"
- "In this video"
- "According to scientists"
- textbook definitions
- lecture language
- long technical terminology
- generic introductions
- lists/countdowns/top 5
- unrelated facts
- repetitive explanations
- generic laboratory imagery unless the topic actually happens in a lab

STORY:
Scene 1 (0–3): explosive hook. State the weirdest or most surprising part.
Scene 2 (3–8): deepen the mystery; make the viewer need the answer.
Scene 3 (8–15): simple explanation in normal human language.
Scene 4 (15–22): concrete everyday example or demonstration.
Scene 5 (22–30): reframe; reveal what the viewer misunderstood.
Scene 6 (30–38): strongest twist/payoff or surprising implication.
Scene 7 (38–45): satisfying ending. Then optionally introduce a completely
new curiosity topic as the FINAL sentence only.

The story must work even if the viewer never watches another Short.

VISUALS:
Every visual must literally show what the narration is talking about.
If narration says a hand touches metal, show a hand touching metal.
If it says an animal jumps, show the animal jumping.
If it says a glass fogs up, show the glass fogging up.
Do not convert explanations into diagrams, arrows, equations, particles,
microscopic fantasy, generic science labs, or abstract glowing effects.

For each scene, shot 1 establishes the moment and shot 2 advances it.
Shot 2 must change action, physical state, perspective, reaction, comparison,
or revealed detail. Never make two nearly identical images.

IMAGE PROMPTS:
- visible content only
- concrete subject + action + place + important detail
- 15–35 words
- no camera instructions inside image_prompt
- no captions/text/logos/watermarks/UI
- no "cinematic science illustration" unless genuinely appropriate
- default to cinematic_photograph or realistic_3d_render
- use natural varied lighting appropriate to the actual location
- use bright interesting compositions

CONTINUITY:
Only define recurring subjects when they genuinely recur.
Do NOT force a person, notebook, laboratory, glassware, or other object into
shots where the narration does not require it.
Continuity supports the story; it never overrides literal visual relevance.

NEXT TOPIC:
Create one specific curiosity topic that naturally follows the current story.
It is metadata for the next Short. Mention it only in Scene 7's final sentence.
Do not explain it. Do not put it in the description. Do not say "next video",
"coming next", "stay tuned", or "part 2".

Return ONLY JSON.
"""


def _build_schema():
    visual = {
        "type": "object",
        "properties": {
            "segment": {"type": "integer"},
            "duration": {"type": "integer"},
            "camera": {"type": "string"},
            "animation": {"type": "string"},
            "zoom_strength": {"type": "string"},
            "motion_intensity": {"type": "string"},
            "visual_complexity": {"type": "string"},
            "image_style": {"type": "string"},
            "lighting": {"type": "string"},
            "color_palette": {"type": "string"},
            "overlay": {"type": "object", "properties": {"type": {"type": "string"}, "description": {"type": "string"}}, "required": ["type", "description"]},
            "image_prompt": {"type": "string"},
            "visual_impact": {"type": "integer"},
        },
        "required": ["segment", "duration", "camera", "animation", "zoom_strength", "motion_intensity", "visual_complexity", "image_style", "lighting", "color_palette", "overlay", "image_prompt", "visual_impact"],
    }
    scene = {
        "type": "object",
        "properties": {
            "scene": {"type": "integer"},
            "purpose": {"type": "string"},
            "retention_purpose": {"type": "string"},
            "narration": {"type": "string"},
            "source_ids": {"type": "array", "items": {"type": "string"}},
            "subtitle_text": {"type": "string"},
            "caption_highlights": {"type": "array", "items": {"type": "object", "properties": {"word": {"type": "string"}, "emphasis": {"type": "string"}}, "required": ["word", "emphasis"]}},
            "subtitle_style": {"type": "string"},
            "emphasis_word": {"type": "string"},
            "duration": {"type": "integer"},
            "pause_after_ms": {"type": "integer"},
            "emotional_tone": {"type": "string"},
            "visual_priority": {"type": "string"},
            "transition": {"type": "string"},
            "sfx_cue": {"type": "object", "properties": {"term": {"type": "string"}, "at_ms": {"type": "integer"}}, "required": ["term", "at_ms"]},
            "music_cue": {"type": "string"},
            "confidence": {"type": "string"},
            "visuals": {"type": "array", "items": visual},
        },
        "required": ["scene", "purpose", "retention_purpose", "narration", "source_ids", "subtitle_text", "caption_highlights", "subtitle_style", "emphasis_word", "duration", "pause_after_ms", "emotional_tone", "visual_priority", "transition", "sfx_cue", "music_cue", "confidence", "visuals"],
    }
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "category": {"type": "string"},
            "thumbnail_prompt": {"type": "string"},
            "voice_style": {"type": "object", "properties": {"tone": {"type": "string"}, "pace": {"type": "string"}, "pitch": {"type": "string"}}, "required": ["tone", "pace", "pitch"]},
            "music": {"type": "object", "properties": {"search": {"type": "string"}, "arc": {"type": "string"}}, "required": ["search", "arc"]},
            "visual_identity": {"type": "object", "properties": {"style": {"type": "string"}, "palette": {"type": "string"}, "mood_arc": {"type": "string"}}, "required": ["style", "palette", "mood_arc"]},
            "visual_continuity": {"type": "object", "properties": {"recurring_subjects": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "type": {"type": "string"}, "appearance": {"type": "string"}, "continuity": {"type": "string"}}, "required": ["name", "type", "appearance", "continuity"]}}, "recurring_objects": {"type": "array", "items": {"type": "string"}}, "recurring_environment": {"type": "string"}, "continuity_rules": {"type": "array", "items": {"type": "string"}}}, "required": ["recurring_subjects", "recurring_objects", "recurring_environment", "continuity_rules"]},
            "retention_self_check": {"type": "object", "properties": {"weakest_scene": {"type": "integer"}, "reason": {"type": "string"}}, "required": ["weakest_scene", "reason"]},
            "next_short": {"type": "object", "properties": {"topic": {"type": "string"}, "teaser": {"type": "string"}, "why_viewers_should_return": {"type": "string"}, "subscription_cta": {"type": "string"}}, "required": ["topic", "teaser", "why_viewers_should_return", "subscription_cta"]},
            "scene_plan": {"type": "array", "items": scene},
        },
        "required": ["title", "description", "tags", "category", "thumbnail_prompt", "voice_style", "music", "visual_identity", "visual_continuity", "retention_self_check", "next_short", "scene_plan"],
    }


def _parse(text):
    text = _clean(text)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.I).strip()
        text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


def _bridge(next_topic):
    return f"But that leaves one bigger question: {next_topic}."


def _normalize(script, topic):
    if not isinstance(script, dict):
        raise RuntimeError("Gemini returned a non-object script.")
    scenes = script.get("scene_plan")
    if not isinstance(scenes, list) or len(scenes) != SCENE_COUNT:
        raise RuntimeError(f"Expected exactly {SCENE_COUNT} scenes.")

    script["topic"] = topic
    script["title"] = _clean(script.get("title"))[:70] or topic[:70]
    script["description"] = _clean(script.get("description"))
    if not script["description"]:
        script["description"] = f"A strange little mystery hiding in everyday life: {topic}."
    script["tags"] = [_clean(x).lstrip("#") for x in script.get("tags", []) if _clean(x)][:12]
    script["category"] = _clean(script.get("category")) or "science"
    script["thumbnail_prompt"] = _clean(script.get("thumbnail_prompt"))

    next_short = script.get("next_short") or {}
    next_topic = _clean(next_short.get("topic"))
    if not next_topic:
        raise RuntimeError("next_short.topic is empty.")
    script["next_short"] = {
        "topic": next_topic[:300],
        "teaser": _clean(next_short.get("teaser"))[:220] or next_topic,
        "why_viewers_should_return": _clean(next_short.get("why_viewers_should_return"))[:220] or next_topic,
        "subscription_cta": _clean(next_short.get("subscription_cta"))[:160] or "Follow for another weird little mystery.",
    }

    identity = script.get("visual_identity") or {}
    script["visual_identity"] = {
        "style": _clean(identity.get("style")) or "cinematic real-world storytelling with natural locations and tactile detail",
        "palette": _clean(identity.get("palette")) or "natural colors with crisp highlights and believable contrast",
        "mood_arc": _clean(identity.get("mood_arc")) or "curiosity, playful tension, surprise, satisfying payoff",
    }

    continuity = script.get("visual_continuity") or {}
    subjects = []
    for item in continuity.get("recurring_subjects", [])[:6]:
        if isinstance(item, dict) and _clean(item.get("name")) and _clean(item.get("appearance")):
            subjects.append({"name": _clean(item.get("name")), "type": _clean(item.get("type")), "appearance": _clean(item.get("appearance")), "continuity": _clean(item.get("continuity")) or "keep appearance consistent whenever visible"})
    script["visual_continuity"] = {
        "recurring_subjects": subjects,
        "recurring_objects": [_clean(x)[:200] for x in continuity.get("recurring_objects", [])[:8] if _clean(x)],
        "recurring_environment": _clean(continuity.get("recurring_environment"))[:500],
        "continuity_rules": [_clean(x)[:250] for x in continuity.get("continuity_rules", [])[:8] if _clean(x)],
    }

    # Enforce exact timing and caption source of truth.
    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            raise RuntimeError(f"Scene {i+1} is invalid.")
        scene["scene"] = i + 1
        scene["duration"] = SCENE_DURATIONS[i]
        narration = _clean(scene.get("narration"))
        if not narration:
            raise RuntimeError(f"Scene {i+1} narration is empty.")
        scene["narration"] = narration
        scene["subtitle_text"] = narration
        scene["source_ids"] = []
        scene["purpose"] = _clean(scene.get("purpose")) if _clean(scene.get("purpose")) in PURPOSES else (["hook", "question", "explanation", "example", "mindblowing_fact", "ending"][i])
        scene["retention_purpose"] = _clean(scene.get("retention_purpose")) if _clean(scene.get("retention_purpose")) in RETENTION else (["open_loop", "curiosity_gap", "reframe", "pattern_break", "payoff", "escalation", "closure"][i])
        scene["emotional_tone"] = _clean(scene.get("emotional_tone")) if _clean(scene.get("emotional_tone")) in TONES else (["curious", "curious", "calm", "playful", "awe", "urgent", "satisfied"][i])
        scene["visual_priority"] = "hero" if i in (0, 4, 5, 6) else "supporting"
        scene["transition"] = _clean(scene.get("transition")) if _clean(scene.get("transition")) in TRANSITIONS else "hard_cut"
        scene["music_cue"] = _clean(scene.get("music_cue")) if _clean(scene.get("music_cue")) in MUSIC_CUES else ("intro" if i == 0 else "build")
        scene["subtitle_style"] = "kinetic_word_by_word"
        scene["pause_after_ms"] = max(0, min(400, _safe_int(scene.get("pause_after_ms"), 0)))
        scene["confidence"] = "high"
        scene["sfx_cue"] = scene.get("sfx_cue") if isinstance(scene.get("sfx_cue"), dict) else {"term": "", "at_ms": 0}
        scene["caption_highlights"] = [{"word": max(_words(narration), key=len), "emphasis": "strong"}] if _words(narration) else []
        scene["emphasis_word"] = scene["caption_highlights"][0]["word"] if scene["caption_highlights"] else ""

        visuals = scene.get("visuals")
        if not isinstance(visuals, list) or len(visuals) != 2:
            raise RuntimeError(f"Scene {i+1} must contain exactly 2 visuals.")
        durations = [SCENE_DURATIONS[i] // 2, SCENE_DURATIONS[i] - (SCENE_DURATIONS[i] // 2)]
        for j, visual in enumerate(visuals):
            if not isinstance(visual, dict):
                visual = {}
                visuals[j] = visual
            prompt = _clean(visual.get("image_prompt"))
            if not prompt:
                prompt = _fallback_visual(narration, j + 1)
            if len(_words(prompt)) < 12:
                prompt = _fallback_visual(narration, j + 1)
            visual.update({
                "segment": j + 1,
                "duration": durations[j],
                "camera": _clean(visual.get("camera")) if _clean(visual.get("camera")) in CAMERAS else ("medium" if j == 0 else "close_up"),
                "animation": _clean(visual.get("animation")) if _clean(visual.get("animation")) in ANIMATIONS else ("zoom_in" if j == 0 else "pan_right"),
                "zoom_strength": _clean(visual.get("zoom_strength")) or "subtle",
                "motion_intensity": _clean(visual.get("motion_intensity")) or "medium",
                "visual_complexity": _clean(visual.get("visual_complexity")) or "moderate",
                "image_style": _clean(visual.get("image_style")) if _clean(visual.get("image_style")) in {"realistic_3d_render", "cinematic_photograph", "macro_photography"} else "cinematic_photograph",
                "lighting": _clean(visual.get("lighting")) or "bright believable natural lighting appropriate to the location",
                "color_palette": _clean(visual.get("color_palette")) or script["visual_identity"]["palette"],
                "overlay": {"type": "none", "description": ""},
                "image_prompt": prompt[:1200],
                "visual_impact": max(1, min(10, _safe_int(visual.get("visual_impact"), 8))),
            })
        scene["visuals"] = visuals

    # Scene 7 must end with the continuation question. Remove accidental mentions elsewhere.
    for scene in scenes[:6]:
        if next_topic.lower() in scene["narration"].lower():
            scene["narration"] = scene["narration"].replace(next_topic, "that mystery")
            scene["subtitle_text"] = scene["narration"]
    final = scenes[6]["narration"].rstrip()
    if next_topic.lower() not in final.lower():
        final = final.rstrip(".!?") + ". " + _bridge(next_topic)
    scenes[6]["narration"] = final
    scenes[6]["subtitle_text"] = final
    scenes[6]["purpose"] = "ending"
    scenes[6]["transition"] = "none"
    scenes[6]["music_cue"] = "fade_out"
    scenes[6]["caption_highlights"] = [{"word": max(_words(final), key=len), "emphasis": "strong"}]
    scenes[6]["emphasis_word"] = scenes[6]["caption_highlights"][0]["word"]

    # Never leak the next topic into the public description.
    description = script["description"]
    if next_topic.lower() in description.lower() or any(x in description.lower() for x in ("next video", "next short", "coming next", "stay tuned", "part 2")):
        script["description"] = f"Why {topic.rstrip('?')} is much stranger than it looks."

    script["scene_plan"] = scenes
    seed = _safe_int(script.get("image_generation", {}).get("seed"), random.randint(1, 2147483647))
    script["image_generation"] = {
        "seed": seed,
        "style_lock": f"{script['visual_identity']['style']}; {script['visual_identity']['palette']}; {script['visual_identity']['mood_arc']}",
        "images_per_scene": 2,
        "total_images": 14,
        "visual_continuity_enabled": True,
        "semantic_prompts": True,
        "portrait_output": True,
    }
    script["video_structure"] = {"format": "short_form_story", "scene_count": 7, "target_duration_seconds": 45, "actual_duration_seconds": 45, "visuals_per_scene": 2, "total_visuals": 14}
    script["publishing"] = {"research_verified": False, "research_sources_require_verification": False, "citations_ready": False, "claim_verification_required": False, "captions_match_narration": True, "semantic_image_prompts": True, "fourteen_visuals_required": True}
    script["generated_at"] = int(time.time())
    script["video_id"] = f"{re.sub(r'[^a-z0-9]+', '-', script['title'].lower()).strip('-')[:40]}-{uuid.uuid4().hex[:8]}"
    return script


def generate_script(topic, config, research=None, extra_feedback=""):
    """Generate an entertainment-first storyboard. `research` is intentionally ignored."""
    topic = _clean(topic)
    if not topic:
        raise RuntimeError("Topic is empty.")
    client = genai.Client(api_key=_api_key())
    prompt = f"""
CURRENT TOPIC:
{topic}

Create a 45-second Short with exactly 7 scenes and 2 visuals per scene.
Use durations 3, 5, 7, 7, 8, 8, 7 seconds.

Make it fun, conversational and surprising. The first sentence must grab
attention immediately. Use a relatable physical example whenever possible.
Explain the idea simply, with a quirky comparison or observation where it
helps. Do not sound scientific for the sake of sounding scientific.

DESCRIPTION:
Write a short description ONLY about the current topic.

NEXT SHORT:
Invent one specific curiosity-driven topic that naturally follows this story.
Mention it only as the final sentence of Scene 7.

VISUALS:
Every image must literally depict the narration. No generic labs, diagrams,
abstract particles, arrows, equations, text, labels or meaningless effects.
Shot 1 establishes; shot 2 reveals something different.

{('PRIOR FEEDBACK:\n' + extra_feedback) if extra_feedback else ''}
"""
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt + (f"\n\nFix this previous validation error:\n{last_error}" if last_error else ""),
                config=types.GenerateContentConfig(
                    system_instruction=_build_system_prompt(),
                    response_mime_type="application/json",
                    response_json_schema=_build_schema(),
                    temperature=0.9,
                ),
            )
            text = getattr(response, "text", None)
            script = _parse(text)
            return _normalize(script, topic)
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
            print(f"❌ Entertainment script attempt {attempt}/{MAX_ATTEMPTS} failed: {last_error}")
            if attempt < MAX_ATTEMPTS:
                time.sleep(2 * attempt)
    raise RuntimeError(f"Entertainment script generation failed: {last_error}")


if __name__ == "__main__":
    print("generate_script.py — entertainment-first mode")
