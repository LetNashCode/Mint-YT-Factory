"""AI visual generation engine for Mint-YT-Factory.

Quality pass:
- ties every image to an exact spoken beat
- enforces must-show / must-not-show constraints
- stronger cinematic realism prompts
- prevents generic topic-only prompts
- adds a Gemini vision relevance gate after generation
- automatically regenerates shots that fail the visual contract
- keeps shot-to-shot continuity without injecting random subjects
- generates larger portrait source images for cleaner 4K upscaling
"""

from __future__ import annotations

import io
import json
import os
import time
import urllib.parse

import requests

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

BASE_URL = "https://image.pollinations.ai/prompt/"
MODEL_NAME = "flux"
VISION_MODEL = "gemini-flash-lite-latest"

HEADERS = {
    "User-Agent": "Mint-YT-Factory/visual-engine",
    "Accept": "image/png,image/jpeg,image/webp,*/*",
}

MAX_RETRIES = 5
RETRY_DELAY = 4
REQUEST_TIMEOUT = 180
BETWEEN_IMAGE_DELAY = 2

DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1792

EXPECTED_SCENES = 7
VISUALS_PER_SCENE = 2
EXPECTED_TOTAL_IMAGES = 14
MIN_IMAGE_BYTES = 10_000
EXPECTED_FORMAT = "PNG"

# The guard is deliberately one/two multimodal requests for the whole Short,
# not one request per image. If Gemini is unavailable, generation fails open.
VISUAL_GUARD_ENABLED = os.environ.get("MINT_DISABLE_VISUAL_GUARD", "0") != "1"
VISUAL_GUARD_MIN_SCORE = 7
VISUAL_GUARD_MAX_REGENERATIONS = 4


def _clean(value, maximum=None):
    text = " ".join(str(value or "").replace("\n", " ").split()).strip()
    if maximum:
        text = text[:maximum]
    return text


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_dimensions(config):
    image = config.get("image", {}) if isinstance(config, dict) else {}
    if not isinstance(image, dict):
        image = {}
    width = _safe_int(image.get("width"), DEFAULT_WIDTH)
    height = _safe_int(image.get("height"), DEFAULT_HEIGHT)
    if width <= 0:
        width = DEFAULT_WIDTH
    if height <= 0:
        height = DEFAULT_HEIGHT
    if width >= height:
        width, height = height, width
    return width, height


def _get_seed(script):
    generation = script.get("image_generation", {}) if isinstance(script, dict) else {}
    if not isinstance(generation, dict):
        generation = {}
    return _safe_int(generation.get("seed"), int(time.time()))


def _shot_seed(base, scene_index, visual_index):
    return int(base) + scene_index * 100 + visual_index


def _retry_seed(seed, attempt):
    return int(seed) + (attempt * 10_000)


def _identity(script):
    identity = script.get("visual_identity", {}) if isinstance(script, dict) else {}
    if not isinstance(identity, dict):
        identity = {}
    generation = script.get("image_generation", {}) if isinstance(script, dict) else {}
    if not isinstance(generation, dict):
        generation = {}
    return (
        _clean(identity.get("style"), 500),
        _clean(identity.get("palette"), 250),
        _clean(identity.get("mood_arc"), 250),
        _clean(generation.get("style_lock"), 500),
    )


def _continuity(script):
    continuity = script.get("visual_continuity", {}) if isinstance(script, dict) else {}
    if not isinstance(continuity, dict):
        continuity = {}
    subjects = continuity.get("recurring_subjects", [])
    if not isinstance(subjects, list):
        subjects = []
    objects = continuity.get("recurring_objects", [])
    if not isinstance(objects, list):
        objects = []
    return subjects[:4], [_clean(x, 150) for x in objects[:5] if _clean(x)], _clean(continuity.get("recurring_environment"), 400)


