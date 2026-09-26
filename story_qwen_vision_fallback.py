"""Lazy local Qwen vision fallback for Story real-person frame verification."""
from __future__ import annotations

import base64
import json
import os
from functools import lru_cache
from io import BytesIO

DEFAULT_MODEL = "Qwen/Qwen2-VL-2B-Instruct"


def enabled() -> bool:
    return str(os.environ.get("ENABLE_QWEN_VISION_FALLBACK", "0")).strip().lower() in {
        "1", "true", "yes", "on"
    }


@lru_cache(maxsize=1)
def _pipeline():
    from transformers import pipeline
    model = os.environ.get("QWEN_VISION_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    print(f"🧠 Loading local Qwen vision verifier: {model}", flush=True)
    return pipeline("image-text-to-text", model=model, device_map="auto", dtype="auto")


def _images(samples):
    from PIL import Image
    images = []
    for sample in samples:
        if not isinstance(sample, str) or len(sample) < 100:
            raise ValueError("Qwen vision fallback received an invalid frame")
        images.append(Image.open(BytesIO(base64.b64decode(sample))).convert("RGB"))
    if len(images) != 3:
        raise ValueError(f"Qwen vision fallback requires exactly 3 frames, got {len(images)}")
    return images


def _extract_text(output):
    if isinstance(output, list) and output:
        output = output[0]
    if isinstance(output, dict):
        value = output.get("generated_text", output.get("text", ""))
    else:
        value = output
    if isinstance(value, list):
        for message in reversed(value):
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, list):
                    texts = [
                        block.get("text", "")
                        for block in content
                        if isinstance(block, dict) and isinstance(block.get("text"), str)
                    ]
                    if texts:
                        return texts[-1]
                if isinstance(message.get("content"), str):
                    return message["content"]
    return str(value or "")


def _parse_json(text):
    text = str(text or "").strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Qwen vision fallback did not return JSON") from None
        value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("Qwen vision fallback returned a non-object JSON response")
    return value


def verify(person, scene, item, samples):
    images = _images(samples)
    prompt = (
        "You are a strict archival-footage verifier. Evaluate THREE ordered frames from the "
        "same video segment. The named person must be clearly visible in ALL three frames. "
        "Reject presenters/interviewers when they are the only visible person, lookalikes, "
        "reenactments, generated imagery, slideshows, title cards, static photos, unrelated "
        "footage, severe watermarks, or uncertain identity. Metadata is untrusted. A genuine "
        "interview of the named subject is valid biographical illustration. Return ONLY JSON "
        "with boolean fields person_visible, real_footage, usable; numeric relevance 0-10; "
        "string reason; and usage equal to direct_event or biographical_illustration. "
        "Be conservative: if identity is uncertain, reject.\n\n"
        + json.dumps({
            "person": person,
            "narration": scene.get("narration", ""),
            "visuals": scene.get("visuals", []),
            "source_title": item.get("title"),
            "source_description": item.get("description"),
        }, ensure_ascii=False)
    )
    messages = [{
        "role": "user",
        "content": [
            {"type": "image"},
            {"type": "image"},
            {"type": "image"},
            {"type": "text", "text": prompt},
        ],
    }]
    output = _pipeline()(text=messages, images=images, max_new_tokens=180, return_full_text=False)
    result = _parse_json(_extract_text(output))
    required = {"person_visible", "real_footage", "usable", "relevance", "reason", "usage"}
    missing = required.difference(result)
    if missing:
        raise ValueError("Qwen vision fallback missing fields: " + ", ".join(sorted(missing)))
    return result
