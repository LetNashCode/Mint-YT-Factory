import os
import urllib.parse
import requests


BASE_URL = "https://image.pollinations.ai/prompt/"


STYLE_PREFIX = (
    "Modern 2D stickman animation. "
    "Professional YouTube animation style. "
    "Minimalist vector illustration. "
    "Simple black stick figures. "
    "Thick smooth black outlines. "
    "White background. "
    "Flat design. "
    "Clean composition. "
    "Consistent stickman character in every scene. "
    "Expressive body language. "
    "Simple facial expressions. "
    "High-quality SVG illustration style. "
    "Large expressive eyes. "
    "Dynamic action pose. "
    "Professional explainer animation. "
    "Perfect anatomy for stickman. "
    "Minimal props. "
    "Cinematic composition. "
    "Vertical 9:16 composition. "
    "Portrait orientation. "
    "Designed for YouTube Shorts. "
    "No realistic humans. "
    "No detailed faces. "
    "No colors except black and white. "
    "No shading. "
    "No gradients. "
    "No textures. "
    "No logo. "
    "No watermark. "
    "No text. "
)

def generate_images(script, workdir, config):

    os.makedirs(workdir, exist_ok=True)

    image_cfg = config["image"]

    model = image_cfg["model"]
    width = image_cfg["width"]
    height = image_cfg["height"]
    enhance = str(image_cfg["enhance"]).lower()
    nologo = str(image_cfg["nologo"]).lower()

    image_paths = []

    total = len(script["scene_plan"])

    for i, scene in enumerate(script["scene_plan"], start=1):

        prompt = (
            STYLE_PREFIX
            + scene["image_prompt"]
            + ". Every human must be a stickman. "
              "Every character uses the exact same stickman design. "
              "Simple vector illustration. "
              "Black outlines only. "
              "White background. "
              "Modern YouTube explainer style. "
              "Minimal objects. "
              "Dynamic pose. "
              "Action frozen at its most dramatic moment. "
              "Clean composition. "
              "Subject fills most of the frame. "
              "Perfect vertical framing. "
              "No realistic people. "
              "No photorealism."
        )

        url = (
            BASE_URL
            + urllib.parse.quote(prompt)
            + f"?width={width}"
            + f"&height={height}"
            + f"&model={model}"
            + f"&nologo={nologo}"
            + f"&enhance={enhance}"
        )

        print("=" * 80)
        print(f"🖼️ Generating Scene {i}/{total}")
        print(prompt)
        print("=" * 80, flush=True)

        response = requests.get(url, timeout=300)
        response.raise_for_status()

        path = os.path.join(
            workdir,
            f"scene_{i:02d}.png",
        )

        with open(path, "wb") as f:
            f.write(response.content)

        image_paths.append(path)

    return image_paths
