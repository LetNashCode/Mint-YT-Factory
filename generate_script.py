"""Entertainment-first story generator with a hard visual-contract gate."""
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
MAX_ATTEMPTS = 6

CAMERAS = {"close_up", "medium", "wide", "macro", "top_down", "side", "aerial", "orbit"}
ANIMATIONS = {"zoom_in", "zoom_out", "pan_left", "pan_right", "rotate", "parallax", "highlight", "hold"}
PURPOSES = {"hook", "question", "explanation", "example", "mindblowing_fact", "ending"}
TONES = {"curious", "tense", "calm", "awe", "playful", "urgent", "satisfied"}
RETENTION = {"open_loop", "escalation", "payoff", "reframe", "curiosity_gap", "pattern_break", "emotional_release", "closure"}
TRANSITIONS = {"hard_cut", "whip_pan", "match_cut", "dissolve", "none"}
MUSIC_CUES = {"intro", "build", "swell", "drop", "fade_out", "none"}

# Phrases that repeatedly produced unsearchable Pexels queries in production.
# These are hard failures unless the same sentence also contains a concrete physical action.
ABSTRACT_VISUAL_PHRASES = (
    "climbs higher", "climbs up", "climbs", "screams", "whispers", "dances",
    "plays an orchestra", "plays a song", "secret code", "physics dances",
    "physics plays", "nature plays", "molecules dance", "atoms dance",
    "tiny workers", "invisible machine", "invisible machines", "secret world",
    "underground world", "comes alive", "gets angry", "gets confused",
    "thinks", "decides", "communicates", "has a conversation", "is having a conversation",
    "tells a story", "tells us", "reveals its secret", "fights", "wins the battle",
    "loses the battle", "plays a tune", "plays music", "becomes an orchestra",
    "kitchen symphony", "acoustic shrinking game", "magic happens", "the magic happens",
)

ABSTRACT_SUBJECTS = {
    "physics", "science", "sound", "pressure", "energy", "force", "nature",
    "the molecules", "molecules", "atoms", "the universe", "time", "gravity",
}

PHYSICAL_TERMS = {
    "water", "kettle", "steam", "bubble", "bubbles", "stove", "metal", "lid",
    "spout", "cup", "pan", "pot", "hand", "finger", "ice", "oil", "soap",
    "foam", "drop", "droplet", "surface", "glass", "flame", "food", "onion",
    "knife", "phone", "screen", "cloth", "sock", "door", "shadow", "light",
    "air", "wind", "balloon", "paper", "wood", "plastic", "coin", "salt",
    "sugar", "coffee", "tea", "bread", "egg", "fruit", "skin", "hair",
    "leaf", "plant", "shoe", "wheel", "wheelchair", "car", "window", "mirror",
    "spoon", "fork", "plate", "bottle", "candle", "smoke", "rain", "snow",
}

BANNED_LECTURE_PHRASES = (
    "did you know", "have you ever wondered", "today we're going to", "in this video",
    "according to scientists", "the scientific explanation is", "this phenomenon occurs because",
    "therefore", "thus", "hence", "in conclusion", "the reason is simply because",
)

TECHNICAL_JARGON = {
    "thermodynamics", "coefficient", "equilibrium", "wavelength", "viscosity",
    "nucleation", "cavitation", "quantum", "electron", "electromagnetic",
    "molecular", "microscopic", "macroscopic", "differential", "oscillation",
}


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
You are the head writer for a high-retention YouTube Shorts channel.

Write ONE 35–45 second curiosity story about the CURRENT TOPIC.
The viewer should feel: "Wait... seriously?!"

IMPORTANT: entertainment comes from the DISCOVERY, not from making the science sound fancy.
Sound like a clever, mischievous friend explaining something weird you can see in everyday life.

VOICE
- conversational spoken English
- playful, quirky, confident and energetic
- short punchy sentences mixed with natural longer sentences
- concrete nouns and physical verbs
- one or two light jokes/comparisons are fine
- simple language first; technical terminology only when genuinely necessary
- never sound like a textbook, documentary narrator or classroom teacher

STORY
Scene 1: immediate weird observation / hook.
Scene 2: make the observation stranger without explaining it yet.
Scene 3: reveal the first simple piece of the mechanism.
Scene 4: show the physical change happening.
Scene 5: reveal the surprising consequence.
Scene 6: deliver the strongest "WAIT, WHAT?" payoff.
Scene 7: close the CURRENT mystery, then tease ONLY the locked next topic in the final sentence.

The story must be ONE chain of cause → visible change → consequence → payoff.
Do not turn it into a list of facts.

