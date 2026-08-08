"""
generate_script.py

Educational YouTube Shorts Script Generator
Version 5.3

Changes from v5.2:
- FIX: removed minItems/maxItems from response_schema (scene_plan,
  visuals, caption_highlights). Gemini's structured-output schema
  support for these keywords has been inconsistent across API/SDK
  versions and was causing a deterministic 400 INVALID_ARGUMENT on
  every generation attempt. Exact counts are still fully enforced
  afterward in validate_script(), so behavior is unchanged.
- Improved error logging in generate_script(): now prints the full
  API error body/response when available, instead of just str(e),
  so future failures are diagnosable from the log alone.

Changes from v5.1:
- Gemini structured JSON schema output
- Automatic retry on malformed JSON
- Automatic retry on validation failures
- Stronger JSON parsing diagnostics
- Fixed 7-scene beat structure
- Educational human biology is allowed
- Medical advice / diagnosis / treatment remains prohibited
- Dangerous encouragement (e.g. prolonged breath-holding) prohibited
- Existing visual consistency / seed / style-lock system preserved
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
# SETTINGS
# --------------------------------------------------------------------------

MAX_GENERATION_ATTEMPTS = 3

# --------------------------------------------------------------------------
# 7-SCENE SHORT FORM BEAT TABLE
# --------------------------------------------------------------------------

_SHORT_FORM_BEAT_TABLE = """
1. HOOK             (0-3s)   Cold open on the most surprising fact or image.
                             Start mid-idea. No setup.

2. QUESTION         (3-8s)   Turn the hook into an open curiosity gap the
                             brain needs answered.

3. EXPLANATION      (8-15s)  Reveal the core mechanism in simple language.

4. EXAMPLE          (15-22s) Ground the mechanism in something real,
                             visual, and easy to understand.

5. MIND-BLOWING     (22-30s) Reveal a second-order implication that
   FACT                       recontextualizes what came before.

6. ESCALATION       (30-38s) Add one final surprising consequence,
                             comparison, or perspective shift.

7. ENDING           (38-45s) Deliver a tight, memorable button.
                             No summary. No "thanks for watching."
                             No dangerous challenge or instruction.
"""

_PURPOSE_CYCLE = [
    "hook",
    "question",
    "explanation",
    "example",
    "mindblowing_fact",
    "ending",
]


def _generate_beat_table(scene_count: int, target_seconds: int) -> str:
    """
    Build a beat table for non-default scene counts.

    The standard 7-scene Short uses the hand-tuned structure above.
    Other scene counts use proportional timing.
    """

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
            middle = _PURPOSE_CYCLE[2:-1]
            purpose = middle[(i - 2) % len(middle)]

        start = int(elapsed)

        elapsed += per_scene

        end = int(elapsed)

        lines.append(
            f"{i + 1}. {purpose.upper():<18} ({start}-{end}s)"
        )

    return "\n".join(lines)


# --------------------------------------------------------------------------
# SYSTEM PROMPT
# --------------------------------------------------------------------------

def build_system_prompt(
    scene_count: int = 7,
    target_seconds: int = 45,
) -> str:

    beat_table = _generate_beat_table(
        scene_count,
        target_seconds,
    )

    return f"""
You are a world-class educational YouTube Shorts writer, director,
and visual prompt engineer.

You work simultaneously as:

1. Writer
2. Director
3. Visual prompt engineer
4. Retention strategist

You create completely original educational YouTube Shorts.

The final video is approximately {target_seconds} seconds long and
contains exactly {scene_count} scenes.

====================================================================
MISSION
====================================================================

Maximize audience retention while teaching ONE genuinely interesting,
scientifically accurate idea.

Every sentence must earn the next few seconds of attention.

Every visual must reinforce what the narration is explaining.

Do not add decorative information that does not support the story.

====================================================================
VIDEO STRUCTURE
====================================================================

{beat_table}

There are ALWAYS exactly {scene_count} scenes.

The final scene MUST be the ending.

Every 2-4 seconds, something new should be revealed, shown, or
reframed.

Use a second visual inside a scene only when it genuinely improves
pacing.

====================================================================
WRITING RULES
====================================================================

- Grade 6 reading level.
- Short, plain, punchy sentences.
- No unnecessary jargon.
- If jargon is unavoidable, immediately explain it.
- Never repeat an idea unnecessarily.
- Never use filler.
- Never sound like an AI assistant.
- Never say "in this video".
- Never say "let's explore".
- Never say "today we're going to".
- Never start with "Did you know".
- Never start with a question.
- Start the hook with a strong statement.
- One story / phenomenon per video.
- No listicles.
- No countdowns.
- No "Top 5".
- No generic motivational endings.

====================================================================
ACCURACY
====================================================================

Every factual claim must be scientifically accurate and defensible.

Never invent statistics.

If you are uncertain about an exact number, do not provide a precise
number.

Use a qualitative comparison instead.

Never present speculation as fact.

Use:

"confidence": "qualitative_estimate"

when a statement is an approximation rather than a precise,
well-established fact.

====================================================================
CONTENT SAFETY
====================================================================

Educational explanations of normal human biology and physiology ARE
allowed.

For example:

- why humans get hiccups
- why onions make us cry
- why we sneeze
- how balance works
- how breathing works
- why our heart beats
- why we feel dizzy
- how the brain processes sound

