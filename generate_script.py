"""
generate_script.py

Educational YouTube Shorts Script Generator
Version 5 — adds cross-scene visual consistency, multi-visual scenes,
self-graded visual impact scoring, and parameterized video structure for
future long-form support.

Pipeline position:
    Topic Generator -> [THIS FILE] -> TikTok TTS -> Pollinations AI Images
    -> MoviePy Assembly -> YouTube Upload

Design principles carried over from v4 (see prior version history):
single source of truth for narration, semantics-as-enums translated to
concrete numbers in code, structural beat vs. retention mechanic kept
separate, IDs/totals computed by code never asked from the model,
self-critique as a factory feedback loop.

What's new in v5 and why:

1. IMAGE CONSISTENCY (highest priority). Independently generated scene
   images drift in style. A model INSTRUCTION to "stay consistent" is
   not an enforcement mechanism — it's a hope. Real enforcement is:
   (a) one seed reused across every image call for this video, and
   (b) a literal shared style-lock phrase appended to every image_prompt
   in code, so consistency doesn't depend on the model remembering to
   repeat itself correctly across 7-14 separate prompts.

2. CAPTION EMPHASIS, NOT FABRICATED TIMING. Millisecond-accurate word
   timing can only be known after TTS actually speaks the line — Gemini
   generates this script BEFORE that happens. Asking the model for
   "highlight_ms" would produce confident-looking numbers with no basis
   in reality. caption_highlights instead captures the model's real job
   (which words deserve emphasis and how strongly) and leaves exact
   timing to a forced-alignment step run on the TTS audio downstream.

3. MULTIPLE VISUALS PER SCENE. A single 6-8 second scene held on one
   static image (even zoomed/panned) is often slower than the "new
   information every 2-4 seconds" rule wants. Scenes now contain 1-2
   "visuals" — independent shots with their own camera/animation/prompt
   — so a single narration block can cut between two images if that
   serves pacing better.

4. VISUAL IMPACT SCORE + AUTO-FLAGGING. Each visual is self-graded 1-10
   by the model. Code then flags any hero-priority visual scoring below
   threshold as needs_regeneration=True, giving the pipeline a concrete,
   pre-computed signal for automatic re-generation instead of requiring
   a human to eyeball thousands of outputs.

5. PARAMETERIZED VIDEO STRUCTURE. scene_count and target duration are no
   longer hardcoded as "7" and "45" throughout the prompt and validator.
   They're read from config, injected into a dynamically built system
   prompt, and written back into the output under video_structure by
   CODE (not the model) — this is a pipeline parameter, not a creative
   choice, so it belongs in the same "deterministic, code-owned" bucket
   as video_id.

Rejected for v5 (with reasoning):
- A standalone "fact_source_type" field was considered but dropped —
  it duplicates the existing top-level "category" field. Per-scene
  domain tagging only earns its complexity if a single video genuinely
  spans multiple science domains, which a 45-second single-phenomenon
  Short generally does not.
"""

import json
import os
import random
import re
import time
import uuid

from google import genai
from google.genai import types


# --------------------------------------------------------------------------
# SYSTEM PROMPT (parameterized — built per call, not a static constant)
# --------------------------------------------------------------------------

_SHORT_FORM_BEAT_TABLE = """
1. HOOK        (0-3s)   Cold open on the most surprising fact or image.
                         Start mid-idea. No setup.
2. QUESTION     (3-8s)   Turn the hook into an open question the brain
                         needs answered.
3. EXPLANATION  (8-20s)  Answer it. Mechanism, not just description.
4. EXAMPLE      (20-32s) Ground it in something real and picturable.
                         (If explanation needs more room, use this scene
                         to continue it and compress example into scene 5.)
5. MIND-BLOWING FACT (32-42s) A second-order implication or scale twist
                         that recontextualizes everything said so far.
6. ENDING       (42-45s) A tight, quotable button. No summary, no
                         "thanks for watching."
"""

_PURPOSE_CYCLE = [
    "hook", "question", "explanation", "example", "mindblowing_fact", "ending",
]


