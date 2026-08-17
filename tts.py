"""
tts.py
Mint-YT-Factory

Version 7.6

TikTok TTS narration engine.

Features:
- Sentence-aware TTS chunking
- 300-byte TikTok TTS safety limit
- Prevents awkward sentence/word cuts between TTS chunks
- Direct chunk joining — NO crossfade
- Adjustable narration speed
- Scene-by-scene narration
- Continuous narration — NO scene silences
- NO artificial final audio tail
- Cleans temporary files
- Compatible with main.py
- Compatible with assemble.py

IMPORTANT:

There are NO intentionally generated silences in this version.

Narration is continuous:
    Scene 1 → Scene 2 → Scene 3 → ...

There is also no crossfade between TikTok TTS chunks.
"""


import os
import re
import shutil
import tempfile

from moviepy.editor import (
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
# 1.00 = normal speed
# 0.95 = 5% slower
# 0.92 = 8% slower  ← recommended
# 0.90 = 10% slower
# 0.85 = 15% slower
#
# The generated audio is slowed down rather than adding artificial pauses.
# ==========================================================================

NARRATION_SPEED = 0.92


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

    No silence is added.
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
    Join TTS chunks directly.

    IMPORTANT:
    - No crossfade
    - No overlap
    - No fade-in
    - No fade-out
    - No silence

    Chunk 1 ends.
    Chunk 2 starts immediately.

    This preserves the natural pauses that TikTok TTS itself
    produces from punctuation.
    """

    if not clips:

        raise RuntimeError(
            "Cannot join an empty TTS clip list."
        )

    if len(clips) == 1:

        return clips[0]

    return concatenate_audioclips(
        clips
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

    The audio contains:

    TTS chunk 1
    → TTS chunk 2
    → TTS chunk 3
    → ...

    No artificial silence is inserted.
    No crossfade is used.
    No final tail is added.
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
        "Artificial silence: DISABLED"
    )

    chunks = split_text(
        text
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
        # Directly join chunks.
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

    Scenes are joined directly with NO artificial silence.

    The narration is continuous:

        Scene 1 → Scene 2 → Scene 3 → ...

    There is no:
    - crossfade
    - fade-in
    - fade-out
    - scene pause
    - final silence tail
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
        # No pause_after_ms is read here.
        # No silence clips are created.
        # --------------------------------------------------------------

        for path in scene_audio_files:

            clip = AudioFileClip(
                path
            )

            scene_clips.append(
                clip
            )

        # --------------------------------------------------------------
        # Combine all scenes directly.
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

    Silences are now completely disabled.

    Always returns 0 seconds so that any older code calling
    this function does not break the pipeline.
    """

    return 0.0