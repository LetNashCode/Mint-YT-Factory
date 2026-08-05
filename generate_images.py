import os
import time
import urllib.parse
import requests

BASE_URL = "https://image.pollinations.ai/prompt/"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

STYLE_PREFIX = (
    "Educational documentary illustration. "
    "Ultra realistic 3D render. "
    "Professional educational artwork. "
    "National Geographic documentary quality. "
    "Highly detailed. "
    "Photorealistic. "
    "Clean composition. "
    "Volumetric lighting. "
    "Sharp focus. "
    "8K quality. "
    "Vertical 9:16 composition. "
    "No text. "
    "No labels. "
    "No watermark. "
    "No logo. "
)


def build_prompt(scene):

    prompt_parts = []

    if scene.get("image_prompt"):
        prompt_parts.append(scene["image_prompt"])

    if scene.get("image_style"):
        prompt_parts.append(scene["image_style"])

    if scene.get("lighting"):
        prompt_parts.append(
            f"Lighting: {scene['lighting']}"
        )

    if scene.get("color_palette"):
        prompt_parts.append(
            f"Color palette: {scene['color_palette']}"
        )

    if scene.get("visual_identity"):
        prompt_parts.append(scene["visual_identity"])

    if scene.get("visual_role"):
        prompt_parts.append(
            f"Visual role: {scene['visual_role']}"
        )

    if scene.get("camera"):
        prompt_parts.append(
            f"Camera angle: {scene['camera']}"
        )

    if scene.get("mood"):
        prompt_parts.append(
            f"Mood: {scene['mood']}"
        )

    prompt_parts.append(
        "Centered subject."
    )

    prompt_parts.append(
        "Designed for YouTube Shorts."
    )

    prompt_parts.append(
        "Educational documentary style."
    )

    prompt = ". ".join(prompt_parts)

    return prompt


def generate_image(prompt, width, height):

    full_prompt = STYLE_PREFIX + prompt

    if len(full_prompt) > 700:
        full_prompt = full_prompt[:700]

    url = (
        BASE_URL
        + urllib.parse.quote(full_prompt)
        + "?model=flux"
        + f"&width={width}"
        + f"&height={height}"
        + f"&seed={int(time.time())}"
        + "&enhance=true"
        + "&nologo=true"
    )

    print("=" * 80)
    print("REQUEST URL")
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

    raise RuntimeError(
        "Failed to generate image."
    )


def generate_images(script, workdir, config):

    os.makedirs(workdir, exist_ok=True)

    width = config["image"]["width"]
    height = config["image"]["height"]

    image_paths = []

    scenes = script["scene_plan"]

    print("=" * 80)
    print("🎨 GENERATING EDUCATIONAL VISUALS")
    print("=" * 80)

    for index, scene in enumerate(scenes, start=1):

        prompt = build_prompt(scene)

        print("=" * 80)
        print(f"SCENE {index}/{len(scenes)}")
        print("=" * 80)
        print(prompt)
        print("=" * 80)

        image = generate_image(
            prompt,
            width,
            height,
        )

        filename = os.path.join(
            workdir,
            f"scene_{index:02d}.png",
        )

        with open(filename, "wb") as f:
            f.write(image)

        print(f"✅ Saved -> {filename}")

        image_paths.append(filename)

        time.sleep(2)

    return image_paths
