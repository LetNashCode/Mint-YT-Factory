import os
import main


def main_entry():
    print("=" * 80)
    print("🚀 MINT-YT-FACTORY STARTED")
    print("=" * 80)
    print("Visual/Search Director: Gemini")
    print("Media priority: Pexels VIDEO → Pixabay VIDEO → Pexels PHOTO → Pixabay PHOTO")
    print("Visual verification: ENABLED — Gemini inspects top stock candidates")
    print("Visual verification threshold: 7.5/10")
    print("Visual verification candidate pool: up to 6 per provider/shot")
    print("AI image generation: DISABLED")
    print("Pollinations/FLUX: DISABLED")
    print("Fallback: stock provider fallback only; no unrelated or AI visual fallback")
    print("Continuation: one locked next topic, final sentence only")
    print("Pexels API key:", "AVAILABLE" if os.environ.get("PEXELS_API_KEY") else "NOT CONFIGURED")
    print("Pixabay API key:", "AVAILABLE" if os.environ.get("PIXABAY_API_KEY") else "NOT CONFIGURED")
    print("Gemini API key:", "AVAILABLE" if os.environ.get("GEMINI_API_KEY") else "NOT CONFIGURED")
    print("Story: TTS-authoritative 35-43.9 seconds")
    print("Captions: Whisper word timing → deterministic fallback if Whisper fails")
    print("TTS duration guard: ENABLED")
    print("=" * 80)
    main.run(dry_run=False)


if __name__ == "__main__":
    main_entry()