def _relevant_continuity(script, prompt):
    subjects, objects, environment = _continuity(script)
    lower = prompt.lower()
    parts = []
    for subject in subjects:
        if not isinstance(subject, dict):
            continue
        name = _clean(subject.get("name"), 100)
        appearance = _clean(subject.get("appearance"), 300)
        if name and any(token in lower for token in name.lower().split() if len(token) >= 4):
            parts.append(f"If {name} is visible, preserve this appearance: {appearance}.")
    for obj in objects:
        if obj.lower() in lower:
            parts.append(f"Keep the recurring object {obj} consistent.")
    if environment:
        env_tokens = [x for x in environment.lower().split() if len(x) >= 5]
        if any(x in lower for x in env_tokens):
            parts.append(f"Keep the recurring environment consistent: {environment}.")
    return " ".join(parts)


def re_tokens(text):
    return [token for token in _clean(text).lower().replace("-", " ").split() if len(token) >= 4]


def _semantic_contract(scene, visual, scene_index, visual_index):
    narration = _clean(scene.get("narration"), 500)
    spoken = _clean(visual.get("spoken_line"), 350) or narration
    focus = _clean(visual.get("visual_focus"), 180)
    action = _clean(visual.get("visual_action"), 300)
    must_show = [_clean(x, 120) for x in visual.get("must_show", []) if _clean(x)][:6]
    must_not_show = [_clean(x, 120) for x in visual.get("must_not_show", []) if _clean(x)][:8]
    prompt = _clean(visual.get("image_prompt"), 900)

    if not prompt:
        raise RuntimeError(f"Scene {scene_index} Shot {visual_index} has no image_prompt.")
    if not focus:
        raise RuntimeError(f"Scene {scene_index} Shot {visual_index} has no visual_focus.")
    if not action:
        raise RuntimeError(f"Scene {scene_index} Shot {visual_index} has no visual_action.")

    prompt_lower = prompt.lower()
    candidates = [focus] + must_show
    if not any(any(token in prompt_lower for token in re_tokens(item)) for item in candidates if item):
        raise RuntimeError(f"Scene {scene_index} Shot {visual_index} failed semantic prompt gate.")

    return narration, spoken, focus, action, must_show, must_not_show, prompt


def build_prompt(scene, visual, script=None, scene_index=1, visual_index=1, correction=""):
    if not isinstance(scene, dict) or not isinstance(visual, dict):
        raise RuntimeError(f"Scene {scene_index} Shot {visual_index} is invalid.")
    script = script if isinstance(script, dict) else {}
    narration, spoken, focus, action, must_show, must_not_show, image_prompt = _semantic_contract(scene, visual, scene_index, visual_index)
    style, palette, mood, style_lock = _identity(script)

    parts = [
        "REALISTIC CINEMATIC VISUAL. Generate only the physical scene described below.",
        f"Exact spoken beat: {spoken}.",
        f"Main subject: {focus}.",
        f"Visible physical action/state: {action}.",
        f"Source visual description: {image_prompt}.",
        "The main subject and action must dominate the frame and be immediately recognizable.",
        "Use believable real-world scale, materials, physics, reflections and shadows.",
        "Natural cinematic lighting and photographic detail; no illustration or cartoon look.",
    ]
    if must_show:
        parts.append("MUST VISIBLY CONTAIN: " + "; ".join(must_show) + ".")
    if must_not_show:
        parts.append("MUST NOT CONTAIN: " + "; ".join(must_not_show) + ".")
    if style:
        parts.append(f"Production style: {style}.")
    if palette:
        parts.append(f"Color treatment: {palette}.")
    if mood:
        parts.append(f"Emotional feel: {mood}.")
    if style_lock:
        parts.append(f"Global style lock: {style_lock}.")

    continuity = _relevant_continuity(script, image_prompt + " " + focus)
    if continuity:
        parts.append(continuity)

    if visual_index == 2:
        previous = scene.get("visuals", [])[0] if isinstance(scene.get("visuals"), list) and scene.get("visuals") else {}
        previous_prompt = _clean(previous.get("image_prompt"), 400) if isinstance(previous, dict) else ""
        parts.append("This is shot 2 of the same moment. Advance the action or reveal a new physical detail; do not duplicate the previous composition.")
        if previous_prompt:
            parts.append(f"Shot 1 context: {previous_prompt}.")
    else:
        parts.append("This is shot 1. Establish the exact physical moment clearly and immediately.")

    if correction:
        parts.append(f"CORRECTION REQUIRED: {correction}. Make the declared subject and action unmistakable.")

    parts.append("No text, captions, subtitles, labels, logos, watermarks, UI, diagrams, arrows, formulas or decorative symbols.")
    return _clean(" ".join(parts), 1900)


