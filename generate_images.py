import os
import time
import urllib.parse
import requests

BASE_URL = "https://image.pollinations.ai/prompt/"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

STYLE_PREFIX = (
    "Graphic novel illustration. "
    "Dark comic book art. "
)


def generate_image(prompt, width, height):

    full_prompt = "cat"

    url = BASE_URL + urllib.parse.quote(full_prompt)

    print("=" * 80)
    print("REQUEST URL:")
    print(url)
    print("=" * 80)

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=180,
    )

    response.raise_for_status()

    return response.content


def generate_images(script, workdir, config):

    os.makedirs(workdir, exist_ok=True)

    width = config["image"]["width"]
    height = config["image"]["height"]

    image_paths = []

    print("=" * 80)
    print("🎨 Generating Images with Pollinations")
    print("=" * 80)

    total = len(script["scene_plan"])

    for i, scene in enumerate(script["scene_plan"], start=1):

        print("=" * 80)
        print(f"Scene {i}/{total}")
        print("=" * 80)

        print(scene["image_prompt"])
        print()

        image = generate_image(
            scene["image_prompt"],
            width,
            height,
        )

        filename = os.path.join(
            workdir,
            f"scene_{i:02d}.png",
        )

        with open(filename, "wb") as f:
            f.write(image)

        print(f"✅ Saved {filename}")

        image_paths.append(filename)

        time.sleep(2)

    return image_paths