However:

NEVER provide:

- medical diagnosis
- medical treatment
- medication instructions
- medical recommendations
- financial advice
- political persuasion
- religious persuasion
- dangerous challenges
- instructions encouraging dangerous behavior
- instructions for prolonged breath-holding
- instructions for self-experimentation involving physical danger
- violence or gore
- conspiracy theories presented as fact

IMPORTANT:

If the topic involves a potentially dangerous behavior, explain the
SCIENCE rather than encouraging the viewer to try it.

For example, do NOT end a breath-holding video with:

"You can always hold on longer."

Instead, use a safe educational conclusion such as:

"That urge to breathe is your brain protecting you."

====================================================================
TOPIC GUARDRAILS
====================================================================

GOOD:

- everyday science
- physics
- biology
- chemistry
- space
- engineering
- technology
- earth science
- psychology
- human physiology

NEVER:

- listicles
- celebrity news
- politics
- religious persuasion
- conspiracy-as-fact
- medical advice
- financial advice
- dangerous challenges
- gore
- instructions for dangerous experimentation

====================================================================
VISUAL CONSISTENCY
====================================================================

All scenes must look like they belong to the same production.

Choose ONE coherent visual identity.

Keep:

- rendering approach
- lighting philosophy
- color family
- cinematic language

consistent across the entire video.

Do not randomly switch between unrelated styles.

====================================================================
TOP-LEVEL FIELDS
====================================================================

title

Maximum 60 characters.

Create immediate curiosity.

description

One concise educational paragraph.

No hashtags.

tags

8-12 lowercase SEO tags.

No duplicates.

No hashtags.

category

One of:

space
physics
biology
chemistry
technology
engineering
earth_science
human_body
psychology

thumbnail_prompt

A highly detailed AI image prompt.

One striking hero image.

Vertical composition.

Leave clear negative space in the upper or lower third for a title
overlay added later.

voice_style

Object:

{{
    "tone": "...",
    "pace": "slow|medium|fast",
    "pitch": "low|medium|high"
}}

music

Object:

{{
    "search": "...",
    "arc": "..."
}}

visual_identity

Object:

{{
    "style": "...",
    "palette": "...",
    "mood_arc": "..."
}}

retention_self_check

Object:

{{
    "weakest_scene": integer,
    "reason": "..."
}}

Be honest.

====================================================================
SCENE PLAN
====================================================================

Generate EXACTLY {scene_count} scenes.

Each scene MUST contain:

scene

Integer {1}-{scene_count}.

purpose

One of:

hook
question
explanation
example
mindblowing_fact
ending

retention_purpose

One of:

open_loop
escalation
payoff
reframe
curiosity_gap
pattern_break
emotional_release
closure

narration

The exact spoken narration.

subtitle_text

Shorter, punchier on-screen caption.

caption_highlights

List of 1-3 objects:

{{
    "word": "...",
    "emphasis": "strong|light"
}}

The word MUST appear in subtitle_text.

subtitle_style

One of:

bold_center
kinetic_word_by_word
lower_third
minimal_clean

emphasis_word

One word from the narration that should receive vocal emphasis.

duration

Integer 3-8.

pause_after_ms

Integer 0-600.

emotional_tone

One of:

curious
tense
calm
awe
playful
urgent
satisfied

visual_priority

One of:

hero
supporting

At most 3 scenes should be hero.

transition

One of:

hard_cut
whip_pan
match_cut
dissolve
none

The final scene MUST use:

none

sfx_cue

Object:

{{
    "term": "...",
    "at_ms": integer
}}

music_cue

One of:

intro
build
swell
drop
fade_out
none

confidence

One of:

high
qualitative_estimate

visuals

List of 1-2 visual objects.

====================================================================
VISUALS
====================================================================

Each visual MUST contain:

segment

Integer 1 or 2.

duration

Integer seconds.

The sum of all visual durations MUST equal the scene duration.

camera

One of:

close_up
medium
wide
macro
top_down
side
aerial
orbit

animation

One of:

zoom_in
zoom_out
pan_left
pan_right
rotate
parallax
highlight
hold

Use "hold" at most once in the entire video.

Never use "hold" for the first visual of scene 1.

zoom_strength

subtle
medium
strong

motion_intensity

low
medium
high

visual_complexity

simple
moderate
complex

image_style

realistic_3d_render
scientific_illustration
cinematic_photograph
macro_photography
infographic_diagram

lighting

Short description.

color_palette

Must remain consistent with visual_identity.

overlay

Object:

{{
    "type": "none|arrow|icon|diagram|comparison_graphic",
    "description": "..."
}}

image_prompt

One extremely detailed image-generation prompt.

It must describe ONE clear visual.

Always include:

- exact subject
- exact action/state
- image style
- lighting
- documentary quality
- ultra detailed
- vertical composition
- No text.
- No labels.
- No logos.
- No watermark.

visual_impact

Integer 1-10.

Be honest.

====================================================================
IMPORTANT JSON RULES
====================================================================

You MUST return valid JSON.

Do not output:

- markdown
- code fences
- commentary
- explanations
- comments
- trailing commas
- single quotes
- JavaScript
- Python

Every property name MUST use double quotes.

Every string MUST use double quotes.

Do not place stray characters between properties.

