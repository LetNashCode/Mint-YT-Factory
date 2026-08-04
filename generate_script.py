"""
generate_script.py
Story-first generator for YouTube Shorts.
"""

import json
import os
from google import genai
from google.genai import types

SYSTEM_PROMPT = """
You are one of the world's best YouTube Shorts storytellers.

MISSION

-Your ONLY objective is to maximize audience retention.
-The viewer should feel compelled to watch until the final second.
-Every 2–4 seconds something new, surprising, emotional, dangerous, mysterious or unexpected must happen.
-Never allow the story to become predictable.
-Think like a Hollywood screenwriter, not an AI assistant.
-If the script is not binge-worthy, rewrite it before returning.
The user will provide ONE unique video idea.

Your job is to transform that idea into a highly engaging YouTube Shorts story.

First determine which of the following series best fits the provided idea.

SERIES

1. Survival Simulator
2. One Wrong Choice
3. You Wake Up As
4. Last Person Alive
5. Every Minute Gets Worse
6. Impossible Challenge
7. Reality Glitch
8. Choose Your Fate

Do NOT change the idea.

If the provided idea is "Escape Jurassic Park", the story must remain about escaping Jurassic Park.

Never replace it with another scenario.

Never substitute another character, place, or challenge.

Expand ONLY the provided idea into a cinematic story following the BruhZen Formula.

Every story must feel unique, unpredictable and emotionally engaging.

Return ONLY valid JSON.

SCHEMA

{
  "title":"",
  "description":"",
  "tags":[],
  "hook":"",
  "story":"",
  "twist":"",
  "ending":"",
  "music_search":"",
  "sfx_search":[],
  "scene_plan":[
    {
      "text":"",
      "emotion":"",
      "duration":5,
      "image_prompt":""
    }
  ]
}


Return ONLY valid JSON.
"""


def generate_script(topic:str, config:dict)->dict:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    prompt = f"""
Video Idea:
{topic}

The story MUST be based ONLY on this idea.

Do not replace it with another idea.

Audience:
{config["channel"]["audience"]}

Tone:
{config["channel"]["tone"]}

Target Length:
{config["script"]["target_narration_seconds"]} seconds.

Return ONLY valid JSON.

The generated story must remain faithful to the supplied video idea.
"""

    response = client.models.generate_content(
        model="gemini-flash-lite-latest",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )

    text=response.text.strip()
    text=text.replace("```json","").replace("```","").strip()

    decoder=json.JSONDecoder()
    obj,_=decoder.raw_decode(text)
    print("=" * 80)
    print("GENERATED SCRIPT")
    print("=" * 80)
    print(json.dumps(obj, indent=2, ensure_ascii=False))
    print("=" * 80, flush=True)
    return obj


if __name__=="__main__":
    import yaml
    with open("config.yaml") as f:
        cfg=yaml.safe_load(f)

    print(json.dumps(
        generate_script("The signal from space nobody can explain",cfg),
        indent=2,
        ensure_ascii=False
    ))
