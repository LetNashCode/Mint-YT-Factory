import os
import requests

HF_API_TOKEN = os.environ["HF_TOKEN"]

# Example model (replace with your preferred HF model)
MODEL = "black-forest-labs/FLUX.1-schnell"

API_URL = f"https://router.huggingface.co/hf-inference/models/{MODEL}"

STYLE_PREFIX = (
    "Modern 2D stickman animation. "
    "Professional YouTube animation style. "
    "Minimalist vector illustration. "
    "Simple black stick figures. "
    "Thick smooth black outlines. "
    "White background. "
    "Flat design. "
    "Consistent stickman character in every scene. "
    "Large expressive eyes. "
    "Vertical 9:16 composition. "
)

headers = {
    "Authorization": f"Bearer {HF_API_TOKEN}",
    "Content-Type": "application/json",
}


def generate_image(prompt, width, height):
    payload = {
        "inputs": prompt,
        "parameters": {
            "width": width,
            "height": height,
        },
    }

    response = requests.post(
        API_URL,
        headers=headers,
        json=payload,
        timeout=300,
    )

    response.raise_for_status()

    return response.content


def generate_images(script, workdir, config):

    os.makedirs(workdir, exist_ok=True)

    width = config["image"]["width"]
    height = config["image"]["height"]

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
              "No photorealism."
        )

        print("=" * 80)
        print(f"🖼️ Generating Scene {i}/{total}")
        print("=" * 80)

        image = generate_image(prompt, width, height)

        path = os.path.join(
            workdir,
            f"scene_{i:02d}.png",
        )

        with open(path, "wb") as f:
            f.write(image)

        image_paths.append(path)

    return image_paths