def _generate_beat_table(scene_count: int, target_seconds: int) -> str:
    """Build a beat table for non-default scene counts. The 7-scene short
    form has a hand-tuned table above; anything else gets a proportional
    generic one so the architecture supports longer formats later without
    a rewrite."""

    if scene_count == 7:
        return _SHORT_FORM_BEAT_TABLE

    lines = []
    per_scene = target_seconds / scene_count
    elapsed = 0.0
    for i in range(scene_count):
        if i == scene_count - 1:
            purpose = "ending"
        elif i == 0:
            purpose = "hook"
        elif i == 1:
            purpose = "question"
        else:
            # cycle through the middle beats, saving "ending" for last
            middle = _PURPOSE_CYCLE[2:-1]
            purpose = middle[(i - 2) % len(middle)]
        start = int(elapsed)
        elapsed += per_scene
        end = int(elapsed)
        lines.append(f"{i + 1}. {purpose.upper():<16} ({start}-{end}s)")
    return "\n".join(lines)


def build_system_prompt(scene_count: int = 7, target_seconds: int = 45) -> str:
    """Assemble the full system prompt for the requested video structure."""

    beat_table = _generate_beat_table(scene_count, target_seconds)

    return f"""
You are a world-class educational YouTube Shorts writer, director, and
prompt engineer, working simultaneously as all three.

You write the way the best science/education channels on YouTube think —
Kurzgesagt, Veritasium, Vox, Johnny Harris, RealLifeLore — but you never
copy their wording, jokes, or phrasing. You copy their STRUCTURE, PACING,
and CURIOSITY MECHANICS, then produce 100% original content for a
{target_seconds}-second vertical Short.

You do not just write a script. You output a complete production
storyboard that a fully automated pipeline will execute with zero human
review. Every field you fill in becomes a literal instruction to a video
editor (MoviePy), a text-to-speech engine, and an AI image generator.
There is no human checking your work before it goes into the video, so
precision is not optional.

====================================================================
MISSION
====================================================================

Maximize audience retention while teaching one genuinely interesting,
scientifically accurate idea. Every sentence must earn the next three
seconds of attention. Every visual and audio choice must reinforce what
the narration is doing at that exact moment — nothing is decorative.

====================================================================
VIDEO BEAT STRUCTURE (~{target_seconds} seconds, {scene_count} scenes)
====================================================================
{beat_table}

There are always exactly {scene_count} scenes and the last scene is
always the ending. Every 2-4 seconds, something new must be revealed,
shown, or reframed — use a second visual within a scene (see VISUALS
below) if one image can't carry that pacing on its own.

====================================================================
WRITING RULES
====================================================================

- Grade 6 reading level. Short, plain, punchy sentences.
- No jargon unless immediately translated into a concrete image.
- Never repeat a word, phrase, or idea already used earlier in the script.
- No filler ("basically", "essentially", "in fact").
- Never sound like an AI assistant. No "in this video", "let's explore".
- Never open the hook with "Did you know...", "Today we're going to...",
  "Have you ever wondered...", or any question. Open on a statement.

====================================================================
ACCURACY RULES — NON-NEGOTIABLE
====================================================================

- Every claim must be scientifically accurate and defensible.
- If unsure of an exact number or mechanism, do NOT invent one. Use a
  qualitative comparison instead ("faster than a bullet", not a made-up
  precise speed).
- Never state speculation or disputed claims as settled fact.
- Never give medical, financial, political, or religious content.
- Set "confidence" to "qualitative_estimate" on any scene where a claim
  is an approximation rather than a precise, verifiable fact.

====================================================================
TOPIC GUARDRAILS
====================================================================

GOOD: mechanisms behind everyday phenomena, physics, biology, technology,
space, engineering — "why/how" questions with a real, teachable answer.
NEVER: listicles, celebrity news, politics, religion, conspiracy-as-fact,
medical advice, financial advice, violence, gore.

====================================================================
VISUAL CONSISTENCY
====================================================================

All scenes in this video must look like they belong to the same
production. Pick ONE coherent visual identity in visual_identity and
apply it in spirit to every single image_prompt — same rendering
approach, same lighting philosophy, same color family. Do not switch
from photoreal to illustration to diagram style between scenes unless
the scene's image_style explicitly calls for it. Consistency is enforced
programmatically downstream, but your prompts must not fight that by
describing wildly different worlds.

====================================================================
TOP-LEVEL FIELDS
====================================================================

title            Max 60 chars. Instant curiosity. Prefer Why/How framing.
description      One concise educational paragraph. No hashtags.
tags             8-12 lowercase SEO tags, no duplicates, no hashtags.
category         One short lowercase label: space, physics, biology,
                 chemistry, technology, engineering, earth_science,
                 human_body, or psychology.
thumbnail_prompt A single extremely detailed AI image prompt for the
                 static YouTube thumbnail (see IMAGE PROMPTS below).
                 Bold, high-contrast hero shot of the video's single
                 most striking visual, with clear negative space in the
                 upper or lower third for a title overlay in post.
voice_style      Object: {{"tone": short phrase e.g. "warm confident
                 educator", "pace": one of slow|medium|fast, "pitch":
                 one of low|medium|high}}.
music            Object: {{"search": one search phrase for a documentary/
                 science-tone music library, "arc": one sentence
                 describing how the track should evolve across the
                 video}}.
visual_identity  Object: {{"style": default image style for this video,
                 "palette": 3-5 word color palette description, "mood_arc":
                 one sentence describing how visual mood shifts across
                 the video}}.
retention_self_check  Object: {{"weakest_scene": integer 1-{scene_count}
                 naming the scene most likely to lose a viewer, "reason":
                 one short sentence why}}. Be honest.

====================================================================
SCENE PLAN — THE STORYBOARD
====================================================================

Generate EXACTLY {scene_count} scene objects.

Each scene object must contain:

scene              Integer 1-{scene_count}, matching position.
purpose            One of: hook | question | explanation | example |
                   mindblowing_fact | ending.
retention_purpose  One of: open_loop | escalation | payoff | reframe |
                   curiosity_gap | pattern_break | emotional_release |
                   closure. The psychological mechanism keeping the
                   viewer watching at this moment.
narration          The exact line(s) spoken during this scene.
subtitle_text      The on-screen caption text — usually shorter and
                   punchier than narration.
caption_highlights List of 1-3 objects {{"word": one word from
                   subtitle_text, "emphasis": "strong" or "light"}}, in
                   the order they appear. This tells the editor WHICH
                   words to visually emphasize — exact timing is
                   computed later from the actual TTS audio, not by you.
subtitle_style     One of: bold_center | kinetic_word_by_word |
                   lower_third | minimal_clean.
emphasis_word      The single word in narration that should land
                   hardest vocally.
duration           Integer seconds, 3-8: the TOTAL time for this scene,
                   equal to the sum of its visuals' durations.
pause_after_ms     Integer 0-600. Silence held after this scene ends.
emotional_tone     One of: curious | tense | calm | awe | playful |
                   urgent | satisfied.
visual_priority    One of: hero | supporting. Mark at most 3 scenes per
                   video as hero.
transition         How this scene cuts into the NEXT one. One of:
                   hard_cut | whip_pan | match_cut | dissolve | none.
                   The final scene must be "none".
sfx_cue            Object: {{"term": short SFX search term, "at_ms":
                   integer milliseconds into this scene when it hits}}.
music_cue          One of: intro | build | swell | drop | fade_out |
                   none.
confidence         One of: high | qualitative_estimate.
visuals            List of 1-2 objects — see VISUALS below. Use 2 only
                   when a single sentence genuinely benefits from a cut
                   partway through (e.g. cause shown, then effect shown).

====================================================================
VISUALS (nested inside each scene)
====================================================================

Each visual object must contain:

segment            Integer, 1 or 2, position within the scene.
duration           Integer seconds. Sum of all visuals in a scene must
                   equal that scene's "duration".
camera             One of: close_up | medium | wide | macro | top_down |
                   side | aerial | orbit.
animation          One of: zoom_in | zoom_out | pan_left | pan_right |
                   rotate | parallax | highlight | hold. Use "hold" at
                   most once in the entire video, never in scene 1.
zoom_strength      One of: subtle | medium | strong.
motion_intensity   One of: low | medium | high.
visual_complexity  One of: simple | moderate | complex.
image_style        One of: realistic_3d_render | scientific_illustration
                   | cinematic_photograph | macro_photography |
                   infographic_diagram.
lighting           Short phrase, e.g. "volumetric side lighting".
color_palette      Short phrase, consistent with visual_identity.
overlay            Object: {{"type": one of none|arrow|icon|diagram|
                   comparison_graphic, "description": short description
                   if type is not "none", else empty string}}.
image_prompt       A single, extremely detailed, self-contained AI
                   image-generation prompt (see IMAGE PROMPTS below).
visual_impact      Integer 1-10: your honest rating of how visually
                   striking and scroll-stopping this specific image
                   will be. Do not inflate this — low scores on
                   supporting shots are fine and expected.

====================================================================
IMAGE PROMPTS
====================================================================

Every image_prompt (and the thumbnail_prompt) must describe exactly ONE
clear visual and be production-ready. Always include:
- The single subject and exactly what it's doing/showing.
- The chosen image_style spelled out in words.
- Quality tags fitting the shot: documentary quality, volumetric
  lighting, ultra detailed.
- "Vertical composition."
- "No text. No labels. No logos. No watermark."

GOOD:
"Ultra realistic 3D render of a cross section of the human inner ear,
showing tiny hair cells vibrating inside the cochlea. Macro detail, soft
blue bioluminescent lighting, documentary quality, ultra detailed,
vertical composition. No text. No labels. No watermark."

BAD (too vague, not directable):
"A person explaining science." / "Earth from space." / "A classroom."

====================================================================
OUTPUT FORMAT
====================================================================

Return ONLY a single valid JSON object matching this exact schema. No
markdown fences. No commentary. No trailing text.

{{
    "title": "",
    "description": "",
    "tags": [],
    "category": "",
    "thumbnail_prompt": "",
    "voice_style": {{"tone": "", "pace": "", "pitch": ""}},
    "music": {{"search": "", "arc": ""}},
    "visual_identity": {{"style": "", "palette": "", "mood_arc": ""}},
    "retention_self_check": {{"weakest_scene": 1, "reason": ""}},
    "scene_plan": [
        {{
            "scene": 1,
            "purpose": "",
            "retention_purpose": "",
            "narration": "",
            "subtitle_text": "",
            "caption_highlights": [{{"word": "", "emphasis": "strong"}}],
            "subtitle_style": "",
            "emphasis_word": "",
            "duration": 6,
            "pause_after_ms": 0,
            "emotional_tone": "",
            "visual_priority": "",
            "transition": "",
            "sfx_cue": {{"term": "", "at_ms": 0}},
            "music_cue": "",
            "confidence": "high",
            "visuals": [
                {{
                    "segment": 1,
                    "duration": 6,
                    "camera": "",
                    "animation": "",
                    "zoom_strength": "",
                    "motion_intensity": "",
                    "visual_complexity": "",
                    "image_style": "",
                    "lighting": "",
                    "color_palette": "",
                    "overlay": {{"type": "none", "description": ""}},
                    "image_prompt": "",
                    "visual_impact": 7
                }}
            ]
        }}
    ]
}}
"""


