"""
tts.py
Mint-YT-Factory

Version 8.1 — SINGLE-SHOT TIKTOK TTS TEST

PURPOSE
-------
Send the ENTIRE story narration to TikTok TTS in ONE request.

IMPORTANT TEST RULE
-------------------
There is NO local chunking.

There is NO 300-byte limit.

There is NO sentence splitting.

There is NO word splitting.

There is NO scene-by-scene TTS.

There is NO fallback to chunks.

If TikTok/TikTokTTS rejects the complete narration,
the pipeline FAILS and prints the complete error information
so we can identify the actual limitation.

The original narration is preserved.

Pronunciation corrections are applied ONLY to the text
sent to TikTok TTS.

The final output remains:

    workdir/story.mp3

Compatible with main.py and assemble.py.
"""


import os
import re
import traceback

from moviepy.editor import AudioFileClip

from tiktoktts import TTS


# ==========================================================================
# CONFIG
# ==========================================================================

SAMPLE_RATE = 44100

NARRATION_SPEED = 0.90


# ==========================================================================
# PRONUNCIATION CORRECTIONS
# ==========================================================================
#
# These replacements affect ONLY the text sent to TikTok TTS.
#
# The original script narration remains unchanged.
# Therefore Whisper captions still correspond to the original narration.
# ==========================================================================

PRONUNCIATION_REPLACEMENTS = {

    "insects": "in-sects",
    "insect": "in-sect",

    "noise": "noyz",
    "noises": "noy-ziz",

    "species": "spee-sheez",

    "scientific": "sigh-en-TIF-ik",
    "scientifically": "sigh-en-TIF-ik-lee",

    "environment": "en-vy-run-ment",
    "environments": "en-vy-run-ments",

    "organism": "OR-guh-niz-um",
    "organisms": "OR-guh-niz-ums",

}


# ==========================================================================
# TEXT CLEANING
# ==========================================================================

