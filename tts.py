"""
tts.py
Mint-YT-Factory

Version 11.0 — KOKORO PRIMARY + EDGE FALLBACK

Primary narration is generated locally with Kokoro-82M using the af_heart
American-English voice. No API key or external TTS endpoint is required.
Microsoft Edge TTS remains an automatic network fallback.
"""

import asyncio
import os
import re
import time

import numpy as np
from moviepy.editor import AudioFileClip, concatenate_audioclips

SAMPLE_RATE = 44100
KOKORO_SAMPLE_RATE = 24000
TARGET_MAX_DURATION = 43.70
MIN_PLAYBACK_SPEED = 0.95
MAX_PLAYBACK_SPEED = 1.10
TTS_SAFE_CHARS = 285
TTS_RETRIES = 2

# Kokoro is the production provider. The model and voice weights are
# downloaded/cached automatically by the kokoro package on first use.
KOKORO_ENABLED = os.environ.get("MINT_KOKORO_TTS", "1").strip().lower() not in {"0", "false", "no"}
KOKORO_VOICE = os.environ.get("MINT_KOKORO_VOICE", "af_heart").strip() or "af_heart"
KOKORO_LANG = os.environ.get("MINT_KOKORO_LANG", "a").strip() or "a"

# Edge remains available as a keyless emergency provider if Kokoro cannot
# initialize or generate audio on the GitHub runner.
EDGE_ENABLED = os.environ.get("MINT_EDGE_TTS_FALLBACK", "1").strip().lower() not in {"0", "false", "no"}

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


def hard_split_text(text, max_chars=TTS_SAFE_CHARS):
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


def build_tts_chunks(text):
    chunks, current = [], ""
    for sentence in split_sentences(text):
        if utf8_length(sentence) <= TTS_SAFE_CHARS:
            candidate = sentence if not current else current + " " + sentence
            if utf8_length(candidate) <= TTS_SAFE_CHARS:
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
    return chunks


def apply_narration_speed(clip):
    try:
        duration = float(clip.duration)
        required = duration / TARGET_MAX_DURATION if TARGET_MAX_DURATION > 0 else 1.0
        speed = min(MAX_PLAYBACK_SPEED, max(MIN_PLAYBACK_SPEED, required))
    except Exception:
        duration, speed = float(getattr(clip, "duration", 0.0) or 0.0), 1.0
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


# Keep one Kokoro pipeline in memory for all chunks. This avoids repeatedly
# loading the 82M model and makes chunked narration practical on CI runners.
_KOKORO_PIPELINE = None
_KOKORO_PIPELINE_KEY = None


def _get_kokoro_pipeline():
    global _KOKORO_PIPELINE, _KOKORO_PIPELINE_KEY
    key = (KOKORO_LANG, KOKORO_VOICE)
    if _KOKORO_PIPELINE is not None and _KOKORO_PIPELINE_KEY == key:
        return _KOKORO_PIPELINE
    try:
        from kokoro import KPipeline
    except ImportError as error:
        raise RuntimeError("kokoro is not installed") from error
    print(f"🧠 Loading Kokoro-82M | lang={KOKORO_LANG} | voice={KOKORO_VOICE}")
    try:
        _KOKORO_PIPELINE = KPipeline(lang_code=KOKORO_LANG)
    except Exception as error:
        raise RuntimeError(f"Kokoro pipeline initialization failed: {error}") from error
    _KOKORO_PIPELINE_KEY = key
    print("✅ Kokoro-82M pipeline ready")
    return _KOKORO_PIPELINE


def _generate_kokoro_chunk(text, voice_config, request_number):
    if not KOKORO_ENABLED:
        raise RuntimeError("Kokoro is disabled")
    try:
        import soundfile as sf
    except ImportError as error:
        raise RuntimeError("soundfile is not installed") from error

    voice = str(voice_config.get("voice_name") or KOKORO_VOICE).strip() or KOKORO_VOICE
    lang = str(voice_config.get("kokoro_lang") or KOKORO_LANG).strip() or KOKORO_LANG
    global _KOKORO_PIPELINE_KEY
    if lang != KOKORO_LANG:
        _KOKORO_PIPELINE_KEY = None
    pipeline = _get_kokoro_pipeline()
    path = os.path.abspath(f"tts_kokoro_chunk_{request_number}.wav")
    if os.path.exists(path):
        os.remove(path)

    audio_parts = []
    try:
        generator = pipeline(text, voice=voice)
        for _, _, audio in generator:
            if audio is not None:
                if hasattr(audio, "detach"):
                    audio = audio.detach().cpu().numpy()
                audio = np.asarray(audio, dtype=np.float32).reshape(-1)
                if audio.size:
                    audio_parts.append(audio)
    except Exception as error:
        raise RuntimeError(f"Kokoro generation failed: {error}") from error

    if not audio_parts:
        raise RuntimeError("Kokoro returned no usable audio.")
    audio = np.concatenate(audio_parts)
    sf.write(path, audio, KOKORO_SAMPLE_RATE, subtype="PCM_16")
    if not os.path.exists(path) or os.path.getsize(path) < 1024:
        raise RuntimeError("Kokoro returned an empty audio file.")
    print(f"✅ Kokoro chunk {request_number} succeeded | voice={voice} | sample_rate={KOKORO_SAMPLE_RATE}")
    return path


