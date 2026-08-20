"""
tts.py
Mint-YT-Factory

Version 8.2 — CHUNKED TIKTOK TTS

PURPOSE
-------
Generate ONE continuous narration from the complete story.

TikTokTTS has an internal hard limit of 300 UTF-8 characters per
request. Therefore the complete narration is split into natural
sentence-aware chunks.

IMPORTANT
---------
This is NOT scene-level TTS.

There are:
    - No scene audio files
    - No artificial scene pauses
    - No word splitting
    - No arbitrary character splitting where avoidable
    - No crossfade
    - No fallback voice

There ARE:
    - Multiple TikTok TTS requests when required
    - Natural sentence-boundary chunking
    - ONE final story.mp3

The original narration is preserved.

Pronunciation corrections are applied ONLY to the text sent to
TikTok TTS.

Final output:

    workdir/story.mp3

Compatible with main.py and assemble.py.
"""

import os
import re
import traceback

from moviepy.editor import AudioFileClip, concatenate_audioclips

from tiktoktts import TTS


# ==========================================================================
# CONFIG
# ==========================================================================

SAMPLE_RATE = 44100

NARRATION_SPEED = 0.90

# TikTokTTS internally rejects >300 UTF-8 characters.
# Keep a safety margin rather than targeting exactly 300.
TIKTOK_MAX_CHARS = 300
TIKTOK_SAFE_CHARS = 285


# ==========================================================================
# PRONUNCIATION CORRECTIONS
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

def clean_text(text):

    if not text:
        return ""

    text = str(text)

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

def build_tts_pronunciation_text(text):

    text = clean_text(text)

    if not text:
        return ""

    result = text

    for original, replacement in PRONUNCIATION_REPLACEMENTS.items():

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

    return clean_text(result)


# ==========================================================================
# UTF-8 LENGTH
# ==========================================================================

def utf8_length(text):

    return len(
        text.encode("utf-8")
    )


# ==========================================================================
# SENTENCE SPLITTING
# ==========================================================================

def split_sentences(text):

    text = clean_text(text)

    if not text:
        return []

    # Split after normal sentence punctuation.
    #
    # Lookbehind keeps punctuation attached to the sentence.
    sentences = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    sentences = [
        clean_text(sentence)
        for sentence in sentences
        if clean_text(sentence)
    ]

    return sentences


# ==========================================================================
# HARD SPLIT
# ==========================================================================

def hard_split_text(
    text,
    max_chars=TIKTOK_SAFE_CHARS,
):
    """
    Split a single oversized sentence without breaking words unless
    absolutely necessary.

    This is only used when an individual sentence itself exceeds
    TikTok's request limit.
    """

    text = clean_text(text)

    if not text:
        return []

    words = text.split()

    chunks = []
    current = ""

    for word in words:

        candidate = (
            word
            if not current
            else current + " " + word
        )

        if utf8_length(candidate) <= max_chars:

            current = candidate

            continue

        if current:

            chunks.append(
                current
            )

        # --------------------------------------------------------------
        # A single word may itself be too long.
        # Extremely rare, but handle it safely.
        # --------------------------------------------------------------

        if utf8_length(word) <= max_chars:

            current = word

        else:

            raw = word

            while utf8_length(raw) > max_chars:

                piece = raw[:max_chars]

                # UTF-8 safety.
                while utf8_length(piece) > max_chars:

                    piece = piece[:-1]

                chunks.append(
                    piece
                )

                raw = raw[len(piece):]

            current = raw

    if current:

        chunks.append(
            current
        )

    return chunks


# ==========================================================================
# BUILD TIKTOK CHUNKS
# ==========================================================================

