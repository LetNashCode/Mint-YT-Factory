"""
generate_images.py

AI Visual Generation for Mint-YT-Factory
Version 6.0

Purpose:
Generate high-quality AI visuals from the storyboard produced by
generate_script.py.

Major improvements:
- Generates every visual segment from scene["visuals"]
- Uses detailed scene-level image prompts
- Preserves visual identity across the entire Short
- Uses controlled seed variation
- Better prompt construction
- No arbitrary 700-character prompt truncation
- Automatic retries
- AI artifact prevention
- Stronger cinematic composition
- Compatible with the existing main.py pipeline
"""

import os
import time
import urllib.parse
import requests


# ==========================================================================
# CONFIGURATION
# ==========================================================================

BASE_URL = "https://image.pollinations.ai/prompt/"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

MAX_RETRIES = 5

RETRY_DELAY = 5

DEFAULT_WIDTH = 768
DEFAULT_HEIGHT = 1365


# ==========================================================================
# GLOBAL VISUAL STYLE
# ==========================================================================

GLOBAL_STYLE = """
Premium cinematic educational documentary visualization.

Highly realistic.
Scientifically grounded.
Professional documentary production quality.

Natural physical proportions.
Realistic materials.
Realistic textures.
Realistic depth.
Realistic lighting.

Strong subject separation.
Clear visual hierarchy.
One dominant subject.
One clear visual idea.

Cinematic composition.
Natural depth of field.
Subtle atmospheric depth.
Sharp primary subject.
Controlled background detail.

Designed specifically for vertical 9:16 YouTube Shorts.

No text.
No typography.
No captions.
No labels.
No diagrams containing words.
No logos.
No watermark.

Avoid generic AI-art appearance.
Avoid fantasy aesthetics.
Avoid cartoon aesthetics.
Avoid excessive neon.
Avoid excessive glowing objects.
Avoid unnecessary particles.
Avoid duplicated objects.
Avoid extra limbs.
Avoid distorted anatomy.
Avoid malformed hands.
Avoid floating objects.
Avoid impossible geometry.
Avoid clutter.
"""


# ==========================================================================
# VISUAL STYLE MAPPING
# ==========================================================================

IMAGE_STYLE_MAP = {

    "realistic_3d_render":
        """
        Photorealistic cinematic 3D scientific reconstruction.
        Physically realistic surfaces and materials.
        High-end documentary visualization.
        """,

    "scientific_illustration":
        """
        Premium scientific visualization.
        Anatomically and physically accurate.
        Clean realistic scientific artwork.
        """,

    "cinematic_photograph":
        """
        Cinematic documentary photograph.
        Natural photographic lighting.
        Realistic lens characteristics.
        Authentic environmental detail.
        """,

    "macro_photography":
        """
        Extreme macro documentary photography.
        Highly detailed microscopic surface texture.
        Shallow realistic depth of field.
        """,

    "infographic_diagram":
        """
        Clean scientific visualization.
        Minimal diagrammatic composition.
        No written labels or text.
        Physically accurate visual relationships.
        """,
}


# ==========================================================================
# CAMERA MAPPING
# ==========================================================================

CAMERA_MAP = {

    "close_up":
        "tight close-up framing with the subject filling most of the frame",

    "medium":
        "medium cinematic framing showing the subject and immediate environment",

    "wide":
        "wide cinematic composition showing the subject within its environment",

    "macro":
        "extreme macro framing showing fine physical detail",

    "top_down":
        "precise top-down cinematic composition",

    "side":
        "cinematic side-view composition",

    "aerial":
        "high aerial documentary perspective",

    "orbit":
        "cinematic three-quarter orbital perspective",
}


# ==========================================================================
# LIGHTING MAPPING
# ==========================================================================

DEFAULT_LIGHTING = (
    "soft cinematic key light, realistic natural fill light, "
    "subtle rim lighting, physically plausible shadows, "
    "high dynamic range"
)


# ==========================================================================
# PROMPT CLEANING
# ==========================================================================

def _clean_prompt(text):
    """
    Remove accidental formatting while preserving useful detail.
    """

    if not text:
        return ""

    text = str(text)

    text = text.replace(
        "\n",
        " ",
    )

    text = text.replace(
        "```",
        "",
    )

    text = " ".join(
        text.split()
    )

    return text.strip()


# ==========================================================================
# BUILD VISUAL PROMPT
# ==========================================================================