def clean_text(
    text,
):

    if not text:

        return ""

    text = str(
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

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
# TTS PRONUNCIATION TEXT
# ==========================================================================

def build_tts_pronunciation_text(
    text,
):

    text = clean_text(
        text
    )

    if not text:

        return ""

    result = text

    for original, replacement in (
        PRONUNCIATION_REPLACEMENTS.items()
    ):

        pattern = (
            r"(?<![\w'-])"
            + re.escape(original)
            + r"(?![\w'-])"
        )

        result = re.sub(
            pattern,
            replacement,
            result,
            flags=re.IGNORECASE,
        )

    return clean_text(
        result
    )


# ==========================================================================
# NARRATION SPEED
# ==========================================================================

def apply_narration_speed(
    clip,
    speed=NARRATION_SPEED,
):

    try:

        speed = float(
            speed
        )

    except Exception:

        speed = 1.0

    speed = max(
        0.80,
        min(
            speed,
            1.10,
        ),
    )

    if abs(
        speed - 1.0
    ) < 0.001:

        return clip

    try:

        from moviepy.audio.fx.all import speedx

        return speedx(
            clip,
            factor=speed,
        )

    except Exception as error:

        print(
            "⚠️ Narration speed adjustment failed."
        )

        print(
            f"Error type: {type(error).__name__}"
        )

        print(
            f"Error: {error}"
        )

        print(
            "Using original TikTok TTS speed."
        )

        return clip


# ==========================================================================
# TIKTOK ERROR REPORTING
# ==========================================================================

def print_tiktok_error(
    error,
    text,
):

    print()
    print("=" * 80)
    print("❌ TIKTOK TTS REQUEST FAILED")
    print("=" * 80)

    print(
        f"Exception type: {type(error).__name__}"
    )

    print(
        f"Exception message: {error}"
    )

    print()
    print("Full exception representation:")
    print(
        repr(error)
    )

    print()
    print("Narration information:")
    print(
        f"Characters sent: {len(text)}"
    )

    print(
        f"UTF-8 bytes sent: {len(text.encode('utf-8'))}"
    )

    print()
    print("IMPORTANT:")
    print(
        "This request was intentionally sent as ONE single "
        "TikTok TTS request."
    )

    print(
        "NO local 300-byte limit was applied."
    )

    print(
        "NO local chunking was applied."
    )

    print(
        "NO fallback TTS request was attempted."
    )

    print()
    print("Traceback:")
    traceback.print_exc()

    print("=" * 80)
    print()


# ==========================================================================
# SINGLE-SHOT TTS
# ==========================================================================

def synthesize_narration(
    text,
    config,
    out_path,
):
    """
    Send the COMPLETE narration to TikTok TTS exactly once.

    There is deliberately NO:

    - byte limit
    - character limit
    - sentence splitting
    - word splitting
    - chunking
    - chunk gap
    - scene pause
    - crossfade
    - fallback request

    If TikTok rejects the request, the exception is printed and raised.
    """

    original_text = clean_text(
        text
    )

    if not original_text:

        raise RuntimeError(
            "Cannot synthesize empty narration."
        )

    # ----------------------------------------------------------------------
    # Pronunciation-adjusted copy.
    # ----------------------------------------------------------------------

    tts_text = build_tts_pronunciation_text(
        original_text
    )

    # ----------------------------------------------------------------------
    # Voice configuration.
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # Logging.
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🎙️ TIKTOK TTS — SINGLE REQUEST TEST")
    print("=" * 80)

    print(
        f"Voice: {voice}"
    )

    print(
        f"Original characters: "
        f"{len(original_text)}"
    )

    print(
        f"TTS characters: "
        f"{len(tts_text)}"
    )

    print(
        f"TTS UTF-8 bytes: "
        f"{len(tts_text.encode('utf-8'))}"
    )

    print(
        f"Narration speed: "
        f"{NARRATION_SPEED:.2f}x"
    )

    print()
    print("TTS REQUEST MODE")
    print("----------------")
    print("Requests: 1")
    print("Chunking: DISABLED")
    print("Sentence splitting: DISABLED")
    print("Word splitting: DISABLED")
    print("300-byte limit: DISABLED")
    print("Character limit: DISABLED")
    print("Chunk gaps: DISABLED")
    print("Scene pauses: DISABLED")
    print("Crossfade: DISABLED")
    print("Fallback request: DISABLED")

    # ----------------------------------------------------------------------
    # Pronunciation logging.
    # ----------------------------------------------------------------------

    if original_text != tts_text:

        print()
        print(
            "🔊 TTS pronunciation corrections applied."
        )

        print()
        print("ORIGINAL:")
        print(
            original_text
        )

        print()
        print("TTS VERSION:")
        print(
            tts_text
        )

    # ----------------------------------------------------------------------
    # Create TTS.
    # ----------------------------------------------------------------------

    print()
    print("=" * 80)
    print("🎤 SENDING COMPLETE NARRATION TO TIKTOK")
    print("=" * 80)

    print(
        "The following text is being sent in ONE request:"
    )

    print()

    print(
        tts_text
    )

    print()
    print("=" * 80)

    tts = TTS()

    tts.SetVoice(
        voice
    )

    # ----------------------------------------------------------------------
    # tiktoktts writes to output.mp3.
    # ----------------------------------------------------------------------

    source = "output.mp3"

    if os.path.exists(
        source
    ):

        try:

            os.remove(
                source
            )

        except Exception as error:

            raise RuntimeError(
                "Could not remove stale output.mp3."
            ) from error

    # ----------------------------------------------------------------------
    # ONE AND ONLY ONE TTS REQUEST.
    # ----------------------------------------------------------------------

    try:

        tts.New(
            tts_text
        )

    except Exception as error:

        print_tiktok_error(
            error,
            tts_text,
        )

        raise RuntimeError(
            "TikTok TTS rejected the single-shot narration request."
        ) from error

    # ----------------------------------------------------------------------
    # Verify output.
    # ----------------------------------------------------------------------

    if not os.path.exists(
        source
    ):

        raise RuntimeError(
            "TikTok TTS returned without an exception, "
            "but output.mp3 was not created."
        )

    # ----------------------------------------------------------------------
    # Load generated audio.
    # ----------------------------------------------------------------------

    clip = None
    processed = None

    try:

        clip = AudioFileClip(
            source
        )

        print()
        print(
            f"Raw TikTok audio duration: "
            f"{clip.duration:.2f}s"
        )

        # --------------------------------------------------------------
        # Speed adjustment happens AFTER TikTok generates the audio.
        # --------------------------------------------------------------

        processed = apply_narration_speed(
            clip,
            NARRATION_SPEED,
        )

        print(
            f"Final narration duration: "
            f"{processed.duration:.2f}s"
        )

        # --------------------------------------------------------------
        # Output directory.
        # --------------------------------------------------------------

        output_dir = os.path.dirname(
            out_path
        )

        if output_dir:

            os.makedirs(
                output_dir,
                exist_ok=True,
            )

        # --------------------------------------------------------------
        # Save final audio.
        # --------------------------------------------------------------

        processed.write_audiofile(
            out_path,
            codec="mp3",
            fps=SAMPLE_RATE,
            logger=None,
        )

        print()
        print("=" * 80)
        print("✅ SINGLE-SHOT TIKTOK TTS SUCCESS")
        print("=" * 80)

        print(
            f"Output: {out_path}"
        )

        print(
            f"Duration: {processed.duration:.2f}s"
        )

        print(
            "TikTok TTS requests: 1"
        )

        print(
            "Audio chunks generated locally: 0"
        )

        print(
            "Artificial gaps: 0"
        )

        print("=" * 80)

        return out_path

    finally:

        try:

            if processed is not None:

                processed.close()

        except Exception:

            pass

        try:

            if clip is not None:

                clip.close()

        except Exception:

            pass

        # --------------------------------------------------------------
        # Remove TikTok temporary file.
        # --------------------------------------------------------------

        try:

            if os.path.exists(
                source
            ):

                os.remove(
                    source
                )

        except Exception:

            pass


# ==========================================================================
# COMPLETE SCRIPT NARRATION
# ==========================================================================

def synthesize_script(
    script,
    config,
    workdir,
):
    """
    Combine all scene narration into ONE text string and send it
    to TikTok TTS exactly ONCE.

    Example:

        Scene 1 narration
        Scene 2 narration
        Scene 3 narration
        ...
        Scene 7 narration

                    ↓

        ONE continuous text string

                    ↓

        tts.New(full_narration)

                    ↓

        ONE TikTok-generated audio file

                    ↓

        story.mp3

    No scene audio files are created.
    No scene audio is concatenated.
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

    # ----------------------------------------------------------------------
    # Extract scene narration.
    # ----------------------------------------------------------------------

    narration_parts = []

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
                "has no narration. Skipping."
            )

            continue

        print(
            f"Scene {scene_index}: "
            f"{len(narration)} characters"
        )

        narration_parts.append(
            narration
        )

    if not narration_parts:

        raise RuntimeError(
            "No narration was found in scene_plan."
        )

    # ----------------------------------------------------------------------
    # One continuous narration string.
    #
    # Normal spaces are used.
    # No artificial silence is inserted.
    # ----------------------------------------------------------------------

    full_narration = " ".join(
        narration_parts
    )

    print()
    print("=" * 80)
    print("🎙️ COMPLETE STORY → SINGLE TIKTOK TTS REQUEST")
    print("=" * 80)

    print(
        f"Scenes: {len(narration_parts)}"
    )

    print(
        f"Total characters: "
        f"{len(full_narration)}"
    )

    print(
        f"Total UTF-8 bytes: "
        f"{len(full_narration.encode('utf-8'))}"
    )

    print()
    print("The COMPLETE story will be sent to TikTok TTS")
    print("in ONE request.")
    print()
    print("There will be:")
    print("  ❌ No chunking")
    print("  ❌ No 300-byte restriction")
    print("  ❌ No scene-level TTS")
    print("  ❌ No sentence splitting")
    print("  ❌ No word splitting")
    print("  ❌ No artificial gaps")
    print("  ❌ No scene pauses")
    print("  ❌ No fallback request")
    print()
    print("There will be:")
    print("  ✅ ONE TikTok TTS request")
    print("  ✅ ONE generated narration")
    print("  ✅ ONE final story.mp3")

    print("=" * 80)

    # ----------------------------------------------------------------------
    # Output.
    # ----------------------------------------------------------------------

    output_path = os.path.join(
        workdir,
        "story.mp3",
    )

    # ----------------------------------------------------------------------
    # ONE SINGLE TTS CALL.
    # ----------------------------------------------------------------------

    synthesize_narration(
        full_narration,
        config,
        output_path,
    )

    if not os.path.exists(
        output_path
    ):

        raise RuntimeError(
            "TTS finished without creating story.mp3."
        )

    # ----------------------------------------------------------------------
    # Verify final audio.
    # ----------------------------------------------------------------------

    verification_clip = None

    try:

        verification_clip = AudioFileClip(
            output_path
        )

        print()
        print("=" * 80)
        print("🎧 FINAL NARRATION")
        print("=" * 80)

        print(
            f"File: {output_path}"
        )

        print(
            f"Duration: "
            f"{verification_clip.duration:.2f}s"
        )

        print(
            "TikTok TTS requests: 1"
        )

        print(
            "Local audio chunks: 0"
        )

        print(
            "Scene audio files: 0"
        )

        print(
            "Artificial gaps: 0"
        )

        print("=" * 80)

    finally:

        try:

            if verification_clip is not None:

                verification_clip.close()

        except Exception:

            pass

    return [
        output_path
    ]


# ==========================================================================
# LEGACY COMPATIBILITY
# ==========================================================================

def scene_indexed_pause(
    scene,
):
    """
    Legacy compatibility.

    Scene pauses are disabled.
    """

    return 0.0