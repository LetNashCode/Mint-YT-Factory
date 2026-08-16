"""
tts.py
Mint-YT-Factory

Version 7.2

TikTok TTS narration engine.

Fixes:
- Sentence-aware TTS chunking
- 300-byte TikTok TTS safety limit
- Prevents awkward sentence/word cuts between TTS chunks
- Short crossfade between TTS chunks
- Small final audio tail to prevent abrupt ending
- Scene-by-scene narration
- Preserves scene pauses
- Correct scene pause indexing
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
    CompositeAudioClip,
    concatenate_audioclips,
)

from tiktoktts import TTS


# ==========================================================================
# CONFIG
# ==========================================================================

MAX_BYTES = 300

SAMPLE_RATE = 44100

DEFAULT_PAUSE_MS = 0

# Small overlap between independently generated TTS chunks.
# This removes noticeable gaps/clicks between chunks.
CHUNK_CROSSFADE_MS = 60

# Small silence after the final spoken word.
# Prevents the final syllable from feeling abruptly cut off.
FINAL_TAIL_MS = 250


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

    # Normalize whitespace.
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
# SENTENCE SPLITTING
# ==========================================================================

def split_sentences(text):
    """
    Split narration into natural sentence units.

    Sentence boundaries are preferred so TikTok TTS can generate
    complete thoughts with natural prosody.

    This is intentionally conservative and keeps punctuation attached.
    """

    text = clean_text(
        text
    )

    if not text:
        return []

    # Split after normal sentence-ending punctuation.
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
    """
    Extremely long word safety fallback.

    Normally this will never be needed, but it prevents a single
    unusually long token from exceeding TikTok's byte limit.
    """

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
    """
    Split one sentence on word boundaries while respecting
    the TikTok TTS byte limit.

    This function is only used when a complete sentence cannot
    fit into one TTS request.
    """

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

        # Save current chunk.
        if current:

            chunks.append(
                current
            )

        # Handle a single oversized word.
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

                # All but the final piece become complete chunks.
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
    """
    Split narration into TikTok-compatible chunks.

    IMPORTANT:

    Priority is:

    1. Complete sentence
    2. Word boundary
    3. Byte limit

    This is much better than blindly splitting the entire narration
    every 300 bytes because TTS gets complete thoughts whenever possible.
    """

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
        # Best case:
        # Entire sentence fits into one TTS request.
        # --------------------------------------------------------------

        if sentence_bytes <= limit:

            chunks.append(
                sentence
            )

            continue

        # --------------------------------------------------------------
        # Sentence is too long.
        #
        # Only now do we split it by words.
        # --------------------------------------------------------------

        chunks.extend(
            _split_sentence_by_words(
                sentence,
                limit,
            )
        )

    # Final safety validation.
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
# CHUNK AUDIO JOIN
# ==========================================================================

def join_tts_clips(
    clips,
    crossfade_ms=CHUNK_CROSSFADE_MS,
):
    """
    Join independently generated TTS clips with a very short
    crossfade.

    This prevents:
    - tiny clicks
    - hard waveform cuts
    - obvious chunk boundaries
    - unnatural silence between TTS requests

    The overlap is deliberately small so words do not sound doubled.
    """

    if not clips:

        raise RuntimeError(
            "Cannot join an empty TTS clip list."
        )

    if len(clips) == 1:

        return clips[0]

    overlap = (
        max(
            0,
            float(crossfade_ms),
        )
        / 1000.0
    )

    positioned = []

    current_start = 0.0

    for index, clip in enumerate(
        clips
    ):

        # Never allow the overlap to be longer than the clip.
        actual_overlap = min(
            overlap,
            max(
                0.0,
                clip.duration / 2.0,
            ),
        )

        if index == 0:

            start = 0.0

        else:

            start = (
                current_start
                - actual_overlap
            )

        processed = clip

        # Fade in from the previous chunk.
        if actual_overlap > 0:

            try:

                processed = (
                    processed
                    .audio_fadein(
                        actual_overlap
                    )
                )

            except Exception:

                pass

        # Fade out into the next chunk.
        if actual_overlap > 0:

            try:

                processed = (
                    processed
                    .audio_fadeout(
                        actual_overlap
                    )
                )

            except Exception:

                pass

        processed = processed.set_start(
            start
        )

        positioned.append(
            processed
        )

        current_start = (
            start
            + clip.duration
        )

    total_duration = max(
        clip.start + clip.duration
        for clip in positioned
    )

    return CompositeAudioClip(
        positioned
    ).set_duration(
        total_duration
    )


# ==========================================================================
# FINAL AUDIO TAIL
# ==========================================================================

def add_final_tail(
    clip,
    milliseconds=FINAL_TAIL_MS,
):
    """
    Add a small silence after the final spoken word.

    This is intentionally short.
    It prevents the final syllable from feeling chopped off.
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
    Convert one block of narration into audio.

    Text is split at natural sentence boundaries whenever possible.
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

    joined = None

    final = None

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

            # Make sure no stale output.mp3 is reused.
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

        if not clips:

            raise RuntimeError(
                "No TTS audio clips were generated."
            )

        # --------------------------------------------------------------
        # Join chunks with tiny crossfades.
        # --------------------------------------------------------------

        joined = join_tts_clips(
            clips,
            CHUNK_CROSSFADE_MS,
        )

        print(
            f"Joined audio duration: "
            f"{joined.duration:.2f}s"
        )

        # --------------------------------------------------------------
        # Add small final tail.
        # --------------------------------------------------------------

        final = add_final_tail(
            joined,
            FINAL_TAIL_MS,
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
            f"Final audio duration: "
            f"{final.duration:.2f}s"
        )

        final.write_audiofile(
            out_path,
            codec="mp3",
            fps=SAMPLE_RATE,
            logger=None,
        )

        print(
            f"✅ Narration saved: "
            f"{out_path}"
        )

        return out_path

    finally:

        # --------------------------------------------------------------
        # Close joined/final clips.
        # --------------------------------------------------------------

        try:

            if final is not None:
                final.close()

        except Exception:

            pass

        try:

            if joined is not None:
                joined.close()

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

    The final result is returned as one MP3 path so main.py
    and assemble.py remain compatible.
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

    # Keep the actual scene objects that produced audio.
    # This prevents pause indexing errors if a scene has no narration.
    generated_scene_indices = []

    pause_clips = []

    scene_clips = []

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
        # Load scene audio.
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
            # Add pause AFTER this actual scene.
            # ----------------------------------------------------------

            pause_ms = scene_indexed_pause(
                scene
            )

            if pause_ms > 0:

                silence = create_silence(
                    pause_ms / 1000.0
                )

                if silence:

                    scene_clips.append(
                        silence
                    )

                    pause_clips.append(
                        silence
                    )

        # --------------------------------------------------------------
        # Final narration.
        # --------------------------------------------------------------

        final = concatenate_audioclips(
            scene_clips
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