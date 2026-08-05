"""
topics.py

Generates one unique educational YouTube Shorts topic.
"""

import json
import os

from google import genai
from google.genai import types


USED_TOPICS_PATH = "used_topics.json"


SYSTEM_PROMPT = """
You are the content strategist behind one of the world's largest educational YouTube Shorts channels.

Generate ONE highly viral educational topic.

The topic MUST belong to ONE of these categories:

1. Human Body
2. Psychology
3. Science
4. Space
5. Earth
6. Technology
7. History
8. Animals

Rules:

• Return ONLY ONE topic.
• Maximum 8 words.
• Must be phrased as a curiosity question.
• No clickbait.
• No listicles.
• No "Top 10".
• No "Did you know".
• No emojis.
• No numbering.
• No quotation marks.
• No punctuation at the end.
• Must make people instantly curious.
• Never repeat previous topics.
"""


def _load_used():

    if os.path.exists(USED_TOPICS_PATH):
        with open(USED_TOPICS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    return []


def _save_used(used):

    with open(USED_TOPICS_PATH, "w", encoding="utf-8") as f:
        json.dump(
            used,
            f,
            indent=2,
            ensure_ascii=False,
        )


def get_next_topic():

    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"]
    )

    used = _load_used()

    previous = "\n".join(used[-300:])

    prompt = f"""
Previously used topics:

{previous}

Generate ONE completely different educational topic.

Return ONLY the topic.
"""

    for _ in range(5):

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=1.1,
            ),
        )

        topic = (
            response.text.strip()
            .replace('"', "")
            .replace(".", "")
            .strip()
        )

        if topic not in used:

            used.append(topic)

            _save_used(used)

            print("=" * 80)
            print("GENERATED TOPIC")
            print("=" * 80)
            print(topic)
            print("=" * 80)

            return topic

    raise RuntimeError("Could not generate a unique topic.")