def _build_url(prompt, width, height, seed):
    encoded = urllib.parse.quote(prompt, safe="")
    return f"{BASE_URL}{encoded}?model={MODEL_NAME}&width={int(width)}&height={int(height)}&seed={int(seed)}"


def _validate_response(response):
    if response is None or response.status_code != 200:
        status = getattr(response, "status_code", "none")
        text = getattr(response, "text", "")[:300]
        raise RuntimeError(f"Image HTTP error {status}: {text}")
    content = response.content
    if not content or len(content) < MIN_IMAGE_BYTES:
        raise RuntimeError("Generated image response is empty or suspiciously small.")
    content_type = response.headers.get("Content-Type", "").lower()
    signatures = (b"\x89PNG", b"\xff\xd8\xff", b"RIFF")
    if "image" not in content_type and not any(content.startswith(x) for x in signatures):
        raise RuntimeError("Provider returned a non-image response.")
    return content


def generate_image(prompt, width, height, seed):
    session = requests.Session()
    session.headers.update(HEADERS)
    api_key = os.environ.get("POLLINATIONS_API_KEY")
    if api_key:
        session.headers["Authorization"] = f"Bearer {api_key}"
    last_error = None
    try:
        for attempt in range(MAX_RETRIES):
            attempt_seed = _retry_seed(seed, attempt)
            try:
                print(f"🎨 Image attempt {attempt + 1}/{MAX_RETRIES} | seed={attempt_seed} | size={width}x{height}")
                response = session.get(_build_url(prompt, width, height, attempt_seed), timeout=REQUEST_TIMEOUT)
                content = _validate_response(response)
                if Image is not None:
                    image = Image.open(io.BytesIO(content))
                    image.verify()
                print(f"✅ Image generated: {len(content):,} bytes")
                return content
            except Exception as error:
                last_error = error
                print(f"❌ Image attempt failed: {type(error).__name__}: {error}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
    finally:
        session.close()
    raise RuntimeError(f"Failed to generate image after {MAX_RETRIES} attempts: {last_error}")


def _save_image(content, path, width, height):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if Image is None:
        with open(path, "wb") as handle:
            handle.write(content)
        return path
    image = Image.open(io.BytesIO(content))
    image.load()
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    if image.size != (int(width), int(height)):
        image = image.resize((int(width), int(height)), Image.Resampling.LANCZOS)
    image.save(path, format="PNG", optimize=True)
    with Image.open(path) as check:
        if check.format != EXPECTED_FORMAT or check.size != (int(width), int(height)):
            raise RuntimeError(f"Final image validation failed: {check.format} {check.size}")
        check.verify()
    if os.path.getsize(path) < MIN_IMAGE_BYTES:
        raise RuntimeError(f"Generated image is too small: {path}")
    return path


def _validate_script(script):
    if not isinstance(script, dict):
        raise RuntimeError("Script must be a dictionary.")
    scenes = script.get("scene_plan")
    if not isinstance(scenes, list) or len(scenes) != EXPECTED_SCENES:
        raise RuntimeError(f"Expected exactly {EXPECTED_SCENES} scenes.")
    total = 0
    for i, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise RuntimeError(f"Scene {i} is invalid.")
        visuals = scene.get("visuals")
        if not isinstance(visuals, list) or len(visuals) != VISUALS_PER_SCENE:
            raise RuntimeError(f"Scene {i} must contain exactly {VISUALS_PER_SCENE} visuals.")
        for j, visual in enumerate(visuals, 1):
            _semantic_contract(scene, visual, i, j)
            total += 1
    if total != EXPECTED_TOTAL_IMAGES:
        raise RuntimeError(f"Expected {EXPECTED_TOTAL_IMAGES} visuals, found {total}.")
    return scenes


def _guard_image_bytes(path):
    if Image is None:
        return None
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((512, 896), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=72, optimize=True)
        return buffer.getvalue()


def _parse_guard_response(text, expected_count):
    text = _clean(text)
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("results", [])
    if not isinstance(data, list):
        raise RuntimeError("Visual guard returned an invalid result list.")
    results = []
    for item in data:
        if not isinstance(item, dict):
            continue
        results.append({
            "index": _safe_int(item.get("index"), 0),
            "score": _safe_int(item.get("score"), 0),
            "pass": bool(item.get("pass")),
            "reason": _clean(item.get("reason"), 300),
        })
    if len(results) != expected_count:
        raise RuntimeError(f"Visual guard expected {expected_count} results, got {len(results)}.")
    return results


def _vision_guard(records):
    """Check generated images against their actual visual contracts.

    This is intentionally a batch check: 14 images are reviewed in two requests
    rather than making 14 extra Gemini calls. Errors fail open so the production
    pipeline is never broken solely because the optional guard is unavailable.
    """
    if not VISUAL_GUARD_ENABLED or genai is None or types is None:
        print("Visual relevance guard: DISABLED")
        return []
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Visual relevance guard: SKIPPED (no GEMINI_API_KEY)")
        return []

    client = genai.Client(api_key=api_key)
    all_results = []
    for start in range(0, len(records), 7):
        batch = records[start:start + 7]
        contents = []
        instructions = [
            "You are a strict visual quality-control editor for a YouTube Short.",
            "For each numbered image, compare what is ACTUALLY visible with its spoken beat.",
            "Score 0-10. Pass only if the main subject AND physical action/state are clearly visible.",
            "Fail generic topic images, wrong objects, random people, unrelated scenery, diagrams, or images that only vaguely match.",
            "Do not judge artistic beauty. Judge semantic accuracy.",
            "Return ONLY JSON: {\"results\":[{\"index\":1,\"score\":9,\"pass\":true,\"reason\":\"...\"}]}"
        ]
        for offset, record in enumerate(batch, 1):
            image_bytes = _guard_image_bytes(record["path"])
            if not image_bytes:
                raise RuntimeError("Pillow is required for visual relevance guard.")
            contents.append(types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"))
            contents.append(
                f"IMAGE {offset}: spoken beat={record['spoken']}; main subject={record['focus']}; action={record['action']}; must show={record['must_show']}; must not show={record['must_not_show']}"
            )
        contents.append("\n".join(instructions))
        try:
            response = client.models.generate_content(model=VISION_MODEL, contents=contents)
            results = _parse_guard_response(getattr(response, "text", ""), len(batch))
            for result in results:
                result["global_index"] = start + result["index"]
                all_results.append(result)
        except Exception as error:
            print(f"⚠️ Visual relevance guard unavailable: {type(error).__name__}: {error}")
            return []
    return all_results


def generate_images(script, workdir, config):
    os.makedirs(workdir, exist_ok=True)
    scenes = _validate_script(script)
    width, height = _get_dimensions(config)
    base_seed = _get_seed(script)
    image_paths = []
    records = []

    print("=" * 80)
    print("🎨 ENTERTAINMENT-FIRST AI VISUAL GENERATION")
    print("=" * 80)
    print("Semantic visual contract: ENABLED")
    print("Realism-first prompting: ENABLED")
    print(f"Source resolution: {width}x{height}")
    print(f"Total images: {EXPECTED_TOTAL_IMAGES}")
    print(f"Visual relevance guard: {'ENABLED' if VISUAL_GUARD_ENABLED else 'DISABLED'}")

    global_index = 0
    for scene_index, scene in enumerate(scenes, 1):
        scene_paths = []
        print("=" * 80)
        print(f"🎬 SCENE {scene_index}/{EXPECTED_SCENES}")
        print(f"Narration: {scene.get('narration', '')}")
        print("=" * 80)

        for visual_index, visual in enumerate(scene["visuals"], 1):
            global_index += 1
            prompt = build_prompt(scene, visual, script, scene_index, visual_index)
            seed = _shot_seed(base_seed, scene_index, visual_index)
            print(f"🖼️ SHOT {visual_index}/{VISUALS_PER_SCENE} | focus={visual.get('visual_focus')} | action={visual.get('visual_action')}")
            print(f"Prompt: {prompt}")
            content = generate_image(prompt, width, height, seed)
            filename = os.path.join(workdir, f"scene_{scene_index:02d}_shot_{visual_index:02d}.png")
            _save_image(content, filename, width, height)
            scene_paths.append(filename)
            _, spoken, focus, action, must_show, must_not_show, _ = _semantic_contract(scene, visual, scene_index, visual_index)
            records.append({"global_index": global_index, "scene": scene_index, "shot": visual_index, "path": filename, "prompt": prompt, "spoken": spoken, "focus": focus, "action": action, "must_show": "; ".join(must_show), "must_not_show": "; ".join(must_not_show), "seed": seed})
            print(f"✅ Saved: {filename}")
            if not (scene_index == EXPECTED_SCENES and visual_index == VISUALS_PER_SCENE):
                time.sleep(BETWEEN_IMAGE_DELAY)
        image_paths.append(scene_paths)

    if sum(len(x) for x in image_paths) != EXPECTED_TOTAL_IMAGES:
        raise RuntimeError("Visual generation contract failed.")

    # ------------------------------------------------------------------
    # Actual image-level semantic QC.
    # ------------------------------------------------------------------
    guard_results = _vision_guard(records)
    failures = [x for x in guard_results if x.get("score", 0) < VISUAL_GUARD_MIN_SCORE or not x.get("pass")]

    if failures:
        print("=" * 80)
        print(f"⚠️ VISUAL GUARD FOUND {len(failures)} WEAK SHOT(S)")
        print("=" * 80)
        for failure in failures[:VISUAL_GUARD_MAX_REGENERATIONS]:
            index = failure.get("global_index", 0)
            if index < 1 or index > len(records):
                continue
            record = records[index - 1]
            correction = failure.get("reason") or "the declared subject/action is not clearly visible"
            print(f"🔄 Regenerating Scene {record['scene']} Shot {record['shot']}: {correction}")
            corrected_prompt = build_prompt(
                scenes[record["scene"] - 1],
                scenes[record["scene"] - 1]["visuals"][record["shot"] - 1],
                script,
                record["scene"],
                record["shot"],
                correction=correction,
            )
            corrected = generate_image(corrected_prompt, width, height, record["seed"] + 500_000)
            _save_image(corrected, record["path"], width, height)
            record["prompt"] = corrected_prompt

    print("=" * 80)
    print("✅ VISUAL GENERATION COMPLETE")
    print(f"Images generated: {EXPECTED_TOTAL_IMAGES}")
    print(f"Resolution: {width}x{height}")
    if VISUAL_GUARD_ENABLED:
        print(f"Vision QC results: {len(guard_results)}")
        print(f"Regenerated weak shots: {min(len(failures), VISUAL_GUARD_MAX_REGENERATIONS)}")
    print("Semantic prompt gate: PASSED")
    print("=" * 80)
    return image_paths


def generate_single_image(prompt, workdir, filename="generated.png", width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, seed=None):
    os.makedirs(workdir, exist_ok=True)
    seed = int(time.time()) if seed is None else int(seed)
    if width >= height:
        width, height = height, width
    content = generate_image(_clean(prompt, 1800), width, height, seed)
    return _save_image(content, os.path.join(workdir, filename), width, height)
