"""
topics.py
Mint-YT-Factory

Research-first educational topic generator.
"""

import json
import os

from google import genai
from google.genai import types


USED_TOPICS_PATH = "used_topics.json"


SYSTEM_PROMPT = """
You are the content strategist for a high-quality educational YouTube
Shorts channel.

Generate ONE educational topic that is highly likely to have strong,
credible, publicly verifiable research available.

Allowed categories:

1. Human Body
2. Psychology
3. Science
4. Space
5. Earth
6. Technology
7. History
8. Animals

============================================================
HARD RULES
============================================================

- Return ONLY ONE topic.
- Maximum 8 words.
- Phrase it as a curiosity question.
- No clickbait.
- No listicles.
- No "Top 10".
- No "Did you know".
- No emojis.
- No numbering.
- No quotation marks.
- No punctuation at the end.
- Do not make supernatural claims.
- Do not make conspiracy claims.
- Do not make medical diagnosis or treatment claims.
- Avoid controversial claims requiring political or ideological debate.
- Avoid topics where reliable evidence is unlikely to exist.
- Prefer topics that can be supported by multiple scholarly,
  government, university, or research-institution sources.
- The final topic must describe ONE specific phenomenon or question.
- Never repeat previous topics.
"""


def _load_used():

    if os.path.exists(
        USED_TOPICS_PATH
    ):

        with open(
            USED_TOPICS_PATH,
            "r",
            encoding="utf-8",
        ) as f:

            return json.load(f)

    return []


def _save_used(used):

    with open(
        USED_TOPICS_PATH,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            used,
            f,
            indent=2,
            ensure_ascii=False,
        )


def _clean_topic(topic):

    topic = str(
        topic or ""
    ).strip()

    topic = topic.replace(
        '"',
        "",
    ).replace(
        "'",
        "",
    )

    topic = topic.rstrip(
        ".!? "
    )

    topic = " ".join(
        topic.split()
    )

    return topic


def _valid_topic(topic):

    if not topic:
        return False

    words = topic.split()

    if len(words) > 8:
        return False

    forbidden = [
        "top 10",
        "top 5",
        "did you know",
        "conspiracy",
        "aliens",
        "miracle",
    ]

    lowered = topic.lower()

    for phrase in forbidden:

        if phrase in lowered:
            return False

    return True


def get_next_topic():

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "GEMINI_API_KEY environment "
            "variable is missing."
        )

    client = genai.Client(
        api_key=api_key
    )

    used = _load_used()

    previous = "\n".join(
        used[-300:]
    )

    prompt = f"""
Previously used topics:

{previous}

Generate ONE completely different educational topic.

The topic must be specific enough for a research system to find
at least two credible independent sources.

Prefer questions about established scientific, historical,
technological, astronomical, biological, psychological,
geological, or engineering phenomena.

Do not invent obscure claims.

Return ONLY the topic.
"""

    for attempt in range(5):

        response = client.models.generate_content(

            model="gemini-flash-lite-latest",

            contents=prompt,

            config=types.GenerateContentConfig(

                system_instruction=
                    SYSTEM_PROMPT,

                temperature=0.9,
            ),
        )

        topic = _clean_topic(
            response.text
        )

        if not _valid_topic(
            topic
        ):

            continue

        if topic in used:

            continue

        used.append(
            topic
        )

        _save_used(
            used
        )

        print("=" * 80)
        print("GENERATED RESEARCH-FRIENDLY TOPIC")
        print("=" * 80)
        print(topic)
        print("=" * 80)

        return topic

    raise RuntimeError(
        "Could not generate a unique "
        "research-friendly topic."
    )