"""Entertainment-first 45-second story generator for Mint-YT-Factory.

The narration is written for spoken delivery first: playful, visual, punchy and
human. Technical detail is only used when it makes the story clearer or funnier.
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


def _words(text):
    return re.findall(r"\b[\w'-]+\b", _clean(text))


def _api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY environment variable is missing.")
    return key


def _build_system_prompt():
    return r"""
You are the head writer for a wildly engaging YouTube Shorts channel called Wonder Minute.
Write ONE self-contained 35–45 second curiosity story about the supplied CURRENT topic.

Your job is NOT to sound smart. Your job is to make the viewer grin, lean closer and think:
"Wait... seriously?!"

VOICE / DELIVERY:
- sound like a clever, slightly mischievous human friend telling a story
- conversational spoken English, not essay English
- playful, quirky, confident, energetic
- short sentences mixed with occasional punchy fragments
- use vivid verbs and concrete objects the viewer can picture
- use natural rhetorical reactions such as "Yep.", "And here's the weird part.", "Sounds impossible, right?"
- use one memorable funny comparison or bit of personification when it genuinely fits
- build curiosity before explaining anything
- explain the mechanism in ordinary language first; technical terminology is optional
- if a technical term is essential, immediately translate it into normal language
- let the narrator have a little personality; do not make every sentence purely factual

PACING:
- Hook immediately. No warm-up.
- Every 1–2 sentences should either reveal something, change the viewer's mental picture,
  create a question, or deliver a surprising consequence.
- Avoid long definition sentences.
- Use punctuation naturally for spoken rhythm: commas, dashes and short sentences.
- Prefer a concrete scene over abstract explanation.

ABSOLUTELY AVOID:
- "Did you know"
- "Have you ever wondered"
- "Today we're going to"
- "In this video"
- "According to scientists"
- "The scientific explanation is"
- "This phenomenon occurs because"
- textbook definitions
- lecture voice
- academic transitions such as "therefore", "thus", "hence"
- lists, countdowns, Top 5, numbered facts
- fake quotes, fake studies, fake statistics or invented precise measurements
- stuffing several unrelated facts into one story
- excessive words such as molecule, electron, quantum, thermodynamics, coefficient,
  equilibrium, wavelength, mechanism, phenomenon, density, viscosity unless genuinely necessary

STORY STRUCTURE:
Scene 1 (0–3s): a punchy weird hook. Make the viewer immediately notice the mystery.
Scene 2 (3–8s): make the situation stranger. Do not explain yet.
Scene 3 (8–15s): give the simple "oh, that's why" setup.
Scene 4 (15–22s): show a concrete everyday example or physical consequence.
Scene 5 (22–30s): flip the viewer's assumption or reveal the surprising detail.
Scene 6 (30–38s): strongest payoff. This should feel like the "WAIT, WHAT?" moment.
Scene 7 (38–45s): finish the CURRENT story with a satisfying line. The production system may
then append exactly one continuation topic as the final sentence. Never introduce that topic
or any other future mystery earlier.

VISUAL-FIRST WRITING:
Every sentence must be easy to visualize. If you cannot imagine a literal shot for it,
rewrite it. Prefer things like a hand, glass, ice cube, sock, door, spoon, phone, animal,
steam, water, shadow, flame, food, clothing, etc. over abstract language.

VISUAL CONTRACT:
For each shot provide:
- spoken_line: the exact narration beat the image represents
- visual_focus: the main visible subject
- visual_action: the exact physical action/state
- must_show: concrete visible details
- must_not_show: misleading things to avoid
- image_prompt: 15–40 words describing ONLY the literal scene
Shot 1 establishes the moment. Shot 2 advances it with a different action, physical state,
reaction, closer detail or consequence.
Never use diagrams, equations, arrows, generic laboratories, abstract particles or symbolic
representations when the narration can be shown literally.

NEXT TOPIC:
Provide one specific curiosity topic that naturally follows the current story.
It is metadata for the production system. Mention it only in the final sentence of Scene 7.
Never put it in the description or earlier narration.

