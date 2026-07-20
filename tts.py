"""
Text-to-speech using edge-tts (free, Microsoft Edge neural voices,
includes good Indian-English and Hindi voices, no API key required).
"""
import asyncio
import os
import time

import edge_tts


async def _synthesize(text: str, voice: str, rate: str, pitch: str, out_path: str):
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(out_path)


def synthesize_narration(text: str, config: dict, out_path: str, max_retries: int = 4) -> str:
    """Microsoft's free TTS service occasionally rejects a request for no
    clear reason (a known, common edge-tts issue, not specific to this
    project). Retrying almost always succeeds within a couple of attempts."""
    voice_cfg = config["voice"]
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            asyncio.run(
                _synthesize(
                    text=text,
                    voice=voice_cfg["voice_name"],
                    rate=voice_cfg.get("rate", "+0%"),
                    pitch=voice_cfg.get("pitch", "+0Hz"),
                    out_path=out_path,
                )
            )
            return out_path
        except Exception as e:
            last_error = e
            print(f"TTS attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                time.sleep(2 * attempt)
    raise last_error


def synthesize_script(script: dict, config: dict, workdir: str) -> list:
    """Synthesize one audio file per item, returns list of file paths in order."""
    os.makedirs(workdir, exist_ok=True)
    paths = []
    for item in script["items"]:
        out_path = os.path.join(workdir, f"item_{item['rank']}.mp3")
        synthesize_narration(item["narration"], config, out_path)
        paths.append(out_path)
    return paths


if __name__ == "__main__":
    import yaml

    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    synthesize_narration(
        "Number five. This fort has kept its secrets for three hundred years.",
        cfg,
        "test_voice.mp3",
    )
    print("Saved test_voice.mp3")
