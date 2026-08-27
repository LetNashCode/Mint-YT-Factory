"""
tts.py
Mint-YT-Factory

Version 10.0 — RESILIENT TTS: EDGE PRIMARY + OPTIONAL TIKTOK + GTTS FALLBACK
"""

import asyncio
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
TTS_RETRIES = 2

# The old community TikTok proxy can currently redirect to ottsy.weilbyte.dev
# and time out. Do NOT use it unless explicitly enabled.
TIKTOK_ENABLED = os.environ.get("MINT_TIKTOK_TTS_FALLBACK", "0").strip().lower() in {"1", "true", "yes"}
TIKTOK_TTS_BACKENDS = (
    "https://tiktok-tts.weilnet.workers.dev/api/generation",
    "https://api16-normal-v6.tiktokv.com/media/api/text/speech/invoke/",
    "https://api16-normal-c-useast1a.tiktokv.com/media/api/text/speech/invoke/",
    "https://api16-normal-c-useast2a.tiktokv.com/media/api/text/speech/invoke/",
    "https://api16-normal-useast5.us.tiktokv.com/media/api/text/speech/invoke/",
)
TIKTOK_USER_AGENT = (
    "com.zhiliaoapp.musically/2022600030 "
    "(Linux; U; Android 7.1.2; es_ES; SM-G988N; Build/NRD90M;tt-ok/3.12.13.1)"
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


def build_tts_chunks(text):
    chunks, current = [], ""
    for sentence in split_sentences(text):
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
    for i, chunk in enumerate(chunks, 1):
        if utf8_length(chunk) > TIKTOK_MAX_CHARS:
            raise RuntimeError(f"TTS chunk {i} exceeds the hard 300-character limit.")
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


def _edge_voice(voice_config):
    configured = str(voice_config.get("edge_voice") or "").strip()
    if configured:
        return configured
    legacy = str(voice_config.get("voice_name") or "").strip().lower()
    if legacy.startswith("en_us"):
        return "en-US-GuyNeural"
    return "en-US-GuyNeural"


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


def _decode_tiktok_response(response):
    response.raise_for_status()
    data = response.json()
    if data.get("success") is True and data.get("data"):
        return base64.b64decode(data["data"]), "community-worker"
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
    raise RuntimeError(data.get("status_msg") or data.get("statusMessage") or data.get("error") or str(data))


def _request_tiktok(text, voice):
    last_error = None
    for backend in TIKTOK_TTS_BACKENDS:
        try:
            if backend.endswith("/api/generation"):
                response = requests.post(backend, json={"text": text, "voice": voice}, headers={"User-Agent": TIKTOK_USER_AGENT}, timeout=(5, 15))
            else:
                response = requests.post(
                    backend,
                    params={"text_speaker": voice, "req_text": text, "speaker_map_type": "0", "aid": "1233"},
                    headers={"User-Agent": TIKTOK_USER_AGENT},
                    timeout=(5, 15),
                )
            audio, name = _decode_tiktok_response(response)
            if audio:
                return audio, name
        except Exception as error:
            last_error = error
            print(f"⚠️ Optional TikTok backend failed: {backend} — {type(error).__name__}: {error}")
    raise RuntimeError("All optional TikTok TTS backends failed") from last_error


def _generate_gtts_chunk(text, request_number):
    try:
        from gtts import gTTS
    except ImportError as error:
        raise RuntimeError("gTTS is not installed") from error
    path = os.path.abspath(f"tts_gtts_chunk_{request_number}.mp3")
    if os.path.exists(path):
        os.remove(path)
    gTTS(text=text, lang="en", slow=False).save(path)
    if not os.path.exists(path) or os.path.getsize(path) < 1024:
        raise RuntimeError("gTTS returned no usable audio.")
    print(f"✅ gTTS emergency fallback chunk {request_number} succeeded")
    return path


def generate_tts_chunk(text, voice_config, request_number):
    last_error = None
    print(f"🎤 TTS chunk {request_number} | chars={len(text)}")

    # Production default: Edge TTS. It is keyless and does not depend on the
    # unstable ottsy proxy. edge-tts uses Microsoft's online TTS service.
    for attempt in range(1, TTS_RETRIES + 1):
        try:
            return _generate_edge_chunk(text, voice_config, request_number)
        except Exception as error:
            last_error = error
            print(f"⚠️ Edge TTS attempt {attempt}/{TTS_RETRIES} failed: {type(error).__name__}: {error}")
            if attempt < TTS_RETRIES:
                time.sleep(attempt)

    # TikTok is deliberately opt-in because the current public endpoints are
    # failing in GitHub Actions. It can be re-enabled without code changes.
    if TIKTOK_ENABLED:
        try:
            legacy_voice = str(voice_config.get("tiktok_voice_name") or "en_us_010")
            audio, backend = _request_tiktok(text, legacy_voice)
            path = os.path.abspath(f"tts_tiktok_chunk_{request_number}.mp3")
            with open(path, "wb") as handle:
                handle.write(audio)
            print(f"✅ Optional TikTok fallback succeeded via {backend}")
            return path
        except Exception as error:
            last_error = error
            print(f"⚠️ Optional TikTok fallback failed: {type(error).__name__}: {error}")

    # Final network fallback. This is slower/less expressive than Edge but
    # prevents the entire production run from dying on a transient provider outage.
    try:
        return _generate_gtts_chunk(text, request_number)
    except Exception as error:
        last_error = error
        print(f"❌ gTTS emergency fallback failed: {type(error).__name__}: {error}")

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
    print("🎙️ RESILIENT TTS — CHUNKED CONTINUOUS NARRATION")
    print("=" * 80)
    print(f"Configured provider: {voice_config.get('provider', 'edge')}")
    print(f"Edge voice: {_edge_voice(voice_config)}")
    print("Primary backend: Microsoft Edge TTS (keyless)")
    print("TikTok fallback: " + ("ENABLED" if TIKTOK_ENABLED else "DISABLED by default"))
    print("Emergency fallback: gTTS")
    print(f"Original characters: {len(original_text)}")
    print(f"TTS characters: {len(tts_text)}")
    print(f"Chunks: {len(chunks)}")
    print(f"Target max duration: {TARGET_MAX_DURATION:.2f}s")
    print("Adaptive narration speed: ENABLED")
    print("Sentence-aware chunking: ENABLED")
    print("Artificial gaps: DISABLED")

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
    if not isinstance(script, dict):
        raise RuntimeError("Script must be a dictionary.")
    narration = _script_narration(script)
    if not narration:
        raise RuntimeError("Script contains no scene narration.")
    os.makedirs(out_dir, exist_ok=True)
    return synthesize_narration(narration, config, os.path.join(out_dir, "story.mp3"))