def build_prompt(
    scene,
    visual,
    script=None,
):
    """
    Build a strong production prompt from the storyboard.

    Priority:
        visual.image_prompt
        visual technical information
        scene context
        global style
    """

    parts = []

    # ----------------------------------------------------------------------
    # PRIMARY IMAGE DESCRIPTION
    # ----------------------------------------------------------------------

    image_prompt = _clean_prompt(
        visual.get(
            "image_prompt",
            "",
        )
    )

    if image_prompt:

        parts.append(
            image_prompt
        )

    # ----------------------------------------------------------------------
    # VISUAL STYLE
    # ----------------------------------------------------------------------

    image_style = visual.get(
        "image_style",
        "realistic_3d_render",
    )

    style_description = IMAGE_STYLE_MAP.get(
        image_style,
        IMAGE_STYLE_MAP[
            "realistic_3d_render"
        ],
    )

    parts.append(
        style_description
    )

    # ----------------------------------------------------------------------
    # CAMERA
    # ----------------------------------------------------------------------

    camera = visual.get(
        "camera",
        "medium",
    )

    parts.append(
        CAMERA_MAP.get(
            camera,
            CAMERA_MAP["medium"],
        )
    )

    # ----------------------------------------------------------------------
    # LIGHTING
    # ----------------------------------------------------------------------

    lighting = _clean_prompt(
        visual.get(
            "lighting",
            DEFAULT_LIGHTING,
        )
    )

    if lighting:

        parts.append(
            f"Lighting: {lighting}."
        )

    # ----------------------------------------------------------------------
    # COLOR
    # ----------------------------------------------------------------------

    palette = _clean_prompt(
        visual.get(
            "color_palette",
            "",
        )
    )

    if palette:

        parts.append(
            f"Color palette: {palette}."
        )

    # ----------------------------------------------------------------------
    # VISUAL IDENTITY
    # ----------------------------------------------------------------------

    if script:

        identity = script.get(
            "visual_identity",
            {},
        )

        if isinstance(
            identity,
            dict,
        ):

            style = _clean_prompt(
                identity.get(
                    "style",
                    "",
                )
            )

            mood_arc = _clean_prompt(
                identity.get(
                    "mood_arc",
                    "",
                )
            )

            if style:

                parts.append(
                    f"Overall visual identity: {style}."
                )

            if mood_arc:

                parts.append(
                    f"Production mood: {mood_arc}."
                )

    # ----------------------------------------------------------------------
    # SCENE PURPOSE
    # ----------------------------------------------------------------------

    purpose = scene.get(
        "purpose",
        "",
    )

    if purpose:

        parts.append(
            f"Scene purpose: {purpose}."
        )

    # ----------------------------------------------------------------------
    # EMOTIONAL TONE
    # ----------------------------------------------------------------------

    emotional_tone = scene.get(
        "emotional_tone",
        "",
    )

    if emotional_tone:

        parts.append(
            f"Emotional tone: {emotional_tone}."
        )

    # ----------------------------------------------------------------------
    # VISUAL ROLE
    # ----------------------------------------------------------------------

    priority = scene.get(
        "visual_priority",
        "supporting",
    )

    parts.append(
        f"Visual priority: {priority}."
    )

    # ----------------------------------------------------------------------
    # COMPOSITION
    # ----------------------------------------------------------------------

    parts.append(
        """
The main subject must be immediately recognizable within one second.

Place the main subject in a strong cinematic composition.

Use realistic scale and perspective.

Keep the background visually supportive rather than competing
with the main subject.

Create clear foreground, subject, and background separation.

The image should look like a frame from an expensive science
documentary rather than generic AI artwork.
"""
    )

    # ----------------------------------------------------------------------
    # GLOBAL STYLE
    # ----------------------------------------------------------------------

    parts.append(
        GLOBAL_STYLE
    )

    return "\n\n".join(
        parts
    )


# ==========================================================================
# SEED
# ==========================================================================

def _get_base_seed(script):

    try:

        seed = int(
            script.get(
                "image_generation",
                {},
            ).get(
                "seed",
                int(
                    time.time()
                ),
            )
        )

    except Exception:

        seed = int(
            time.time()
        )

    return seed


# ==========================================================================
# IMAGE REQUEST
# ==========================================================================

