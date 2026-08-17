"""
tts.py
Mint-YT-Factory

Version 7.7

TikTok TTS narration engine.

Features:
- Sentence-aware TTS chunking
- 300-byte TikTok TTS safety limit
- Prevents awkward sentence/word cuts between TTS chunks
- Direct chunk joining — NO crossfade
- Very short natural gap ONLY between forced TTS chunks
- Slower narration for improved clarity
- TTS-only pronunciation correction
- Scene-by-scene narration
- Continuous scene narration
- NO scene silences
- NO artificial final audio tail
- Cleans temporary files
- Compatible with main.py
- Compatible with assemble.py

IMPORTANT:

The pronunciation correction is applied ONLY to the text sent
to TikTok TTS.

The original narration remains unchanged.

Example:

Actual narration:
    "The insects create noise."

TTS pronunciation text:
    "The in-sects create noyz."

Captions can therefore still display:

    "The insects create noise."

There is NO crossfade.

There are NO scene pauses.

There is NO final silence tail.

A tiny gap is inserted ONLY when one narration block has to be
split into multiple TikTok TTS chunks because of the byte limit.
"""


import os
import re
import shutil
import tempfile

from moviepy.editor import (
    AudioClip,
    AudioFileClip,
    concatenate_audioclips,
)

from tiktoktts import TTS


# ==========================================================================
# CONFIG
# ==========================================================================

MAX_BYTES = 300

SAMPLE_RATE = 44100


# ==========================================================================
# NARRATION SPEED
# ==========================================================================
#
# 1.00 = normal
# 0.95 = 5% slower
# 0.92 = 8% slower
# 0.90 = 10% slower  ← recommended
# 0.85 = 15% slower
#
# 0.90 gives the voice slightly more time to pronounce each word clearly.
# ==========================================================================

NARRATION_SPEED = 0.90


# ==========================================================================
# TTS CHUNK GAP
# ==========================================================================
#
# This is NOT a scene pause.
#
# It is used ONLY when one narration block has been split into multiple
# TikTok TTS requests because of the 300-byte limit.
#
# Without this gap:
#
#     Chunk 1: "...the insects"
#     Chunk 2: "create..."
#
# can sometimes sound like:
#
#     "...theinsectscreate..."
#
# A very short gap makes the boundary clearer without making the narration
# sound artificially slow.
# ==========================================================================

TTS_CHUNK_GAP_MS = 90


# ==========================================================================
# PRONUNCIATION CORRECTIONS
# ==========================================================================
#
# IMPORTANT:
#
# These replacements are ONLY sent to TikTok TTS.
#
# They do NOT modify:
# - script narration
# - captions
# - subtitles
# - descriptions
# - YouTube metadata
#
# Add new words here if TikTok consistently mispronounces them.
#
# The replacement is deliberately phonetic rather than a dictionary
# spelling.
# ==========================================================================