def build_tiktok_chunks(text):

    text = clean_text(text)

    if not text:
        return []

    sentences = split_sentences(
        text
    )

    chunks = []

    current = ""

    for sentence in sentences:

        sentence_length = utf8_length(
            sentence
        )

        # --------------------------------------------------------------
        # Normal sentence fits.
        # --------------------------------------------------------------

        if sentence_length <= TIKTOK_SAFE_CHARS:

            candidate = (
                sentence
                if not current
                else current + " " + sentence
            )

            if utf8_length(candidate) <= TIKTOK_SAFE_CHARS:

                current = candidate

            else:

                if current:

                    chunks.append(
                        current
                    )

                current = sentence

            continue

        # --------------------------------------------------------------
        # Sentence itself is too large.
        # Flush current chunk first.
        # --------------------------------------------------------------

        if current:

            chunks.append(
                current
            )

            current = ""

        # --------------------------------------------------------------
        # Break oversized sentence by words.
        # --------------------------------------------------------------

        sentence_chunks = hard_split_text(
            sentence,
            TIKTOK_SAFE_CHARS,
        )

        chunks.extend(
            sentence_chunks
        )

    if current:

        chunks.append(
            current
        )

    # ------------------------------------------------------------------
    # Final safety verification.
    # ------------------------------------------------------------------

    for index, chunk in enumerate(
        chunks,
        start=1,
    ):

        length = utf8_length(
            chunk
        )

        if length > TIKTOK_MAX_CHARS:

            raise RuntimeError(
                f"TikTok chunk {index} exceeds "
                f"the hard 300-character limit: "
                f"{length} UTF-8 characters."
            )

    return chunks


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
            1.25,
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
    request_number,
):

    print()
    print("=" * 80)
    print("❌ TIKTOK TTS REQUEST FAILED")
    print("=" * 80)

    print(
        f"Request: {request_number}"
    )

    print(
        f"Exception type: {type(error).__name__}"
    )

    print(
        f"Exception message: {error}"
    )

    print()
    print("Narration information:")

    print(
        f"Characters: {len(text)}"
    )

    print(
        f"UTF-8 characters: {utf8_length(text)}"
    )

    print()
    print("Traceback:")

    traceback.print_exc()

    print("=" * 80)
    print()


# ==========================================================================
# GENERATE ONE TIKTOK CHUNK
# ==========================================================================

def generate_tiktok_chunk(
    text,
    voice,
    request_number,
):

    source = "output.mp3"

    if os.path.exists(source):

        try:

            os.remove(source)

        except Exception as error:

            raise RuntimeError(
                "Could not remove stale output.mp3."
            ) from error

    print()
    print(
        f"🎤 TikTok TTS request "
        f"{request_number}"
    )

    print(
        f"Characters: {len(text)}"
    )

    print(
        f"UTF-8 characters: "
        f"{utf8_length(text)}"
    )

    print(
        f"Text: {text}"
    )

    tts = TTS()

    tts.SetVoice(
        voice
    )

    try:

        tts.New(
            text
        )

    except Exception as error:

        print_tiktok_error(
            error,
            text,
            request_number,
        )

        raise RuntimeError(
            f"TikTok TTS request "
            f"{request_number} failed."
        ) from error

    if not os.path.exists(source):

        raise RuntimeError(
            f"TikTok TTS request "
            f"{request_number} completed without "
            f"creating output.mp3."
        )

    # ------------------------------------------------------------------
    # Move the generated file to a unique filename.
    # ------------------------------------------------------------------

    chunk_path = os.path.abspath(
        f"tiktok_chunk_{request_number}.mp3"
    )

    if os.path.exists(chunk_path):

        os.remove(
            chunk_path
        )

    os.replace(
        source,
        chunk_path
    )

    return chunk_path


# ==========================================================================
# SYNTHESIZE NARRATION
# ==========================================================================

