import os
from huggingface_hub import InferenceClient

client = InferenceClient(
    provider="fal-ai",
    api_key=os.environ["HF_TOKEN"],
)

image = client.text_to_image(
    "A cinematic horror movie still of a man looking into a mirror where his reflection smiles back. Ultra realistic. Vertical 9:16.",
    model="black-forest-labs/FLUX.1-dev",
)

image.save("test.png")

print("✅ Success! Image saved as test.png")
