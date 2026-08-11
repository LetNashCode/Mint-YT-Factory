"""
generate_images.py

Cinematic AI Visual Generator
Version 6.0

Designed for:
    generate_script.py v5.3+

Purpose:
    Convert Gemini scene visual plans into high-quality AI images.

Major improvements:
    - Uses scene.visuals[] instead of ignoring visual planning data
    - Uses global visual_identity from the script
    - No artificial prompt truncation
    - Strong cinematic prompt construction
    - Consistent visual identity across the entire video
    - Consistent seed family across scenes
    - Configurable Pollinations model
    - Supports current Pollinations API when API key is available
    - Legacy Pollinations endpoint fallback
    - Saves prompts for debugging
    - Preserves generate_images() interface
    - Generates exactly one primary image per scene
    - Existing assemble.py/main.py interface remains compatible
"""

import json
import os
import random
import time
import urllib.parse

import requests


# ==========================================================================
# SETTINGS
# ==========================================================================

DEFAULT_MODEL = "flux"

DEFAULT_WIDTH = 768
DEFAULT_HEIGHT = 1365

MAX_RETRIES = 5

RETRY_DELAY_SECONDS = 5

REQUEST_TIMEOUT_SECONDS = 180

# Current Pollinations unified API.
CURRENT_BASE_URL = "https://gen.pollinations.ai/image/"

# Legacy endpoint kept as fallback for existing projects.
LEGACY_BASE_URL = "https://image.pollinations.ai/prompt/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    )
}


# ==========================================================================
# GLOBAL VISUAL PHILOSOPHY
# ==========================================================================

GLOBAL_NEGATIVE_PROMPT = """
No text.
No typography.
No captions.
No subtitles.
No labels.
No arrows unless explicitly requested.
No UI.
No logos.
No brand marks.
No watermark.
No signature.
No border.
No frame.
No collage.
No split screen.
No poster design.
No infographic layout unless explicitly requested.
No generic stock-photo look.
No cheap cartoon look.
No plastic-looking toy appearance.
No oversaturated colors.
No excessive glow.
No distorted anatomy.
No duplicated objects.
No extra limbs.
No malformed hands.
No impossible geometry.
No random objects unrelated to the subject.
No visual clutter.
"""


CINEMATIC_BASE = """
Premium cinematic science documentary visual.

Photorealistic or physically plausible depending on the selected
visual style.

The image must look like a frame from a high-budget modern science
documentary, not a generic AI artwork.

Strong subject hierarchy.
One unmistakable visual idea.
Clear foreground, subject, and background separation.
Natural depth.
Controlled composition.
Professional cinematography.
Physically believable lighting.
Fine surface detail.
Realistic materials.
Subtle atmospheric depth.
High dynamic range.
Sharp primary subject.
Natural contrast.
Premium production quality.

Vertical 9:16 composition for YouTube Shorts.

The primary subject must be immediately understandable within
one second.

The subject should occupy approximately 55-80 percent of the
useful frame when appropriate.

Leave safe visual breathing room around important edges.

No text.
No labels.
No logos.
No watermark.
"""


# ==========================================================================
# HELPERS
# ==========================================================================

def _safe_string(value):
    if value is None:
        return ""

    return str(value).strip()


def _get_model(config):
    """
    Model selection priority:

    1. config.yaml image.model
    2. POLLINATIONS_IMAGE_MODEL environment variable
    3. DEFAULT_MODEL
    """

    try:
        configured = config.get(
            "image",
            {},
        ).get(
            "model"
        )

        if configured:
            return str(
                configured
            ).strip()

    except Exception:
        pass

    env_model = os.environ.get(
        "POLLINATIONS_IMAGE_MODEL"
    )

    if env_model:
        return env_model.strip()

    return DEFAULT_MODEL


def _get_dimensions(config):
    """
    Preserve existing config.yaml dimensions.
    """

    image_config = config.get(
        "image",
        {},
    )

    width = int(
        image_config.get(
            "width",
            DEFAULT_WIDTH,
        )
    )

    height = int(
        image_config.get(
            "height",
            DEFAULT_HEIGHT,
        )
    )

    return width, height