Return ONLY the JSON object.
"""


# --------------------------------------------------------------------------
# USER PROMPT
# --------------------------------------------------------------------------

def build_user_prompt(topic: str, config: dict) -> str:

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

Produce the complete production storyboard.

Follow every rule in the system instructions.

The response MUST be one valid JSON object.

Return ONLY JSON.
"""


# --------------------------------------------------------------------------
# GEMINI STRUCTURED OUTPUT SCHEMA
# --------------------------------------------------------------------------

def build_response_schema(scene_count: int) -> dict:
    """
    JSON schema supplied directly to Gemini.

    FIX (v5.3): minItems/maxItems removed from all array fields
    (scene_plan, visuals, caption_highlights). Gemini's structured
    output schema support for these keywords has been inconsistent
    across API/SDK versions and was causing a deterministic
    400 INVALID_ARGUMENT on every generation attempt.

    Exact scene count, exact visuals-per-scene (1-2), and
    caption_highlights count (1-3) are still fully enforced
    afterward in validate_script(), so runtime behavior is
    unchanged -- only the schema sent to the API is smaller.
    """

    visual_schema = {
        "type": "object",
        "properties": {
            "segment": {
                "type": "integer"
            },
            "duration": {
                "type": "integer"
            },
            "camera": {
                "type": "string",
                "enum": [
                    "close_up",
                    "medium",
                    "wide",
                    "macro",
                    "top_down",
                    "side",
                    "aerial",
                    "orbit",
                ],
            },
            "animation": {
                "type": "string",
                "enum": [
                    "zoom_in",
                    "zoom_out",
                    "pan_left",
                    "pan_right",
                    "rotate",
                    "parallax",
                    "highlight",
                    "hold",
                ],
            },
            "zoom_strength": {
                "type": "string",
                "enum": [
                    "subtle",
                    "medium",
                    "strong",
                ],
            },
            "motion_intensity": {
                "type": "string",
                "enum": [
                    "low",
                    "medium",
                    "high",
                ],
            },
            "visual_complexity": {
                "type": "string",
                "enum": [
                    "simple",
                    "moderate",
                    "complex",
                ],
            },
            "image_style": {
                "type": "string",
                "enum": [
                    "realistic_3d_render",
                    "scientific_illustration",
                    "cinematic_photograph",
                    "macro_photography",
                    "infographic_diagram",
                ],
            },
            "lighting": {
                "type": "string"
            },
            "color_palette": {
                "type": "string"
            },
            "overlay": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "none",
                            "arrow",
                            "icon",
                            "diagram",
                            "comparison_graphic",
                        ],
                    },
                    "description": {
                        "type": "string"
                    },
                },
                "required": [
                    "type",
                    "description",
                ],
            },
            "image_prompt": {
                "type": "string"
            },
            "visual_impact": {
                "type": "integer"
            },
        },
        "required": [
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
        ],
    }

    scene_schema = {
        "type": "object",
        "properties": {
            "scene": {
                "type": "integer"
            },
            "purpose": {
                "type": "string",
                "enum": [
                    "hook",
                    "question",
                    "explanation",
                    "example",
                    "mindblowing_fact",
                    "ending",
                ],
            },
            "retention_purpose": {
                "type": "string",
                "enum": [
                    "open_loop",
                    "escalation",
                    "payoff",
                    "reframe",
                    "curiosity_gap",
                    "pattern_break",
                    "emotional_release",
                    "closure",
                ],
            },
            "narration": {
                "type": "string"
            },
            "subtitle_text": {
                "type": "string"
            },
            "caption_highlights": {
                "type": "array",
                # minItems: 1, maxItems: 3 removed -- enforced in validate_script()
                "items": {
                    "type": "object",
                    "properties": {
                        "word": {
                            "type": "string"
                        },
                        "emphasis": {
                            "type": "string",
                            "enum": [
                                "strong",
                                "light",
                            ],
                        },
                    },
                    "required": [
                        "word",
                        "emphasis",
                    ],
                },
            },
            "subtitle_style": {
                "type": "string",
                "enum": [
                    "bold_center",
                    "kinetic_word_by_word",
                    "lower_third",
                    "minimal_clean",
                ],
            },
            "emphasis_word": {
                "type": "string"
            },
            "duration": {
                "type": "integer"
            },
            "pause_after_ms": {
                "type": "integer"
            },
            "emotional_tone": {
                "type": "string",
                "enum": [
                    "curious",
                    "tense",
                    "calm",
                    "awe",
                    "playful",
                    "urgent",
                    "satisfied",
                ],
            },
            "visual_priority": {
                "type": "string",
                "enum": [
                    "hero",
                    "supporting",
                ],
            },
            "transition": {
                "type": "string",
                "enum": [
                    "hard_cut",
                    "whip_pan",
                    "match_cut",
                    "dissolve",
                    "none",
                ],
            },
            "sfx_cue": {
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string"
                    },
                    "at_ms": {
                        "type": "integer"
                    },
                },
                "required": [
                    "term",
                    "at_ms",
                ],
            },
            "music_cue": {
                "type": "string",
                "enum": [
                    "intro",
                    "build",
                    "swell",
                    "drop",
                    "fade_out",
                    "none",
                ],
            },
            "confidence": {
                "type": "string",
                "enum": [
                    "high",
                    "qualitative_estimate",
                ],
            },
            "visuals": {
                "type": "array",
                # minItems: 1, maxItems: 2 removed -- enforced in validate_script()
                "items": visual_schema,
            },
        },
        "required": [
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
        ],
    }

    return {
        "type": "object",
        "properties": {
            "title": {
                "type": "string"
            },
            "description": {
                "type": "string"
            },
            "tags": {
                "type": "array",
                "items": {
                    "type": "string"
                },
            },
            "category": {
                "type": "string",
                "enum": [
                    "space",
                    "physics",
                    "biology",
                    "chemistry",
                    "technology",
                    "engineering",
                    "earth_science",
                    "human_body",
                    "psychology",
                ],
            },
            "thumbnail_prompt": {
                "type": "string"
            },
            "voice_style": {
                "type": "object",
                "properties": {
                    "tone": {
                        "type": "string"
                    },
                    "pace": {
                        "type": "string",
                        "enum": [
                            "slow",
                            "medium",
                            "fast",
                        ],
                    },
                    "pitch": {
                        "type": "string",
                        "enum": [
                            "low",
                            "medium",
                            "high",
                        ],
                    },
                },
                "required": [
                    "tone",
                    "pace",
                    "pitch",
                ],
            },
            "music": {
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string"
                    },
                    "arc": {
                        "type": "string"
                    },
                },
                "required": [
                    "search",
                    "arc",
                ],
            },
            "visual_identity": {
                "type": "object",
                "properties": {
                    "style": {
                        "type": "string"
                    },
                    "palette": {
                        "type": "string"
                    },
                    "mood_arc": {
                        "type": "string"
                    },
                },
                "required": [
                    "style",
                    "palette",
                    "mood_arc",
                ],
            },
            "retention_self_check": {
                "type": "object",
                "properties": {
                    "weakest_scene": {
                        "type": "integer"
                    },
                    "reason": {
                        "type": "string"
                    },
                },
                "required": [
                    "weakest_scene",
                    "reason",
                ],
            },
            "scene_plan": {
                "type": "array",
                # minItems/maxItems: scene_count removed -- enforced in validate_script()
                "items": scene_schema,
            },
        },
        "required": [
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
        ],
    }