def build_user_prompt(topic: str, config: dict) -> str:
    """Assemble the per-request prompt from topic + channel config."""

    return f"""
TOPIC
{topic}

AUDIENCE
{config["channel"]["audience"]}

TONE
{config["channel"]["tone"]}

LANGUAGE
{config["script"]["language"]}

TARGET NARRATION LENGTH
{config["script"]["target_narration_seconds"]} seconds

Produce the complete production storyboard for this topic, following
every rule and every field in the system instructions exactly.

Return ONLY valid JSON. No markdown. No commentary.
"""


def generate_script(topic: str, config: dict) -> dict:
    """Call Gemini to produce one full educational Short storyboard."""

    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"]
    )

    scene_count = int(config["script"].get("scene_count", 7))
    target_seconds = int(config["script"]["target_narration_seconds"])

    prompt = build_user_prompt(topic, config)
    system_prompt = build_system_prompt(scene_count, target_seconds)

    print("=" * 80)
    print("GENERATING SCRIPT")
    print("=" * 80)
    print(topic)
    print("=" * 80)

    response = client.models.generate_content(

        model="gemini-2.5-flash-lite",

        contents=prompt,

        config=types.GenerateContentConfig(

            system_instruction=system_prompt,

            response_mime_type="application/json",

            temperature=1.05,

            top_p=0.95,

        ),

    )

    text = response.text

    text = (
        text.replace("```json", "")
        .replace("```", "")
        .strip()
    )

    decoder = json.JSONDecoder()

    script, _ = decoder.raw_decode(text)

    script["topic"] = topic

    # video_structure is a pipeline parameter, not a creative decision —
    # written by code, same as video_id, never asked from the model.
    script["video_structure"] = {
        "format": "short_form" if scene_count == 7 else "custom",
        "scene_count": scene_count,
        "target_duration_seconds": target_seconds,
    }

    print("=" * 80)
    print("SCRIPT GENERATED")
    print("=" * 80)

    print(
        json.dumps(
            script,
            indent=2,
            ensure_ascii=False,
        )
    )

    print("=" * 80)

    return script, scene_count


