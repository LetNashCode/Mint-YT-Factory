"""
tts.py
Mint-YT-Factory

Version 7.1

TikTok TTS narration engine.

Features:
- TikTok TTS
- 300-byte chunk limit
- Scene-by-scene narration
- Preserves scene pauses
- Concatenates all audio into one MP3
- Cleans temporary files
- Compatible with main.py
- Compatible with assemble.py
"""

import os
import re
import shutil
import tempfile

from moviepy.editor import (
    AudioFileClip,
    AudioClip,
    concatenate_audioclips,
)

from tiktoktts import TTS


# ==========================================================================
# CONFIG
# ==========================================================================

MAX_BYTES = 300

SAMPLE_RATE = 44100

DEFAULT_PAUSE_MS = 0


# ==========================================================================
# TEXT CLEANING
# ==========================================================================

def clean_text(text):
    """
    Clean narration text without changing its meaning.
    """

    if not text:
        return ""

    text = str(text)

    # Remove excessive whitespace.
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    # Collapse repeated punctuation.
    text = re.sub(
        r"!{2,}",
        "!",
        text,
    )

    text = re.sub(
        r"\?{2,}",
        "?",
        text,
    )

    # Remove accidental markdown.
    text = text.replace(
        "**",
        "",
    )

    text = text.replace(
        "__",
        "",
    )

    return text.strip()


# ==========================================================================
# TEXT SPLITTING
# ==========================================================================

def split_text(
    text,
    limit=MAX_BYTES,
):
    """
    Split text into chunks that stay below
    the TikTok TTS byte limit.

    Splitting happens on word boundaries.
    """

    text = clean_text(
        text
    )

    if not text:
        return []

    words = text.split()

    chunks = []

    current = ""

    for word in words:

        candidate = (

            word

            if not current

            else

            current
            + " "
            + word
        )

        if len(
            candidate.encode(
                "utf-8"
            )
        ) <= limit:

            current = candidate

        else:

            if current:

                chunks.append(
                    current
                )

            # ----------------------------------------------------------
            # Extremely long single word.
            # ----------------------------------------------------------

            if len(
                word.encode(
                    "utf-8"
                )
            ) > limit:

                encoded = word.encode(
                    "utf-8"
                )

                start = 0

                while start < len(
                    encoded
                ):

                    piece = encoded[
                        start:
                        start + limit
                    ]

                    chunks.append(
                        piece.decode(
                            "utf-8",
                            errors="ignore",
                        )
                    )

                    start += limit

                current = ""

            else:

                current = word

    if current:

        chunks.append(
            current
        )

    return chunks


# ==========================================================================
# PAUSE AUDIO
# ==========================================================================

def create_silence(
    duration,
):
    """
    Create silent audio for scene pauses.
    """

    duration = float(
        duration
    )

    if duration <= 0:

        return None

    silence = AudioClip(
        lambda t: 0,
        duration=duration,
        fps=SAMPLE_RATE,
    )

    return silence


# ==========================================================================
# SINGLE TTS GENERATION
# ==========================================================================

def synthesize_narration(
    text,
    config,
    out_path,
):
    """
    Convert one block of narration into audio.

    The text is automatically split into
    TikTok-compatible chunks.
    """

    text = clean_text(
        text
    )

    if not text:

        raise RuntimeError(
            "Cannot synthesize empty narration."
        )

    voice_config = config.get(
        "voice",
        {},
    )

    if not isinstance(
        voice_config,
        dict,
    ):

        voice_config = {}

    voice = voice_config.get(
        "voice_name"
    )

    if not voice:

        raise RuntimeError(
            "config.yaml is missing "
            "voice.voice_name."
        )

    print("=" * 80)
    print("🎙️ TIKTOK TTS")
    print("=" * 80)

    print(
        f"Voice: {voice}"
    )

    chunks = split_text(
        text
    )

    print(
        f"Text chunks: "
        f"{len(chunks)}"
    )

    if not chunks:

        raise RuntimeError(
            "Text produced no TTS chunks."
        )

    tts = TTS()

    tts.SetVoice(
        voice
    )

    temp_dir = tempfile.mkdtemp(
        prefix="mint_tts_"
    )

    temp_files = []

    clips = []

    try:

        # --------------------------------------------------------------
        # Generate every TTS chunk.
        # --------------------------------------------------------------

        for index, chunk in enumerate(
            chunks
        ):

            print(
                f"🎤 Generating chunk "
                f"{index + 1}/{len(chunks)}"
            )

            tts.New(
                chunk
            )

            source = "output.mp3"

            if not os.path.exists(
                source
            ):

                raise RuntimeError(
                    "TikTok TTS did not create "
                    "output.mp3."
                )

            filename = os.path.join(

                temp_dir,

                f"tts_part_{index:03d}.mp3",
            )

            shutil.move(
                source,
                filename,
            )

            temp_files.append(
                filename
            )

        # --------------------------------------------------------------
        # Load generated audio.
        # --------------------------------------------------------------

        for filename in temp_files:

            clip = AudioFileClip(
                filename
            )

            clips.append(
                clip
            )

        if not clips:

            raise RuntimeError(
                "No TTS audio clips were generated."
            )

        # --------------------------------------------------------------
        # Concatenate.
        # --------------------------------------------------------------

        final = concatenate_audioclips(
            clips
        )

        output_dir = os.path.dirname(
            out_path
        )

        if output_dir:

            os.makedirs(
                output_dir,
                exist_ok=True,
            )

        print(
            f"Audio duration: "
            f"{final.duration:.2f}s"
        )

        final.write_audiofile(

            out_path,

            codec="mp3",

            fps=SAMPLE_RATE,

            logger=None,
        )

        final.close()

        print(
            f"✅ Narration saved: "
            f"{out_path}"
        )

        return out_path

    finally:

        # --------------------------------------------------------------
        # Close clips.
        # --------------------------------------------------------------

        for clip in clips:

            try:

                clip.close()

            except Exception:

                pass

        # --------------------------------------------------------------
        # Remove temporary files.
        # --------------------------------------------------------------

        for filename in temp_files:

            try:

                if os.path.exists(
                    filename
                ):

                    os.remove(
                        filename
                    )

            except Exception:

                pass

        try:

            shutil.rmtree(
                temp_dir,
                ignore_errors=True,
            )

        except Exception:

            pass


