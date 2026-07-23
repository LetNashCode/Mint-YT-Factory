import os
import urllib.parse
import requests


BASE_URL = "https://image.pollinations.ai/prompt/"


STYLE_PREFIX = (
    "Ultra cinematic. "
    "Movie still. "
    "Hyper realistic. "
    "Highly detailed. "
    "Professional color grading. "
    "Volumetric lighting. "
    "Sharp focus. "
    "Vertical composition. "
    "9:16. "
)


def generate_images(script, workdir):

    os.makedirs(workdir, exist_ok=True)

    image_paths = []

    for i, scene in enumerate(script["scene_plan"]):

        prompt = STYLE_PREFIX + scene["visual_prompt"]

        url = BASE_URL + urllib.parse.quote(prompt)

        print(f"Generating image {i+1}/{len(script['scene_plan'])}")
        print(prompt)

        response = requests.get(url, timeout=180)

        response.raise_for_status()

        path = os.path.join(
            workdir,
            f"scene_{i+1:02d}.png",
        )

        with open(path, "wb") as f:
            f.write(response.content)

        image_paths.append(path)

    return image_paths
