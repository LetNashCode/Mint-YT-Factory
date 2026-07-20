"""
Generates a structured Top-5 script using the Google Gemini API
(free tier — no billing required for this project's usage level).

Uses the current `google-genai` SDK (the older `google-generativeai`
package was retired by Google).

Output is strict JSON so downstream steps (TTS, visuals, captions,
title/description) can all consume it without any fragile text-parsing.
"""
import json
import os

from google import genai
from google.genai import types

SYSTEM_PROMPT = """You write scripts for a YouTube Shorts channel that does \
dramatic "Top 5" countdown videos in a specific niche. You write ONLY valid \
JSON, nothing else — no markdown fences, no preamble.

The JSON schema you must return:
{
  "hook_line": "one punchy sentence said in the first 2 seconds to stop the scroll",
  "topic_title": "short human-readable topic name, e.g. 'Haunted Forts of India'",
  "items": [
    {
      "rank": 5,
      "name": "short name of this item",
      "narration": "2-3 sentences of dramatic narration for this item, written in Hindi (Devanagari script), to be spoken aloud by a text-to-speech voice",
      "narration_hinglish": "the SAME narration content, but transliterated into Hinglish (Hindi words written in Roman/English letters, the way Indians casually type Hindi in texts/social media, e.g. 'Ye kahani hai ek purani havli ki'). This is only used for on-screen captions, not for audio.",
      "visual_keywords": ["2-4 words describing what stock footage would match this, e.g. 'old fort night fog'"]
    }
  ]
}

Rules:
- Exactly the requested number of items, ranked from highest number down to #1 (countdown style, most shocking/best saved for #1).
- Narration must be spoken-language, not written-language: short sentences, no complex punctuation, dramatic pacing.
- narration_hinglish must match narration's meaning and pacing closely (same sentence breaks), just in Roman script instead of Devanagari.
- Never name real living private individuals or attribute crimes to real named people. Folklore, historical legends, and clearly-attributed public reports are fine.
- Total narration across all items should fit the requested target duration at natural spoken pace (~2.4 words/second).
- No sexual, graphic gore, or hateful content. Spooky and suspenseful, not gruesome.
"""


def generate_script(topic: str, config: dict) -> dict:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    items = config["script"]["items_per_video"]
    seconds = config["script"]["target_narration_seconds"]
    language = config["script"]["language"]
    niche = config["channel"]["niche"]
    tone = config["channel"]["tone"]
    audience = config["channel"]["audience"]

    user_prompt = f"""Channel niche: {niche}
Tone: {tone}
Audience: {audience}
Language for spoken narration: {language} (write in Devanagari script for correct TTS pronunciation)
Topic for this video: {topic}
Number of countdown items: {items}
Target total narration length: about {seconds} seconds spoken aloud

Write the script now as JSON only."""

    response = client.models.generate_content(
        model="gemini-flash-lite-latest",
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )

    text = response.text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    # Gemini occasionally appends stray text/whitespace after the JSON object.
    # Parse only the first valid JSON value and ignore anything after it.
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(text)
    return obj


if __name__ == "__main__":
    import yaml

    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    script = generate_script("haunted forts and palaces across India", cfg)
    print(json.dumps(script, indent=2, ensure_ascii=False))
