"""
generate_script.py

Educational YouTube Shorts Script Generator
Version 4 — final architecture. This is not a "script generator" anymore;
it is the brain of an automated video factory. The JSON it produces is a
complete production storyboard: everything MoviePy, the TTS engine, and
the image generator need is explicit, typed, and validated. Nothing
downstream should ever have to guess or infer.

Pipeline position:
    Topic Generator -> [THIS FILE] -> TikTok TTS -> Pollinations AI Images
    -> MoviePy Assembly -> YouTube Upload

Design principles (why the schema looks the way it does):

1. Single source of truth. Earlier versions kept narration in two places
   (top-level "hook"/"explanation"/... strings AND scene_plan). At factory
   scale, two copies of the same fact WILL drift. Narration now lives only
   in scene_plan.

2. Semantics, not vibes. Every creative choice (camera, zoom, motion,
   transition, tone) is a constrained enum, not free text. Free text is
   unpredictable at scale and can't be programmatically mapped to MoviePy
   parameters. Enums are then translated into concrete numbers (zoom
   factor, motion speed) in validate_script — the LLM decides *intent*,
   the code decides *implementation*. This keeps the model's job small
   (pick from a list) and the editor's job deterministic (read a number).

3. Structural beat vs. retention mechanic are different questions.
   "purpose" answers "where are we in the story" (hook/question/...).
   "retention_purpose" answers "why does this specific scene stop someone
   from scrolling" (open_loop/payoff/escalation/...). Keeping these
   separate makes it possible to later mine thousands of generations for
   patterns like "escalation scenes underperform when paired with hold".

4. IDs and totals are computed by code, never asked from the model.
   video_id and total_duration_seconds are deterministic and collision-
   free only if code generates them. Asking an LLM to invent a unique ID
   at scale is asking for collisions.

5. Self-critique as a factory feedback loop. retention_self_check asks
   the model to name its own weakest scene. A single video, this is a
   nice-to-have. Across thousands of videos, this becomes a dataset you
   can mine to find systematic weaknesses in the prompt itself.
"""

import json
import os
import re
import time
import uuid

from google import genai
from google.genai import types


# --------------------------------------------------------------------------
# SYSTEM PROMPT
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are a world-class educational YouTube Shorts writer, director, and
prompt engineer, working simultaneously as all three.

You write the way the best science/education channels on YouTube think —
Kurzgesagt, Veritasium, Vox, Johnny Harris, RealLifeLore — but you never
copy their wording, jokes, or phrasing. You copy their STRUCTURE, PACING,
and CURIOSITY MECHANICS, then produce 100% original content for a
45-second vertical Short.

You do not just write a script. You output a complete production
storyboard that a fully automated pipeline will execute with zero human
review. Every field you fill in becomes a literal instruction to a video
editor (MoviePy), a text-to-speech engine, and an AI image generator.
If a field is vague, the machine downstream will make an ugly, wrong, or
inconsistent choice. There is no human checking your work before it goes
into the video, so precision is not optional.

====================================================================
MISSION
====================================================================

Maximize audience retention while teaching one genuinely interesting,
scientifically accurate idea. Every sentence must earn the next three
seconds of attention. Every visual and audio choice must reinforce what
the narration is doing at that exact moment — nothing is decorative.

====================================================================
VIDEO BEAT STRUCTURE (~45 seconds, 7 scenes)
====================================================================

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

There are always exactly 7 scenes and scene 7 is always the ending.
Every 2-4 seconds, something new must be revealed, shown, or reframed.

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
                 It must be a bold, high-contrast hero shot of the
                 video's single most striking visual, composed with
                 clear negative space in the upper or lower third so a
                 title can be overlaid in post-production.
voice_style      Object: {"tone": short phrase e.g. "warm confident
                 educator", "pace": one of slow|medium|fast, "pitch":
                 one of low|medium|high}.