def _get_api_key():
    """
    Current Pollinations API uses a server-side API key.

    POLLINATIONS_API_KEY is preferred.

    The old pipeline did not require this variable, so the function
    returns None when it is unavailable and the legacy endpoint can
    still be attempted.
    """

    return (
        os.environ.get(
            "POLLINATIONS_API_KEY"
        )
        or os.environ.get(
            "POLLINATIONS_API_TOKEN"
        )
    )


def _get_style_lock(script):
    """
    Build a global visual identity instruction.

    This is intentionally stronger than the old style_lock because
    image generation should receive the same visual language for
    every scene.
    """

    identity = script.get(
        "visual_identity",
        {},
    )

    style = _safe_string(
        identity.get(
            "style"
        )
    )

    palette = _safe_string(
        identity.get(
            "palette"
        )
    )

    mood_arc = _safe_string(
        identity.get(
            "mood_arc"
        )
    )

    parts = []

    if style:
        parts.append(
            f"Overall visual style: {style}"
        )

    if palette:
        parts.append(
            f"Consistent color palette: {palette}"
        )

    if mood_arc:
        parts.append(
            f"Overall mood progression: {mood_arc}"
        )

    if not parts:
        return (
            "Use a premium cinematic science documentary "
            "visual identity consistently across the video."
        )

    return ". ".join(parts) + "."


def _visual_style_instruction(image_style):
    """
    Translate Gemini's image_style enum into a stronger image-generation
    instruction.
    """

    style = _safe_string(
        image_style
    ).lower()

    mapping = {

        "realistic_3d_render": """
Photorealistic high-end 3D scientific visualization.
Physically plausible materials.
Realistic volumetric depth.
Precise anatomical or mechanical detail where applicable.
Cinematic rendering rather than game-engine aesthetics.
""",

        "scientific_illustration": """
Premium scientific visualization.
Accurate forms and proportions.
Clear visual explanation.
Sophisticated museum-quality scientific artwork.
Realistic depth and lighting.
Not childish.
Not cartoon-like.
""",

        "cinematic_photograph": """
High-end cinematic documentary photography.
Natural realistic textures.
Real optical depth of field.
Professional lens characteristics.
Subtle filmic contrast.
Authentic environmental detail.
""",

        "macro_photography": """
Extreme macro documentary photography.
Microscopic surface detail.
Very shallow depth of field.
Natural optical falloff.
Realistic textures and tiny structures.
""",

        "infographic_diagram": """
Premium scientific visualization with restrained explanatory graphics.
Clean spatial hierarchy.
Minimal visual elements.
Only use diagrammatic elements when explicitly requested.
No text or labels.
""",
    }

    return mapping.get(
        style,
        """
Premium photorealistic cinematic science documentary visualization.
""",
    ).strip()


def _camera_instruction(camera):
    mapping = {

        "close_up": """
Close-up cinematic framing.
Subject dominates the frame.
Reveal important surface detail.
Strong foreground separation.
""",

        "medium": """
Medium cinematic framing.
Subject clearly visible with enough surrounding context
to explain the phenomenon.
""",

        "wide": """
Wide cinematic establishing composition.
Show the environment and scale of the phenomenon.
Maintain a clearly dominant subject.
""",

        "macro": """
Extreme macro framing.
Reveal fine physical detail invisible to the naked eye.
""",

        "top_down": """
Professional overhead documentary composition.
Clean geometry.
Strong visual organization.
""",

        "side": """
Side-profile cinematic composition.
Strong depth and directional visual flow.
""",

        "aerial": """
Cinematic aerial perspective.
Clear sense of scale and environment.
""",

        "orbit": """
Dynamic orbital camera perspective.
Subject remains dominant while surrounding environment
creates dimensional depth.
""",
    }

    return mapping.get(
        _safe_string(camera).lower(),
        """
Cinematic medium framing with strong subject separation.
""",
    ).strip()


