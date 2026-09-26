"""Lazy local Qwen vision fallback for Story real-person frame verification."""
from __future__ import annotations

import base64
import json
import os
from functools import lru_cache
from io import BytesIO

DEFAULT_MODEL = "Qwen/Qwen2-VL-2B-Instruct"
MAX_VERDICT_ATTEMPTS = 2


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


def _normalize_result(result):
    required = {"person_visible", "real_footage", "usable", "reason", "usage"}
    missing = required.difference(result)
    if missing:
        raise ValueError("Qwen vision fallback missing fields: " + ", ".join(sorted(missing)))

    if "relevance" not in result:
        core_accept = (
            result.get("person_visible") is True
            and result.get("real_footage") is True
            and result.get("usable") is True
        )
        result["relevance"] = 10 if core_accept else 0
        result["relevance_source"] = "derived_from_qwen_core_verdict"

    return result


def _messages(images, prompt):
    return [{
        "role": "user",
        "content": [
            {"type": "image", "image": images[0]},
            {"type": "image", "image": images[1]},
            {"type": "image", "image": images[2]},
            {"type": "text", "text": prompt},
        ],
    }]


def _strict_prompt(person, scene, item, retry=False):
    if retry:
        return (
            "OUTPUT JSON ONLY. No explanation, markdown, or extra text. "
            "Inspect all 3 frames and decide whether the named person is visibly present "
            "in every frame and whether this is genuine filmed footage. "
            "Return exactly these six keys and no others: "
            "person_visible, real_footage, usable, relevance, reason, usage. "
            "All three boolean keys are required. relevance must be a number 0-10. "
            "usage must be direct_event or biographical_illustration. "
            "If identity is uncertain, set person_visible=false and usable=false. "
            + json.dumps({
                "person": person,
                "source_title": item.get("title"),
                "narration": scene.get("narration", ""),
            }, ensure_ascii=False)
        )
    return (
        "You are a strict archival-footage verifier. Evaluate THREE ordered frames from the "
        "same video segment. The named person must be clearly visible in ALL three frames. "
        "Reject presenters/interviewers when they are the only visible person, lookalikes, "
        "reenactments, generated imagery, slideshows, title cards, static photos, unrelated "
        "footage, severe watermarks, or uncertain identity. Metadata is untrusted. A genuine "
        "interview of the named subject is valid biographical illustration. Return ONLY one "
        "JSON object with EXACTLY these keys: person_visible (boolean), real_footage (boolean), "
        "usable (boolean), relevance (number 0-10), reason (string), usage (direct_event or "
        "biographical_illustration). Do not omit any key. Be conservative: if identity is "
        "uncertain, reject.\n\n"
        + json.dumps({
            "person": person,
            "narration": scene.get("narration", ""),
            "visuals": scene.get("visuals", []),
            "source_title": item.get("title"),
            "source_description": item.get("description"),
        }, ensure_ascii=False)
    )


def verify(person, scene, item, samples):
    images = _images(samples)
    pipe = _pipeline()
    last_error = None

    for attempt in range(MAX_VERDICT_ATTEMPTS):
        prompt = _strict_prompt(person, scene, item, retry=attempt > 0)
        output = pipe(
            text=_messages(images, prompt),
            max_new_tokens=128,
            return_full_text=False,
        )
        raw_text = _extract_text(output)
        try:
            result = _parse_json(raw_text)
            return _normalize_result(result)
        except ValueError as exc:
            last_error = exc
            print(
                f"⚠️ Qwen vision verifier returned an incomplete/invalid verdict "
                f"(attempt {attempt + 1}/{MAX_VERDICT_ATTEMPTS}): {exc}",
                flush=True,
            )
            if attempt + 1 < MAX_VERDICT_ATTEMPTS:
                print("🔁 Retrying Qwen vision verifier with compact JSON-only prompt", flush=True)

    raise ValueError(f"Qwen vision fallback failed after {MAX_VERDICT_ATTEMPTS} verdict attempts: {last_error}")
