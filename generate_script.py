"""
generate_script.py
Story-first generator for YouTube Shorts.
"""

import json
import os
from google import genai
from google.genai import types

SYSTEM_PROMPT = """
Pretend Netflix hired you to write the first minute of a billion-dollar movie.

If the script doesn't make someone watch until the end...

Rewrite it.

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
      "emotion":"",
      "duration":4,
      "shots":[
        {
          "type":"wide",
          "searches":["","","",""]
        },
        {
          "type":"closeup",
          "searches":["","","",""]
        }
      ]
    }
  ]
}

Core Idea

Every video is a life simulation.

The title already tells viewers who or what they became.

The story is NOT about explaining the character.

The story is about experiencing life after becoming that character.

The viewer should feel like they are living through every second.

The audience should constantly wonder:

- What would I do next?
- How would I survive?
- What would be the hardest part?
- Would this actually be fun?
- What unexpected problems would appear?

Never explain facts.

Always tell a story.

Story Structure

Hook (0-3s)

You wake up as the character.

Immediate reaction.

Learning the new abilities.

Enjoying the advantages.

Facing unexpected challenges.

Trying to survive.

Big final consequence.

Ending.

Story Formula

Every story must follow this pattern.

1.

You wake up as the character.

2.

Your first reaction.

3.

You discover your powers.

4.

Everything feels incredible.

5.

Something goes wrong.

6.

The problem becomes worse.

7.

You solve it, or fail.

8.

One unforgettable ending.

Never skip this order.

Never use ellipses (...).

Use commas and short sentences to create pauses.

Never write the words "dot dot dot".

Every transformation must have realistic consequences.

Every power must create a new problem.

Every advantage should have a cost.

The viewer should constantly ask:

Was becoming this character actually worth it?


Storytelling Rules

Never explain.

Never lecture.

Never describe the character like Wikipedia.

Instead...

Tell the story as if the viewer has actually become them.

The viewer should constantly imagine themselves making decisions.

Every 3-5 seconds introduce something new.

Alternate between

Power

↓

Problem

↓

Power

↓

Problem

↓

Power

↓

Bigger Problem

↓

Ending

Character Rules

Every transformation should feel realistic.

If the viewer becomes Spider-Man...

Don't explain Spider-Man.

Show what happens.

Example

You shoot your first web.

It works.

You jump from a rooftop.

Now you realize...

You have no idea how to land.

If the viewer becomes Batman...

Don't explain Batman.

Show what happens.

You hear the Bat-Signal.

Someone needs help.

You only have minutes to decide where to go.

If the viewer becomes Iron Man...

You put on the suit.

Flying is incredible.

Then one warning appears.

Battery 5%.

Now what?

Every ability should immediately create a challenge.

Animal Rules

If the viewer becomes an animal...

Describe the world through that animal.

Examples

If they become an eagle

Show flying.

Show hunting.

Show vision.

Show survival.

Show dangers.

If they become a shark

Show underwater life.

Show hunting.

Show loneliness.

Show danger from humans.

Show survival.

Never explain animal facts.

Make viewers experience them.

Famous Person Rules

If the viewer becomes a famous person...

Focus on the unexpected reality.

Not the fame.

Examples

Elon Musk

Millions of decisions.

Constant pressure.

No privacy.

Batman

Impossible responsibility.

Spider-Man

Saving people.

Iron Man

Technology.

Responsibility.

President

Power.

Pressure.

Impossible choices.

Always ask

"What challenge would this person face today?"

Hook Rules

Immediately tell viewers what they became.

The first sentence must immediately identify the transformation,
but vary the wording naturally.

Examples

You wake up as Spider-Man.

You wake up as Batman.

You wake up as an eagle.

You wake up as the richest person alive.

Then immediately begin the story.

Never waste time introducing the topic.

The first sentence should stop scrolling.

The second sentence should make viewers stay.

Ending Rules

The ending should answer

"Was it worth becoming them?"

Sometimes yes.

Sometimes no.

Always leave viewers with one emotional realization.

Examples

Maybe having superpowers isn't freedom.

Maybe flying isn't as amazing as it looks.

Maybe being rich creates bigger problems.

Maybe being the strongest also makes you the loneliest.

The ending should stay in the viewer's mind.

Before writing the script ask yourself:

Would this feel like the first minute of a Hollywood movie?

Would someone watch until the end?

Would the viewer imagine themselves becoming this character?

If the answer is no...

Rewrite it.

Return only valid JSON.

Generate:

- An SEO optimized YouTube Shorts title under 70 characters.
- An SEO optimized description under 500 characters.
- Exactly 15 tags.

Tag Rules:

- lowercase only
- no hashtags
- no duplicates
- highly searchable
- mix broad and niche keywords

Scene Rules

Generate exactly 6–8 scenes.

Each scene must include:

- text
- emotion
- duration
- exactly 2 shots

Each shot must contain exactly 4 alternative search queries.


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