# --------------------------------------------------------------------------
# VALIDATION + NORMALIZATION
# --------------------------------------------------------------------------
#
# The model decides INTENT (enums). This layer decides IMPLEMENTATION
# (concrete numbers, shared seed, style-lock text), so nothing downstream
# has to interpret a string or trust the model's memory across 7+ prompts.

REQUIRED_KEYS = [
    "title",
    "description",
    "tags",
    "category",
    "thumbnail_prompt",
    "voice_style",
    "music",
    "visual_identity",
    "retention_self_check",
    "scene_plan",
]

REQUIRED_SCENE_KEYS = [
    "scene",
    "purpose",
    "retention_purpose",
    "narration",
    "subtitle_text",
    "caption_highlights",
    "subtitle_style",
    "emphasis_word",
    "duration",
    "pause_after_ms",
    "emotional_tone",
    "visual_priority",
    "transition",
    "sfx_cue",
    "music_cue",
    "confidence",
    "visuals",
]

REQUIRED_VISUAL_KEYS = [
    "segment",
    "duration",
    "camera",
    "animation",
    "zoom_strength",
    "motion_intensity",
    "visual_complexity",
    "image_style",
    "lighting",
    "color_palette",
    "overlay",
    "image_prompt",
    "visual_impact",
]

VALID_PURPOSE = {
    "hook", "question", "explanation", "example",
    "mindblowing_fact", "ending",
}