def _animation_composition_instruction(animation):
    """
    Animation does not actually animate the generated image.

    Instead, use it to choose a composition that works well with the
    later Ken Burns / motion stage.
    """

    mapping = {

        "zoom_in": """
Compose with strong central subject detail and layered depth.
Leave enough surrounding space for a later cinematic push-in.
""",

        "zoom_out": """
Compose with the subject clearly readable while preserving
meaningful environmental space for a later pull-back.
""",

        "pan_left": """
Create strong horizontal visual flow from right toward left.
Leave visual space in the direction of movement.
""",

        "pan_right": """
Create strong horizontal visual flow from left toward right.
Leave visual space in the direction of movement.
""",

        "rotate": """
Use a visually balanced composition with circular or radial depth
that can support a subtle rotation effect.
""",

        "parallax": """
Use clearly separated foreground, middle ground, and background
layers to create strong parallax potential.
""",

        "highlight": """
Create a clearly identifiable focal subject with surrounding
context that can support a later visual highlight.
""",

        "hold": """
Create an exceptionally strong standalone composition.
The image must remain visually interesting even without movement.
""",
    }

    return mapping.get(
        _safe_string(animation).lower(),
        """
Create strong layered depth suitable for subtle cinematic motion.
""",
    ).strip()


def _motion_instruction(motion_intensity):
    mapping = {

        "low": """
Keep composition calm and stable.
Use subtle depth rather than extreme perspective.
""",

        "medium": """
Use moderate depth and directional composition.
Suitable for smooth cinematic camera movement.
""",

        "high": """
Use dramatic depth, strong perspective and clear foreground/background
separation suitable for energetic Shorts pacing.
""",
    }

    return mapping.get(
        _safe_string(
            motion_intensity
        ).lower(),
        "",
    ).strip()


def _complexity_instruction(complexity):
    mapping = {

        "simple": """
Keep the scene visually clean.
One dominant subject.
Minimal background distractions.
""",

        "moderate": """
Use enough environmental detail to communicate the concept,
while maintaining one dominant focal point.
""",

        "complex": """
Use rich environmental and scientific detail,
but preserve a clear primary subject and readable composition.
""",
    }

    return mapping.get(
        _safe_string(
            complexity
        ).lower(),
        "",
    ).strip()


