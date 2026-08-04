import os
from google import genai
from google.genai import types

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)

def generate_images(script, workdir, config):

    os.makedirs(workdir, exist_ok=True)

    image_paths = []

    total = len(script["scene_plan"])

    print("=" * 80)
    print("🎨 Using Imagen 4")
    print("=" * 80)

    for i, scene in enumerate(script["scene_plan"], start=1):

        print("=" * 80)
        print(f"🖼️ Generating Scene {i}/{total}")
        print("=" * 80)

        prompt = scene["image_prompt"]

        print(prompt)
        print()

    return image_paths
