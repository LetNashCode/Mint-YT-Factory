"""Pollinations image-generation fallback for Mint-YT-Factory.

Used only when verified Pexels/Pixabay media cannot illustrate a shot.
The prompt is deliberately literal: the generated frame must show the exact
physical subject/state from the narration, not a generic science illustration.

IMPORTANT: Gemini is NOT used for image generation. Gemini remains available
elsewhere in the pipeline only for visual verification/search direction.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image
from io import BytesIO

ATTEMPTS = 3
API_URL = "https://image.pollinations.ai/prompt/{prompt}"
WIDTH = int(os.getenv("POLLINATIONS_IMAGE_WIDTH", "1080"))
HEIGHT = int(os.getenv("POLLINATIONS_IMAGE_HEIGHT", "1920"))


def _prompt(directed: dict) -> str:
    spoken = str(directed.get("spoken_beat") or "").strip()
    brief = str(directed.get("casting_brief") or "").strip()
    focus = str(directed.get("visual_focus") or "").strip()
    action = str(directed.get("visual_action") or "").strip()
    image_prompt = str(directed.get("image_prompt") or "").strip()
    must = ", ".join(str(x).strip() for x in directed.get("must_match", []) if str(x).strip())
    avoid = ", ".join(str(x).strip() for x in directed.get("avoid", []) if str(x).strip())

    return f"""Photorealistic vertical 9:16 frame for a fast, fun YouTube Short.
Show the EXACT physical subject and EXACT visible action/state from the spoken beat.
This is a literal visual, not an abstract science illustration.

SPOKEN BEAT: {spoken}
MAIN SUBJECT: {focus}
VISIBLE ACTION / STATE: {action}
DIRECTOR BRIEF: {brief}
ORIGINAL CAMERA PROMPT: {image_prompt}
MUST MATCH: {must}
MUST NOT SHOW: {avoid}

Hard rules: the named object must be unmistakably recognizable; show the spoken action
or its immediate physical result; for invisible mechanisms use a truthful physical proxy
such as a cut-open object, visible steam, swelling, cracking, bursting or melting;
prefer realistic macro/close-up for small subjects; no diagrams, equations, labels,
arrows, text, logos, fantasy particles, cartoon science, generic laboratories,
unrelated objects or symbolic metaphors; never substitute a related object; cinematic
lighting is welcome but relevance is more important; no people unless explicitly required."""


def _validate_and_save(data: bytes, output: Path) -> None:
    image = Image.open(BytesIO(data))
    image.load()
    if image.width < 256 or image.height < 256:
        raise RuntimeError(f"Pollinations image too small: {image.width}x{image.height}")
    image = image.convert("RGB")
    image.save(output, format="JPEG", quality=95, optimize=True)
    if output.stat().st_size <= 10_000:
        raise RuntimeError("Pollinations image output is unexpectedly small")


def generate(directed: dict, path: str) -> bool:
    """Generate a literal portrait fallback image with Pollinations and save it."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    prompt = quote(_prompt(directed), safe="")
    last_error: Exception | None = None

    for attempt in range(1, ATTEMPTS + 1):
        try:
            url = API_URL.format(prompt=prompt)
            response = requests.get(
                url,
                params={
                    "width": WIDTH,
                    "height": HEIGHT,
                    "nologo": "true",
                },
                headers={"User-Agent": "Mint-YT-Factory/11.0"},
                timeout=180,
            )
            response.raise_for_status()
            if not response.content:
                raise RuntimeError("Pollinations returned an empty response")
            _validate_and_save(response.content, output)
            return True
        except Exception as exc:
            last_error = exc
            print(f"      ⚠️ Pollinations image fallback {attempt}/{ATTEMPTS}: {type(exc).__name__}: {exc}")
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass
            if attempt < ATTEMPTS:
                time.sleep(2.0 * attempt)

    print(f"      ❌ Pollinations image fallback exhausted: {type(last_error).__name__ if last_error else 'unknown'}")
    return False