def synthesize_narration(
    text,
    config,
    out_path,
):

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
    # Build chunks.
    # ----------------------------------------------------------------------

    chunks = build_tiktok_chunks(
        tts_text
    )

    if not chunks:

        raise RuntimeError(
            "No TikTok TTS chunks were generated."
        )

    print()
    print("=" * 80)
    print("🎙️ TIKTOK TTS — CHUNKED CONTINUOUS NARRATION")
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
        f"TTS UTF-8 characters: "
        f"{utf8_length(tts_text)}"
    )

    print(
        f"Chunks: {len(chunks)}"
    )

    print(
        f"Maximum chunk size: "
        f"{max(utf8_length(c) for c in chunks)}"
    )

    print(
        f"Narration speed: "
        f"{NARRATION_SPEED:.2f}x"
    )

    print()
    print("TTS REQUEST MODE")
    print("----------------")

    print(
        f"Requests: {len(chunks)}"
    )

    print(
        "Sentence-aware chunking: ENABLED"
    )

    print(
        f"Safe chunk limit: "
        f"{TIKTOK_SAFE_CHARS}"
    )

    print(
        "Scene-level TTS: DISABLED"
    )

    print(
        "Word-level TTS: DISABLED"
    )

    print(
        "Artificial gaps: DISABLED"
    )

    print(
        "Scene pauses: DISABLED"
    )

    print(
        "Crossfade: DISABLED"
    )

    print(
        "Fallback voice: DISABLED"
    )

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
    # Generate chunks.
    # ----------------------------------------------------------------------

    chunk_paths = []

    clips = []

    processed_clips = []

    try:

        for index, chunk in enumerate(
            chunks,
            start=1,
        ):

            chunk_path = generate_tiktok_chunk(
                chunk,
                voice,
                index,
            )

            chunk_paths.append(
                chunk_path
            )

        # --------------------------------------------------------------
        # Load all generated audio.
        # --------------------------------------------------------------

        print()
        print("=" * 80)
        print("🎧 ASSEMBLING CONTINUOUS NARRATION")
        print("=" * 80)

        for index, chunk_path in enumerate(
            chunk_paths,
            start=1,
        ):

            clip = AudioFileClip(
                chunk_path
            )

            clips.append(
                clip
            )

            print(
                f"Chunk {index}: "
                f"{clip.duration:.2f}s"
            )

        # --------------------------------------------------------------
        # Concatenate with ZERO artificial silence.
        # --------------------------------------------------------------

        combined = concatenate_audioclips(
            clips
        )

        print()
        print(
            f"Raw combined duration: "
            f"{combined.duration:.2f}s"
        )

        # --------------------------------------------------------------
        # Apply narration speed AFTER concatenation.
        # --------------------------------------------------------------

        # Keep the complete narration inside the YouTube Shorts 60s limit.
        # Never truncate the final sentence. If natural TTS is longer than
        # 60s, increase playback speed only as much as necessary.
        max_duration = 59.70
        required_speed = max(
            1.0,
            combined.duration / max_duration,
        )
        effective_speed = min(
            max(1.0, required_speed),
            1.25,
        )

        if effective_speed > 1.0:
            print(
                f"⏱️ Long narration detected: {combined.duration:.2f}s. "
                f"Compressing to <=60s at {effective_speed:.3f}x without cutting content."
            )

        processed = apply_narration_speed(
            combined,
            effective_speed,
        )

        processed_clips.append(
            processed
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
        print("✅ TIKTOK TTS NARRATION SUCCESS")
        print("=" * 80)

        print(
            f"Output: {out_path}"
        )

        print(
            f"TikTok TTS requests: "
            f"{len(chunks)}"
        )

        print(
            "Final audio files: 1"
        )

        print(
            "Scene audio files: 0"
        )

        print(
            "Artificial gaps: 0"
        )

        print(
            "Scene pauses: 0"
        )

        print("=" * 80)

        return out_path

    finally:

        # --------------------------------------------------------------
        # Close processed audio.
        # --------------------------------------------------------------

        for clip in processed_clips:

            try:
                clip.close()
            except Exception:
                pass

        # --------------------------------------------------------------
        # Close source clips.
        # --------------------------------------------------------------

        for clip in clips:

            try:
                clip.close()
            except Exception:
                pass

        # --------------------------------------------------------------
        # Remove temporary TikTok files.
        # --------------------------------------------------------------

        for chunk_path in chunk_paths:

            try:

                if os.path.exists(
                    chunk_path
                ):

                    os.remove(
                        chunk_path
                    )

            except Exception:

                pass

        # --------------------------------------------------------------
        # Remove stale output.mp3.
        # --------------------------------------------------------------

        try:

            if os.path.exists(
                "output.mp3"
            ):

                os.remove(
                    "output.mp3"
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
    # ----------------------------------------------------------------------

    full_narration = " ".join(
        narration_parts
    )

    print()
    print("=" * 80)
    print("🎙️ COMPLETE STORY → TIKTOK TTS")
    print("=" * 80)

    print(
        f"Scenes: {len(narration_parts)}"
    )

    print(
        f"Total characters: "
        f"{len(full_narration)}"
    )

    print(
        f"Total UTF-8 characters: "
        f"{utf8_length(full_narration)}"
    )

    print()
    print("The complete story remains ONE narration.")

    print()
    print("TikTok's 300-character request limit requires")
    print("the narration to be sent as multiple requests.")

    print()
    print("There will be:")

    print(
        "  ❌ No scene-level TTS"
    )

    print(
        "  ❌ No word splitting"
    )

    print(
        "  ❌ No artificial gaps"
    )

    print(
        "  ❌ No scene pauses"
    )

    print(
        "  ❌ No crossfade"
    )

    print(
        "  ❌ No fallback voice"
    )

    print()

    print(
        "  ✅ Sentence-aware chunks"
    )

    print(
        "  ✅ Multiple TikTok requests when required"
    )

    print(
        "  ✅ One continuous final narration"
    )

    print(
        "  ✅ One final story.mp3"
    )

    print("=" * 80)

    # ----------------------------------------------------------------------
    # Output.
    # ----------------------------------------------------------------------

    output_path = os.path.join(
        workdir,
        "story.mp3",
    )

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
            "Final audio files: 1"
        )

        print(
            "Local temporary chunks: removed"
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

    Scene pauses remain disabled.
    """

    return 0.0