"""
tts.py
Mint-YT-Factory

Version 8.3 — CHUNKED TIKTOK TTS WITH TRANSIENT RETRIES

Generate ONE continuous narration from the complete story. TikTokTTS has an
internal hard limit of 300 UTF-8 characters per request, so narration is split
at natural sentence boundaries. Individual TikTok failures are retried with
backoff because the unofficial endpoint can intermittently return HTTP 500.
"""

import os
import re
import time
import traceback

from moviepy.editor import AudioFileClip, concatenate_audioclips
from tiktoktts import TTS

SAMPLE_RATE = 44100
NARRATION_SPEED = 0.90
TIKTOK_MAX_CHARS = 300
TIKTOK_SAFE_CHARS = 285
TIKTOK_REQUEST_RETRIES = 4
TIKTOK_RETRY_DELAYS = (1.5, 3.0, 6.0, 10.0)

PRONUNCIATION_REPLACEMENTS = {
    "insects": "in-sects", "insect": "in-sect",
    "noise": "noyz", "noises": "noy-ziz",
    "species": "spee-sheez",
    "scientific": "sigh-en-TIF-ik",
    "scientifically": "sigh-en-TIF-ik-lee",
    "environment": "en-vy-run-ment",
    "environments": "en-vy-run-ments",
    "organism": "OR-guh-niz-um",
    "organisms": "OR-guh-niz-ums",
}


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"\s+", " ", str(text))
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\?{2,}", "?", text)
    return text.replace("**", "").replace("__", "").strip()


def build_tts_pronunciation_text(text):
    result = clean_text(text)
    for original, replacement in PRONUNCIATION_REPLACEMENTS.items():
        pattern = r"(?<![\w'-])" + re.escape(original) + r"(?![\w'-])"
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return clean_text(result)


def utf8_length(text):
    return len(text.encode("utf-8"))


def split_sentences(text):
    return [
        clean_text(x)
        for x in re.split(r"(?<=[.!?])\s+", clean_text(text))
        if clean_text(x)
    ]


def hard_split_text(text, max_chars=TIKTOK_SAFE_CHARS):
    words = clean_text(text).split()
    chunks, current = [], ""

    for word in words:
        candidate = word if not current else current + " " + word
        if utf8_length(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)

        if utf8_length(word) <= max_chars:
            current = word
        else:
            raw = word
            while utf8_length(raw) > max_chars:
                piece = raw[:max_chars]
                while utf8_length(piece) > max_chars:
                    piece = piece[:-1]
                chunks.append(piece)
                raw = raw[len(piece):]
            current = raw

    if current:
        chunks.append(current)
    return chunks


def build_tiktok_chunks(text):
    sentences = split_sentences(text)
    chunks, current = [], ""

    for sentence in sentences:
        if utf8_length(sentence) <= TIKTOK_SAFE_CHARS:
            candidate = sentence if not current else current + " " + sentence
            if utf8_length(candidate) <= TIKTOK_SAFE_CHARS:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = sentence
        else:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(hard_split_text(sentence))

    if current:
        chunks.append(current)

    for index, chunk in enumerate(chunks, 1):
        if utf8_length(chunk) > TIKTOK_MAX_CHARS:
            raise RuntimeError(
                f"TikTok chunk {index} exceeds the hard 300-character limit: "
                f"{utf8_length(chunk)} UTF-8 characters."
            )
    return chunks


def apply_narration_speed(clip, speed=NARRATION_SPEED):
    try:
        speed = float(speed)
    except Exception:
        speed = 1.0

    speed = max(0.80, min(speed, 1.10))
    if abs(speed - 1.0) < 0.001:
        return clip

    try:
        from moviepy.audio.fx.all import speedx
        return speedx(clip, factor=speed)
    except Exception as error:
        print(f"⚠️ Narration speed adjustment failed: {error}")
        return clip


def print_tiktok_error(error, text, request_number, attempt=None):
    print("=" * 80)
    print("❌ TIKTOK TTS REQUEST FAILED")
    print("=" * 80)
    print(f"Request: {request_number}")
    if attempt is not None:
        print(f"Attempt: {attempt}/{TIKTOK_REQUEST_RETRIES}")
    print(f"Exception type: {type(error).__name__}")
    print(f"Exception message: {error}")
    print(f"Characters: {len(text)}")
    print(f"UTF-8 characters: {utf8_length(text)}")
    print("=" * 80)