def generate_image(
    prompt,
    width,
    height,
    seed,
):
    """
    Generate one image through Pollinations.
    """

    full_prompt = _clean_prompt(
        prompt
    )

    encoded_prompt = urllib.parse.quote(
        full_prompt,
        safe="",
    )

    url = (
        BASE_URL
        + encoded_prompt
        + "?model=flux"
        + f"&width={int(width)}"
        + f"&height={int(height)}"
        + f"&seed={int(seed)}"
        + "&enhance=true"
        + "&nologo=true"
    )

    print("=" * 80)
    print("IMAGE GENERATION REQUEST")
    print("=" * 80)
    print(
        f"Seed: {seed}"
    )
    print(
        f"Size: {width}x{height}"
    )
    print(
        f"Prompt length: {len(full_prompt)}"
    )
    print("=" * 80)

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):

        try:

            print(
                f"🎨 Image attempt "
                f"{attempt}/{MAX_RETRIES}"
            )

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=180,
            )

            print(
                f"HTTP status: "
                f"{response.status_code}"
            )

            response.raise_for_status()

            content = response.content

            if not content:

                raise RuntimeError(
                    "Image response was empty."
                )

            content_type = (
                response.headers.get(
                    "Content-Type",
                    "",
                ).lower()
            )

            if (
                "image" not in content_type
                and len(content) < 10000
            ):

                raise RuntimeError(
                    "Server returned an unexpected "
                    "non-image response."
                )

            print(
                "✅ Image generated successfully."
            )

            return content

        except Exception as error:

            last_error = error

            print(
                f"❌ Image attempt "
                f"{attempt} failed:"
            )

            print(
                error
            )

            if attempt < MAX_RETRIES:

                time.sleep(
                    RETRY_DELAY
                )

    raise RuntimeError(
        "Failed to generate image after "
        f"{MAX_RETRIES} attempts: "
        f"{last_error}"
    )


# ==========================================================================
# SAVE IMAGE
# ==========================================================================

def _save_image(
    content,
    path,
):

    with open(
        path,
        "wb",
    ) as file:

        file.write(
            content
        )

    size = os.path.getsize(
        path
    )

    if size < 1000:

        raise RuntimeError(
            f"Generated image appears invalid: "
            f"{path}"
        )

    return path


# ==========================================================================
# GENERATE ALL VISUALS
# ==========================================================================

def generate_images(
    script,
    workdir,
    config,
):

    os.makedirs(
        workdir,
        exist_ok=True,
    )

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

    # Force portrait orientation.
    if width >= height:

        width, height = (
            height,
            width,
        )

    base_seed = _get_base_seed(
        script
    )

    image_paths = []

    scenes = script.get(
        "scene_plan",
        [],
    )

    if not scenes:

        raise RuntimeError(
            "Script contains no scene_plan."
        )

    print("=" * 80)
    print("🎨 GENERATING AI VISUALS")
    print("=" * 80)
    print(
        f"Scenes: {len(scenes)}"
    )
    print(
        f"Resolution: {width}x{height}"
    )
    print(
        f"Base seed: {base_seed}"
    )
    print("=" * 80)

    # ----------------------------------------------------------------------
    # EVERY SCENE
    # ----------------------------------------------------------------------

    for scene_index, scene in enumerate(
        scenes,
        start=1,
    ):

        visuals = scene.get(
            "visuals",
            [],
        )

        if not visuals:

            raise RuntimeError(
                f"Scene {scene_index} has no visuals."
            )

        scene_paths = []

        print("=" * 80)
        print(
            f"SCENE {scene_index}/{len(scenes)}"
        )
        print(
            f"Visuals: {len(visuals)}"
        )
        print("=" * 80)

        # ------------------------------------------------------------------
        # EVERY SHOT
        # ------------------------------------------------------------------

        for visual_index, visual in enumerate(
            visuals,
            start=1,
        ):

            prompt = build_prompt(
                scene,
                visual,
                script,
            )

            # Deterministic but different seed for every shot.
            shot_seed = (
                base_seed
                + (
                    scene_index * 100
                )
                + visual_index
            )

            print(
                f"SHOT {visual_index}/{len(visuals)}"
            )

            print(
                f"Seed: {shot_seed}"
            )

            print(
                "Prompt:"
            )

            print(
                prompt
            )

            print("=" * 80)

            image = generate_image(
                prompt,
                width,
                height,
                shot_seed,
            )

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
            )

            print(
                f"✅ Saved -> {filename}"
            )

            scene_paths.append(
                filename
            )

            # Small delay to reduce request bursts.
            time.sleep(
                2
            )

        image_paths.append(
            scene_paths
        )

    # ----------------------------------------------------------------------
    # SUMMARY
    # ----------------------------------------------------------------------

    total_images = sum(
        len(scene)
        for scene in image_paths
    )

    print("=" * 80)
    print("✅ VISUAL GENERATION COMPLETE")
    print("=" * 80)
    print(
        f"Scenes: {len(image_paths)}"
    )
    print(
        f"Images generated: {total_images}"
    )
    print("=" * 80)

    return image_paths


# ==========================================================================
# OPTIONAL SINGLE-IMAGE HELPER
# ==========================================================================

def generate_single_image(
    prompt,
    workdir,
    filename="generated.png",
    width=DEFAULT_WIDTH,
    height=DEFAULT_HEIGHT,
    seed=None,
):

    os.makedirs(
        workdir,
        exist_ok=True,
    )

    if seed is None:

        seed = int(
            time.time()
        )

    image = generate_image(
        prompt,
        width,
        height,
        seed,
    )

    path = os.path.join(
        workdir,
        filename,
    )

    _save_image(
        image,
        path,
    )

    return path