def _build_visual_prompt(
    script,
    scene,
    visual,
    scene_index,
):
    """
    Build the final image prompt.

    Gemini's image_prompt remains the creative concept.

    This function adds the production-level visual direction.
    """

    image_prompt = _safe_string(
        visual.get(
            "image_prompt"
        )
    )

    image_style = _safe_string(
        visual.get(
            "image_style"
        )
    )

    lighting = _safe_string(
        visual.get(
            "lighting"
        )
    )

    palette = _safe_string(
        visual.get(
            "color_palette"
        )
    )

    camera = _safe_string(
        visual.get(
            "camera"
        )
    )

    animation = _safe_string(
        visual.get(
            "animation"
        )
    )

    motion_intensity = _safe_string(
        visual.get(
            "motion_intensity"
        )
    )

    complexity = _safe_string(
        visual.get(
            "visual_complexity"
        )
    )

    overlay = visual.get(
        "overlay",
        {},
    )

    overlay_type = _safe_string(
        overlay.get(
            "type"
        )
    )

    overlay_description = _safe_string(
        overlay.get(
            "description"
        )
    )

    scene_purpose = _safe_string(
        scene.get(
            "purpose"
        )
    )

    emotional_tone = _safe_string(
        scene.get(
            "emotional_tone"
        )
    )

    # ------------------------------------------------------------------
    # SUBJECT / ACTION
    # ------------------------------------------------------------------

    parts = [

        CINEMATIC_BASE,

        f"""
SCENE PURPOSE:
{scene_purpose}

EMOTIONAL TONE:
{emotional_tone}

PRIMARY VISUAL CONCEPT:
{image_prompt}
""",

        _get_style_lock(
            script
        ),

        _visual_style_instruction(
            image_style
        ),

        _camera_instruction(
            camera
        ),

        _animation_composition_instruction(
            animation
        ),

        _motion_instruction(
            motion_intensity
        ),

        _complexity_instruction(
            complexity
        ),
    ]

    # ------------------------------------------------------------------
    # LIGHTING
    # ------------------------------------------------------------------

    if lighting:

        parts.append(
            f"""
LIGHTING DIRECTION:
{lighting}

Lighting must feel physically plausible and cinematic.
Do not flatten the image with uniform illumination.
"""
        )

    # ------------------------------------------------------------------
    # COLOR
    # ------------------------------------------------------------------

    if palette:

        parts.append(
            f"""
COLOR DIRECTION:
{palette}

Maintain this palette consistently with the other scenes.
Do not introduce unrelated dominant colors.
"""
        )

    # ------------------------------------------------------------------
    # OVERLAY
    # ------------------------------------------------------------------

    if overlay_type and overlay_type != "none":

        parts.append(
            f"""
VISUAL OVERLAY CONCEPT:
{overlay_type}

{overlay_description}

Keep the visual clean and premium.
Do not generate written text.
"""
        )

    # ------------------------------------------------------------------
    # COMPOSITION
    # ------------------------------------------------------------------

    parts.append(
        """
COMPOSITION:

Create one clear visual idea.

The viewer should understand the subject immediately.

Use a strong foreground-to-background depth relationship.

Avoid placing important subject details against visually confusing
background elements.

Use cinematic negative space where appropriate.

The image must look intentional and professionally art-directed.

Do not create a generic centered stock image unless centered framing
is clearly the strongest composition for the subject.

Vertical 9:16.
"""
    )

    # ------------------------------------------------------------------
    # DOCUMENTARY QUALITY
    # ------------------------------------------------------------------

    parts.append(
        """
QUALITY TARGET:

High-end modern science documentary.
Premium streaming-documentary production value.
Physically believable details.
Natural material response.
Realistic textures.
Subtle atmospheric depth.
Controlled highlights.
Natural shadows.
Sharp primary subject.
No plastic AI appearance.

The image should feel like it was deliberately photographed or
rendered by a professional visual-effects and documentary team.
"""
    )

    # ------------------------------------------------------------------
    # NEGATIVE
    # ------------------------------------------------------------------

    parts.append(
        GLOBAL_NEGATIVE_PROMPT
    )

    final_prompt = "\n\n".join(
        part.strip()
        for part in parts
        if part and part.strip()
    )

    return final_prompt.strip()


# ==========================================================================
# REQUEST URL
# ==========================================================================

def _build_request(
    prompt,
    model,
    width,
    height,
    seed,
):
    """
    Build request for the current Pollinations API when a key exists.

    The current API documents:
        /image/{prompt}
        model
        width
        height
        seed
        quality

    The legacy endpoint remains available as fallback for compatibility.
    """

    api_key = _get_api_key()

    if api_key:

        base_url = CURRENT_BASE_URL

        headers = dict(
            HEADERS
        )

        headers[
            "Authorization"
        ] = f"Bearer {api_key}"

        params = {
            "model": model,
            "width": width,
            "height": height,
            "seed": seed,
            "quality": "high",
        }

        return (
            base_url,
            params,
            headers,
        )

    # ------------------------------------------------------------------
    # LEGACY FALLBACK
    # ------------------------------------------------------------------

    base_url = LEGACY_BASE_URL

    headers = dict(
        HEADERS
    )

    params = {
        "model": model,
        "width": width,
        "height": height,
        "seed": seed,
        "nologo": "true",
    }

    return (
        base_url,
        params,
        headers,
    )


# ==========================================================================
# IMAGE GENERATION
# ==========================================================================

