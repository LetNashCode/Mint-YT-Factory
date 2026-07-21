"""
generate_script.py
Story-first generator for YouTube Shorts.
"""

import json
import os
from google import genai
from google.genai import types

SYSTEM_PROMPT = """
You are an elite viral YouTube Shorts writer.

Return ONLY valid JSON.

Schema:
{
  "title":"",
  "description":"",
  "tags":[],
  "hook":"",
  "story":"",
  "twist":"",
  "ending":"",
  "scene_plan":[
    {
      "text":"",
      "duration":4,
      "shots":[
        {
          "type":"wide",
          "searches":[
            "",
            "",
            "",
            "",
            ""
          ]
        },
        {
          "type":"medium",
          "searches":[
            "",
            "",
            "",
            "",
            ""
          ]
        },
        {
          "type":"closeup",
          "searches":[
            "",
            "",
            "",
            "",
            ""
          ]
        },
        {
          "type":"detail",
          "searches":[
            "",
            "",
            "",
            "",
            ""
          ]
        }
      ]
    }
  ]
}

Rules:
- English only.
- 40-45 seconds.
- Hook (0-3s)
- Story (3-20s)
- Twist (20-35s)
- Ending with open loop (35-45s)
- No countdowns.
- No lists.
- No greetings.
- Every sentence must increase curiosity.
- Create 6-8 scenes.
- Each scene needs cinematic visual keywords.

Generate an SEO optimized YouTube Shorts title under 70 characters.

Generate an SEO optimized YouTube description under 500 characters.

Generate exactly 15 tags.

Rules for tags:
- lowercase only
- no hashtags
- no duplicates
- specific to the topic
- mix broad and niche keywords
- maximize YouTube search discoverability

For every scene generate exactly 4 shots.

Each shot must contain exactly 5 alternative search queries.

The search queries should describe the SAME shot from different perspectives.

Example:

Wide Shot:
- titanic ship sailing at night cinematic
- luxury ocean liner atlantic
- historic steamship aerial
- passenger liner sunset
- dramatic ocean ship

Close Up:
- captain steering ship
- ship wheel close up
- vintage navigation room
- captain looking through binoculars
- sailor operating controls

Rules:

- highly specific
- cinematic
- searchable on Pixabay and Pexels
- avoid generic words
- no repeated searches
- every search should increase the chance of finding relevant footage
- generate realistic stock footage searches
"""

def generate_script(topic:str, config:dict)->dict:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    prompt=f"""
Topic:
{topic}

Audience:
{config["channel"]["audience"]}

Tone:
{config["channel"]["tone"]}

Target Length:
{config["script"]["target_narration_seconds"]} seconds.

Return JSON only.
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