VALID_RETENTION_PURPOSE = {
    "open_loop", "escalation", "payoff", "reframe",
    "curiosity_gap", "pattern_break", "emotional_release", "closure",
}

VALID_SUBTITLE_STYLE = {
    "bold_center", "kinetic_word_by_word", "lower_third", "minimal_clean",
}

VALID_EMPHASIS = {"strong", "light"}

VALID_EMOTIONAL_TONE = {
    "curious", "tense", "calm", "awe", "playful", "urgent", "satisfied",
}

VALID_VISUAL_PRIORITY = {"hero", "supporting"}
VALID_VISUAL_COMPLEXITY = {"simple", "moderate", "complex"}

VALID_CAMERA = {
    "close_up", "medium", "wide", "macro",
    "top_down", "side", "aerial", "orbit",
}

VALID_ANIMATION = {
    "zoom_in", "zoom_out", "pan_left", "pan_right",
    "rotate", "parallax", "highlight", "hold",
}

VALID_ZOOM_STRENGTH = {"subtle", "medium", "strong"}
VALID_MOTION_INTENSITY = {"low", "medium", "high"}

VALID_TRANSITION = {
    "hard_cut", "whip_pan", "match_cut", "dissolve", "none",
}

VALID_IMAGE_STYLE = {
    "realistic_3d_render", "scientific_illustration",
    "cinematic_photograph", "macro_photography", "infographic_diagram",
}

