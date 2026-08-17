"""
tts.py
Mint-YT-Factory

Version 7.6

TikTok TTS narration engine.

Features:
- Sentence-aware TTS chunking
- 300-byte TikTok TTS safety limit
- Prevents awkward sentence/word cuts between TTS chunks
- No crossfade between TTS chunks
- Adjustable narration speed
- Scene-by-scene narration
- Preserves scene pauses
- Small final audio tail added ONLY to final narration
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


# --------------------------------------------------------------------------
# NARRATION SPEED
# --------------------------------------------------------------------------
#
# 1.00 = normal speed
# 0.95 = 5% slower
# 0.92 = 8% slower
# 0.90 = 10% slower
# 0.85 = 15% slower
#
# Current setting:
# 0.92 = approximately 8% slower
# --------------------------------------------------------------------------

NARRATION_SPEED = 0.92


# --------------------------------------------------------------------------
# FINAL AUDIO TAIL
# --------------------------------------------------------------------------
#
# Small silence after the FINAL spoken word only.
#
# IMPORTANT:
# This is NOT added after every scene.
# --------------------------------------------------------------------------

FINAL_TAIL_MS = 250


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
# PAUSE AUDIO
# ==========================================================================

def create_silence(
    duration,
):

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

    This changes playback speed without changing pitch.
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
# CHUNK AUDIO JOIN
# ==========================================================================

def join_tts_clips(
    clips,
):
    """
    Join TTS chunks sequentially.

    IMPORTANT:
    There is NO crossfade.

    Chunk 2 begins exactly when Chunk 1 ends.
    No overlap.
    No fade-in.
    No fade-out.
    No artificial gap.
    """

    if not clips:

        raise RuntimeError(
            "Cannot join an empty TTS clip list."
        )

    if len(clips) == 1:

        return clips[0]

    # ----------------------------------------------------------------------
    # Direct sequential concatenation.
    #
    # Each chunk plays immediately after the previous chunk.
    # ----------------------------------------------------------------------

    return concatenate_audioclips(
        clips
    )


# ==========================================================================
# FINAL AUDIO TAIL
# ==========================================================================

def add_final_tail(
    clip,
    milliseconds=FINAL_TAIL_MS,
):
    """
    Add a small silence after the FINAL spoken word.

    IMPORTANT:
    This function is called only once on the final combined
    narration, NOT once per scene.
    """

    tail_seconds = (
        max(
            0,
            float(milliseconds),
        )
        / 1000.0
    )

    if tail_seconds <= 0:

        return clip

    silence = create_silence(
        tail_seconds
    )

    if silence is None:

        return clip

    final = concatenate_audioclips(
        [
            clip,
            silence,
        ]
    )

    return final


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

    The final tail is NOT added here.

    This function is used for individual scenes, so adding the
    final tail here would incorrectly add silence after every scene.

    TTS chunks are joined directly with NO crossfade.
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
        "Chunk crossfade: DISABLED"
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
        # Join chunks DIRECTLY.
        #
        # NO CROSSFADE.
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
        # NO FINAL TAIL HERE.
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

    Scene pauses are preserved.

    Narration is slowed to NARRATION_SPEED.

    TTS chunks have NO crossfade.

    The final 250 ms tail is added ONLY after the complete
    narration has been assembled.
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
        "Chunk crossfade: DISABLED"
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

    generated_scene_indices = []

    pause_clips = []

    scene_clips = []

    combined = None

    final = None

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

            generated_scene_indices.append(
                scene_index - 1
            )

        if not scene_audio_files:

            raise RuntimeError(
                "No scene narration was generated."
            )

        # --------------------------------------------------------------
        # Load scene audio and add scene pauses.
        # --------------------------------------------------------------

        for file_index, path in enumerate(
            scene_audio_files
        ):

            clip = AudioFileClip(
                path
            )

            scene_clips.append(
                clip
            )

            actual_scene_index = (
                generated_scene_indices[
                    file_index
                ]
            )

            scene = scenes[
                actual_scene_index
            ]

            # ----------------------------------------------------------
            # scene_indexed_pause() already returns seconds.
            # ----------------------------------------------------------

            pause_seconds = scene_indexed_pause(
                scene
            )

            if pause_seconds > 0:

                silence = create_silence(
                    pause_seconds
                )

                if silence:

                    scene_clips.append(
                        silence
                    )

                    pause_clips.append(
                        silence
                    )

        # --------------------------------------------------------------
        # Combine all scenes.
        # --------------------------------------------------------------

        combined = concatenate_audioclips(
            scene_clips
        )

        print("=" * 80)
        print("🎧 COMBINED NARRATION")
        print("=" * 80)

        print(
            f"Before final tail: "
            f"{combined.duration:.2f}s"
        )

        # --------------------------------------------------------------
        # Add final tail ONCE.
        # --------------------------------------------------------------

        final = add_final_tail(
            combined,
            FINAL_TAIL_MS,
        )

        print(
            f"After final tail: "
            f"{final.duration:.2f}s"
        )

        output_path = os.path.join(
            workdir,
            "story.mp3",
        )

        final.write_audiofile(
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
        # Close final clip.
        # --------------------------------------------------------------

        try:

            if final is not None:

                final.close()

        except Exception:

            pass

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
        # Close silence clips.
        # --------------------------------------------------------------

        for silence in pause_clips:

            try:

                silence.close()

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
# PAUSE HELPER
# ==========================================================================

def scene_indexed_pause(
    scene,
):
    """
    Return scene pause in seconds.

    Input:
        pause_after_ms = milliseconds

    Output:
        seconds

    Maximum pause is capped at 600 ms.
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

    pause_ms = min(
        pause_ms,
        600,
    )

    return pause_ms / 1000.0