import os
import shutil

from tiktoktts import TTS

VOICE_ID = "en_female_ht_f08_wonderful_world"


def synthesize_narration(text: str, config: dict, out_path: str) -> str:
    tts = TTS()

    tts.SetVoice(VOICE_ID)

    tts.New(text)

    shutil.move("output.mp3", out_path)

    return out_path


def synthesize_script(script: dict, config: dict, workdir: str) -> list:
    os.makedirs(workdir, exist_ok=True)

    paths = []

    for i, item in enumerate(script["items"], start=1):
        out_path = os.path.join(workdir, f"item_{i}.mp3")
        synthesize_narration(item["narration"], config, out_path)
        paths.append(out_path)

    return paths


if __name__ == "__main__":
    synthesize_narration(
        "This signal from space still has no explanation.",
        {},
        "test.mp3",
    )
    print("Done")