def _edge_voice(voice_config):
    configured = str(voice_config.get("edge_voice") or "").strip()
    return configured or "en-US-GuyNeural"


def _edge_rate(voice_config):
    try:
        speed = float(voice_config.get("speed", 1.0))
    except Exception:
        speed = 1.0
    pct = int(round((speed - 1.0) * 100))
    return f"{pct:+d}%"


def _generate_edge_chunk(text, voice_config, request_number):
    try:
        import edge_tts
    except ImportError as error:
        raise RuntimeError("edge-tts is not installed") from error
    voice = _edge_voice(voice_config)
    rate = _edge_rate(voice_config)
    path = os.path.abspath(f"tts_edge_chunk_{request_number}.mp3")
    if os.path.exists(path):
        os.remove(path)

    async def _save():
        communicator = edge_tts.Communicate(text, voice, rate=rate)
        await communicator.save(path)

    asyncio.run(_save())
    if not os.path.exists(path) or os.path.getsize(path) < 1024:
        raise RuntimeError("Edge TTS returned no usable audio.")
    print(f"✅ Edge TTS chunk {request_number} succeeded | voice={voice} | rate={rate}")
    return path


def generate_tts_chunk(text, voice_config, request_number):
    last_error = None
    print(f"🎤 TTS chunk {request_number} | chars={len(text)}")

    # Primary: local Kokoro-82M. No API key, no session, and no third-party
    # TTS endpoint is involved in normal production.
    for attempt in range(1, TTS_RETRIES + 1):
        try:
            return _generate_kokoro_chunk(text, voice_config, request_number)
        except Exception as error:
            last_error = error
            print(f"⚠️ Kokoro attempt {attempt}/{TTS_RETRIES} failed: {type(error).__name__}: {error}")
            if attempt < TTS_RETRIES:
                time.sleep(attempt)

    # Keyless Edge fallback preserves the existing production safety net.
    if EDGE_ENABLED:
        for attempt in range(1, TTS_RETRIES + 1):
            try:
                return _generate_edge_chunk(text, voice_config, request_number)
            except Exception as error:
                last_error = error
                print(f"⚠️ Edge fallback attempt {attempt}/{TTS_RETRIES} failed: {type(error).__name__}: {error}")
                if attempt < TTS_RETRIES:
                    time.sleep(attempt)

    raise RuntimeError(f"All configured TTS providers failed for chunk {request_number}") from last_error


def synthesize_narration(text, config, out_path):
    original_text = clean_text(text)
    if not original_text:
        raise RuntimeError("Cannot synthesize empty narration.")
    tts_text = build_tts_pronunciation_text(original_text)
    voice_config = config.get("voice", {}) if isinstance(config, dict) else {}
    if not isinstance(voice_config, dict):
        voice_config = {}
    chunks = build_tts_chunks(tts_text)
    if not chunks:
        raise RuntimeError("No TTS chunks were generated.")

    print("\n" + "=" * 80)
    print("🎙️ KOKORO TTS — CHUNKED CONTINUOUS NARRATION")
    print("=" * 80)
    print(f"Configured provider: {voice_config.get('provider', 'kokoro')}")
    print(f"Kokoro voice: {voice_config.get('voice_name', KOKORO_VOICE)}")
    print(f"Kokoro language: {voice_config.get('kokoro_lang', KOKORO_LANG)}")
    print("Primary backend: Kokoro-82M (local, keyless)")
    print("API key: NOT REQUIRED")
    print("Session ID: NOT REQUIRED")
    print("Edge fallback: " + ("ENABLED" if EDGE_ENABLED else "DISABLED"))
    print(f"Original characters: {len(original_text)}")
    print(f"TTS characters: {len(tts_text)}")
    print(f"Chunks: {len(chunks)}")
    print(f"Target max duration: {TARGET_MAX_DURATION:.2f}s")
    print("Adaptive narration speed: ENABLED")
    print("Sentence-aware chunking: ENABLED")
    print("Scene-level TTS: DISABLED")
    print("Artificial gaps: DISABLED")
    print("Crossfade: DISABLED")

    chunk_paths, clips = [], []
    combined = processed = None
    try:
        for index, chunk in enumerate(chunks, 1):
            chunk_paths.append(generate_tts_chunk(chunk, voice_config, index))
        print("\n🎧 ASSEMBLING CONTINUOUS NARRATION")
        for index, path in enumerate(chunk_paths, 1):
            clip = AudioFileClip(path)
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
            try:
                clip.close()
            except Exception:
                pass
        for clip in (processed, combined):
            try:
                if clip is not None:
                    clip.close()
            except Exception:
                pass
        for path in chunk_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass


def _script_narration(script):
    scenes = script.get("scene_plan", []) if isinstance(script, dict) else []
    if not isinstance(scenes, list):
        return ""
    return clean_text(" ".join(str(scene.get("narration", "")) for scene in scenes if isinstance(scene, dict)))


def synthesize_script(script, config, out_dir):
    if not isinstance(script, dict):
        raise RuntimeError("Script must be a dictionary.")
    narration = _script_narration(script)
    if not narration:
        raise RuntimeError("Script contains no scene narration.")
    os.makedirs(out_dir, exist_ok=True)
    return synthesize_narration(narration, config, os.path.join(out_dir, "story.mp3"))
