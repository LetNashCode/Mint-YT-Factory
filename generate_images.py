"""
generate_images.py

Mint-YT-Factory
Puter AI Image Generation

Purpose:
Generate AI visuals from the storyboard produced by generate_script.py.

Pipeline:

generate_script.py
        ↓
generate_images.py
        ↓
generate_images_puter.js
        ↓
Puter AI
        ↓
PNG images
        ↓
assemble.py

Puter handles the actual image generation.
This file handles storyboard parsing, prompts, seeds,
file naming, retries and pipeline integration.
"""

import os
import subprocess
import time


# ==========================================================================
# CONFIGURATION
# ==========================================================================

DEFAULT_WIDTH = 768
DEFAULT_HEIGHT = 1365

MAX_RETRIES = 3

RETRY_DELAY = 5

PUTER_SCRIPT = os.path.join(
    os.path.dirname(
        os.path.abspath(__file__)
    ),
    "generate_images_puter.js",
)


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
# DEFAULT LIGHTING
# ==========================================================================

DEFAULT_LIGHTING = (
    "soft cinematic key light, realistic natural fill light, "
    "subtle rim lighting, physically plausible shadows, "
    "high dynamic range"
)


# ==========================================================================
# HELPERS
# ==========================================================================

def _clean_prompt(text):

    if not text:
        return ""

    text = str(text)

    text = text.replace(
        "\n",
        " "
    )

    text = text.replace(
        "```",
        ""
    )

    text = " ".join(
        text.split()
    )

    return text.strip()


# ==========================================================================
# BUILD PROMPT
# ==========================================================================