def generate_tiktok_chunk(text, voice, request_number):
    source = "output.mp3"
    last_error = None

    for attempt in range(1, TIKTOK_REQUEST_RETRIES + 1):
        if os.path.exists(source):
            try:
                os.remove(source)
            except Exception as error:
                raise RuntimeError("Could not remove stale output.mp3.") from error

        print()
        print(
            f"🎤 TikTok TTS request {request_number} — "
            f"attempt {attempt}/{TIKTOK_REQUEST_RETRIES}"
        )
        print(f"Characters: {len(text)}")
        print(f"UTF-8 characters: {utf8_length(text)}")
        print(f"Text: {text}")

        try:
            tts = TTS()
            tts.SetVoice(voice)
            tts.New(text)

            if not os.path.exists(source):
                raise RuntimeError(
                    "TikTok returned successfully but did not create output.mp3."
                )

            chunk_path = os.path.abspath(f"tiktok_chunk_{request_number}.mp3")
            if os.path.exists(chunk_path):
                os.remove(chunk_path)
            os.replace(source, chunk_path)

            print(
                f"✅ TikTok TTS request {request_number} "
                f"succeeded on attempt {attempt}"
            )
            return chunk_path

        except Exception as error:
            last_error = error
            print_tiktok_error(error, text, request_number, attempt)

            if attempt < TIKTOK_REQUEST_RETRIES:
                delay = TIKTOK_RETRY_DELAYS[attempt - 1]
                print(f"🔁 Transient TTS failure. Retrying in {delay:.1f}s...")
                time.sleep(delay)

    raise RuntimeError(
        f"TikTok TTS request {request_number} failed after "
        f"{TIKTOK_REQUEST_RETRIES} attempts."
    ) from last_error


def synthesize_narration(text, config, out_path):
    original_text = clean_text(text)
    if not original_text:
        raise RuntimeError("Cannot synthesize empty narration.")

    tts_text = build_tts_pronunciation_text(original_text)

    voice_config = config.get("voice", {})
    if not isinstance(voice_config, dict):
        voice_config = {}

    voice = voice_config.get("voice_name")
    if not voice:
        raise RuntimeError("config.yaml is missing voice.voice_name.")

    chunks = build_tiktok_chunks(tts_text)
    if not chunks:
        raise RuntimeError("No TikTok TTS chunks were generated.")

    print("\n" + "=" * 80)
    print("🎙️ TIKTOK TTS — CHUNKED CONTINUOUS NARRATION")
    print("=" * 80)
    print(f"Voice: {voice}")
    print(f"Original characters: {len(original_text)}")
    print(f"TTS characters: {len(tts_text)}")
    print(f"TTS UTF-8 characters: {utf8_length(tts_text)}")
    print(f"Chunks: {len(chunks)}")
    print(f"Maximum chunk size: {max(utf8_length(c) for c in chunks)}")
    print(f"Narration speed: {NARRATION_SPEED:.2f}x")
    print("\nTTS REQUEST MODE")
    print("----------------")
    print(f"Requests: {len(chunks)}")
    print("Sentence-aware chunking: ENABLED")
    print(f"Safe chunk limit: {TIKTOK_SAFE_CHARS}")
    print("Transient request retries: ENABLED")
    print(f"Retries per request: {TIKTOK_REQUEST_RETRIES}")
    print("Scene-level TTS: DISABLED")
    print("Word-level TTS: DISABLED")
    print("Artificial gaps: DISABLED")
    print("Scene pauses: DISABLED")
    print("Crossfade: DISABLED")
    print("Fallback voice: DISABLED")

    if original_text != tts_text:
        print("\n🔊 TTS pronunciation corrections applied.")

    chunk_paths, clips = [], []
    combined = None
    processed = None

    try:
        for index, chunk in enumerate(chunks, 1):
            chunk_paths.append(generate_tiktok_chunk(chunk, voice, index))

        print("\n" + "=" * 80)
        print("🎧 ASSEMBLING CONTINUOUS NARRATION")
        print("=" * 80)

        for index, chunk_path in enumerate(chunk_paths, 1):
            clip = AudioFileClip(chunk_path)
            clips.append(clip)
            print(f"Chunk {index}: {clip.duration:.2f}s")

        combined = concatenate_audioclips(clips)
        print(f"Raw combined duration: {combined.duration:.2f}s")

        processed = apply_narration_speed(combined)
        print(f"Final narration duration: {processed.duration:.2f}s")

        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        processed.write_audiofile(
            out_path,
            fps=SAMPLE_RATE,
            codec="libmp3lame",
            bitrate="192k",
            verbose=False,
            logger=None,
        )
        return out_path

    except Exception:
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass
        raise

    finally:
        if processed is not None:
            try:
                processed.close()
            except Exception:
                pass
        if combined is not None:
            try:
                combined.close()
            except Exception:
                pass
        for path in chunk_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
