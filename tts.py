import os
import shutil

from moviepy.editor import AudioFileClip, concatenate_audioclips
from tiktoktts import TTS

VOICE_ID = "en_us_ghostface"
MAX_BYTES = 300


def split_text(text, limit=MAX_BYTES):
    words = text.split()
    chunks = []
    current = ""

    for word in words:
        test = word if not current else current + " " + word

        if len(test.encode("utf-8")) <= limit:
            current = test
        else:
            chunks.append(current)
            current = word

    if current:
        chunks.append(current)

    return chunks


def synthesize_narration(text, config, out_path):
    tts = TTS()
    tts.SetVoice(VOICE_ID)

    parts = []
    chunks = split_text(text)

    for i, chunk in enumerate(chunks):
        tts.New(chunk)

        part = f"part_{i}.mp3"
        shutil.move("output.mp3", part)
        parts.append(part)

    clips = [AudioFileClip(p) for p in parts]

    final = concatenate_audioclips(clips)
    final.write_audiofile(
        out_path,
        fps=44100,
        codec="mp3",
        logger=None,
    )

    final.close()

    for clip in clips:
        clip.close()

    for p in parts:
        os.remove(p)

    return out_path


def synthesize_script(script, config, workdir):
    os.makedirs(workdir, exist_ok=True)

    paths = []

    for i, item in enumerate(script["items"], start=1):
        out = os.path.join(workdir, f"item_{i}.mp3")
        synthesize_narration(item["narration"], config, out)
        paths.append(out)

    return paths


if __name__ == "__main__":
    synthesize_narration(
        "Hello world.",
        {},
        "test.mp3",
    )
    print("Done")
