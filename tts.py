"""
tts.py
Mint-YT-Factory

Version 9.0 — KEYLESS TIKTOK TTS WITH BACKEND FAILOVER

The old `tiktoktts` package depended on ottsy.weilbyte.dev, which is no
longer reliable. This implementation calls keyless TikTok-TTS-compatible
backends directly and keeps the existing chunking, duration control, and
MoviePy assembly pipeline unchanged.
"""

import base64
import os
import re
import time

import requests
from moviepy.editor import AudioFileClip, concatenate_audioclips

SAMPLE_RATE = 44100
TARGET_MAX_DURATION = 43.70
MIN_PLAYBACK_SPEED = 0.95
MAX_PLAYBACK_SPEED = 1.10
TIKTOK_MAX_CHARS = 300
TIKTOK_SAFE_CHARS = 285
TIKTOK_REQUEST_RETRIES = 4
TIKTOK_RETRY_DELAYS = (1.5, 3.0, 6.0, 10.0)

# Keyless backends. The first endpoint is the current community Cloudflare
# Worker implementation. The remaining endpoints are TikTok's own speech
# endpoints and require no API key/session for the public TTS path when the
# selected voice is supported.
TIKTOK_TTS_BACKENDS = (
    "https://tiktok-tts.weilnet.workers.dev/api/generation",
    "https://api16-normal-v6.tiktokv.com/media/api/text/speech/invoke/",
    "https://api16-normal-c-useast1a.tiktokv.com/media/api/text/speech/invoke/",
    "https://api16-normal-c-useast2a.tiktokv.com/media/api/text/speech/invoke/",
    "https://api16-normal-useast5.us.tiktokv.com/media/api/text/speech/invoke/",
)

TIKTOK_USER_AGENT = (
    "com.zhiliaoapp.musically/2022600030 "
    "(Linux; U; Android 7.1.2; es_ES; SM-G988N; "
    "Build/NRD90M;tt-ok/3.12.13.1)"
)

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
    return [clean_text(x) for x in re.split(r"(?<=[.!?])\s+", clean_text(text)) if clean_text(x)]


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
            raise RuntimeError(f"TikTok chunk {index} exceeds the hard 300-character limit.")
    return chunks


def apply_narration_speed(clip):
    """Adapt playback speed so normal TTS variance cannot cross 44.35s."""
    try:
        duration = float(clip.duration)
        required = duration / TARGET_MAX_DURATION if TARGET_MAX_DURATION > 0 else 1.0
        speed = max(MIN_PLAYBACK_SPEED, required)
        speed = min(MAX_PLAYBACK_SPEED, speed)
    except Exception:
        duration = float(getattr(clip, "duration", 0.0) or 0.0)
        speed = 1.0

    if abs(speed - 1.0) < 0.001:
        print(f"✅ Narration speed adjustment not needed ({duration:.2f}s)")
        return clip
    try:
        transformed = clip.fl_time(lambda t: t / speed, apply_to=["audio"])
        transformed = transformed.set_duration(duration / speed)
        print(f"✅ Adaptive narration speed: {speed:.3f}x ({duration:.2f}s → {duration / speed:.2f}s)")
        return transformed
    except Exception as error:
        print(f"⚠️ Narration speed adjustment failed: {error}")
        return clip


def _decode_backend_response(response):
    """Return MP3 bytes from known keyless TikTok response formats."""
    response.raise_for_status()
    data = response.json()

    # Community worker: {success: true, data: <base64>}
    if data.get("success") is True and data.get("data"):
        return base64.b64decode(data["data"]), "community-worker"

    # TikTok private endpoint: {status_code: 0, data: {v_str: <base64>}}
    if data.get("status_code") == 0:
        nested = data.get("data") or {}
        encoded = nested.get("v_str") if isinstance(nested, dict) else None
        if encoded:
            return base64.b64decode(encoded), "tiktok-direct"

    if data.get("statusCode") == 0:
        nested = data.get("data") or {}
        encoded = nested.get("v_str") if isinstance(nested, dict) else None
        if encoded:
            return base64.b64decode(encoded), "tiktok-direct"

    message = data.get("status_msg") or data.get("statusMessage") or data.get("error") or str(data)
    raise RuntimeError(f"TTS backend rejected request: {message}")


def _request_keyless_tiktok_tts(text, voice):
    """Try all configured keyless backends before failing the chunk."""
    last_error = None

    for backend in TIKTOK_TTS_BACKENDS:
        try:
            if backend.endswith("/api/generation"):
                response = requests.post(
                    backend,
                    json={"text": text, "voice": voice},
                    headers={"User-Agent": TIKTOK_USER_AGENT},
                    timeout=(10, 45),
                )
            else:
                params = {
                    "text_speaker": voice,
                    "req_text": text,
                    "speaker_map_type": "0",
                    "aid": "1233",
                }
                response = requests.post(
                    backend,
                    params=params,
                    headers={"User-Agent": TIKTOK_USER_AGENT},
                    timeout=(10, 45),
                )

            audio_bytes, backend_name = _decode_backend_response(response)
            if not audio_bytes:
                raise RuntimeError("TTS backend returned empty audio.")
            return audio_bytes, backend_name
        except Exception as error:
            last_error = error
            print(f"⚠️ Keyless TikTok backend failed: {backend} — {type(error).__name__}: {error}")

    raise RuntimeError("All keyless TikTok TTS backends failed.") from last_error


