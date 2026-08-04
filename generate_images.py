import os
from google import genai
from google.genai import types


client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)


def generate_images(script, workdir, config):

    os.makedirs(workdir, exist_ok=True)

    image_paths = []

    print("=" * 80)
    print("🎨 Using Imagen 4")
    print("=" * 80)

    return image_paths