HARD VISUAL CONTRACT
Every spoken beat must be literally filmable.
Every sentence must contain or clearly refer to a concrete physical subject, object, person,
material, environment or observable event.
Every visual must answer:
1. WHAT is visible?
2. WHAT is it physically doing or changing?
3. WHERE is it happening?

A viewer should be able to search the sentence on a stock-footage site without interpreting
metaphors.

GOOD:
"Tiny bubbles form on the hot metal at the bottom of the kettle."
"As the water gets hotter, those bubbles rise and collapse."
"Steam finally starts escaping from the spout."

BAD:
"The sound climbs higher."
"The kettle starts screaming."
"Physics turns the kitchen into an orchestra."
"The pressure gets angry."
"Molecules start dancing."
"The kettle reveals its secret."

If you want a playful metaphor, immediately anchor it to a literal physical event.
GOOD: "The kettle sounds almost like a scream as steam rushes through the spout."
BAD: "The kettle screams."

DO NOT use abstract verbs as the primary visual action: climbs, screams, whispers, dances,
plays, thinks, decides, communicates, fights, wins, loses, reveals, remembers, gets angry,
gets confused, comes alive.

DO NOT invent microscopic characters, invisible machines, secret worlds, fantasy interiors,
abstract particle scenes, equations, diagrams or symbolic animations when real footage can show
the idea.

PREFER concrete demonstrations: pouring, cutting, boiling, freezing, melting, bubbling,
steaming, cracking, sticking, rubbing, squeezing, dropping, spinning, shaking, opening,
closing, expanding, shrinking, changing color or changing texture.

SCIENCE LANGUAGE
Explain the mechanism like a smart friend. Avoid jargon. If a technical term is needed,
explain it in ordinary words immediately.
Never use jargon merely to make the script sound intelligent.

HOOK
Never start with "Did you know", "Have you ever wondered", "Today we're going to", or
"In this video". Start with the weird thing itself.

NO FILLER
Every 1–2 sentences must reveal something, change the viewer's mental model, create curiosity,
or deliver a consequence. Do not pad the story to hit the word count.

VISUALS
Each scene has exactly 2 visuals.
Shot 1 establishes the physical situation.
Shot 2 must advance it with a new physical action, state, angle, reaction or consequence.
The two shots must not be generic duplicates.

For every visual provide:
- spoken_line: exact narration represented
- visual_focus: concrete visible subject
- visual_action: concrete physical action/state
- must_show: specific visible details
- must_not_show: misleading alternatives
- image_prompt: literal real-world 15–40 word scene description

Image prompts must NEVER contain metaphorical actions. Write them as if directing a camera operator.

NEXT TOPIC
The next topic is metadata. It may appear ONLY in the final sentence of Scene 7.
Never mention it in Scenes 1–6, the description, title, tags or thumbnail prompt.

Return ONLY JSON matching the supplied schema.
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


def _contains_any(text, phrases):
    lower = _clean(text).lower()
    return [p for p in phrases if p in lower]


