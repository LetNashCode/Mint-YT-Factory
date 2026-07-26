import os
import urllib.parse
import requests


BASE_URL = "https://image.pollinations.ai/prompt/"


STYLE_PREFIX = (
    "Ultra cinematic movie still. "
    "Hyper realistic. "
    "Professional photography. "
    "8K. "
    "Hollywood blockbuster. "
    "Highly detailed. "
    "Professional color grading. "
    "Volumetric lighting. "
    "Ray traced lighting. "
    "Sharp focus. "
    "Portrait orientation. "
    "Vertical 9:16 composition. "
    "Subject fills the frame. "
    "Dynamic cinematic composition. "
    "Dramatic camera angle. "
    "Photorealistic. "
    "No text. "
    "No captions. "
    "No logo. "
    "No watermark. "
)


def generate_images(script, workdir):

    os.makedirs(workdir, exist_ok=True)

    image_paths = []

    total = len(script["scene_plan"])

    for i, scene in enumerate(script["scene_plan"], start=1):

        prompt = (
            STYLE_PREFIX
            + scene["image_prompt"]
            + ". Full body if needed. Portrait framing. Subject centered. "
              "Designed specifically for a vertical smartphone screen. "
              "No wide landscape composition."
        )

        url = (
            BASE_URL
            + urllib.parse.quote(prompt)
            + "?width=1080"
            + "&height=1920"
            + "&model=gptimage"
            + "&nologo=true"
            + "&enhance=true"
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
