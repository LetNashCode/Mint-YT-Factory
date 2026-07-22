import os
import re
import shutil

from moviepy.editor import AudioFileClip, concatenate_audioclips
from tiktoktts import TTS

VOICE_ID = "en_us_ghostface"
MAX_BYTES = 300


def apply_emotion(text, emotion):
    """
    Placeholder for future emotion support.
    Currently returns the text unchanged because
    TikTok TTS reads "..." as "dot dot dot".
    """
    if not text:
        return ""

    return text.strip()


def split_text(text, limit=MAX_BYTES):
    words = text.split()

    chunks = []
    current = ""

    for word in words:

        test = word if not current else current + " " + word

        if len(test.encode("utf-8")) <= limit:
            current = test
        else:
            if current:
                chunks.append(current)
            current = word

    if current:
        chunks.append(current)

    return chunks


def synthesize_narration(text, config, out_path):

    tts = TTS()
    tts.SetVoice(VOICE_ID)

    temp = []

    for i, chunk in enumerate(split_text(text)):

        chunk = re.sub(r"\!{2,}", "!", chunk)
        chunk = re.sub(r"\?{2,}", "?", chunk)
        chunk = re.sub(r"\s+", " ", chunk).strip()

        tts.New(chunk)

        part = f"tts_part_{i}.mp3"

        shutil.move("output.mp3", part)

        temp.append(part)

    clips = [AudioFileClip(x) for x in temp]

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

    for file in temp:
        os.remove(file)

    return out_path


def synthesize_script(script, config, workdir):

    os.makedirs(workdir, exist_ok=True)

    narration = []

    narration.append(
        apply_emotion(
            script["hook"],
            "curiosity",
        )
    )

    narration.append(
        apply_emotion(
            script["story"],
            "suspense",
        )
    )

    narration.append(
        apply_emotion(
            script["twist"],
            "shock",
        )
    )

    narration.append(
        apply_emotion(
            script["ending"],
            "mystery",
        )
    )

    full_text = " ".join(
        part for part in narration if part
    )

    out = os.path.join(
        workdir,
        "story.mp3",
    )

    synthesize_narration(
        full_text,
        config,
        out,
    )

    return [out]
