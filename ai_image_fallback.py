"""Gemini image-generation fallback for Mint-YT-Factory.

Used only when verified Pexels/Pixabay media cannot illustrate a shot.
The prompt is deliberately literal: the generated frame must show the exact
physical subject/state from the narration, not a generic science illustration.

The fallback uses Gemini's REST generateContent endpoint rather than relying on
an installed google-genai SDK schema for response_format. This avoids breaking
when the runner's SDK version does not expose the image response-format field.
"""
from __future__ import annotations

import base64
import os
import time
from pathlib import Path

import requests

MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
ATTEMPTS = 3
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


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


def _extract_image(response_json: dict) -> bytes | None:
    for candidate in response_json.get("candidates", []) or []:
        content = candidate.get("content") or {}
        for part in content.get("parts", []) or []:
            inline = part.get("inlineData") or part.get("inline_data") or {}
            encoded = inline.get("data")
            if encoded:
                return base64.b64decode(encoded)
    return None


def generate(directed: dict, path: str) -> bool:
    """Generate a literal vertical fallback image and save it to *path*."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None

    for attempt in range(1, ATTEMPTS + 1):
        try:
            payload = {
                "contents": [{"parts": [{"text": _prompt(directed)}]}],
                "generationConfig": {
                    "responseModalities": ["IMAGE"],
                    "responseFormat": {"image": {"aspectRatio": "9:16"}},
                },
            }
            response = requests.post(
                API_URL.format(model=MODEL),
                params={"key": _key()},
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=120,
            )
            if not response.ok:
                raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:500]}")

            data = response.json()
            image_bytes = _extract_image(data)
            if not image_bytes:
                raise RuntimeError("Gemini returned no inline image data")

            output.write_bytes(image_bytes)
            if output.exists() and output.stat().st_size > 10_000:
                return True
            raise RuntimeError("Gemini image output is unexpectedly small")
        except Exception as exc:
            last_error = exc
            print(f"      ⚠️ Gemini image fallback {attempt}/{ATTEMPTS}: {type(exc).__name__}: {exc}")
            if attempt < ATTEMPTS:
                time.sleep(1.5 * attempt)

    print(f"      ❌ Gemini image fallback exhausted: {type(last_error).__name__ if last_error else 'unknown'}")
    return False
