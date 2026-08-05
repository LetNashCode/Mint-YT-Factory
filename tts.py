import os
import re
import shutil

from moviepy.editor import AudioFileClip, concatenate_audioclips
from tiktoktts import TTS

MAX_BYTES = 300


def split_text(text, limit=MAX_BYTES):

    words = text.split()

    chunks = []

    current = ""

    for word in words:

        candidate = word if not current else current + " " + word

        if len(candidate.encode("utf-8")) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = word

    if current:
        chunks.append(current)

    return chunks


def clean_text(text):

    text = re.sub(r"\s+", " ", text)

    text = re.sub(r"\!{2,}", "!", text)

    text = re.sub(r"\?{2,}", "?", text)

    return text.strip()


def synthesize_narration(text, config, out_path):

    voice = config["voice"]["voice_name"]

    tts = TTS()

    tts.SetVoice(voice)

    temp_files = []

    for i, chunk in enumerate(split_text(clean_text(text))):

        tts.New(chunk)

        filename = f"tts_part_{i}.mp3"

        shutil.move("output.mp3", filename)

        temp_files.append(filename)

    clips = [
        AudioFileClip(x)
        for x in temp_files
    ]

    final = concatenate_audioclips(clips)

    final.write_audiofile(
        out_path,
        codec="mp3",
        fps=44100,
        logger=None,
    )

    final.close()

    for clip in clips:
        clip.close()

    for file in temp_files:
        os.remove(file)

    return out_path


def synthesize_script(script, config, workdir):

    os.makedirs(workdir, exist_ok=True)

    narration = []

    for key in [

        "hook",

        "question",

        "explanation",

        "example",

        "mindblowing_fact",

        "ending",

    ]:

        if key in script:

            narration.append(script[key])

    text = " ".join(narration)

    out = os.path.join(
        workdir,
        "story.mp3",
    )

    synthesize_narration(
        text,
        config,
        out,
    )

    return [out]