# --------------------------------------------------------------------------
# JSON PARSING
# --------------------------------------------------------------------------

def parse_gemini_json(text: str) -> dict:
    """
    Parse Gemini response.

    Structured output should make malformed JSON extremely rare.

    We still retain a conservative fallback parser for cases where
    Gemini/API behavior returns markdown fences or surrounding text.
    """

    if text is None or not text.strip():
        raise RuntimeError(
            "Gemini returned an empty response; cannot parse JSON."
        )

    text = text.strip()

    # First attempt: exact response.
    try:
        parsed = json.loads(text)

        if not isinstance(parsed, dict):
            raise RuntimeError(
                "Gemini returned valid JSON, but it was not a JSON object."
            )

        return parsed

    except json.JSONDecodeError:
        pass

    # Second attempt: remove markdown fences.
    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
    ).strip()

    try:
        parsed = json.loads(cleaned)

        if not isinstance(parsed, dict):
            raise RuntimeError(
                "Gemini returned valid JSON, but it was not a JSON object."
            )

        return parsed

    except json.JSONDecodeError:
        pass

    # Third attempt: extract outer object.
    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start != -1 and end > start:
        candidate = cleaned[start:end + 1]

        # Only remove trailing commas.
        candidate = re.sub(
            r",(\s*[}\]])",
            r"\1",
            candidate,
        )

        try:
            parsed = json.loads(candidate)

            if not isinstance(parsed, dict):
                raise RuntimeError(
                    "Gemini returned valid JSON, but it was not a JSON object."
                )

            return parsed

        except json.JSONDecodeError as e:
            error = e

    else:
        error = json.JSONDecodeError(
            "No JSON object found",
            cleaned,
            0,
        )

    print("=" * 80)
    print("JSON PARSE ERROR")
    print("=" * 80)
    print(f"Error message: {error.msg}")
    print(f"Line: {getattr(error, 'lineno', 'unknown')}")
    print(f"Column: {getattr(error, 'colno', 'unknown')}")
    print(f"Character position: {getattr(error, 'pos', 'unknown')}")
    print("=" * 80)
    print("RAW GEMINI RESPONSE")
    print("=" * 80)
    print(text)
    print("=" * 80)

    raise RuntimeError(
        "Failed to parse Gemini JSON response: "
        f"{error.msg} "
        f"(line {getattr(error, 'lineno', '?')}, "
        f"column {getattr(error, 'colno', '?')})"
    )


# --------------------------------------------------------------------------
# GENERATION
# --------------------------------------------------------------------------