def print_tiktok_error(error, text, request_number, attempt):
    print("=" * 80)
    print("❌ TIKTOK TTS REQUEST FAILED")
    print("=" * 80)
    print(f"Request: {request_number} | Attempt: {attempt}/{TIKTOK_REQUEST_RETRIES}")
    print(f"Exception type: {type(error).__name__}")
    print(f"Exception message: {error}")
    print(f"Characters: {len(text)} | UTF-8 characters: {utf8_length(text)}")
    print("=" * 80)


def generate_tiktok_chunk(text, voice, request_number):
    last_error = None
    for attempt in range(1, TIKTOK_REQUEST_RETRIES + 1):
        print(f"🎤 TikTok TTS request {request_number} — attempt {attempt}/{TIKTOK_REQUEST_RETRIES}")
        print(f"Characters: {len(text)} | UTF-8 characters: {utf8_length(text)}")
        print(f"Text: {text}")
        try:
            audio_bytes, backend_name = _request_keyless_tiktok_tts(text, voice)
            chunk_path = os.path.abspath(f"tiktok_chunk_{request_number}.mp3")
            if os.path.exists(chunk_path):
                os.remove(chunk_path)
            with open(chunk_path, "wb") as output:
                output.write(audio_bytes)
            print(f"✅ TikTok TTS request {request_number} succeeded on attempt {attempt}")
            print(f"🔊 TTS backend: {backend_name} (keyless)")
            return chunk_path
        except Exception as error:
            last_error = error
            print_tiktok_error(error, text, request_number, attempt)
            if attempt < TIKTOK_REQUEST_RETRIES:
                delay = TIKTOK_RETRY_DELAYS[attempt - 1]
                print(f"🔁 Transient TTS failure. Retrying in {delay:.1f}s...")
                time.sleep(delay)
    raise RuntimeError(f"TikTok TTS request {request_number} failed after {TIKTOK_REQUEST_RETRIES} attempts.") from last_error


def synthesize_narration(text, config, out_path):
    original_text = clean_text(text)
    if not original_text:
        raise RuntimeError("Cannot synthesize empty narration.")
    tts_text = build_tts_pronunciation_text(original_text)
    voice_config = config.get("voice", {}) if isinstance(config, dict) else {}
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
    print("Backend: keyless TikTok-compatible API failover")
    print("API key: NOT REQUIRED")
    print("Session ID: NOT REQUIRED")
    print(f"Original characters: {len(original_text)}")
    print(f"TTS characters: {len(tts_text)}")
    print(f"Chunks: {len(chunks)}")
    print(f"Target max duration: {TARGET_MAX_DURATION:.2f}s")
    print("Adaptive narration speed: ENABLED")
    print("Sentence-aware chunking: ENABLED")
    print("Transient request retries: ENABLED")
    print("Scene-level TTS: DISABLED")
    print("Artificial gaps: DISABLED")
    print("Crossfade: DISABLED")
    print("Fallback voice: DISABLED")

    chunk_paths, clips = [], []
    combined = None
    processed = None
    try:
        for index, chunk in enumerate(chunks, 1):
            chunk_paths.append(generate_tiktok_chunk(chunk, voice, index))
        print("\n🎧 ASSEMBLING CONTINUOUS NARRATION")
        for index, chunk_path in enumerate(chunk_paths, 1):
            clip = AudioFileClip(chunk_path)
            clips.append(clip)
            print(f"Chunk {index}: {clip.duration:.2f}s")
        combined = concatenate_audioclips(clips)
        print(f"Raw combined duration: {combined.duration:.2f}s")
        processed = apply_narration_speed(combined)
        print(f"Final narration duration: {processed.duration:.2f}s")
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        processed.write_audiofile(out_path, fps=SAMPLE_RATE, codec="libmp3lame", bitrate="192k", verbose=False, logger=None)
        return out_path
    finally:
        for clip in clips:
            try: clip.close()
            except Exception: pass
        for clip in (processed, combined):
            try:
                if clip is not None: clip.close()
            except Exception: pass
        for path in chunk_paths:
            try:
                if os.path.exists(path): os.remove(path)
            except Exception: pass


def _script_narration(script):
    scenes = script.get("scene_plan", []) if isinstance(script, dict) else []
    if not isinstance(scenes, list):
        return ""
    return clean_text(" ".join(str(scene.get("narration", "")) for scene in scenes if isinstance(scene, dict)))


def synthesize_script(script, config, out_dir):
    """Stable public entrypoint expected by main.py and runtime overrides."""
    if not isinstance(script, dict):
        raise RuntimeError("Script must be a dictionary.")
    narration = _script_narration(script)
    if not narration:
        raise RuntimeError("Script contains no scene narration.")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "story.mp3")
    return synthesize_narration(narration, config, out_path)
