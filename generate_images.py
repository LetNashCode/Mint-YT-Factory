import os
import time
import urllib.parse
import requests

BASE_URL = "https://image.pollinations.ai/prompt/"

STYLE_PREFIX = (
    "Graphic novel illustration. "
    "Dark comic book art. "
)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def generate_image(prompt, width, height):

    full_prompt = STYLE_PREFIX + prompt

      
    url = (
        BASE_URL
        + urllib.parse.quote(full_prompt)
        + "?model=flux"
    )

    print("REQUEST URL:")
    print(url)
    print("-" * 80)

    for attempt in range(5):

        try:

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=180,
            )

            response.raise_for_status()

            if response.content:
                return response.content

        except Exception as e:

            print(f"Retry {attempt+1}/5")
            print(e)

            time.sleep(5)

    raise Exception("Failed to generate image after 5 attempts.")


def generate_images(script, workdir, config):

    os.makedirs(workdir, exist_ok=True)

    width = config["image"]["width"]
    height = config["image"]["height"]

    image_paths = []

    total = len(script["scene_plan"])

    print("=" * 80)
    print("🎨 Using Pollinations")
    print("=" * 80)

    for i, scene in enumerate(script["scene_plan"], start=1):

        print("=" * 80)
        print(f"🖼️ Generating Scene {i}/{total}")
        print("=" * 80)

        image = generate_image(
            scene["image_prompt"],
            width,
            height,
        )

        path = os.path.join(
            workdir,
            f"scene_{i:02d}.png",
        )

        with open(path, "wb") as f:
            f.write(image)

        print(f"Saved -> {path}")

        image_paths.append(path)

    return image_paths