VALID_OVERLAY_TYPE = {"none", "arrow", "icon", "diagram", "comparison_graphic"}
VALID_MUSIC_CUE = {"intro", "build", "swell", "drop", "fade_out", "none"}
VALID_CONFIDENCE = {"high", "qualitative_estimate"}

# Semantic label -> concrete MoviePy parameter. The model never sees these
# numbers; it only ever picks the enum. Editor code reads the numbers.
ZOOM_STRENGTH_TO_FACTOR = {"subtle": 1.06, "medium": 1.15, "strong": 1.30}
MOTION_INTENSITY_TO_SPEED = {"low": 0.5, "medium": 1.0, "high": 1.6}

VISUAL_IMPACT_REGEN_THRESHOLD = 5


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40] or "video"


def _check_enum(value, allowed, label):
    if value not in allowed:
        raise RuntimeError(f"{label}: invalid value '{value}'. Expected one of {sorted(allowed)}.")


def _build_style_lock(visual_identity: dict) -> str:
    """Turn visual_identity into a literal phrase appended to every
    image_prompt in the video. This is the actual consistency enforcement
    mechanism — not a model instruction, a guaranteed shared substring."""

    style = visual_identity.get("style", "").strip()
    palette = visual_identity.get("palette", "").strip()
    parts = [p for p in [style, palette] if p]
    if not parts:
        return ""
    return "Consistent visual identity across the video: " + ", ".join(parts) + "."