def build_prompt(
    scene,
    visual,
    script=None,
):

    parts = []

    # ----------------------------------------------------------------------
    # IMAGE DESCRIPTION
    # ----------------------------------------------------------------------

    image_prompt = _clean_prompt(
        visual.get(
            "image_prompt",
            ""
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
        "realistic_3d_render"
    )

    parts.append(
        IMAGE_STYLE_MAP.get(
            image_style,
            IMAGE_STYLE_MAP[
                "realistic_3d_render"
            ]
        )
    )

    # ----------------------------------------------------------------------
    # CAMERA
    # ----------------------------------------------------------------------

    camera = visual.get(
        "camera",
        "medium"
    )

    parts.append(
        CAMERA_MAP.get(
            camera,
            CAMERA_MAP["medium"]
        )
    )

    # ----------------------------------------------------------------------
    # LIGHTING
    # ----------------------------------------------------------------------

    lighting = _clean_prompt(
        visual.get(
            "lighting",
            DEFAULT_LIGHTING
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
            ""
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
            {}
        )

        if isinstance(
            identity,
            dict
        ):

            style = _clean_prompt(
                identity.get(
                    "style",
                    ""
                )
            )

            mood_arc = _clean_prompt(
                identity.get(
                    "mood_arc",
                    ""
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

    purpose = _clean_prompt(
        scene.get(
            "purpose",
            ""
        )
    )

    if purpose:
        parts.append(
            f"Scene purpose: {purpose}."
        )

    # ----------------------------------------------------------------------
    # EMOTIONAL TONE
    # ----------------------------------------------------------------------

    emotional_tone = _clean_prompt(
        scene.get(
            "emotional_tone",
            ""
        )
    )

    if emotional_tone:
        parts.append(
            f"Emotional tone: {emotional_tone}."
        )

    # ----------------------------------------------------------------------
    # VISUAL PRIORITY
    # ----------------------------------------------------------------------

    priority = scene.get(
        "visual_priority",
        "supporting"
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
                {}
            ).get(
                "seed",
                int(time.time())
            )
        )

    except Exception:

        seed = int(
            time.time()
        )

    return seed


# ==========================================================================
# PUTER IMAGE GENERATION
# ==========================================================================

def generate_image(
    prompt,
    output_path,
    seed,
):

    print("")
    print("=" * 80)
    print("🎨 PUTER IMAGE GENERATION")
    print("=" * 80)

    print(
        f"Seed: {seed}"
    )

    print(
        f"Prompt length: {len(prompt)}"
    )

    print(
        f"Output: {output_path}"
    )

    print("=" * 80)

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        print(
            f"🎨 Attempt {attempt}/{MAX_RETRIES}"
        )

        env = os.environ.copy()

        env[
            "PUTER_IMAGE_PROMPT"
        ] = prompt

        env[
            "PUTER_OUTPUT_PATH"
        ] = output_path

        env[
            "PUTER_IMAGE_SEED"
        ] = str(seed)

        try:

            result = subprocess.run(
                [
                    "node",
                    PUTER_SCRIPT
                ],
                env=env,
                text=True,
                check=False
            )

            if result.returncode != 0:

                raise RuntimeError(
                    "Puter generator exited with "
                    f"code {result.returncode}"
                )

            if not os.path.exists(
                output_path
            ):

                raise RuntimeError(
                    "Puter completed but image "
                    "file was not created."
                )

            file_size = os.path.getsize(
                output_path
            )

            if file_size < 1000:

                raise RuntimeError(
                    "Generated image file appears invalid."
                )

            print(
                f"✅ Image generated successfully."
            )

            print(
                f"📦 Size: {file_size} bytes"
            )

            return output_path

        except Exception as error:

            last_error = error

            print(
                f"❌ Attempt {attempt} failed:"
            )

            print(
                error
            )

            if attempt < MAX_RETRIES:

                print(
                    f"⏳ Retrying in "
                    f"{RETRY_DELAY} seconds..."
                )

                time.sleep(
                    RETRY_DELAY
                )

    raise RuntimeError(
        "Puter image generation failed after "
        f"{MAX_RETRIES} attempts: {last_error}"
    )


# ==========================================================================
# GENERATE ALL VISUALS
# ==========================================================================

def generate_images(
    script,
    workdir,
    config
):

    os.makedirs(
        workdir,
        exist_ok=True
    )

    if not os.path.exists(
        PUTER_SCRIPT
    ):

        raise RuntimeError(
            "generate_images_puter.js was not found at:\n"
            f"{PUTER_SCRIPT}"
        )

    scenes = script.get(
        "scene_plan",
        []
    )

    if not scenes:

        raise RuntimeError(
            "Script contains no scene_plan."
        )

    base_seed = _get_base_seed(
        script
    )

    print("")
    print("=" * 80)
    print("🎨 GENERATING AI VISUALS WITH PUTER")
    print("=" * 80)

    print(
        f"Scenes: {len(scenes)}"
    )

    print(
        f"Base seed: {base_seed}"
    )

    print(
        "Model: gpt-image-2"
    )

    print(
        "Ratio: 9:16"
    )

    print("=" * 80)

    image_paths = []

    # ----------------------------------------------------------------------
    # EVERY SCENE
    # ----------------------------------------------------------------------

    for scene_index, scene in enumerate(
        scenes,
        start=1
    ):

        visuals = scene.get(
            "visuals",
            []
        )

        if not visuals:

            raise RuntimeError(
                f"Scene {scene_index} has no visuals."
            )

        scene_paths = []

        print("")
        print("=" * 80)
        print(
            f"SCENE {scene_index}/{len(scenes)}"
        )
        print(
            f"Visuals: {len(visuals)}"
        )
        print("=" * 80)

        # ------------------------------------------------------------------
        # EVERY VISUAL
        # ------------------------------------------------------------------

        for visual_index, visual in enumerate(
            visuals,
            start=1
        ):

            prompt = build_prompt(
                scene,
                visual,
                script
            )

            shot_seed = (
                base_seed
                + scene_index * 100
                + visual_index
            )

            filename = (
                f"scene_{scene_index:02d}"
                f"_shot_{visual_index:02d}.png"
            )

            output_path = os.path.join(
                workdir,
                filename
            )

            print("")
            print(
                f"SHOT {visual_index}/{len(visuals)}"
            )

            print(
                f"Seed: {shot_seed}"
            )

            print(
                f"File: {filename}"
            )

            generated_path = generate_image(
                prompt,
                output_path,
                shot_seed
            )

            scene_paths.append(
                generated_path
            )

            # Small delay between images.
            time.sleep(2)

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

    print("")
    print("=" * 80)
    print("✅ PUTER VISUAL GENERATION COMPLETE")
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
# SINGLE IMAGE HELPER
# ==========================================================================

def generate_single_image(
    prompt,
    workdir,
    filename="generated.png",
    width=DEFAULT_WIDTH,
    height=DEFAULT_HEIGHT,
    seed=None
):

    os.makedirs(
        workdir,
        exist_ok=True
    )

    if seed is None:

        seed = int(
            time.time()
        )

    output_path = os.path.join(
        workdir,
        filename
    )

    return generate_image(
        prompt,
        output_path,
        seed
    )