def _visual_contract_errors(scenes, next_topic):
    errors = []
    narration_words = 0
    all_narration = []

    for i, scene in enumerate(scenes):
        n = _clean(scene.get("narration"))
        narration_words += len(_words(n))
        all_narration.append(n.lower())
        if not n:
            errors.append(f"Scene {i+1}: empty narration")
            continue

        lecture_hits = _contains_any(n, BANNED_LECTURE_PHRASES)
        if lecture_hits:
            errors.append(f"Scene {i+1}: lecture phrase(s): {', '.join(lecture_hits)}")

        abstract_hits = _contains_any(n, ABSTRACT_VISUAL_PHRASES)
        physical_hits = [w for w in PHYSICAL_TERMS if re.search(rf"\b{re.escape(w)}\b", n.lower())]
        if abstract_hits and not physical_hits:
            errors.append(f"Scene {i+1}: abstract/non-searchable narration: {n}")

        if i < 6 and next_topic and next_topic.lower() in n.lower():
            errors.append(f"Scene {i+1}: next topic leaked before Scene 7")

        visuals = scene.get("visuals")
        if not isinstance(visuals, list) or len(visuals) != VISUALS_PER_SCENE:
            errors.append(f"Scene {i+1}: exactly 2 visuals required")
            continue

        previous_focus = ""
        for j, visual in enumerate(visuals):
            prefix = f"Scene {i+1} Shot {j+1}"
            focus = _clean(visual.get("visual_focus"))
            action = _clean(visual.get("visual_action"))
            prompt = _clean(visual.get("image_prompt"))
            spoken = _clean(visual.get("spoken_line"))

            if not focus or not action or not prompt:
                errors.append(f"{prefix}: missing concrete visual fields")
                continue
            if len(prompt.split()) < 8:
                errors.append(f"{prefix}: image prompt too vague")
            if len(prompt.split()) > 60:
                errors.append(f"{prefix}: image prompt too verbose")

            visual_abstract = _contains_any(" ".join([focus, action, prompt]), ABSTRACT_VISUAL_PHRASES)
            if visual_abstract:
                errors.append(f"{prefix}: abstract visual wording: {', '.join(visual_abstract)}")

            if not physical_hits and not _contains_any(" ".join([focus, action, prompt]), PHYSICAL_TERMS):
                errors.append(f"{prefix}: no concrete physical subject detected")

            if spoken and n.lower() not in spoken.lower() and spoken.lower() not in n.lower():
                # Spoken-line can be a beat extracted from the scene, but it must overlap meaningfully.
                overlap = set(re.findall(r"[a-z]{4,}", spoken.lower())) & set(re.findall(r"[a-z]{4,}", n.lower()))
                if len(overlap) < 2:
                    errors.append(f"{prefix}: spoken_line does not map to scene narration")

            if j == 1 and previous_focus and focus.lower() == previous_focus.lower():
                errors.append(f"{prefix}: Shot 2 duplicates Shot 1 focus")
            previous_focus = focus

    if not any(re.search(r"[.!?]", x) for x in all_narration):
        errors.append("Narration has no sentence punctuation")

    if not next_topic:
        errors.append("next_short.topic is empty")

    return errors, narration_words


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
        p = _clean(scene.get("purpose"))
        scene["purpose"] = p if p in PURPOSES else ("hook" if i == 0 else "ending" if i == 6 else "explanation")
        r = _clean(scene.get("retention_purpose"))
        scene["retention_purpose"] = r if r in RETENTION else ("open_loop" if i < 2 else "payoff" if i >= 5 else "escalation")
        scene["subtitle_style"] = _clean(scene.get("subtitle_style")) or "dynamic"
        scene["emphasis_word"] = _words(narration)[0] if _words(narration) else ""
        tone = _clean(scene.get("emotional_tone"))
        scene["emotional_tone"] = tone if tone in TONES else ("playful" if i in (0, 3) else "curious")
        scene["visual_priority"] = _clean(scene.get("visual_priority")) or "primary"
        transition = _clean(scene.get("transition"))
        scene["transition"] = transition if transition in TRANSITIONS else "hard_cut"
        music = _clean(scene.get("music_cue"))
        scene["music_cue"] = music if music in MUSIC_CUES else ("intro" if i == 0 else "fade_out" if i == 6 else "build")
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
            camera = _clean(visual.get("camera"))
            visual["camera"] = camera if camera in CAMERAS else "medium"
            animation = _clean(visual.get("animation"))
            visual["animation"] = animation if animation in ANIMATIONS else ("zoom_in" if j == 0 else "pan_right")
            visual["zoom_strength"] = _clean(visual.get("zoom_strength")) or "subtle"
            visual["motion_intensity"] = _clean(visual.get("motion_intensity")) or "medium"
            visual["visual_complexity"] = _clean(visual.get("visual_complexity")) or "moderate"
            style = _clean(visual.get("image_style"))
            visual["image_style"] = style if style in {"realistic_3d_render", "cinematic_photograph", "macro_photography"} else "cinematic_photograph"
            visual["lighting"] = _clean(visual.get("lighting")) or "natural believable lighting"
            visual["color_palette"] = _clean(visual.get("color_palette")) or script["visual_identity"]["palette"]
            visual["overlay"] = visual.get("overlay") if isinstance(visual.get("overlay"), dict) else {"type": "none", "description": ""}
            visual["spoken_line"] = _clean(visual.get("spoken_line")) or narration
            visual["visual_focus"] = _clean(visual.get("visual_focus"))
            visual["visual_action"] = _clean(visual.get("visual_action"))
            visual["must_show"] = [_clean(x) for x in (visual.get("must_show") or []) if _clean(x)][:6]
            visual["must_not_show"] = [_clean(x) for x in (visual.get("must_not_show") or []) if _clean(x)][:8]
            visual["visual_impact"] = max(1, min(10, int(visual.get("visual_impact", 8) or 8)))
            visual["image_prompt"] = _clean(visual.get("image_prompt"))

        meaningful = [w for w in _words(narration) if len(w.strip(".,!?;:'\"")) >= 4]
        chosen = meaningful[:3] or _words(narration)[:1]
        scene["caption_highlights"] = [{"word": w, "emphasis": "strong"} for w in chosen]

    # We require Gemini to provide the final tease itself. Do not silently invent one here,
    # because doing so bypasses the story quality gate.
    scene7 = scenes[6]
    if next_topic.lower() not in scene7["narration"].lower():
        raise RuntimeError("Scene 7 must contain the locked next topic in its final sentence.")

    next_key = re.sub(r"[^a-z0-9 ]", " ", next_topic.lower()).strip()
    for scene in scenes[:6]:
        if next_key and next_key in re.sub(r"[^a-z0-9 ]", " ", scene["narration"].lower()):
            raise RuntimeError("Next topic appeared before Scene 7.")

    errors, word_count = _visual_contract_errors(scenes, next_topic)
    # 95–115 is intentionally tighter than the previous 110–135 request.
    if word_count < 95 or word_count > 115:
        errors.append(f"Spoken word count {word_count} is outside 95–115")

    if errors:
        preview = " | ".join(errors[:10])
        raise RuntimeError(f"VISUAL CONTRACT FAILED: {preview}")

    script["retention_self_check"] = script.get("retention_self_check") or {"weakest_scene": 4, "reason": "Every scene advances the same mystery."}
    script["publishing"] = {
        "research_verified": False,
        "research_sources_require_verification": False,
        "citations_ready": False,
        "claim_verification_required": False,
        "captions_match_narration": True,
        "semantic_image_prompts": True,
        "fourteen_visuals_required": True,
        "visual_contract_passed": True,
    }
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
Target 95–115 total spoken words INCLUDING the final next-topic tease.