def validate_script(script: dict, expected_scene_count: int = 7) -> dict:
    """Validate + normalize a generated storyboard so nothing downstream
    has to guess. Raises RuntimeError with a specific message on any
    schema violation — fail loudly, never silently patch bad content."""

    if not isinstance(script, dict):
        raise RuntimeError("Gemini did not return a JSON object.")

    for key in REQUIRED_KEYS:
        if key not in script:
            raise RuntimeError(f"Missing required key: {key}")

    if not isinstance(script["tags"], list) or not script["tags"]:
        raise RuntimeError("tags must be a non-empty list.")

    for obj_key, required_subkeys in [
        ("voice_style", ["tone", "pace", "pitch"]),
        ("music", ["search", "arc"]),
        ("visual_identity", ["style", "palette", "mood_arc"]),
        ("retention_self_check", ["weakest_scene", "reason"]),
    ]:
        if not isinstance(script[obj_key], dict):
            raise RuntimeError(f"{obj_key} must be an object.")
        for sub in required_subkeys:
            if sub not in script[obj_key]:
                raise RuntimeError(f"{obj_key} missing '{sub}'.")

    if not (1 <= int(script["retention_self_check"]["weakest_scene"]) <= expected_scene_count):
        raise RuntimeError(f"retention_self_check.weakest_scene must be 1-{expected_scene_count}.")

    if not isinstance(script["scene_plan"], list):
        raise RuntimeError("scene_plan must be a list.")

    if len(script["scene_plan"]) != expected_scene_count:
        raise RuntimeError(
            f"Expected {expected_scene_count} scenes but got {len(script['scene_plan'])}."
        )

    # Image consistency: one seed for the whole video, one style-lock
    # phrase appended to every prompt in the video (scenes + thumbnail).
    seed = random.randint(1, 2_147_483_647)
    style_lock = _build_style_lock(script["visual_identity"])

    hold_count = 0
    total_duration = 0

    for index, scene in enumerate(script["scene_plan"], start=1):

        if not isinstance(scene, dict):
            raise RuntimeError(f"Scene {index} is invalid.")

        for key in REQUIRED_SCENE_KEYS:
            if key not in scene:
                raise RuntimeError(f"Scene {index} missing '{key}'.")

        if int(scene["scene"]) != index:
            raise RuntimeError(
                f"Scene {index} has out-of-order 'scene' number {scene['scene']}."
            )

        _check_enum(scene["purpose"], VALID_PURPOSE, f"Scene {index} purpose")
        _check_enum(scene["retention_purpose"], VALID_RETENTION_PURPOSE, f"Scene {index} retention_purpose")
        _check_enum(scene["subtitle_style"], VALID_SUBTITLE_STYLE, f"Scene {index} subtitle_style")
        _check_enum(scene["emotional_tone"], VALID_EMOTIONAL_TONE, f"Scene {index} emotional_tone")
        _check_enum(scene["visual_priority"], VALID_VISUAL_PRIORITY, f"Scene {index} visual_priority")
        _check_enum(scene["transition"], VALID_TRANSITION, f"Scene {index} transition")
        _check_enum(scene["music_cue"], VALID_MUSIC_CUE, f"Scene {index} music_cue")
        _check_enum(scene["confidence"], VALID_CONFIDENCE, f"Scene {index} confidence")

        if index == expected_scene_count and scene["transition"] != "none":
            raise RuntimeError(f"Final scene ({expected_scene_count}) transition must be 'none'.")

        if not isinstance(scene["caption_highlights"], list):
            raise RuntimeError(f"Scene {index} caption_highlights must be a list.")
        for h in scene["caption_highlights"]:
            if not isinstance(h, dict) or "word" not in h or "emphasis" not in h:
                raise RuntimeError(f"Scene {index} caption_highlights entries need 'word' and 'emphasis'.")
            _check_enum(h["emphasis"], VALID_EMPHASIS, f"Scene {index} caption_highlights.emphasis")

        if not isinstance(scene["sfx_cue"], dict) or "term" not in scene["sfx_cue"] or "at_ms" not in scene["sfx_cue"]:
            raise RuntimeError(f"Scene {index} sfx_cue must be an object with 'term' and 'at_ms'.")

        if not isinstance(scene["duration"], (int, float)):
            raise RuntimeError(f"Scene {index} duration must be numeric.")
        scene["duration"] = max(3, min(8, int(scene["duration"])))
        total_duration += scene["duration"]

        scene["pause_after_ms"] = max(0, min(600, int(scene.get("pause_after_ms", 0))))
        scene["narration"] = str(scene["narration"]).strip()
        scene["subtitle_text"] = str(scene["subtitle_text"]).strip()

        if not isinstance(scene["visuals"], list) or not (1 <= len(scene["visuals"]) <= 2):
            raise RuntimeError(f"Scene {index} must have 1 or 2 visuals.")

        visuals_duration_sum = 0

        for v_index, visual in enumerate(scene["visuals"], start=1):

            if not isinstance(visual, dict):
                raise RuntimeError(f"Scene {index} visual {v_index} is invalid.")

            for key in REQUIRED_VISUAL_KEYS:
                if key not in visual:
                    raise RuntimeError(f"Scene {index} visual {v_index} missing '{key}'.")

            if int(visual["segment"]) != v_index:
                raise RuntimeError(f"Scene {index} visual {v_index} has out-of-order 'segment'.")

            _check_enum(visual["camera"], VALID_CAMERA, f"Scene {index} visual {v_index} camera")
            _check_enum(visual["animation"], VALID_ANIMATION, f"Scene {index} visual {v_index} animation")
            _check_enum(visual["zoom_strength"], VALID_ZOOM_STRENGTH, f"Scene {index} visual {v_index} zoom_strength")
            _check_enum(visual["motion_intensity"], VALID_MOTION_INTENSITY, f"Scene {index} visual {v_index} motion_intensity")
            _check_enum(visual["visual_complexity"], VALID_VISUAL_COMPLEXITY, f"Scene {index} visual {v_index} visual_complexity")
            _check_enum(visual["image_style"], VALID_IMAGE_STYLE, f"Scene {index} visual {v_index} image_style")

            if visual["animation"] == "hold":
                hold_count += 1
                if index == 1 and v_index == 1:
                    raise RuntimeError("Scene 1's first visual must not use 'hold'.")

            if not isinstance(visual["overlay"], dict) or "type" not in visual["overlay"]:
                raise RuntimeError(f"Scene {index} visual {v_index} overlay must be an object with 'type'.")
            _check_enum(visual["overlay"]["type"], VALID_OVERLAY_TYPE, f"Scene {index} visual {v_index} overlay.type")
            visual["overlay"].setdefault("description", "")

            if not isinstance(visual["duration"], (int, float)):
                raise RuntimeError(f"Scene {index} visual {v_index} duration must be numeric.")
            visual["duration"] = max(2, int(visual["duration"]))
            visuals_duration_sum += visual["duration"]

            impact = visual.get("visual_impact")
            if not isinstance(impact, (int, float)) or not (1 <= impact <= 10):
                raise RuntimeError(f"Scene {index} visual {v_index} visual_impact must be 1-10.")
            visual["visual_impact"] = int(impact)

            # Consistency enforcement: model decides content, code
            # guarantees every prompt shares the same style-lock phrase.
            visual["image_prompt"] = str(visual["image_prompt"]).strip()
            if style_lock and style_lock not in visual["image_prompt"]:
                visual["image_prompt"] = f"{visual['image_prompt']} {style_lock}"

            # Pipeline signal: auto-flag weak hero shots for regeneration
            # instead of requiring a human to review every video.
            visual["needs_regeneration"] = (
                scene["visual_priority"] == "hero"
                and visual["visual_impact"] < VISUAL_IMPACT_REGEN_THRESHOLD
            )

            visual["zoom_factor"] = ZOOM_STRENGTH_TO_FACTOR[visual["zoom_strength"]]
            visual["motion_speed"] = MOTION_INTENSITY_TO_SPEED[visual["motion_intensity"]]

        if visuals_duration_sum != scene["duration"]:
            raise RuntimeError(
                f"Scene {index}: visuals durations sum to {visuals_duration_sum}s "
                f"but scene duration is {scene['duration']}s."
            )

    if hold_count > 1:
        raise RuntimeError(
            f"'hold' animation used {hold_count} times; only one hold is allowed per video."
        )

    script["title"] = script["title"].strip()[:60]
    script["description"] = script["description"].strip()[:5000]
    script["tags"] = [str(t).strip().lower() for t in script["tags"]]
    script["category"] = str(script["category"]).strip().lower()

    script["thumbnail_prompt"] = script["thumbnail_prompt"].strip()
    if style_lock and style_lock not in script["thumbnail_prompt"]:
        script["thumbnail_prompt"] = f"{script['thumbnail_prompt']} {style_lock}"

    script["image_generation"] = {
        "seed": seed,
        "style_lock": style_lock,
    }

    # IDs and totals are computed here, never trusted from the model —
    # this is what keeps thousands of generated videos collision-free
    # and internally consistent.
    script["video_id"] = f"{_slugify(script['title'])}-{uuid.uuid4().hex[:8]}"
    script["generated_at"] = int(time.time())
    script.setdefault("video_structure", {})
    script["video_structure"]["actual_duration_seconds"] = total_duration

    return script


# --------------------------------------------------------------------------
# CLI / MANUAL TEST HARNESS
# --------------------------------------------------------------------------

if __name__ == "__main__":

    import yaml

    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    test_topics = [
        "Why can't you tickle yourself",
        "Why do onions make you cry",
        "Why is space silent",
        "How WiFi finds your phone",
        "Why don't birds get electrocuted on power lines",
        "How airplanes fly",
        "Why is the ocean salty",
    ]

    for topic in test_topics:

        print("=" * 100)
        print("TOPIC")
        print(topic)
        print("=" * 100)

        script, scene_count = generate_script(topic, config)
        script = validate_script(script, expected_scene_count=scene_count)

        print(
            json.dumps(
                script,
                indent=2,
                ensure_ascii=False,
            )
        )

        print("=" * 100)
        print("SCRIPT VALID")
        print("=" * 100)
