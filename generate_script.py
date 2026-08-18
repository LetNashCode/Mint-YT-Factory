"""
generate_images.py
Mint-YT-Factory

Version 8.1

AI Visual Generation Engine

Fixes in 8.1:
- Applies image_style, lighting and color_palette from each visual.
- Applies the script-level style_lock consistently.
- Uses continuity as a consistency constraint instead of forcing every
  recurring subject into every image.
- Gives Shot 2 a clearer visual progression without copying Shot 1.
- Adds explicit visible-content guidance so metadata is not rendered as text.
- Uses deterministic shot seeds and deterministic retry seeds.
- Validates the complete 14-image production contract before generation.
- Preserves existing generate_images() and generate_single_image() APIs.
"""

import os
import time
import urllib.parse

import requests

try:
    from PIL import Image
    from io import BytesIO
except ImportError:
    Image = None
    BytesIO = None


# ==========================================================================
# CONFIGURATION
# ==========================================================================

BASE_URL = "https://image.pollinations.ai/prompt/"
MODEL_NAME = "flux"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept": "image/png,image/jpeg,image/webp,*/*",
}

MAX_RETRIES = 5
RETRY_DELAY = 5
REQUEST_TIMEOUT = 180
BETWEEN_IMAGE_DELAY = 2

DEFAULT_WIDTH = 768
DEFAULT_HEIGHT = 1365

EXPECTED_SCENES = 7
VISUALS_PER_SCENE = 2
EXPECTED_TOTAL_IMAGES = 14

MIN_IMAGE_BYTES = 10_000
EXPECTED_FORMAT = "PNG"

MAX_RECURRING_SUBJECTS = 4
MAX_RECURRING_OBJECTS = 5
MAX_CONTINUITY_RULES = 5

MAX_STYLE_LENGTH = 500
MAX_PALETTE_LENGTH = 300
MAX_MOOD_LENGTH = 300
MAX_ENVIRONMENT_LENGTH = 500
MAX_PROMPT_LENGTH = 1800


# ==========================================================================
# BASIC HELPERS
# ==========================================================================

def _clean_prompt(text):
    if not text:
        return ""

    text = str(text)
    text = text.replace("\n", " ")
    text = text.replace("```", "")

    return " ".join(text.split()).strip()


def _clean_text(value, maximum=None):
    if value is None:
        return ""

    value = " ".join(str(value).split()).strip()

    if maximum:
        value = value[:maximum]

    return value


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ==========================================================================
# VISUAL IDENTITY
# ==========================================================================

def _get_visual_identity(script):
    identity = script.get(
        "visual_identity",
        {},
    )

    if not isinstance(identity, dict):
        identity = {}

    return {
        "style": _clean_text(
            identity.get("style", ""),
            MAX_STYLE_LENGTH,
        ),

        "palette": _clean_text(
            identity.get("palette", ""),
            MAX_PALETTE_LENGTH,
        ),

        "mood_arc": _clean_text(
            identity.get("mood_arc", ""),
            MAX_MOOD_LENGTH,
        ),
    }


def _get_style_lock(script):
    generation = script.get(
        "image_generation",
        {},
    )

    if not isinstance(generation, dict):
        generation = {}

    return _clean_text(
        generation.get(
            "style_lock",
            "",
        ),
        1000,
    )


# ==========================================================================
# VISUAL CONTINUITY
# ==========================================================================

def _get_visual_continuity(script):
    continuity = script.get(
        "visual_continuity",
        {},
    )

    if not isinstance(continuity, dict):
        continuity = {}

    subjects = continuity.get(
        "recurring_subjects",
        [],
    )

    if not isinstance(subjects, list):
        subjects = []

    normalized_subjects = []

    for subject in subjects[
        :MAX_RECURRING_SUBJECTS
    ]:

        if not isinstance(
            subject,
            dict,
        ):
            continue

        name = _clean_text(
            subject.get(
                "name",
                "",
            ),
            100,
        )

        appearance = _clean_text(
            subject.get(
                "appearance",
                "",
            ),
            500,
        )

        continuity_rule = _clean_text(
            subject.get(
                "continuity",
                "",
            ),
            300,
        )

        if not name or not appearance:
            continue

        normalized_subjects.append({
            "name": name,
            "appearance": appearance,
            "continuity": (
                continuity_rule
                or
                "keep the same appearance whenever this subject is visible"
            ),
        })

    objects = continuity.get(
        "recurring_objects",
        [],
    )

    if not isinstance(
        objects,
        list,
    ):
        objects = []

    normalized_objects = [
        _clean_text(
            item,
            200,
        )
        for item in objects[
            :MAX_RECURRING_OBJECTS
        ]
        if _clean_text(item)
    ]

    environment = _clean_text(
        continuity.get(
            "recurring_environment",
            "",
        ),
        MAX_ENVIRONMENT_LENGTH,
    )

    rules = continuity.get(
        "continuity_rules",
        [],
    )

    if not isinstance(
        rules,
        list,
    ):
        rules = []

    normalized_rules = [
        _clean_text(
            rule,
            300,
        )
        for rule in rules[
            :MAX_CONTINUITY_RULES
        ]
        if _clean_text(rule)
    ]

    return {
        "subjects": normalized_subjects,
        "objects": normalized_objects,
        "environment": environment,
        "rules": normalized_rules,
    }


# ==========================================================================
# IMAGE GENERATION METADATA
# ==========================================================================

def _get_image_generation_config(script):
    generation = script.get(
        "image_generation",
        {},
    )

    if not isinstance(
        generation,
        dict,
    ):
        generation = {}

    seed = _safe_int(
        generation.get("seed"),
        int(time.time()),
    )

    return {
        "seed": seed,
        "style_lock": _get_style_lock(script),
    }


def _get_base_seed(script):
    return _get_image_generation_config(
        script
    )["seed"]


def _get_shot_seed(
    base_seed,
    scene_index,
    visual_index,
):
    """
    Stable seed for every shot.

    Same script + same base seed + same scene/shot
    always produces the same requested seed.
    """

    return (
        int(base_seed)
        + (scene_index * 100)
        + visual_index
    )


def _get_retry_seed(
    original_seed,
    attempt,
):
    """
    Attempt 0 uses the normal shot seed.

    Later attempts use deterministic alternate seeds.
    """

    if attempt <= 0:
        return int(
            original_seed
        )

    return (
        int(original_seed)
        + (
            attempt
            * 10_000
        )
    )


# ==========================================================================
# SHOT CONTEXT
# ==========================================================================

def _get_scene_context(scene):
    if not isinstance(
        scene,
        dict,
    ):
        return {}

    return {
        "emotional_tone": _clean_text(
            scene.get(
                "emotional_tone",
                "",
            ),
            100,
        ),

        "visual_priority": _clean_text(
            scene.get(
                "visual_priority",
                "",
            ),
            100,
        ),

        "transition": _clean_text(
            scene.get(
                "transition",
                "",
            ),
            100,
        ),
    }


# ==========================================================================
# PROMPT COMPONENTS
# ==========================================================================

def _build_identity_block(script):
    identity = _get_visual_identity(
        script
    )

    style_lock = _get_style_lock(
        script
    )

    parts = []

    if identity["style"]:
        parts.append(
            f"Consistent production style: "
            f"{identity['style']}."
        )

    if identity["palette"]:
        parts.append(
            f"Consistent color palette: "
            f"{identity['palette']}."
        )

    if identity["mood_arc"]:
        parts.append(
            f"Overall mood progression: "
            f"{identity['mood_arc']}."
        )

    if style_lock:
        parts.append(
            f"Global style lock: "
            f"{style_lock}."
        )

    return " ".join(
        parts
    )


def _build_subject_block(
    script,
    semantic_prompt,
):
    """
    Continuity subjects are only constraints when they are
    relevant to the current semantic shot.

    This prevents Gemini from accidentally creating the
    same person in every scene.
    """

    continuity = _get_visual_continuity(
        script
    )

    subjects = continuity[
        "subjects"
    ]

    if not subjects:
        return ""

    semantic_lower = semantic_prompt.lower()

    relevant = []

    for subject in subjects:

        name = subject[
            "name"
        ].lower()

        appearance = subject.get(
            "appearance",
            "",
        ).lower()

        name_tokens = [
            token
            for token in name.split()
            if len(token) >= 4
        ]

        appearance_tokens = [
            token
            for token in appearance.split()
            if len(token) >= 6
        ]

        if (
            name in semantic_lower
            or any(
                token in semantic_lower
                for token in name_tokens
            )
            or any(
                token in semantic_lower
                for token in appearance_tokens
            )
        ):
            relevant.append(
                subject
            )

    if not relevant:
        return (
            "Recurring subjects exist in the story, "
            "but do not add them unless the main visual "
            "description requires them."
        )

    parts = [
        "Continuity for subjects visible in this shot:"
    ]

    for subject in relevant:

        parts.append(
            (
                f"{subject['name']}: "
                f"{subject['appearance']}. "
                f"{subject['continuity']}."
            )
        )

    return " ".join(
        parts
    )


def _build_object_block(
    script,
    semantic_prompt,
):
    continuity = _get_visual_continuity(
        script
    )

    objects = continuity[
        "objects"
    ]

    if not objects:
        return ""

    semantic_lower = semantic_prompt.lower()

    relevant = []

    for item in objects:

        tokens = [
            token
            for token in item.lower().split()
            if len(token) >= 4
        ]

        if (
            item.lower()
            in semantic_lower
            or any(
                token in semantic_lower
                for token in tokens
            )
        ):
            relevant.append(
                item
            )

    if not relevant:
        return (
            "Keep recurring objects consistent "
            "whenever they are visible; do not introduce "
            "them unless the visual description calls for them."
        )

    return (
        "Recurring object continuity: "
        + "; ".join(relevant)
        + ". Keep their shape, proportions "
        "and appearance consistent."
    )


def _build_environment_block(script):
    continuity = _get_visual_continuity(
        script
    )

    environment = continuity[
        "environment"
    ]

    if not environment:
        return ""

    return (
        "Recurring environment: "
        + environment
        + ". Maintain the same environmental "
        "identity whenever visible."
    )


def _build_rules_block(script):
    continuity = _get_visual_continuity(
        script
    )

    rules = continuity[
        "rules"
    ]

    if not rules:
        return ""

    return (
        "Continuity rules: "
        + "; ".join(rules)
        + "."
    )


def _build_visual_metadata_block(
    visual,
):
    """
    These fields were present in generate_script.py
    but were previously ignored by the image generator.

    They now influence image generation.
    """

    parts = []

    image_style = _clean_text(
        visual.get(
            "image_style",
            "",
        ),
        120,
    )

    lighting = _clean_text(
        visual.get(
            "lighting",
            "",
        ),
        250,
    )

    palette = _clean_text(
        visual.get(
            "color_palette",
            "",
        ),
        250,
    )

    if image_style:
        parts.append(
            f"Rendering approach: "
            f"{image_style}."
        )

    if lighting:
        parts.append(
            f"Lighting: "
            f"{lighting}."
        )

    if palette:
        parts.append(
            f"Shot color treatment: "
            f"{palette}."
        )

    return " ".join(
        parts
    )


def _build_previous_shot_context(
    scene,
    visual_index,
):
    """
    Shot 2 should belong to the same moment but
    should not simply duplicate Shot 1.
    """

    if visual_index <= 1:
        return ""

    visuals = scene.get(
        "visuals",
        [],
    )

    if not isinstance(
        visuals,
        list,
    ):
        return ""

    if not visuals:
        return ""

    previous = visuals[0]

    if not isinstance(
        previous,
        dict,
    ):
        return ""

    previous_prompt = _clean_prompt(
        previous.get(
            "image_prompt",
            "",
        )
    )

    if not previous_prompt:
        return ""

    previous_prompt = previous_prompt[
        :500
    ]

    return (
        "This is shot 2 of the same scene. "
        "Preserve continuity with shot 1, but do not "
        "duplicate its composition. Change the viewpoint, "
        "framing, visible detail, action or revealed information. "
        f"Shot 1 context: {previous_prompt}"
    )


# ==========================================================================
# BUILD IMAGE PROMPT
# ==========================================================================

def build_prompt(
    scene,
    visual,
    script=None,
    scene_index=1,
    visual_index=1,
):
    """
    Build the final Pollinations prompt.

    Gemini's image_prompt remains the primary semantic
    description.

    Production metadata is added around it.
    """

    if not isinstance(
        visual,
        dict,
    ):
        raise RuntimeError(
            f"Scene {scene_index} "
            f"visual {visual_index} is invalid."
        )

    semantic_prompt = _clean_prompt(
        visual.get(
            "image_prompt",
            "",
        )
    )

    if not semantic_prompt:

        raise RuntimeError(
            f"Scene {scene_index} "
            f"visual {visual_index} "
            "has an empty image_prompt."
        )

    if not isinstance(
        script,
        dict,
    ):
        script = {}

    parts = [
        semantic_prompt
    ]

    identity_block = _build_identity_block(
        script
    )

    if identity_block:
        parts.append(
            identity_block
        )

    subject_block = _build_subject_block(
        script,
        semantic_prompt,
    )

    if subject_block:
        parts.append(
            subject_block
        )

    object_block = _build_object_block(
        script,
        semantic_prompt,
    )

    if object_block:
        parts.append(
            object_block
        )

    environment_block = _build_environment_block(
        script
    )

    if environment_block:
        parts.append(
            environment_block
        )

    rules_block = _build_rules_block(
        script
    )

    if rules_block:
        parts.append(
            rules_block
        )

    metadata_block = _build_visual_metadata_block(
        visual
    )

    if metadata_block:
        parts.append(
            metadata_block
        )

    previous_shot_block = _build_previous_shot_context(
        scene,
        visual_index,
    )

    if previous_shot_block:
        parts.append(
            previous_shot_block
        )

    scene_context = _get_scene_context(
        scene
    )

    if scene_context.get(
        "emotional_tone"
    ):

        parts.append(
            (
                "Scene emotional tone: "
                f"{scene_context['emotional_tone']}."
            )
        )

    if scene_context.get(
        "visual_priority"
    ):

        parts.append(
            (
                "Visual priority: "
                f"{scene_context['visual_priority']}."
            )
        )

    if visual_index == 1:

        parts.append(
            "Establish the visual moment clearly."
        )

    else:

        parts.append(
            "Advance the visual story with a clearly "
            "different shot that reveals or demonstrates "
            "something new."
        )

    parts.append(
        "Visible content only. No written words, labels, "
        "captions, subtitles, logos, watermarks or "
        "interface elements."
    )

    final_prompt = _clean_prompt(
        " ".join(parts)
    )

    if len(
        final_prompt
    ) > MAX_PROMPT_LENGTH:

        final_prompt = final_prompt[
            :MAX_PROMPT_LENGTH
        ]

        final_prompt = final_prompt.rsplit(
            " ",
            1,
        )[0]

    return final_prompt


# ==========================================================================
# IMAGE URL
# ==========================================================================

def _build_image_url(
    prompt,
    width,
    height,
    seed,
):
    encoded_prompt = urllib.parse.quote(
        prompt,
        safe="",
    )

    return (
        BASE_URL
        + encoded_prompt
        + f"?model={MODEL_NAME}"
        + f"&width={int(width)}"
        + f"&height={int(height)}"
        + f"&seed={int(seed)}"
        + "&enhance=true"
        + "&nologo=true"
    )


# ==========================================================================
# HTTP RESPONSE VALIDATION
# ==========================================================================

def _validate_image_response(
    response,
):
    if response is None:

        raise RuntimeError(
            "Empty HTTP response."
        )

    if response.status_code != 200:

        preview = (
            response.text[:300]
            if response.text
            else ""
        )

        raise RuntimeError(
            f"HTTP {response.status_code}: "
            f"{preview}"
        )

    content = response.content

    if not content:

        raise RuntimeError(
            "Image response was empty."
        )

    if len(content) < MIN_IMAGE_BYTES:

        raise RuntimeError(
            "Image response is suspiciously small."
        )

    content_type = (
        response.headers.get(
            "Content-Type",
            "",
        )
        .lower()
    )

    image_signatures = (
        b"\x89PNG",
        b"\xff\xd8\xff",
        b"RIFF",
    )

    has_image_content_type = (
        "image"
        in content_type
    )

    has_image_signature = any(
        content.startswith(
            signature
        )
        for signature in image_signatures
    )

    if (
        not has_image_content_type
        and
        not has_image_signature
    ):

        preview = content[:300]

        try:

            preview = preview.decode(
                "utf-8",
                errors="ignore",
            )

        except Exception:

            preview = "<binary response>"

        raise RuntimeError(
            "Server returned a non-image response: "
            f"{preview}"
        )

    return content


# ==========================================================================
# PIL IMAGE VALIDATION
# ==========================================================================

def _validate_with_pillow(
    content,
    expected_width,
    expected_height,
):
    if Image is None:
        return content

    try:

        image = Image.open(
            BytesIO(content)
        )

        image.verify()

        image = Image.open(
            BytesIO(content)
        )

        actual_width, actual_height = (
            image.size
        )

        if (
            actual_width <= 0
            or
            actual_height <= 0
        ):

            raise RuntimeError(
                "Generated image has invalid dimensions."
            )

        return content

    except Exception as error:

        raise RuntimeError(
            "Pillow could not validate generated image: "
            f"{error}"
        )


# ==========================================================================
# IMAGE REQUEST
# ==========================================================================

def generate_image(
    prompt,
    width,
    height,
    seed,
):
    prompt = _clean_prompt(
        prompt
    )

    if not prompt:

        raise RuntimeError(
            "Cannot generate an image "
            "with an empty prompt."
        )

    last_error = None

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    try:

        for attempt in range(
            MAX_RETRIES
        ):

            attempt_seed = _get_retry_seed(
                seed,
                attempt,
            )

            url = _build_image_url(
                prompt,
                width,
                height,
                attempt_seed,
            )

            print("=" * 80)
            print(
                "IMAGE GENERATION REQUEST"
            )
            print("=" * 80)

            print(
                f"Attempt: "
                f"{attempt + 1}/{MAX_RETRIES}"
            )

            print(
                f"Seed: "
                f"{attempt_seed}"
            )

            print(
                f"Size: "
                f"{width}x{height}"
            )

            print(
                f"Prompt length: "
                f"{len(prompt)}"
            )

            print(
                f"Prompt: "
                f"{prompt}"
            )

            print("=" * 80)

            try:

                print(
                    f"🎨 Image attempt "
                    f"{attempt + 1}/{MAX_RETRIES}"
                )

                response = session.get(
                    url,
                    timeout=REQUEST_TIMEOUT,
                )

                print(
                    f"HTTP status: "
                    f"{response.status_code}"
                )

                content = _validate_image_response(
                    response
                )

                content = _validate_with_pillow(
                    content,
                    width,
                    height,
                )

                print(
                    f"Image bytes: "
                    f"{len(content):,}"
                )

                print(
                    "✅ Image generated successfully."
                )

                return content

            except Exception as error:

                last_error = error

                print(
                    f"❌ Image attempt "
                    f"{attempt + 1} failed:"
                )

                print(
                    f"{type(error).__name__}: "
                    f"{error}"
                )

                if (
                    attempt
                    <
                    MAX_RETRIES - 1
                ):

                    print(
                        f"⏳ Retrying in "
                        f"{RETRY_DELAY} seconds..."
                    )

                    time.sleep(
                        RETRY_DELAY
                    )

    finally:

        session.close()

    raise RuntimeError(
        "Failed to generate image after "
        f"{MAX_RETRIES} attempts: "
        f"{last_error}"
    )


# ==========================================================================
# SAVE / NORMALIZE IMAGE
# ==========================================================================

def _save_image(
    content,
    path,
    width,
    height,
):
    if not content:

        raise RuntimeError(
            "Cannot save empty image content."
        )

    output_dir = os.path.dirname(
        path
    )

    if output_dir:

        os.makedirs(
            output_dir,
            exist_ok=True,
        )

    if Image is not None:

        try:

            image = Image.open(
                BytesIO(content)
            )

            image.load()

            if image.mode not in (
                "RGB",
                "RGBA",
            ):

                image = image.convert(
                    "RGB"
                )

            if image.size != (
                int(width),
                int(height),
            ):

                image = image.resize(
                    (
                        int(width),
                        int(height),
                    ),
                    Image.Resampling.LANCZOS,
                )

            image.save(
                path,
                format="PNG",
                optimize=True,
            )

        except Exception as error:

            raise RuntimeError(
                "Failed to normalize image to PNG: "
                f"{error}"
            )

    else:

        with open(
            path,
            "wb",
        ) as file:

            file.write(
                content
            )

    if not os.path.exists(
        path
    ):

        raise RuntimeError(
            f"Image was not created: {path}"
        )

    size = os.path.getsize(
        path
    )

    if size < MIN_IMAGE_BYTES:

        try:

            os.remove(
                path
            )

        except Exception:

            pass

        raise RuntimeError(
            f"Generated image appears invalid: "
            f"{path}"
        )

    if Image is not None:

        try:

            with Image.open(
                path
            ) as image:

                if image.format != EXPECTED_FORMAT:

                    raise RuntimeError(
                        f"Expected PNG but got "
                        f"{image.format}."
                    )

                if image.size != (
                    int(width),
                    int(height),
                ):

                    raise RuntimeError(
                        "Final image dimensions are incorrect: "
                        f"{image.size} instead of "
                        f"{width}x{height}."
                    )

                image.verify()

        except Exception as error:

            raise RuntimeError(
                f"Final PNG validation failed: "
                f"{error}"
            )

    return path


# ==========================================================================
# IMAGE CONFIG
# ==========================================================================

def _get_image_dimensions(
    config,
):
    image_config = (
        config.get(
            "image",
            {},
        )
        if isinstance(
            config,
            dict,
        )
        else {}
    )

    if not isinstance(
        image_config,
        dict,
    ):

        image_config = {}

    width = _safe_int(
        image_config.get(
            "width",
            DEFAULT_WIDTH,
        ),
        DEFAULT_WIDTH,
    )

    height = _safe_int(
        image_config.get(
            "height",
            DEFAULT_HEIGHT,
        ),
        DEFAULT_HEIGHT,
    )

    if width <= 0:
        width = DEFAULT_WIDTH

    if height <= 0:
        height = DEFAULT_HEIGHT

    if width >= height:

        width, height = (
            height,
            width,
        )

    return width, height


# ==========================================================================
# SCRIPT STRUCTURE VALIDATION
# ==========================================================================

def _validate_script_structure(
    script,
):
    if not isinstance(
        script,
        dict,
    ):

        raise RuntimeError(
            "Script must be a dictionary."
        )

    scenes = script.get(
        "scene_plan",
        [],
    )

    if not isinstance(
        scenes,
        list,
    ):

        raise RuntimeError(
            "script.scene_plan must be a list."
        )

    if len(
        scenes
    ) != EXPECTED_SCENES:

        raise RuntimeError(
            f"Expected exactly "
            f"{EXPECTED_SCENES} scenes, "
            f"but found {len(scenes)}."
        )

    total_visuals = 0

    for scene_index, scene in enumerate(
        scenes,
        start=1,
    ):

        if not isinstance(
            scene,
            dict,
        ):

            raise RuntimeError(
                f"Scene {scene_index} "
                "is not an object."
            )

        scene_number = _safe_int(
            scene.get(
                "scene",
                scene_index,
            ),
            scene_index,
        )

        if scene_number != scene_index:

            raise RuntimeError(
                f"Scene {scene_index} has invalid "
                f"scene number: {scene_number}."
            )

        visuals = scene.get(
            "visuals",
            [],
        )

        if not isinstance(
            visuals,
            list,
        ):

            raise RuntimeError(
                f"Scene {scene_index} "
                "visuals must be a list."
            )

        if len(
            visuals
        ) != VISUALS_PER_SCENE:

            raise RuntimeError(
                f"Scene {scene_index} must contain "
                f"exactly {VISUALS_PER_SCENE} visuals, "
                f"but found {len(visuals)}."
            )

        for visual_index, visual in enumerate(
            visuals,
            start=1,
        ):

            if not isinstance(
                visual,
                dict,
            ):

                raise RuntimeError(
                    f"Scene {scene_index} "
                    f"visual {visual_index} "
                    "is invalid."
                )

            prompt = _clean_prompt(
                visual.get(
                    "image_prompt",
                    "",
                )
            )

            if not prompt:

                raise RuntimeError(
                    f"Scene {scene_index} "
                    f"visual {visual_index} "
                    "has an empty image_prompt."
                )

            total_visuals += 1

    if total_visuals != EXPECTED_TOTAL_IMAGES:

        raise RuntimeError(
            f"Expected exactly "
            f"{EXPECTED_TOTAL_IMAGES} visuals, "
            f"but found {total_visuals}."
        )

    return scenes


# ==========================================================================
# CONTINUITY VALIDATION
# ==========================================================================

def _validate_continuity_metadata(
    script,
):
    identity = _get_visual_identity(
        script
    )

    continuity = _get_visual_continuity(
        script
    )

    style_lock = _get_style_lock(
        script
    )

    print(
        "Visual identity:"
    )

    print(
        f"  Style: "
        f"{identity['style'] or 'not specified'}"
    )

    print(
        f"  Palette: "
        f"{identity['palette'] or 'not specified'}"
    )

    print(
        f"  Mood: "
        f"{identity['mood_arc'] or 'not specified'}"
    )

    print(
        f"  Style lock: "
        f"{style_lock or 'not specified'}"
    )

    print(
        "Visual continuity:"
    )

    print(
        f"  Recurring subjects: "
        f"{len(continuity['subjects'])}"
    )

    print(
        f"  Recurring objects: "
        f"{len(continuity['objects'])}"
    )

    print(
        f"  Environment: "
        f"{'yes' if continuity['environment'] else 'no'}"
    )

    print(
        f"  Continuity rules: "
        f"{len(continuity['rules'])}"
    )

    return True


# ==========================================================================
# GENERATE ALL VISUALS
# ==========================================================================

def generate_images(
    script,
    workdir,
    config,
):
    """
    Generate exactly 14 AI images.

    Return structure:

    [
        [
            scene_01_shot_01.png,
            scene_01_shot_02.png
        ],
        ...
        [
            scene_07_shot_01.png,
            scene_07_shot_02.png
        ]
    ]
    """

    os.makedirs(
        workdir,
        exist_ok=True,
    )

    # ----------------------------------------------------------------------
    # Validate before contacting provider.
    # ----------------------------------------------------------------------

    scenes = _validate_script_structure(
        script
    )

    _validate_continuity_metadata(
        script
    )

    # ----------------------------------------------------------------------
    # Dimensions
    # ----------------------------------------------------------------------

    width, height = _get_image_dimensions(
        config
    )

    # ----------------------------------------------------------------------
    # Seed
    # ----------------------------------------------------------------------

    base_seed = _get_base_seed(
        script
    )

    image_paths = []

    print("=" * 80)
    print(
        "🎨 GENERATING AI VISUALS"
    )
    print("=" * 80)

    print(
        f"Scenes: "
        f"{len(scenes)}"
    )

    print(
        f"Visuals per scene: "
        f"{VISUALS_PER_SCENE}"
    )

    print(
        f"Total images: "
        f"{EXPECTED_TOTAL_IMAGES}"
    )

    print(
        f"Resolution: "
        f"{width}x{height}"
    )

    print(
        f"Base seed: "
        f"{base_seed}"
    )

    print(
        "Provider: "
        "Pollinations AI"
    )

    print(
        f"Model: "
        f"{MODEL_NAME}"
    )

    print(
        "Continuity system: ENABLED"
    )

    print(
        "Style lock: ENABLED"
    )

    print(
        "Per-shot visual metadata: ENABLED"
    )

    print(
        "Portrait normalization: ENABLED"
    )

    print(
        "PNG validation: ENABLED"
    )

    print("=" * 80)

    # ----------------------------------------------------------------------
    # Scene generation
    # ----------------------------------------------------------------------

    for scene_index, scene in enumerate(
        scenes,
        start=1,
    ):

        visuals = scene[
            "visuals"
        ]

        scene_paths = []

        print("=" * 80)

        print(
            f"🎬 SCENE "
            f"{scene_index}/{EXPECTED_SCENES}"
        )

        print("=" * 80)

        for visual_index, visual in enumerate(
            visuals,
            start=1,
        ):

            prompt = build_prompt(
                scene,
                visual,
                script,
                scene_index,
                visual_index,
            )

            shot_seed = _get_shot_seed(
                base_seed,
                scene_index,
                visual_index,
            )

            print("=" * 80)

            print(
                f"🖼️ SHOT "
                f"{visual_index}/{VISUALS_PER_SCENE}"
            )

            print(
                f"Scene: "
                f"{scene_index}"
            )

            print(
                f"Seed: "
                f"{shot_seed}"
            )

            print(
                f"Style: "
                f"{visual.get('image_style', '')}"
            )

            print(
                f"Lighting: "
                f"{visual.get('lighting', '')}"
            )

            print(
                f"Color palette: "
                f"{visual.get('color_palette', '')}"
            )

            print(
                f"Visual impact: "
                f"{visual.get('visual_impact', '')}"
            )

            print(
                f"Prompt: "
                f"{prompt}"
            )

            print("=" * 80)

            # --------------------------------------------------------------
            # Generate
            # --------------------------------------------------------------

            image = generate_image(
                prompt,
                width,
                height,
                shot_seed,
            )

            # --------------------------------------------------------------
            # Save
            # --------------------------------------------------------------

            filename = os.path.join(
                workdir,
                (
                    f"scene_{scene_index:02d}"
                    f"_shot_{visual_index:02d}.png"
                ),
            )

            _save_image(
                image,
                filename,
                width,
                height,
            )

            scene_paths.append(
                filename
            )

            print(
                f"✅ Saved: "
                f"{filename}"
            )

            # --------------------------------------------------------------
            # Prevent burst requests.
            # --------------------------------------------------------------

            if not (
                scene_index == EXPECTED_SCENES
                and
                visual_index == VISUALS_PER_SCENE
            ):

                time.sleep(
                    BETWEEN_IMAGE_DELAY
                )

        image_paths.append(
            scene_paths
        )

    # ==========================================================================
    # FINAL VALIDATION
    # ==========================================================================

    total_images = sum(
        len(scene_paths)
        for scene_paths in image_paths
    )

    if total_images != EXPECTED_TOTAL_IMAGES:

        raise RuntimeError(
            f"Expected exactly "
            f"{EXPECTED_TOTAL_IMAGES} generated images, "
            f"but generated "
            f"{total_images}."
        )

    for scene_index, scene_paths in enumerate(
        image_paths,
        start=1,
    ):

        if len(
            scene_paths
        ) != VISUALS_PER_SCENE:

            raise RuntimeError(
                f"Scene {scene_index} "
                f"contains {len(scene_paths)} "
                f"images instead of "
                f"{VISUALS_PER_SCENE}."
            )

        for visual_index, path in enumerate(
            scene_paths,
            start=1,
        ):

            if not os.path.exists(
                path
            ):

                raise RuntimeError(
                    f"Missing generated image: "
                    f"Scene {scene_index}, "
                    f"Shot {visual_index}: "
                    f"{path}"
                )

            if os.path.getsize(
                path
            ) < MIN_IMAGE_BYTES:

                raise RuntimeError(
                    f"Generated image is too small: "
                    f"{path}"
                )

            if Image is not None:

                try:

                    with Image.open(
                        path
                    ) as image:

                        if image.format != EXPECTED_FORMAT:

                            raise RuntimeError(
                                f"Scene {scene_index} "
                                f"Shot {visual_index}: "
                                f"expected PNG, got "
                                f"{image.format}."
                            )

                        if image.size != (
                            width,
                            height,
                        ):

                            raise RuntimeError(
                                f"Scene {scene_index} "
                                f"Shot {visual_index}: "
                                f"expected "
                                f"{width}x{height}, "
                                f"got "
                                f"{image.size}."
                            )

                        image.verify()

                except Exception as error:

                    raise RuntimeError(
                        f"Final image validation failed "
                        f"for Scene {scene_index}, "
                        f"Shot {visual_index}: "
                        f"{error}"
                    )

    # ==========================================================================
    # SUMMARY
    # ==========================================================================

    print("=" * 80)

    print(
        "✅ VISUAL GENERATION COMPLETE"
    )

    print("=" * 80)

    print(
        f"Scenes: "
        f"{len(image_paths)}"
    )

    print(
        f"Images generated: "
        f"{total_images}"
    )

    print(
        f"Expected images: "
        f"{EXPECTED_TOTAL_IMAGES}"
    )

    print(
        f"Resolution: "
        f"{width}x{height}"
    )

    print(
        "Visual continuity: ENABLED"
    )

    print(
        "Style lock: APPLIED"
    )

    print(
        "Per-shot visual metadata: APPLIED"
    )

    print(
        "Recurring subject continuity: APPLIED"
    )

    print(
        "Environment continuity: APPLIED"
    )

    print(
        "PNG normalization: COMPLETE"
    )

    print(
        "Image validation: PASSED"
    )

    print("=" * 80)

    return image_paths


# ==========================================================================
# OPTIONAL SINGLE IMAGE HELPER
# ==========================================================================

def generate_single_image(
    prompt,
    workdir,
    filename="generated.png",
    width=DEFAULT_WIDTH,
    height=DEFAULT_HEIGHT,
    seed=None,
):
    """
    Generate one standalone image.
    """

    os.makedirs(
        workdir,
        exist_ok=True,
    )

    if seed is None:

        seed = int(
            time.time()
        )

    prompt = _clean_prompt(
        prompt
    )

    if not prompt:

        raise RuntimeError(
            "Cannot generate image "
            "with an empty prompt."
        )

    # ----------------------------------------------------------------------
    # Force portrait.
    # ----------------------------------------------------------------------

    if width >= height:

        width, height = (
            height,
            width,
        )

    image = generate_image(
        prompt,
        width,
        height,
        int(seed),
    )

    path = os.path.join(
        workdir,
        filename,
    )

    _save_image(
        image,
        path,
        width,
        height,
    )

    return path