def generate_image(
    prompt,
    width,
    height,
    seed,
    model=DEFAULT_MODEL,
):
    """
    Generate one image from Pollinations.

    Returns:
        bytes
    """

    base_url, params, headers = _build_request(
        prompt,
        model,
        width,
        height,
        seed,
    )

    encoded_prompt = urllib.parse.quote(
        prompt,
        safe="",
    )

    url = (
        base_url
        + encoded_prompt
    )

    print("=" * 80)
    print("IMAGE MODEL")
    print(model)
    print("=" * 80)

    print("IMAGE SIZE")
    print(
        f"{width}x{height}"
    )

    print("=" * 80)

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        try:

            print(
                f"🎨 Image generation attempt "
                f"{attempt}/{MAX_RETRIES}"
            )

            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            print(
                "STATUS:",
                response.status_code,
            )

            if response.status_code != 200:

                print(
                    response.text[:1000]
                )

            response.raise_for_status()

            content_type = (
                response.headers.get(
                    "Content-Type",
                    "",
                )
                .lower()
            )

            if not response.content:

                raise RuntimeError(
                    "Pollinations returned an empty response."
                )

            # Some services can return an error page with HTTP 200.
            if (
                "image" not in content_type
                and not response.content.startswith(
                    b"\x89PNG"
                )
                and not response.content.startswith(
                    b"\xff\xd8"
                )
            ):

                preview = response.text[:500]

                raise RuntimeError(
                    "Pollinations did not return an image. "
                    f"Content-Type={content_type}; "
                    f"Response={preview}"
                )

            print(
                "✅ Image generated successfully."
            )

            return response.content

        except Exception as e:

            print(
                f"❌ Image attempt {attempt} failed:"
            )

            print(
                f"{type(e).__name__}: {e}"
            )

            if attempt < MAX_RETRIES:

                print(
                    f"Waiting {RETRY_DELAY_SECONDS}s..."
                )

                time.sleep(
                    RETRY_DELAY_SECONDS
                )

    raise RuntimeError(
        "Pollinations failed to generate the image "
        f"after {MAX_RETRIES} attempts."
    )


# ==========================================================================
# SAVE PROMPT
# ==========================================================================

def _save_prompt(
    path,
    prompt,
    metadata,
):
    """
    Save the exact prompt used for the image.

    This is extremely useful when comparing image quality.
    """

    prompt_path = (
        os.path.splitext(
            path
        )[0]
        + "_prompt.txt"
    )

    with open(
        prompt_path,
        "w",
        encoding="utf-8",
    ) as f:

        f.write(
            prompt
        )

        f.write(
            "\n\n"
            + "=" * 80
            + "\nMETADATA\n"
            + "=" * 80
            + "\n"
        )

        json.dump(
            metadata,
            f,
            indent=2,
            ensure_ascii=False,
        )

    return prompt_path


# ==========================================================================
# PRIMARY VISUAL SELECTION
# ==========================================================================

def _select_primary_visual(
    scene,
):
    """
    A scene can contain 1-2 visual segments.

    Existing assembly expects one image per scene, so we select the
    strongest visual concept as the primary image.

    Priority:
        1. visual_impact
        2. hero scene preference
        3. first visual
    """

    visuals = scene.get(
        "visuals",
        [],
    )

    if not visuals:

        return None

    def score(visual):

        try:

            impact = float(
                visual.get(
                    "visual_impact",
                    0,
                )
            )

        except Exception:

            impact = 0

        score_value = impact * 10

        if (
            visual.get(
                "needs_regeneration",
                False,
            )
        ):

            score_value -= 5

        return score_value

    return max(
        visuals,
        key=score,
    )


# ==========================================================================
# GENERATE ALL SCENE IMAGES
# ==========================================================================

