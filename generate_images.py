import os
import time
import urllib.parse
import requests

BASE_URL = "https://image.pollinations.ai/prompt/"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

STYLE_PREFIX = (
    "Educational infographic. "
    "High quality 3D render. "
    "Professional educational illustration. "
    "Clean composition. "
    "Bright colors. "
    "Modern science documentary style. "
    "National Geographic quality. "
    "Highly detailed. "
    "Sharp focus. "
    "Realistic lighting. "
    "White background when appropriate. "
    "No text. "
    "No labels. "
    "No watermark. "
    "No logo. "
    "Vertical 9:16 composition. "
    "Subject centered. "
    "Educational visual. "
)


def generate_image(prompt, width, height):

    full_prompt = STYLE_PREFIX + prompt

    if len(full_prompt) > 350:
        full_prompt = full_prompt[:350]

    url = (
        BASE_URL
        + urllib.parse.quote(full_prompt)
        + f"?model=flux"
        + f"&width={width}"
        + f"&height={height}"
        + f"&seed={int(time.time())}"
        + "&nologo=true"
    )

    print("=" * 80)
    print("REQUEST URL:")
    print(url)
    print("=" * 80)

    for attempt in range(5):

        try:

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=180,
            )

            print("STATUS:", response.status_code)

            if response.status_code != 200:
                print(response.text[:2000])

            response.raise_for_status()

            if response.content:
                return response.content

        except Exception as e:

            print(f"Retry {attempt + 1}/5")
            print(e)

            time.sleep(5)

    raise Exception("Failed to generate image after 5 attempts.")


def generate_images(script, workdir, config):

    os.makedirs(workdir, exist_ok=True)

    width = config["image"]["width"]
    height = config["image"]["height"]

    image_paths = []

    print("=" * 80)
    print("🎨 Generating Educational Visuals")
    print("=" * 80)

    total = len(script["scene_plan"])

    for i, scene in enumerate(script["scene_plan"], start=1):

        print("=" * 80)
        print(f"🖼️ Scene {i}/{total}")
        print("=" * 80)

        print(scene["image_prompt"])

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

        print(f"✅ Saved -> {filename}")

        image_paths.append(filename)

        time.sleep(2)

    return image_paths
