"""Gemini image-generation fallback for Mint-YT-Factory.

Used only when verified Pexels/Pixabay media cannot illustrate a shot.
The prompt is deliberately literal: the generated frame must show the exact
physical subject/state from the narration, not a generic science illustration.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from google import genai
from google.genai import types

MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
ATTEMPTS = 3


def _key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required for AI image fallback.")
    return key


def _prompt(directed: dict) -> str:
    spoken = str(directed.get("spoken_beat") or "").strip()
    brief = str(directed.get("casting_brief") or "").strip()
    focus = str(directed.get("visual_focus") or "").strip()
    action = str(directed.get("visual_action") or "").strip()
    image_prompt = str(directed.get("image_prompt") or "").strip()
    must = ", ".join(str(x).strip() for x in directed.get("must_match", []) if str(x).strip())
    avoid = ", ".join(str(x).strip() for x in directed.get("avoid", []) if str(x).strip())

    return f"""Create ONE photorealistic vertical 9:16 frame for a fast, fun YouTube Short.

This frame is a literal visual for the spoken beat below. Show the EXACT physical subject
and the EXACT visible action/state. Do not illustrate the explanation with abstract science.

SPOKEN BEAT:
{spoken}

MAIN SUBJECT:
{focus}

VISIBLE ACTION / STATE:
{action}

DIRECTOR BRIEF:
{brief}

ORIGINAL CAMERA PROMPT:
{image_prompt}

MUST MATCH:
{must}

MUST NOT SHOW:
{avoid}

HARD RULES:
- The named object must be unmistakably recognizable.
- If an action is spoken, visibly show that action or its immediate physical result.
- If the mechanism is invisible, show a truthful physical proxy such as a cut-open object,
  visible steam, swelling, cracking, bursting, melting, or the resulting object.
- Prefer a realistic macro/close-up when the subject is small.
- No diagrams, equations, labels, arrows, text, logos, fantasy particles, cartoon science,
  generic laboratory scenes, unrelated objects, or symbolic metaphors.
- Do not replace a specific object with a related one. For example, popcorn kernel means
  a popcorn kernel, not corn-on-the-cob.
- Make the frame visually interesting with lighting, depth and composition, but relevance
  is more important than cinematic decoration.
- No people unless a hand/person is explicitly required by the beat.
"""


def generate(directed: dict, path: str) -> bool:
    """Generate a literal vertical fallback image and save it to *path*."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None

    for attempt in range(1, ATTEMPTS + 1):
        try:
            client = genai.Client(api_key=_key())
            response = client.models.generate_content(
                model=MODEL,
                contents=_prompt(directed),
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    response_format={"image": {"aspect_ratio": "9:16"}},
                ),
            )
            for part in response.parts:
                if getattr(part, "inline_data", None) is not None:
                    image = part.as_image()
                    image.save(str(output), format="JPEG", quality=94)
                    if output.exists() and output.stat().st_size > 10_000:
                        return True
            raise RuntimeError("Gemini returned no image data")
        except Exception as exc:
            last_error = exc
            print(f"      ⚠️ Gemini image fallback {attempt}/{ATTEMPTS}: {type(exc).__name__}: {exc}")
            if attempt < ATTEMPTS:
                time.sleep(1.5 * attempt)

    print(f"      ❌ Gemini image fallback exhausted: {type(last_error).__name__ if last_error else 'unknown'}")
    return False
