import json
import os

from google import genai
from google.genai import types


def generate_script(topic: str, config: dict) -> dict:

    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"]
    )

    prompt = f"""
Video Topic

{topic}

Audience:
{config["channel"]["audience"]}

Tone:
{config["channel"]["tone"]}

Target Duration:
{config["script"]["target_narration_seconds"]} seconds

Return ONLY valid JSON.
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=1.1,
        ),
    )

    text = (
        response.text
        .replace("```json", "")
        .replace("```", "")
        .strip()
    )

    decoder = json.JSONDecoder()

    script, _ = decoder.raw_decode(text)

    print("=" * 80)
    print("GENERATED SCRIPT")
    print("=" * 80)
    print(
        json.dumps(
            script,
            indent=2,
            ensure_ascii=False,
        )
    )
    print("=" * 80)

    required = [
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

    for key in required:

        if key not in script:

            raise RuntimeError(
                f"Missing key: {key}"
            )

    return script


if __name__ == "__main__":

    import yaml

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    print(
        json.dumps(
            generate_script(
                "Why can't you tickle yourself",
                config,
            ),
            indent=2,
            ensure_ascii=False,
        )
    )