CURRENT STORY ONLY:
Scenes 1–6 must discuss only the current topic.
Scene 7 must finish the current mystery and end with exactly one natural sentence that names
next_short.topic.

ENTERTAINMENT:
Start with the weirdest observable thing. Make it feel like a clever friend showing the viewer
something they normally overlook. Use playful language, but keep every claim understandable.
Use at most two metaphors in the entire narration, and every metaphor must be anchored to a
literal physical event.

VISUAL CONTRACT — HARD REQUIREMENT:
Every scene narration must be literally filmable.
Every visual needs a concrete subject + physical action/state + location/context.
Do NOT write visual beats such as "the sound climbs", "the kettle screams", "physics dances",
"molecules dance", "the object reveals its secret", "pressure gets angry", or other abstract
metaphorical actions.
If the interesting idea is invisible, explain it through a visible consequence instead.

For example, instead of:
"The sound climbs higher and higher."
write:
"The bubbling changes from slow, deep pops to faster, sharper pops as the water heats up."

Instead of:
"The kettle screams."
write:
"Steam rushes through the small opening in the spout, producing the high sound you hear."

Each Shot 2 must advance Shot 1 physically. Never repeat the same generic stock shot twice.

IMAGE PROMPTS:
Write literal camera-ready descriptions. No metaphor, no diagrams, no equations, no abstract
particles, no generic laboratory, no symbolic representation.

DESCRIPTION:
Describe ONLY the current topic. Never mention the next topic.

NEXT SHORT:
Choose one specific, curiosity-driven everyday mystery related enough to feel like a natural
follow-up, but not a duplicate of the current topic.

{feedback}
"""

    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            retry = ""
            if last_error:
                retry = (
                    "\n\nPREVIOUS ATTEMPT FAILED THE HARD QUALITY GATE."
                    " Rewrite the story instead of defending it."
                    f"\nQUALITY GATE ERROR:\n{last_error}\n"
                    "The replacement must contain concrete, searchable physical beats."
                )
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt + retry,
                config=types.GenerateContentConfig(
                    system_instruction=_build_system_prompt(),
                    response_mime_type="application/json",
                    response_json_schema=_build_schema(),
                    temperature=0.9,
                ),
            )
            text = getattr(response, "text", None)
            if not text:
                raise RuntimeError("Gemini returned an empty response.")
            parsed = _parse(text)
            return _normalize(parsed, topic)
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
            print(f"⚠️ Story quality attempt {attempt}/{MAX_ATTEMPTS} failed: {last_error}")
            if attempt < MAX_ATTEMPTS:
                time.sleep(min(8, 2 * attempt))

    raise RuntimeError(f"SCRIPT GENERATION FAILED AFTER {MAX_ATTEMPTS} QUALITY-GATED ATTEMPTS. Last error: {last_error}")


if __name__ == "__main__":
    print("generate_script.py — entertainment-first + hard visual-contract gate")