Return ONLY JSON.
"""


def _build_schema():
    visual = {
        "type": "object",
        "properties": {
            "segment": {"type": "integer"}, "duration": {"type": "integer"},
            "camera": {"type": "string"}, "animation": {"type": "string"},
            "zoom_strength": {"type": "string"}, "motion_intensity": {"type": "string"},
            "visual_complexity": {"type": "string"}, "image_style": {"type": "string"},
            "lighting": {"type": "string"}, "color_palette": {"type": "string"},
            "overlay": {"type": "object", "properties": {"type": {"type": "string"}, "description": {"type": "string"}}, "required": ["type", "description"]},
            "spoken_line": {"type": "string"}, "visual_focus": {"type": "string"}, "visual_action": {"type": "string"},
            "must_show": {"type": "array", "items": {"type": "string"}}, "must_not_show": {"type": "array", "items": {"type": "string"}},
            "image_prompt": {"type": "string"}, "visual_impact": {"type": "integer"},
        },
        "required": ["segment", "duration", "camera", "animation", "zoom_strength", "motion_intensity", "visual_complexity", "image_style", "lighting", "color_palette", "overlay", "spoken_line", "visual_focus", "visual_action", "must_show", "must_not_show", "image_prompt", "visual_impact"],
    }
    scene = {
        "type": "object",
        "properties": {
            "scene": {"type": "integer"}, "purpose": {"type": "string"}, "retention_purpose": {"type": "string"},
            "narration": {"type": "string"}, "source_ids": {"type": "array", "items": {"type": "string"}},
            "subtitle_text": {"type": "string"},
            "caption_highlights": {"type": "array", "items": {"type": "object", "properties": {"word": {"type": "string"}, "emphasis": {"type": "string"}}, "required": ["word", "emphasis"]}},
            "subtitle_style": {"type": "string"}, "emphasis_word": {"type": "string"}, "duration": {"type": "integer"},
            "pause_after_ms": {"type": "integer"}, "emotional_tone": {"type": "string"}, "visual_priority": {"type": "string"},
            "transition": {"type": "string"}, "sfx_cue": {"type": "object", "properties": {"term": {"type": "string"}, "at_ms": {"type": "integer"}}, "required": ["term", "at_ms"]},
            "music_cue": {"type": "string"}, "confidence": {"type": "string"}, "visuals": {"type": "array", "items": visual},
        },
        "required": ["scene", "purpose", "retention_purpose", "narration", "source_ids", "subtitle_text", "caption_highlights", "subtitle_style", "emphasis_word", "duration", "pause_after_ms", "emotional_tone", "visual_priority", "transition", "sfx_cue", "music_cue", "confidence", "visuals"],
    }
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"}, "description": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}},
            "category": {"type": "string"}, "thumbnail_prompt": {"type": "string"},
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


def _normalize(script, topic):
    if not isinstance(script, dict):
        raise RuntimeError("Gemini returned a non-object script.")
    scenes = script.get("scene_plan")
    if not isinstance(scenes, list) or len(scenes) != SCENE_COUNT:
        raise RuntimeError(f"Expected exactly {SCENE_COUNT} scenes.")

    script["topic"] = topic
    script["title"] = _clean(script.get("title"))[:70] or topic[:70]
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
        "style": _clean(identity.get("style")) or "cinematic real-world storytelling with tactile detail",
        "palette": _clean(identity.get("palette")) or "natural colors with crisp believable contrast",
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
        scene["pause_after_ms"] = max(0, min(400, int(scene.get("pause_after_ms", 0) or 0)))
        scene["purpose"] = _clean(scene.get("purpose")) if _clean(scene.get("purpose")) in PURPOSES else ("hook" if i == 0 else "ending" if i == 6 else "explanation")
        scene["retention_purpose"] = _clean(scene.get("retention_purpose")) if _clean(scene.get("retention_purpose")) in RETENTION else ("open_loop" if i < 2 else "payoff" if i >= 5 else "escalation")
        scene["subtitle_style"] = _clean(scene.get("subtitle_style")) or "dynamic"
        scene["emphasis_word"] = _words(narration)[0] if _words(narration) else ""
        scene["emotional_tone"] = _clean(scene.get("emotional_tone")) if _clean(scene.get("emotional_tone")) in TONES else ("playful" if i in (0, 3) else "curious")
        scene["visual_priority"] = _clean(scene.get("visual_priority")) or "primary"
        scene["transition"] = _clean(scene.get("transition")) if _clean(scene.get("transition")) in TRANSITIONS else "hard_cut"
        scene["music_cue"] = _clean(scene.get("music_cue")) if _clean(scene.get("music_cue")) in MUSIC_CUES else ("intro" if i == 0 else "fade_out" if i == 6 else "build")
        scene["confidence"] = _clean(scene.get("confidence")) or "high"
        scene["sfx_cue"] = scene.get("sfx_cue") if isinstance(scene.get("sfx_cue"), dict) else {"term": "none", "at_ms": 0}

        visuals = scene.get("visuals")
        if not isinstance(visuals, list) or len(visuals) != VISUALS_PER_SCENE:
            raise RuntimeError(f"Scene {i+1} must contain exactly 2 visuals.")
        durations = [scene["duration"] // 2, scene["duration"] - scene["duration"] // 2]
        for j, visual in enumerate(visuals):
            if not isinstance(visual, dict):
                raise RuntimeError(f"Scene {i+1} visual {j+1} is invalid.")
            visual["segment"] = j + 1
            visual["duration"] = durations[j]
            visual["camera"] = _clean(visual.get("camera")) if _clean(visual.get("camera")) in CAMERAS else "medium"
            visual["animation"] = _clean(visual.get("animation")) if _clean(visual.get("animation")) in ANIMATIONS else ("zoom_in" if j == 0 else "pan_right")
            visual["zoom_strength"] = _clean(visual.get("zoom_strength")) or "subtle"
            visual["motion_intensity"] = _clean(visual.get("motion_intensity")) or "medium"
            visual["visual_complexity"] = _clean(visual.get("visual_complexity")) or "moderate"
            visual["image_style"] = _clean(visual.get("image_style")) if _clean(visual.get("image_style")) in {"realistic_3d_render", "cinematic_photograph", "macro_photography"} else "cinematic_photograph"
            visual["lighting"] = _clean(visual.get("lighting")) or "natural believable lighting"
            visual["color_palette"] = _clean(visual.get("color_palette")) or script["visual_identity"]["palette"]
            visual["overlay"] = visual.get("overlay") if isinstance(visual.get("overlay"), dict) else {"type": "none", "description": ""}
            visual["spoken_line"] = _clean(visual.get("spoken_line")) or narration
            visual["visual_focus"] = _clean(visual.get("visual_focus")) or narration[:120]
            visual["visual_action"] = _clean(visual.get("visual_action")) or narration[:180]
            visual["must_show"] = [_clean(x) for x in (visual.get("must_show") or []) if _clean(x)][:6]
            visual["must_not_show"] = [_clean(x) for x in (visual.get("must_not_show") or []) if _clean(x)][:8]
            visual["visual_impact"] = max(1, min(10, int(visual.get("visual_impact", 8) or 8)))
            prompt = _clean(visual.get("image_prompt"))
            if not prompt:
                prompt = f"Literal real-world scene showing {visual['visual_action']} with {visual['visual_focus']} clearly visible"
            visual["image_prompt"] = prompt[:700]

        meaningful = [w for w in _words(narration) if len(w.strip(".,!?;:'\"")) >= 4]
        chosen = meaningful[:3] or _words(narration)[:1]
        scene["caption_highlights"] = [{"word": w, "emphasis": "strong"} for w in chosen]

    scene7 = scenes[6]
    if next_topic.lower() not in scene7["narration"].lower():
        scene7["narration"] = scene7["narration"].rstrip(".!? ") + f" But that leaves one bigger question: {next_topic}."
        scene7["subtitle_text"] = scene7["narration"]

    next_key = re.sub(r"[^a-z0-9 ]", " ", next_topic.lower()).strip()
    for scene in scenes[:6]:
        if next_key and next_key in re.sub(r"[^a-z0-9 ]", " ", scene["narration"].lower()):
            raise RuntimeError("Next topic appeared before Scene 7.")

    script["retention_self_check"] = script.get("retention_self_check") or {"weakest_scene": 4, "reason": "Every scene advances the same mystery."}
    script["publishing"] = {"research_verified": False, "research_sources_require_verification": False, "citations_ready": False, "claim_verification_required": False, "captions_match_narration": True, "semantic_image_prompts": True, "fourteen_visuals_required": True}
    script["generated_at"] = int(time.time())
    script["video_id"] = f"{re.sub(r'[^a-z0-9]+', '-', script['title'].lower()).strip('-')[:40]}-{uuid.uuid4().hex[:8]}"
    return script


def generate_script(topic, config, research=None, extra_feedback=""):
    topic = _clean(topic)
    if not topic:
        raise RuntimeError("Topic is empty.")
    client = genai.Client(api_key=_api_key())
    feedback = ""
    if extra_feedback:
        feedback = "\n\nPRIOR FEEDBACK:\n" + _clean(extra_feedback)

    prompt = f"""
