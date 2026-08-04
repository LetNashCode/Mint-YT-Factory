import os
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

response = client.models.generate_content(
    model="gemini-2.5-flash-image",
    contents="A cinematic horror movie still of a man looking into a mirror where his reflection smiles back. Ultra realistic. Vertical 9:16.",
    config=types.GenerateContentConfig(
        response_modalities=["TEXT", "IMAGE"]
    ),
)

for part in response.candidates[0].content.parts:
    if getattr(part, "inline_data", None):
        with open("test.png", "wb") as f:
            f.write(part.inline_data.data)
        print("✅ Image saved as test.png")
        break
else:
    print(response.text)
