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

        response = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
            ),
        )

        image = response.generated_images[0].image

        path = os.path.join(
            workdir,
            f"scene_{i:02d}.png",
        )

        image.save(path)

        image_paths.append(path)

        print(f"✅ Saved {path}")

        # ONLY TEST ONE IMAGE
        break

    return image_paths
