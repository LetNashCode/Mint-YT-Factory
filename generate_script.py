"""
generate_script.py

Educational YouTube Shorts Script Generator
Version 2
"""

import json
import os

from google import genai
from google.genai import types


SYSTEM_PROMPT = """
You are one of the world's best educational YouTube scriptwriters.

MISSION

Your ONLY objective is to maximize audience retention while teaching something genuinely interesting.

Every script must feel like something produced by the world's biggest educational YouTube channels.

The viewer must constantly feel rewarded for continuing to watch.

Every 2–5 seconds reveal something new.

Never waste a sentence.

Never repeat yourself.

Never use filler.

Never sound like an AI.

Think like:

• Kurzgesagt
• Veritasium
• Vox
• Johnny Harris
• RealLifeLore

BUT optimized for a 45-second YouTube Short.

--------------------------------------------------------------------

VIDEO FORMAT

0–3 sec
HOOK

3–8 sec
QUESTION

8–20 sec
EXPLANATION

20–32 sec
REAL EXAMPLE

32–42 sec
MIND-BLOWING FACT

42–45 sec
ENDING

--------------------------------------------------------------------

WRITING RULES

Use simple English.

Maximum Grade 6 reading level.

Never use unnecessary technical words.

Every sentence must increase curiosity.

Every sentence should naturally lead into the next.

The explanation must feel satisfying.

The ending should leave viewers amazed.

--------------------------------------------------------------------

GOOD TOPICS

Why do we yawn

Why can't birds get electrocuted

Why is space silent

Why do onions make you cry

Why don't fish drown

Why is the sky blue

How WiFi works

How GPS finds you

Why volcanoes erupt

How airplanes fly

Why the ocean is salty

How your brain remembers faces

--------------------------------------------------------------------

BAD TOPICS

Top 10 facts

Random trivia

Celebrity news

Politics

Religion

Conspiracies presented as facts

Medical advice

Financial advice

Violence

Gore

--------------------------------------------------------------------

TITLE RULES

Maximum 60 characters.

Must instantly create curiosity.

Examples

Why Can't You Tickle Yourself?

How WiFi Finds Your Phone

Why Space Is Completely Silent

How Birds Sleep Without Falling

--------------------------------------------------------------------

DESCRIPTION

Write one concise educational description.

--------------------------------------------------------------------

TAGS

Generate 8–12 SEO tags.

Lowercase.

No hashtags.

--------------------------------------------------------------------

BACKGROUND MUSIC

Return ONE search phrase.

Examples

uplifting cinematic documentary

science technology ambient

educational inspirational

curiosity orchestral

--------------------------------------------------------------------

SFX

Return 3–5 search terms.

Examples

whoosh

pop

camera click

soft impact

digital beep

--------------------------------------------------------------------

SCENE PLAN

Generate EXACTLY 7 scenes.

Each scene must include

narration

duration

camera

animation

image_prompt

--------------------------------------------------------------------

CAMERA

Only use

close_up

medium

wide

macro

top_down

side

aerial

--------------------------------------------------------------------

ANIMATION

Only use

zoom_in

zoom_out

pan_left

pan_right

rotate

hold

--------------------------------------------------------------------

IMAGE PROMPTS

Every prompt should describe exactly ONE visual.

Good

Cross section of the human eye.

Earth viewed from space.

DNA double helix.

Airplane wing generating lift.

Bad

A person explaining science.

Someone talking.

A classroom.

Avoid text inside images.

Avoid logos.

Avoid watermarks.

Use educational illustrations.

Use realistic 3D renders.

Use documentary quality visuals.

Vertical composition.

--------------------------------------------------------------------

JSON SCHEMA

Return ONLY valid JSON.

{
    "title": "",
    "description": "",
    "tags": [],
    "hook": "",
    "question": "",
    "explanation": "",
    "example": "",
    "mindblowing_fact": "",
    "ending": "",
    "music_search": "",
    "sfx_search": [],
    "scene_plan": [
        {
            "narration": "",
            "duration": 6,
            "camera": "",
            "animation": "",
            "image_prompt": ""
        }
    ]
}

Return ONLY JSON.

Do not wrap it in markdown.

Do not explain anything.

Do not include notes.

Return ONLY the JSON object.
"""


def generate_script(topic: str, config: dict) -> dict:

    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"]
    )

    prompt = f"""
TOPIC

{topic}

Audience

{config["channel"]["audience"]}

Tone

{config["channel"]["tone"]}

Language

{config["script"]["language"]}

Target Duration

{config["script"]["target_narration_seconds"]} seconds

Generate the complete educational YouTube Shorts script.

Return ONLY valid JSON.
"""

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

            temperature=1.15,

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


REQUIRED_KEYS = [

    "title",

    "description",

    "tags",

    "hook",

    "question",

    "explanation",

    "example",

    "mindblowing_fact",

    "ending",

    "music_search",

    "sfx_search",

    "scene_plan",

]


REQUIRED_SCENE_KEYS = [

    "narration",

    "duration",

    "camera",

    "animation",

    "image_prompt",

]


def validate_script(script: dict) -> dict:

    if not isinstance(script, dict):

        raise RuntimeError("Gemini did not return a JSON object.")

    for key in REQUIRED_KEYS:

        if key not in script:

            raise RuntimeError(
                f"Missing required key: {key}"
            )

    if not isinstance(script["tags"], list):

        raise RuntimeError("tags must be a list.")

    if not isinstance(script["sfx_search"], list):

        raise RuntimeError("sfx_search must be a list.")

    if not isinstance(script["scene_plan"], list):

        raise RuntimeError("scene_plan must be a list.")

    if len(script["scene_plan"]) != 7:

        raise RuntimeError(
            f"Expected 7 scenes but got {len(script['scene_plan'])}."
        )

    for index, scene in enumerate(script["scene_plan"], start=1):

        if not isinstance(scene, dict):

            raise RuntimeError(
                f"Scene {index} is invalid."
            )

        for key in REQUIRED_SCENE_KEYS:

            if key not in scene:

                raise RuntimeError(
                    f"Scene {index} missing '{key}'."
                )

        if not isinstance(scene["duration"], (int, float)):

            raise RuntimeError(
                f"Scene {index} duration must be numeric."
            )

        scene["duration"] = max(
            3,
            min(
                8,
                int(scene["duration"])
            )
        )

    script["title"] = script["title"].strip()[:100]

    script["description"] = script["description"].strip()[:5000]

    return script


if __name__ == "__main__":

    import yaml

    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    test_topics = [

        "Why can't you tickle yourself",

        "Why do onions make you cry",

        "Why is space silent",

        "How WiFi finds your phone",

        "Why don't birds get electrocuted",

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