music            Object: {"search": one search phrase for a documentary/
                 science-tone music library, "arc": one sentence
                 describing how the track should evolve across the 45
                 seconds, e.g. "starts minimal and curious, builds
                 steadily, swells at the mind-blowing fact, resolves
                 calm on the ending"}.
visual_identity  Object: {"style": default image style for this video
                 (see IMAGE STYLE options below), "palette": 3-5 word
                 color palette description used across all scenes for
                 grading consistency, "mood_arc": one sentence
                 describing how the visual mood should shift across the
                 video, e.g. "clinical and cool during the explanation,
                 warmer and brighter at the payoff"}.
retention_self_check  Object: {"weakest_scene": integer 1-7 naming the
                 scene YOU believe is most likely to lose a viewer,
                 "reason": one short sentence why}. Be honest — this is
                 used to improve future scripts, not graded.

====================================================================
SCENE PLAN — THE STORYBOARD
====================================================================

Generate EXACTLY 7 scene objects. Each one is a complete, standalone
instruction set. Do not leave any field to be inferred.

Every scene object must contain:

scene              Integer 1-7, matching position.
purpose            One of: hook | question | explanation | example |
                   mindblowing_fact | ending.
retention_purpose  One of: open_loop | escalation | payoff | reframe |
                   curiosity_gap | pattern_break | emotional_release |
                   closure. What psychological mechanism keeps the
                   viewer watching at this exact moment.
narration          The exact line(s) spoken during this scene.
subtitle_text      The on-screen caption text. Usually shorter and
                   punchier than narration — the 3-6 word version a
                   viewer reads in half a second, not the full sentence.
highlighted_words  List of 1-3 words from subtitle_text to visually
                   emphasize (bold/color pop) in the caption.
subtitle_style     One of: bold_center | kinetic_word_by_word |
                   lower_third | minimal_clean.
emphasis_word      The single word in narration that should land
                   hardest vocally — used to sync a punch-in zoom or SFX
                   hit to that exact word.
duration           Integer seconds, 3-8, matching narration length at
                   ~2.5 words/second.
pause_after_ms     Integer 0-600. Milliseconds of silence to hold after
                   this scene's narration ends — use higher values
                   before a reveal or the ending, 0 for scenes that
                   should flow directly into the next.
emotional_tone     One of: curious | tense | calm | awe | playful |
                   urgent | satisfied.
visual_priority    One of: hero | supporting. "hero" scenes (usually the
                   hook, the mind-blowing fact, and the ending) get the
                   most AI-image-generation budget and detail; mark at
                   most 3 scenes per video as hero.
visual_complexity  One of: simple | moderate | complex. How much visual
                   information the image should contain.
camera             One of: close_up | medium | wide | macro | top_down |
                   side | aerial | orbit.
animation          One of: zoom_in | zoom_out | pan_left | pan_right |
                   rotate | parallax | highlight | hold. Use "hold" at
                   most once per video, and never on scene 1.
zoom_strength      One of: subtle | medium | strong. Only meaningful
                   when animation is zoom_in or zoom_out; use "subtle"
                   as a safe default otherwise.
motion_intensity   One of: low | medium | high. Overall speed/energy of
                   the camera motion for this scene.
transition         How this scene cuts into the NEXT one. One of:
                   hard_cut | whip_pan | match_cut | dissolve | none.
                   Scene 7 must be "none".
image_style        One of: realistic_3d_render | scientific_illustration
                   | cinematic_photograph | macro_photography |
                   infographic_diagram.
lighting           Short phrase, e.g. "volumetric side lighting",
                   "soft diffused daylight", "cool blue bioluminescent
                   glow".
color_palette      Short phrase describing this scene's specific colors,
                   consistent with the video's overall visual_identity.
overlay            Object: {"type": one of none|arrow|icon|diagram|
                   comparison_graphic, "description": short description
                   of the overlay graphic if type is not "none", else
                   empty string}. Use overlays sparingly — only when a
                   simple graphic would make a mechanism instantly
                   clearer than the photo/render alone.
sfx_cue            Object: {"term": short SFX search term, "at_ms":
                   integer milliseconds into this scene when the sound
                   should hit}.
music_cue          One of: intro | build | swell | drop | fade_out |
                   none. Where this scene sits in the track's arc.
image_prompt       A single, extremely detailed, self-contained AI
                   image-generation prompt (see IMAGE PROMPTS below).
confidence         One of: high | qualitative_estimate. Whether the
                   claim in this scene's narration is a precise,
                   verifiable fact or a qualitative approximation.

====================================================================
IMAGE PROMPTS
====================================================================

Every image_prompt (and the thumbnail_prompt) must describe exactly ONE
clear visual and be production-ready. Always include:
- The single subject and exactly what it's doing/showing.
- The chosen image_style spelled out in words (e.g. "ultra realistic 3D
  render", "educational scientific illustration").
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

{
    "title": "",
    "description": "",
    "tags": [],
    "category": "",
    "thumbnail_prompt": "",
    "voice_style": {"tone": "", "pace": "", "pitch": ""},
    "music": {"search": "", "arc": ""},
    "visual_identity": {"style": "", "palette": "", "mood_arc": ""},
    "retention_self_check": {"weakest_scene": 1, "reason": ""},
    "scene_plan": [
        {
            "scene": 1,
            "purpose": "",
            "retention_purpose": "",
            "narration": "",
            "subtitle_text": "",
            "highlighted_words": [],
            "subtitle_style": "",
            "emphasis_word": "",
            "duration": 6,
            "pause_after_ms": 0,
            "emotional_tone": "",
            "visual_priority": "",
            "visual_complexity": "",
            "camera": "",
            "animation": "",
            "zoom_strength": "",
            "motion_intensity": "",
            "transition": "",
            "image_style": "",
            "lighting": "",
            "color_palette": "",
            "overlay": {"type": "none", "description": ""},
            "sfx_cue": {"term": "", "at_ms": 0},
            "music_cue": "",
            "image_prompt": "",
            "confidence": "high"
        }
    ]
}
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

    prompt = build_user_prompt(topic, config)

    print("=" * 80)
    print("GENERATING SCRIPT")
    print("=" * 80)
    print(topic)
    print("=" * 80)

    response = client.models.generate_content(

        model="gemini-2.5-flash-lite",

        contents=prompt,

        config=types.GenerateContentConfig(

            system_instruction=SYSTEM_PROMPT,

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

    return script


# --------------------------------------------------------------------------
# VALIDATION + NORMALIZATION
# --------------------------------------------------------------------------
#
# The model decides INTENT (enums). This layer decides IMPLEMENTATION
# (concrete numbers), so MoviePy never has to interpret a string.

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
    "highlighted_words",
    "subtitle_style",
    "emphasis_word",
    "duration",
    "pause_after_ms",
    "emotional_tone",
    "visual_priority",
    "visual_complexity",
    "camera",
    "animation",
    "zoom_strength",
    "motion_intensity",
    "transition",
    "image_style",
    "lighting",
    "color_palette",
    "overlay",
    "sfx_cue",
    "music_cue",
    "image_prompt",
    "confidence",
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


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40] or "video"


def _check_enum(value, allowed, label):
    if value not in allowed:
        raise RuntimeError(f"{label}: invalid value '{value}'. Expected one of {sorted(allowed)}.")


def validate_script(script: dict) -> dict:
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

    if not (1 <= int(script["retention_self_check"]["weakest_scene"]) <= 7):
        raise RuntimeError("retention_self_check.weakest_scene must be 1-7.")

    if not isinstance(script["scene_plan"], list):
        raise RuntimeError("scene_plan must be a list.")

    if len(script["scene_plan"]) != 7:
        raise RuntimeError(f"Expected 7 scenes but got {len(script['scene_plan'])}.")

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
        _check_enum(scene["visual_complexity"], VALID_VISUAL_COMPLEXITY, f"Scene {index} visual_complexity")
        _check_enum(scene["camera"], VALID_CAMERA, f"Scene {index} camera")
        _check_enum(scene["animation"], VALID_ANIMATION, f"Scene {index} animation")
        _check_enum(scene["zoom_strength"], VALID_ZOOM_STRENGTH, f"Scene {index} zoom_strength")
        _check_enum(scene["motion_intensity"], VALID_MOTION_INTENSITY, f"Scene {index} motion_intensity")
        _check_enum(scene["transition"], VALID_TRANSITION, f"Scene {index} transition")
        _check_enum(scene["image_style"], VALID_IMAGE_STYLE, f"Scene {index} image_style")
        _check_enum(scene["music_cue"], VALID_MUSIC_CUE, f"Scene {index} music_cue")
        _check_enum(scene["confidence"], VALID_CONFIDENCE, f"Scene {index} confidence")

        if scene["animation"] == "hold":
            hold_count += 1
            if index == 1:
                raise RuntimeError("Scene 1 (hook) must not use 'hold'.")

        if index == 7 and scene["transition"] != "none":
            raise RuntimeError("Scene 7 (ending) transition must be 'none'.")

        if not isinstance(scene["overlay"], dict) or "type" not in scene["overlay"]:
            raise RuntimeError(f"Scene {index} overlay must be an object with 'type'.")
        _check_enum(scene["overlay"]["type"], VALID_OVERLAY_TYPE, f"Scene {index} overlay.type")
        scene["overlay"].setdefault("description", "")

        if not isinstance(scene["sfx_cue"], dict) or "term" not in scene["sfx_cue"] or "at_ms" not in scene["sfx_cue"]:
            raise RuntimeError(f"Scene {index} sfx_cue must be an object with 'term' and 'at_ms'.")

        if not isinstance(scene["highlighted_words"], list):
            raise RuntimeError(f"Scene {index} highlighted_words must be a list.")

        if not isinstance(scene["duration"], (int, float)):
            raise RuntimeError(f"Scene {index} duration must be numeric.")
        scene["duration"] = max(3, min(8, int(scene["duration"])))
        total_duration += scene["duration"]

        scene["pause_after_ms"] = max(0, min(600, int(scene.get("pause_after_ms", 0))))

        scene["narration"] = str(scene["narration"]).strip()
        scene["subtitle_text"] = str(scene["subtitle_text"]).strip()
        scene["image_prompt"] = str(scene["image_prompt"]).strip()

        # Model decides intent (enum) -> code decides implementation (number).
        scene["zoom_factor"] = ZOOM_STRENGTH_TO_FACTOR[scene["zoom_strength"]]
        scene["motion_speed"] = MOTION_INTENSITY_TO_SPEED[scene["motion_intensity"]]

    if hold_count > 1:
        raise RuntimeError(
            f"'hold' animation used {hold_count} times; only one hold is allowed per script."
        )

    script["title"] = script["title"].strip()[:60]
    script["description"] = script["description"].strip()[:5000]
    script["tags"] = [str(t).strip().lower() for t in script["tags"]]
    script["category"] = str(script["category"]).strip().lower()
    script["thumbnail_prompt"] = script["thumbnail_prompt"].strip()

    # IDs and totals are computed here, never trusted from the model —
    # this is what keeps thousands of generated videos collision-free
    # and internally consistent.
    script["video_id"] = f"{_slugify(script['title'])}-{uuid.uuid4().hex[:8]}"
    script["generated_at"] = int(time.time())
    script["total_duration_seconds"] = total_duration

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

        script = generate_script(topic, config)
        script = validate_script(script)

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