CURRENT TOPIC:
{topic}

Create exactly 7 scenes with durations 3, 5, 7, 7, 8, 8, 7 seconds.
Write roughly 110–135 spoken words before any continuation sentence.

NON-NEGOTIABLE STYLE:
Make this feel like a fun human telling a weird story to a friend. Start with the strangest
thing, not a definition. Use concrete everyday imagery, playful phrasing and at least one
natural quirky comparison when it fits. Keep the explanation short and return quickly to the
physical story. Avoid sounding scientific, formal or instructional.

The current topic is the ONLY mystery in Scenes 1–6.
Scene 7 must finish that mystery before the continuation sentence.

DESCRIPTION:
Write a short description ONLY about the current topic. Never mention the continuation topic.

NEXT SHORT:
Invent one specific curiosity-driven topic. It may appear only in the final sentence of Scene 7.

VISUALS:
Each image must literally depict the exact spoken beat, subject and physical action. Do not
use generic topic imagery, diagrams, laboratories, abstract particles, symbols or unrelated people.
Shot 2 must visibly advance shot 1.
{feedback}
"""

    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            retry = f"\n\nFix this previous validation error:\n{last_error}" if last_error else ""
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt + retry,
                config=types.GenerateContentConfig(
                    system_instruction=_build_system_prompt(),
                    response_mime_type="application/json",
                    response_json_schema=_build_schema(),
                    temperature=1.0,
                ),
            )
            text = getattr(response, "text", None)
            if not text:
                raise RuntimeError("Gemini returned an empty response.")
            return _normalize(_parse(text), topic)
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
            if attempt < MAX_ATTEMPTS:
                time.sleep(2 * attempt)
    raise RuntimeError(f"SCRIPT GENERATION FAILED. Last error: {last_error}")


if __name__ == "__main__":
    print("generate_script.py entertainment-first module")