def generate_images(
    script,
    workdir,
    config,
):
    """
    Generate one primary AI image for every scene.

    IMPORTANT:
        This preserves the existing return format:

            [
                "scene_01.png",
                "scene_02.png",
                ...
            ]

    Therefore existing main.py and assemble.py should continue
    working without modification.
    """

    os.makedirs(
        workdir,
        exist_ok=True,
    )

    width, height = _get_dimensions(
        config
    )

    model = _get_model(
        config
    )

    scenes = script.get(
        "scene_plan",
        [],
    )

    if not scenes:

        raise RuntimeError(
            "Script contains no scene_plan."
        )

    # ------------------------------------------------------------------
    # VIDEO SEED
    # ------------------------------------------------------------------

    image_generation = script.get(
        "image_generation",
        {},
    )

    configured_seed = image_generation.get(
        "seed"
    )

    try:

        base_seed = int(
            configured_seed
        )

    except Exception:

        base_seed = random.randint(
            1,
            2_147_483_647,
        )

    print("=" * 80)
    print("🎨 CINEMATIC AI VISUAL GENERATION")
    print("=" * 80)

    print(
        f"Model: {model}"
    )

    print(
        f"Resolution: {width}x{height}"
    )

    print(
        f"Base seed: {base_seed}"
    )

    print(
        f"Scenes: {len(scenes)}"
    )

    print("=" * 80)

    image_paths = []

    # ------------------------------------------------------------------
    # GENERATE EACH SCENE
    # ------------------------------------------------------------------

    for scene_index, scene in enumerate(
        scenes,
        start=1,
    ):

        visual = _select_primary_visual(
            scene
        )

        if visual is None:

            raise RuntimeError(
                f"Scene {scene_index} contains no visuals."
            )

        # --------------------------------------------------------------
        # STABLE SCENE SEED
        # --------------------------------------------------------------

        scene_seed = (
            base_seed
            + (scene_index * 1009)
        )

        # --------------------------------------------------------------
        # BUILD PROMPT
        # --------------------------------------------------------------

        prompt = _build_visual_prompt(
            script=script,
            scene=scene,
            visual=visual,
            scene_index=scene_index,
        )

        print("=" * 80)
        print(
            f"SCENE {scene_index}/{len(scenes)}"
        )
        print("=" * 80)

        print(
            "Visual segment:",
            visual.get(
                "segment"
            ),
        )

        print(
            "Visual style:",
            visual.get(
                "image_style"
            ),
        )

        print(
            "Camera:",
            visual.get(
                "camera"
            ),
        )

        print(
            "Visual impact:",
            visual.get(
                "visual_impact"
            ),
        )

        print(
            "Seed:",
            scene_seed,
        )

        print("=" * 80)
        print("FINAL IMAGE PROMPT")
        print("=" * 80)
        print(prompt)
        print("=" * 80)

        # --------------------------------------------------------------
        # OUTPUT
        # --------------------------------------------------------------

        filename = os.path.join(
            workdir,
            f"scene_{scene_index:02d}.png",
        )

        # --------------------------------------------------------------
        # GENERATE
        # --------------------------------------------------------------

        image = generate_image(
            prompt=prompt,
            width=width,
            height=height,
            seed=scene_seed,
            model=model,
        )

        # --------------------------------------------------------------
        # SAVE IMAGE
        # --------------------------------------------------------------

        with open(
            filename,
            "wb",
        ) as f:

            f.write(
                image
            )

        # --------------------------------------------------------------
        # SAVE DEBUG PROMPT
        # --------------------------------------------------------------

        metadata = {

            "scene": scene_index,

            "model": model,

            "width": width,

            "height": height,

            "seed": scene_seed,

            "purpose": scene.get(
                "purpose"
            ),

            "emotional_tone": scene.get(
                "emotional_tone"
            ),

            "visual_segment": visual.get(
                "segment"
            ),

            "image_style": visual.get(
                "image_style"
            ),

            "camera": visual.get(
                "camera"
            ),

            "animation": visual.get(
                "animation"
            ),

            "motion_intensity": visual.get(
                "motion_intensity"
            ),

            "visual_complexity": visual.get(
                "visual_complexity"
            ),

            "visual_impact": visual.get(
                "visual_impact"
            ),
        }

        prompt_path = _save_prompt(
            filename,
            prompt,
            metadata,
        )

        print(
            f"✅ Saved image -> {filename}"
        )

        print(
            f"📝 Saved prompt -> {prompt_path}"
        )

        image_paths.append(
            filename
        )

        # Small delay to avoid hammering the endpoint.
        if scene_index < len(scenes):

            time.sleep(
                2
            )

    print("=" * 80)
    print("✅ ALL CINEMATIC VISUALS GENERATED")
    print("=" * 80)

    for path in image_paths:

        print(
            path
        )

    print("=" * 80)

    return image_paths


# ==========================================================================
# MANUAL TEST
# ==========================================================================

if __name__ == "__main__":

    print(
        "generate_images.py is designed to be called by main.py."
    )

    print(
        "Use main.py or import generate_images()."
    )