# ==========================================================================
# SCENE-BY-SCENE NARRATION
# ==========================================================================

def synthesize_script(
    script,
    config,
    workdir,
):
    """
    Generate narration from the storyboard.

    IMPORTANT:

    Each scene is synthesized separately.

    Scene pauses are preserved.

    The final result is still returned
    as one MP3 path so main.py and
    assemble.py remain compatible.
    """

    os.makedirs(
        workdir,
        exist_ok=True,
    )

    scenes = script.get(
        "scene_plan",
        [],
    )

    if not isinstance(
        scenes,
        list,
    ) or not scenes:

        raise RuntimeError(
            "Script contains no scene_plan."
        )

    print("=" * 80)
    print("🎙️ GENERATING SCENE NARRATION")
    print("=" * 80)

    temp_dir = os.path.join(
        workdir,
        "_tts_scenes",
    )

    os.makedirs(
        temp_dir,
        exist_ok=True,
    )

    scene_audio_files = []

    pause_clips = []

    try:

        # --------------------------------------------------------------
        # Generate each scene.
        # --------------------------------------------------------------

        for scene_index, scene in enumerate(
            scenes,
            start=1,
        ):

            narration = clean_text(

                scene.get(
                    "narration",
                    "",
                )
            )

            if not narration:

                print(
                    f"⚠️ Scene {scene_index} "
                    "has no narration."
                )

                continue

            print("=" * 80)

            print(
                f"SCENE {scene_index}/{len(scenes)}"
            )

            print(
                narration
            )

            print("=" * 80)

            scene_path = os.path.join(

                temp_dir,

                f"scene_{scene_index:02d}.mp3",
            )

            synthesize_narration(

                narration,

                config,

                scene_path,
            )

            scene_audio_files.append(
                scene_path
            )

        if not scene_audio_files:

            raise RuntimeError(
                "No scene narration was generated."
            )

        # --------------------------------------------------------------
        # Load scene audio.
        # --------------------------------------------------------------

        clips = []

        for index, path in enumerate(
            scene_audio_files
        ):

            clip = AudioFileClip(
                path
            )

            clips.append(
                clip
            )

            # ----------------------------------------------------------
            # Add scene pause AFTER this scene.
            # ----------------------------------------------------------

            scene_index = index

            if scene_index < len(
                scenes
            ):

                pause_ms = scene_indexed_pause(
                    scenes[
                        scene_index
                    ]
                )

                if pause_ms > 0:

                    silence = create_silence(
                        pause_ms / 1000.0
                    )

                    if silence:

                        clips.append(
                            silence
                        )

                        pause_clips.append(
                            silence
                        )

        # --------------------------------------------------------------
        # Final narration.
        # --------------------------------------------------------------

        final = concatenate_audioclips(
            clips
        )

        output_path = os.path.join(

            workdir,

            "story.mp3",
        )

        print("=" * 80)
        print("🎧 FINAL NARRATION")
        print("=" * 80)

        print(
            f"Duration: "
            f"{final.duration:.2f}s"
        )

        final.write_audiofile(

            output_path,

            codec="mp3",

            fps=SAMPLE_RATE,

            logger=None,
        )

        final.close()

        # --------------------------------------------------------------
        # Close all clips.
        # --------------------------------------------------------------

        for clip in clips:

            try:

                clip.close()

            except Exception:

                pass

        for silence in pause_clips:

            try:

                silence.close()

            except Exception:

                pass

        print(
            f"✅ Final narration: "
            f"{output_path}"
        )

        return [output_path]

    finally:

        # --------------------------------------------------------------
        # Remove temporary scene audio.
        # --------------------------------------------------------------

        if os.path.exists(
            temp_dir
        ):

            shutil.rmtree(
                temp_dir,
                ignore_errors=True,
            )


# ==========================================================================
# PAUSE HELPER
# ==========================================================================

def scene_indexed_pause(
    scene,
):
    """
    Return scene pause in seconds.
    """

    try:

        pause_ms = float(

            scene.get(
                "pause_after_ms",
                DEFAULT_PAUSE_MS,
            )
        )

    except Exception:

        pause_ms = 0

    pause_ms = max(
        0,
        pause_ms,
    )

    # Keep pauses short enough for Shorts.
    pause_ms = min(
        pause_ms,
        600,
    )

    return pause_ms / 1000.0