PRONUNCIATION_REPLACEMENTS = {

    # Common problem observed in testing.
    "insects": "in-sects",
    "insect": "in-sect",

    # Common TikTok TTS pronunciation issue.
    "noise": "noyz",

    # Useful variations.
    "noises": "noy-ziz",

    # Common science words that can occasionally be unclear.
    "species": "spee-sheez",
    "scientific": "sigh-en-TIF-ik",
    "scientifically": "sigh-en-TIF-ik-lee",

    # Often pronounced too quickly.
    "environment": "en-vy-run-ment",
    "environments": "en-vy-run-ments",

    # Useful for educational/science content.
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

def build_tts_pronunciation_text(
    text,
):
    """
    Create the version of the narration that is sent to TikTok TTS.

    IMPORTANT:

    This function does NOT modify the original narration.

    It only changes words that are known to be pronounced poorly
    by the selected TikTok voice.
    """

    text = clean_text(
        text
    )

    if not text:
        return ""

    result = text

    # ----------------------------------------------------------------------
    # Replace words while preserving normal word boundaries.
    # ----------------------------------------------------------------------

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
# SENTENCE SPLITTING
# ==========================================================================

def split_sentences(text):

    text = clean_text(
        text
    )

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    sentences = []

    for part in parts:

        part = part.strip()

        if part:

            sentences.append(
                part
            )

    return sentences


# ==========================================================================
# BYTE-SAFE WORD SPLITTING
# ==========================================================================

def _split_long_word(
    word,
    limit=MAX_BYTES,
):

    encoded = word.encode(
        "utf-8"
    )

    pieces = []

    start = 0

    while start < len(encoded):

        piece = encoded[
            start:
            start + limit
        ]

        decoded = piece.decode(
            "utf-8",
            errors="ignore",
        )

        if decoded:

            pieces.append(
                decoded
            )

        start += limit

    return pieces


def _split_sentence_by_words(
    sentence,
    limit=MAX_BYTES,
):

    words = sentence.split()

    chunks = []

    current = ""

    for word in words:

        candidate = (
            word
            if not current
            else current
            + " "
            + word
        )

        if len(
            candidate.encode(
                "utf-8"
            )
        ) <= limit:

            current = candidate

            continue

        if current:

            chunks.append(
                current
            )

        if len(
            word.encode(
                "utf-8"
            )
        ) > limit:

            pieces = _split_long_word(
                word,
                limit,
            )

            if pieces:

                chunks.extend(
                    pieces[:-1]
                )

                current = pieces[-1]

            else:

                current = ""

        else:

            current = word

    if current:

        chunks.append(
            current
        )

    return chunks


# ==========================================================================
# TEXT SPLITTING
# ==========================================================================

def split_text(
    text,
    limit=MAX_BYTES,
):

    text = clean_text(
        text
    )

    if not text:
        return []

    sentences = split_sentences(
        text
    )

    chunks = []

    for sentence in sentences:

        sentence_bytes = len(
            sentence.encode(
                "utf-8"
            )
        )

        # --------------------------------------------------------------
        # Entire sentence fits.
        # --------------------------------------------------------------

        if sentence_bytes <= limit:

            chunks.append(
                sentence
            )

            continue

        # --------------------------------------------------------------
        # Sentence is too long.
        # Split only at word boundaries.
        # --------------------------------------------------------------

        chunks.extend(
            _split_sentence_by_words(
                sentence,
                limit,
            )
        )

    # --------------------------------------------------------------
    # Final safety validation.
    # --------------------------------------------------------------

    for index, chunk in enumerate(
        chunks
    ):

        size = len(
            chunk.encode(
                "utf-8"
            )
        )

        if size > limit:

            raise RuntimeError(
                f"TTS chunk {index + 1} "
                f"is {size} bytes, exceeding "
                f"the {limit}-byte limit."
            )

    return chunks


# ==========================================================================
# SILENCE BETWEEN FORCED TTS CHUNKS
# ==========================================================================

def create_tts_chunk_gap():
    """
    Create a very short silence used ONLY between separately generated
    TTS chunks.

    This is NOT used between scenes.

    This is NOT used after the final narration.

    This is NOT used between normal words.
    """

    duration = (
        max(
            0,
            float(TTS_CHUNK_GAP_MS),
        )
        / 1000.0
    )

    if duration <= 0:

        return None

    return AudioClip(
        lambda t: 0,
        duration=duration,
        fps=SAMPLE_RATE,
    )


# ==========================================================================
# NARRATION SPEED
# ==========================================================================

def apply_narration_speed(
    clip,
    speed=NARRATION_SPEED,
):
    """
    Adjust narration playback speed.

    speed:
        1.00 = normal
        0.95 = 5% slower
        0.92 = 8% slower
        0.90 = 10% slower
        0.85 = 15% slower

    No crossfade is added.
    """

    try:

        speed = float(
            speed
        )

    except Exception:

        speed = 1.0

    # ----------------------------------------------------------------------
    # Safety range.
    # ----------------------------------------------------------------------

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

        slowed = speedx(
            clip,
            factor=speed,
        )

        return slowed

    except Exception as error:

        print(
            f"⚠️ Could not adjust narration speed: "
            f"{error}"
        )

        print(
            "Using original TTS speed."
        )

        return clip


# ==========================================================================
# DIRECT TTS CHUNK JOIN
# ==========================================================================

def join_tts_clips(
    clips,
):
    """
    Join TTS chunks without crossfade.

    A tiny gap is inserted ONLY between forced chunks.

    There is:

    - NO crossfade
    - NO overlap
    - NO fade-in
    - NO fade-out
    - NO scene pause
    - NO final silence

    Example:

        Chunk 1
        90 ms gap
        Chunk 2
        90 ms gap
        Chunk 3
    """

    if not clips:

        raise RuntimeError(
            "Cannot join an empty TTS clip list."
        )

    if len(clips) == 1:

        return clips[0]

    parts = []

    for index, clip in enumerate(
        clips
    ):

        parts.append(
            clip
        )

        # --------------------------------------------------------------
        # Add tiny gap only between chunks.
        # --------------------------------------------------------------

        if index < len(clips) - 1:

            gap = create_tts_chunk_gap()

            if gap is not None:

                parts.append(
                    gap
                )

    return concatenate_audioclips(
        parts
    )


# ==========================================================================
# SINGLE TTS GENERATION
# ==========================================================================

def synthesize_narration(
    text,
    config,
    out_path,
):
    """
    Convert one scene/block of narration into audio.

    The ORIGINAL text is preserved.

    A separate pronunciation-adjusted copy is sent to TikTok TTS.

    Example:

        Original:
        "The insects create noise."

        TTS:
        "The in-sects create noyz."

    The final audio contains:

        TTS chunk 1
        → tiny boundary gap
        → TTS chunk 2
        → tiny boundary gap
        → TTS chunk 3

    No crossfade.
    No scene pause.
    No final tail.
    """

    original_text = clean_text(
        text
    )

    if not original_text:

        raise RuntimeError(
            "Cannot synthesize empty narration."
        )

    # ----------------------------------------------------------------------
    # Create TTS-only pronunciation version.
    # ----------------------------------------------------------------------

    tts_text = build_tts_pronunciation_text(
        original_text
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

    print(
        f"Narration speed: "
        f"{NARRATION_SPEED:.2f}x"
    )

    print(
        f"Approximate slowdown: "
        f"{(1 - NARRATION_SPEED) * 100:.0f}%"
    )

    print(
        "Crossfade: DISABLED"
    )

    print(
        "Scene silence: DISABLED"
    )

    print(
        "Final silence tail: DISABLED"
    )

    print(
        f"Forced chunk gap: "
        f"{TTS_CHUNK_GAP_MS}ms"
    )

    if (
        original_text
        != tts_text
    ):

        print(
            "🔊 TTS pronunciation correction applied."
        )

        print(
            f"Original: {original_text}"
        )

        print(
            f"TTS text: {tts_text}"
        )

    # ----------------------------------------------------------------------
    # Split the pronunciation-adjusted text.
    #
    # This is important because replacements can change the byte count.
    # ----------------------------------------------------------------------

    chunks = split_text(
        tts_text
    )

    print(
        f"TTS chunks: "
        f"{len(chunks)}"
    )

    for index, chunk in enumerate(
        chunks,
        start=1,
    ):

        print(
            f"   Chunk {index}: "
            f"{len(chunk.encode('utf-8'))} bytes"
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

    processed_clips = []

    joined = None

    gap_clips = []

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

            print(
                f"   {chunk}"
            )

            # ----------------------------------------------------------
            # Prevent stale output.mp3 reuse.
            # ----------------------------------------------------------

            if os.path.exists(
                "output.mp3"
            ):

                try:

                    os.remove(
                        "output.mp3"
                    )

                except Exception:

                    pass

            # ----------------------------------------------------------
            # Generate TikTok TTS.
            # ----------------------------------------------------------

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

            # ----------------------------------------------------------
            # Apply slower narration speed.
            # ----------------------------------------------------------

            processed = apply_narration_speed(
                clip,
                NARRATION_SPEED,
            )

            processed_clips.append(
                processed
            )

        if not processed_clips:

            raise RuntimeError(
                "No TTS audio clips were generated."
            )

        # --------------------------------------------------------------
        # Join chunks.
        # --------------------------------------------------------------

        joined = join_tts_clips(
            processed_clips
        )

        print(
            f"Scene audio duration after speed adjustment: "
            f"{joined.duration:.2f}s"
        )

        output_dir = os.path.dirname(
            out_path
        )

        if output_dir:

            os.makedirs(
                output_dir,
                exist_ok=True,
            )

        # --------------------------------------------------------------
        # Write scene audio.
        #
        # NO final tail.
        # --------------------------------------------------------------

        joined.write_audiofile(
            out_path,
            codec="mp3",
            fps=SAMPLE_RATE,
            logger=None,
        )

        print(
            f"✅ Scene narration saved: "
            f"{out_path}"
        )

        return out_path

    finally:

        # --------------------------------------------------------------
        # Close joined clip.
        # --------------------------------------------------------------

        try:

            if joined is not None:

                joined.close()

        except Exception:

            pass

        # --------------------------------------------------------------
        # Close generated gap clips if any.
        # --------------------------------------------------------------

        for gap in gap_clips:

            try:

                gap.close()

            except Exception:

                pass

        # --------------------------------------------------------------
        # Close processed clips.
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

    Each scene is synthesized separately.

    Scenes are joined directly with NO artificial scene silence.

    The narration is:

        Scene 1 → Scene 2 → Scene 3 → ...

    There is:

    - NO crossfade
    - NO fade-in
    - NO fade-out
    - NO scene pause
    - NO final silence tail

    Only forced TTS chunk boundaries may contain the tiny
    TTS_CHUNK_GAP_MS gap.
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

    print(
        f"Narration speed: "
        f"{NARRATION_SPEED:.2f}x"
    )

    print(
        f"Approximate slowdown: "
        f"{(1 - NARRATION_SPEED) * 100:.0f}%"
    )

    print(
        "Crossfade: DISABLED"
    )

    print(
        "Scene silences: DISABLED"
    )

    print(
        "Final silence tail: DISABLED"
    )

    print(
        f"TTS chunk gap: "
        f"{TTS_CHUNK_GAP_MS}ms"
    )

    temp_dir = os.path.join(
        workdir,
        "_tts_scenes",
    )

    os.makedirs(
        temp_dir,
        exist_ok=True,
    )

    scene_audio_files = []

    scene_clips = []

    combined = None

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
                    "has no narration. Skipping."
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
        #
        # IMPORTANT:
        #
        # pause_after_ms is intentionally ignored.
        #
        # No scene silence is created.
        # --------------------------------------------------------------

        for path in scene_audio_files:

            clip = AudioFileClip(
                path
            )

            scene_clips.append(
                clip
            )

        # --------------------------------------------------------------
        # Combine scenes directly.
        #
        # Scene 1 → Scene 2 → Scene 3
        #
        # No pause.
        # --------------------------------------------------------------

        combined = concatenate_audioclips(
            scene_clips
        )

        print("=" * 80)
        print("🎧 COMBINED NARRATION")
        print("=" * 80)

        print(
            f"Final narration duration: "
            f"{combined.duration:.2f}s"
        )

        print(
            "Crossfade: NONE"
        )

        print(
            "Scene silence: NONE"
        )

        print(
            "Final silence tail: NONE"
        )

        print(
            f"Forced TTS chunk gap: "
            f"{TTS_CHUNK_GAP_MS}ms"
        )

        output_path = os.path.join(
            workdir,
            "story.mp3",
        )

        combined.write_audiofile(
            output_path,
            codec="mp3",
            fps=SAMPLE_RATE,
            logger=None,
        )

        print(
            f"✅ Final narration: "
            f"{output_path}"
        )

        return [output_path]

    finally:

        # --------------------------------------------------------------
        # Close combined clip.
        # --------------------------------------------------------------

        try:

            if combined is not None:

                combined.close()

        except Exception:

            pass

        # --------------------------------------------------------------
        # Close scene clips.
        # --------------------------------------------------------------

        for clip in scene_clips:

            try:

                clip.close()

            except Exception:

                pass

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
# LEGACY PAUSE HELPER
# ==========================================================================

def scene_indexed_pause(
    scene,
):
    """
    Legacy compatibility function.

    Scene silences are completely disabled.

    Always returns 0 seconds so older code calling this function
    does not break the pipeline.
    """

    return 0.0