def generate_script(topic: str, config: dict) -> dict:

    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"]
    )

    scene_count = int(
        config["script"].get("scene_count", 7)
    )

    target_seconds = int(
        config["script"]["target_narration_seconds"]
    )

    prompt = build_user_prompt(
        topic,
        config,
    )

    system_prompt = build_system_prompt(
        scene_count,
        target_seconds,
    )

    response_schema = build_response_schema(
        scene_count
    )

    print("=" * 80)
    print("GENERATING SCRIPT")
    print("=" * 80)
    print(topic)
    print("=" * 80)

    last_error = None

    for attempt in range(
        1,
        MAX_GENERATION_ATTEMPTS + 1,
    ):

        print(
            f"🧠 Gemini generation attempt "
            f"{attempt}/{MAX_GENERATION_ATTEMPTS}"
        )

        try:

            response = client.models.generate_content(

                model="gemini-flash-lite-latest",

                contents=prompt,

                config=types.GenerateContentConfig(

                    system_instruction=system_prompt,

                    response_mime_type="application/json",

                    response_schema=response_schema,

                    temperature=0.7,

                    top_p=0.90,

                ),
            )

            text = response.text

            script = parse_gemini_json(
                text
            )

            # Pipeline metadata.
            script["topic"] = topic

            script["video_structure"] = {
                "format": (
                    "short_form"
                    if scene_count == 7
                    else "custom"
                ),
                "scene_count": scene_count,
                "target_duration_seconds": target_seconds,
            }

            # Validate BEFORE accepting the response.
            script = validate_script(
                script,
                expected_scene_count=scene_count,
            )

            print("=" * 80)
            print("SCRIPT GENERATED AND VALIDATED")
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

        except Exception as e:

            last_error = e

            print("=" * 80)
            print(
                f"GENERATION ATTEMPT {attempt} FAILED"
            )
            print("=" * 80)
            print(
                f"{type(e).__name__}: {e}"
            )

            # FIX (v5.3): surface the full API error body when available.
            # The Gemini SDK's ClientError often truncates the useful
            # field-level violation message in str(e). This tries every
            # plausible attribute across SDK versions so future 400s are
            # diagnosable directly from the log.
            for attr in (
                "response",
                "body",
                "details",
                "message",
                "args",
            ):
                val = getattr(e, attr, None)

                if val:
                    print(f"--- error.{attr} ---")
                    print(val)

            print("=" * 80)

            if attempt < MAX_GENERATION_ATTEMPTS:

                print(
                    "Retrying Gemini generation..."
                )

                time.sleep(2)

    raise RuntimeError(
        "Gemini failed to produce a valid storyboard after "
        f"{MAX_GENERATION_ATTEMPTS} attempts. "
        f"Last error: {last_error}"
    )


# --------------------------------------------------------------------------
# VALIDATION + NORMALIZATION
# --------------------------------------------------------------------------

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
    "hook",
    "question",
    "explanation",
    "example",
    "mindblowing_fact",
    "ending",
}

VALID_RETENTION_PURPOSE = {
    "open_loop",
    "escalation",
    "payoff",
    "reframe",
    "curiosity_gap",
    "pattern_break",
    "emotional_release",
    "closure",
}

VALID_SUBTITLE_STYLE = {
    "bold_center",
    "kinetic_word_by_word",
    "lower_third",
    "minimal_clean",
}

VALID_EMPHASIS = {
    "strong",
    "light",
}

VALID_EMOTIONAL_TONE = {
    "curious",
    "tense",
    "calm",
    "awe",
    "playful",
    "urgent",
    "satisfied",
}

VALID_VISUAL_PRIORITY = {
    "hero",
    "supporting",
}

VALID_VISUAL_COMPLEXITY = {
    "simple",
    "moderate",
    "complex",
}

VALID_CAMERA = {
    "close_up",
    "medium",
    "wide",
    "macro",
    "top_down",
    "side",
    "aerial",
    "orbit",
}

VALID_ANIMATION = {
    "zoom_in",
    "zoom_out",
    "pan_left",
    "pan_right",
    "rotate",
    "parallax",
    "highlight",
    "hold",
}

VALID_ZOOM_STRENGTH = {
    "subtle",
    "medium",
    "strong",
}

VALID_MOTION_INTENSITY = {
    "low",
    "medium",
    "high",
}

VALID_TRANSITION = {
    "hard_cut",
    "whip_pan",
    "match_cut",
    "dissolve",
    "none",
}

VALID_IMAGE_STYLE = {
    "realistic_3d_render",
    "scientific_illustration",
    "cinematic_photograph",
    "macro_photography",
    "infographic_diagram",
}

VALID_OVERLAY_TYPE = {
    "none",
    "arrow",
    "icon",
    "diagram",
    "comparison_graphic",
}

VALID_MUSIC_CUE = {
    "intro",
    "build",
    "swell",
    "drop",
    "fade_out",
    "none",
}

VALID_CONFIDENCE = {
    "high",
    "qualitative_estimate",
}

ZOOM_STRENGTH_TO_FACTOR = {
    "subtle": 1.06,
    "medium": 1.15,
    "strong": 1.30,
}

MOTION_INTENSITY_TO_SPEED = {
    "low": 0.5,
    "medium": 1.0,
    "high": 1.6,
}

VISUAL_IMPACT_REGEN_THRESHOLD = 5


# --------------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------------

def _slugify(text: str) -> str:

    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        text.lower(),
    ).strip("-")

    return slug[:40] or "video"


def _check_enum(
    value,
    allowed,
    label,
):
    if value not in allowed:
        raise RuntimeError(
            f"{label}: invalid value '{value}'. "
            f"Expected one of {sorted(allowed)}."
        )


def _build_style_lock(
    visual_identity: dict,
) -> str:

    style = str(
        visual_identity.get(
            "style",
            "",
        )
    ).strip()

    palette = str(
        visual_identity.get(
            "palette",
            "",
        )
    ).strip()

    parts = [
        p
        for p in [
            style,
            palette,
        ]
        if p
    ]

    if not parts:
        return ""

    return (
        "Consistent visual identity across the video: "
        + ", ".join(parts)
        + "."
    )


# --------------------------------------------------------------------------
# VALIDATOR
# --------------------------------------------------------------------------

def validate_script(
    script: dict,
    expected_scene_count: int = 7,
) -> dict:

    if not isinstance(
        script,
        dict,
    ):
        raise RuntimeError(
            "Gemini did not return a JSON object."
        )

    for key in REQUIRED_KEYS:

        if key not in script:

            raise RuntimeError(
                f"Missing required key: {key}"
            )

    # --------------------------------------------------------------
    # TOP LEVEL
    # --------------------------------------------------------------

    if (
        not isinstance(
            script["tags"],
            list,
        )
        or not script["tags"]
    ):
        raise RuntimeError(
            "tags must be a non-empty list."
        )

    for obj_key, required_subkeys in [

        (
            "voice_style",
            [
                "tone",
                "pace",
                "pitch",
            ],
        ),

        (
            "music",
            [
                "search",
                "arc",
            ],
        ),

        (
            "visual_identity",
            [
                "style",
                "palette",
                "mood_arc",
            ],
        ),

        (
            "retention_self_check",
            [
                "weakest_scene",
                "reason",
            ],
        ),
    ]:

        if not isinstance(
            script[obj_key],
            dict,
        ):
            raise RuntimeError(
                f"{obj_key} must be an object."
            )

        for sub in required_subkeys:

            if sub not in script[obj_key]:

                raise RuntimeError(
                    f"{obj_key} missing '{sub}'."
                )

    # --------------------------------------------------------------
    # RETENTION CHECK
    # --------------------------------------------------------------

    try:

        weakest_scene = int(
            script[
                "retention_self_check"
            ][
                "weakest_scene"
            ]
        )

    except Exception:

        raise RuntimeError(
            "retention_self_check.weakest_scene must be an integer."
        )

    if not (
        1
        <= weakest_scene
        <= expected_scene_count
    ):

        raise RuntimeError(
            "retention_self_check.weakest_scene "
            f"must be 1-{expected_scene_count}."
        )

    # --------------------------------------------------------------
    # SCENE PLAN
    # --------------------------------------------------------------

    if not isinstance(
        script["scene_plan"],
        list,
    ):

        raise RuntimeError(
            "scene_plan must be a list."
        )

    if (
        len(script["scene_plan"])
        != expected_scene_count
    ):

        raise RuntimeError(
            f"Expected {expected_scene_count} scenes "
            f"but got {len(script['scene_plan'])}."
        )

    # --------------------------------------------------------------
    # IMAGE CONSISTENCY
    # --------------------------------------------------------------

    seed = random.randint(
        1,
        2_147_483_647,
    )

    style_lock = _build_style_lock(
        script["visual_identity"]
    )

    hold_count = 0
    total_duration = 0
    hero_count = 0

    # --------------------------------------------------------------
    # SCENES
    # --------------------------------------------------------------

    for index, scene in enumerate(
        script["scene_plan"],
        start=1,
    ):

        if not isinstance(
            scene,
            dict,
        ):

            raise RuntimeError(
                f"Scene {index} is invalid."
            )

        for key in REQUIRED_SCENE_KEYS:

            if key not in scene:

                raise RuntimeError(
                    f"Scene {index} missing '{key}'."
                )

        # Scene numbering
        try:

            scene_number = int(
                scene["scene"]
            )

        except Exception:

            raise RuntimeError(
                f"Scene {index} has invalid scene number."
            )

        if scene_number != index:

            raise RuntimeError(
                f"Scene {index} has out-of-order "
                f"'scene' number {scene['scene']}."
            )

        # Enums
        _check_enum(
            scene["purpose"],
            VALID_PURPOSE,
            f"Scene {index} purpose",
        )

        _check_enum(
            scene["retention_purpose"],
            VALID_RETENTION_PURPOSE,
            f"Scene {index} retention_purpose",
        )

        _check_enum(
            scene["subtitle_style"],
            VALID_SUBTITLE_STYLE,
            f"Scene {index} subtitle_style",
        )

        _check_enum(
            scene["emotional_tone"],
            VALID_EMOTIONAL_TONE,
            f"Scene {index} emotional_tone",
        )

        _check_enum(
            scene["visual_priority"],
            VALID_VISUAL_PRIORITY,
            f"Scene {index} visual_priority",
        )

        _check_enum(
            scene["transition"],
            VALID_TRANSITION,
            f"Scene {index} transition",
        )

        _check_enum(
            scene["music_cue"],
            VALID_MUSIC_CUE,
            f"Scene {index} music_cue",
        )

        _check_enum(
            scene["confidence"],
            VALID_CONFIDENCE,
            f"Scene {index} confidence",
        )

        # Final transition
        if (
            index == expected_scene_count
            and scene["transition"] != "none"
        ):

            raise RuntimeError(
                f"Final scene ({expected_scene_count}) "
                "transition must be 'none'."
            )

        # Hero count
        if scene["visual_priority"] == "hero":

            hero_count += 1

        # ----------------------------------------------------------
        # CAPTION HIGHLIGHTS
        # ----------------------------------------------------------

        if not isinstance(
            scene["caption_highlights"],
            list,
        ):

            raise RuntimeError(
                f"Scene {index} caption_highlights "
                "must be a list."
            )

        if not (
            1
            <= len(scene["caption_highlights"])
            <= 3
        ):

            raise RuntimeError(
                f"Scene {index} must have 1-3 caption highlights."
            )

        subtitle_words = {
            word.lower()
            for word in re.findall(
                r"\b[\w'-]+\b",
                str(
                    scene["subtitle_text"]
                ),
            )
        }

        for highlight in scene[
            "caption_highlights"
        ]:

            if (
                not isinstance(
                    highlight,
                    dict,
                )
                or "word" not in highlight
                or "emphasis" not in highlight
            ):

                raise RuntimeError(
                    f"Scene {index} caption_highlights "
                    "entries need 'word' and 'emphasis'."
                )

            word = str(
                highlight["word"]
            ).strip()

            _check_enum(
                highlight["emphasis"],
                VALID_EMPHASIS,
                f"Scene {index} "
                "caption_highlights.emphasis",
            )

            if word.lower() not in subtitle_words:

                raise RuntimeError(
                    f"Scene {index} caption highlight "
                    f"'{word}' does not appear in subtitle_text."
                )

        # ----------------------------------------------------------
        # SFX
        # ----------------------------------------------------------

        if (
            not isinstance(
                scene["sfx_cue"],
                dict,
            )
            or "term" not in scene["sfx_cue"]
            or "at_ms" not in scene["sfx_cue"]
        ):

            raise RuntimeError(
                f"Scene {index} sfx_cue must contain "
                "'term' and 'at_ms'."
            )

        try:

            sfx_at = int(
                scene["sfx_cue"]["at_ms"]
            )

        except Exception:

            raise RuntimeError(
                f"Scene {index} sfx_cue.at_ms must be numeric."
            )

        if sfx_at < 0:

            raise RuntimeError(
                f"Scene {index} sfx_cue.at_ms cannot be negative."
            )

        scene["sfx_cue"]["at_ms"] = sfx_at

        # ----------------------------------------------------------
        # DURATION
        # ----------------------------------------------------------

        if not isinstance(
            scene["duration"],
            (int, float),
        ):

            raise RuntimeError(
                f"Scene {index} duration must be numeric."
            )

        scene["duration"] = max(
            3,
            min(
                8,
                int(
                    scene["duration"]
                ),
            ),
        )

        total_duration += scene[
            "duration"
        ]

        # Pause
        try:

            pause = int(
                scene.get(
                    "pause_after_ms",
                    0,
                )
            )

        except Exception:

            pause = 0

        scene["pause_after_ms"] = max(
            0,
            min(
                600,
                pause,
            ),
        )

        # Text normalization
        scene["narration"] = str(
            scene["narration"]
        ).strip()

        scene["subtitle_text"] = str(
            scene["subtitle_text"]
        ).strip()

        scene["emphasis_word"] = str(
            scene["emphasis_word"]
        ).strip()

        if not scene["narration"]:

            raise RuntimeError(
                f"Scene {index} narration is empty."
            )

        if not scene["subtitle_text"]:

            raise RuntimeError(
                f"Scene {index} subtitle_text is empty."
            )

        # ----------------------------------------------------------
        # VISUALS
        # ----------------------------------------------------------

        if (
            not isinstance(
                scene["visuals"],
                list,
            )
            or not (
                1
                <= len(scene["visuals"])
                <= 2
            )
        ):

            raise RuntimeError(
                f"Scene {index} must have 1 or 2 visuals."
            )

        visuals_duration_sum = 0

        for v_index, visual in enumerate(
            scene["visuals"],
            start=1,
        ):

            if not isinstance(
                visual,
                dict,
            ):

                raise RuntimeError(
                    f"Scene {index} visual "
                    f"{v_index} is invalid."
                )

            for key in REQUIRED_VISUAL_KEYS:

                if key not in visual:

                    raise RuntimeError(
                        f"Scene {index} visual "
                        f"{v_index} missing '{key}'."
                    )

            try:

                segment = int(
                    visual["segment"]
                )

            except Exception:

                raise RuntimeError(
                    f"Scene {index} visual "
                    f"{v_index} segment is invalid."
                )

            if segment != v_index:

                raise RuntimeError(
                    f"Scene {index} visual "
                    f"{v_index} has out-of-order segment."
                )

            # Enums
            _check_enum(
                visual["camera"],
                VALID_CAMERA,
                f"Scene {index} visual "
                f"{v_index} camera",
            )

            _check_enum(
                visual["animation"],
                VALID_ANIMATION,
                f"Scene {index} visual "
                f"{v_index} animation",
            )

            _check_enum(
                visual["zoom_strength"],
                VALID_ZOOM_STRENGTH,
                f"Scene {index} visual "
                f"{v_index} zoom_strength",
            )

            _check_enum(
                visual["motion_intensity"],
                VALID_MOTION_INTENSITY,
                f"Scene {index} visual "
                f"{v_index} motion_intensity",
            )

            _check_enum(
                visual["visual_complexity"],
                VALID_VISUAL_COMPLEXITY,
                f"Scene {index} visual "
                f"{v_index} visual_complexity",
            )

            _check_enum(
                visual["image_style"],
                VALID_IMAGE_STYLE,
                f"Scene {index} visual "
                f"{v_index} image_style",
            )

            # Hold
            if visual["animation"] == "hold":

                hold_count += 1

                if (
                    index == 1
                    and v_index == 1
                ):

                    raise RuntimeError(
                        "Scene 1's first visual "
                        "must not use 'hold'."
                    )

            # Overlay
            if (
                not isinstance(
                    visual["overlay"],
                    dict,
                )
                or "type" not in visual["overlay"]
            ):

                raise RuntimeError(
                    f"Scene {index} visual "
                    f"{v_index} overlay must be an object."
                )

            _check_enum(
                visual["overlay"]["type"],
                VALID_OVERLAY_TYPE,
                f"Scene {index} visual "
                f"{v_index} overlay.type",
            )

            visual["overlay"].setdefault(
                "description",
                "",
            )

            # Visual duration
            if not isinstance(
                visual["duration"],
                (int, float),
            ):

                raise RuntimeError(
                    f"Scene {index} visual "
                    f"{v_index} duration must be numeric."
                )

            visual["duration"] = max(
                2,
                int(
                    visual["duration"]
                ),
            )

            visuals_duration_sum += visual[
                "duration"
            ]

            # Impact
            impact = visual.get(
                "visual_impact"
            )

            if (
                not isinstance(
                    impact,
                    (int, float),
                )
                or not (
                    1
                    <= impact
                    <= 10
                )
            ):

                raise RuntimeError(
                    f"Scene {index} visual "
                    f"{v_index} visual_impact "
                    "must be 1-10."
                )

            visual["visual_impact"] = int(
                impact
            )

            # Image prompt
            visual["image_prompt"] = str(
                visual["image_prompt"]
            ).strip()

            if not visual["image_prompt"]:

                raise RuntimeError(
                    f"Scene {index} visual "
                    f"{v_index} image_prompt is empty."
                )

            # Style lock
            if (
                style_lock
                and style_lock
                not in visual["image_prompt"]
            ):

                visual["image_prompt"] = (
                    f"{visual['image_prompt']} "
                    f"{style_lock}"
                )

            # Regeneration flag
            visual["needs_regeneration"] = (
                scene["visual_priority"] == "hero"
                and visual["visual_impact"]
                < VISUAL_IMPACT_REGEN_THRESHOLD
            )

            # Concrete editor values
            visual["zoom_factor"] = (
                ZOOM_STRENGTH_TO_FACTOR[
                    visual["zoom_strength"]
                ]
            )

            visual["motion_speed"] = (
                MOTION_INTENSITY_TO_SPEED[
                    visual["motion_intensity"]
                ]
            )

        # Visual durations must exactly equal scene duration.
        if (
            visuals_duration_sum
            != scene["duration"]
        ):

            raise RuntimeError(
                f"Scene {index}: visuals durations "
                f"sum to {visuals_duration_sum}s "
                f"but scene duration is "
                f"{scene['duration']}s."
            )

    # --------------------------------------------------------------
    # GLOBAL VISUAL RULES
    # --------------------------------------------------------------

    if hold_count > 1:

        raise RuntimeError(
            f"'hold' animation used "
            f"{hold_count} times; only one "
            "hold is allowed per video."
        )

    if hero_count > 3:

        raise RuntimeError(
            f"{hero_count} hero scenes detected. "
            "Maximum is 3."
        )

    # --------------------------------------------------------------
    # FINAL SCENE
    # --------------------------------------------------------------

    final_scene = script[
        "scene_plan"
    ][-1]

    if final_scene["purpose"] != "ending":

        raise RuntimeError(
            "Final scene must have purpose='ending'."
        )

    # --------------------------------------------------------------
    # TOP LEVEL NORMALIZATION
    # --------------------------------------------------------------

    script["title"] = str(
        script["title"]
    ).strip()[:60]

    script["description"] = str(
        script["description"]
    ).strip()[:5000]

    script["tags"] = [
        str(tag)
        .strip()
        .lower()
        for tag in script["tags"]
    ]

    script["category"] = str(
        script["category"]
    ).strip().lower()

    script["thumbnail_prompt"] = str(
        script["thumbnail_prompt"]
    ).strip()

    if style_lock:

        if style_lock not in script[
            "thumbnail_prompt"
        ]:

            script["thumbnail_prompt"] = (
                f"{script['thumbnail_prompt']} "
                f"{style_lock}"
            )

    # --------------------------------------------------------------
    # IMAGE GENERATION CONFIG
    # --------------------------------------------------------------

    script["image_generation"] = {

        "seed": seed,

        "style_lock": style_lock,
    }

    # --------------------------------------------------------------
    # VIDEO ID
    # --------------------------------------------------------------

    script["video_id"] = (
        f"{_slugify(script['title'])}-"
        f"{uuid.uuid4().hex[:8]}"
    )

    script["generated_at"] = int(
        time.time()
    )

    script.setdefault(
        "video_structure",
        {},
    )

    script["video_structure"][
        "actual_duration_seconds"
    ] = total_duration

    return script


# --------------------------------------------------------------------------
# CLI / MANUAL TEST HARNESS
# --------------------------------------------------------------------------

if __name__ == "__main__":

    import yaml

    with open(
        "config.yaml",
        "r",
        encoding="utf-8",
    ) as f:

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

        script = generate_script(
            topic,
            config,
        )

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
