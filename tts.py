"""
tts.py
Mint-YT-Factory

Version 12.1 — SINGLE-PASS KOKORO PRIMARY + EDGE FALLBACK

Narration is synthesized as one continuous request with Kokoro-82M using
 the af_heart American-English voice. Kokoro itself may internally split long
text for inference, but Mint-YT-Factory no longer creates/stitches TTS chunks.
There is no API key or third-party TikTok endpoint in the primary path.
"""

import asyncio
import os
import re
import time

import numpy as np
from moviepy.editor import AudioFileClip

SAMPLE_RATE = 44100
KOKORO_SAMPLE_RATE = 24000
TARGET_MAX_DURATION = 43.70
MIN_PLAYBACK_SPEED = 0.95
MAX_PLAYBACK_SPEED = 1.10
TTS_RETRIES = 2

KOKORO_ENABLED = os.environ.get("MINT_KOKORO_TTS", "1").strip().lower() not in {"0", "false", "no"}
KOKORO_VOICE = os.environ.get("MINT_KOKORO_VOICE", "af_heart").strip() or "af_heart"
KOKORO_LANG = os.environ.get("MINT_KOKORO_LANG", "a").strip() or "a"
EDGE_ENABLED = os.environ.get("MINT_EDGE_TTS_FALLBACK", "1").strip().lower() not in {"0", "false", "no"}

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


def apply_narration_speed(clip):
    """
    Apply adaptive playback speed without letting MoviePy request a frame
    beyond the physical end of the generated WAV.

    Kokoro WAV files can have a tiny discrepancy between MoviePy's reported
    duration and the final readable sample boundary. MoviePy's fl_time()
    transformation can therefore ask the source reader for a frame a few
    milliseconds past EOF while writing the transformed clip. Keep a small
    source-side safety margin before applying the time mapping.
    """
    try:
        duration = float(clip.duration)
        required = duration / TARGET_MAX_DURATION if TARGET_MAX_DURATION > 0 else 1.0
        speed = min(MAX_PLAYBACK_SPEED, max(MIN_PLAYBACK_SPEED, required))
    except Exception:
        duration = float(getattr(clip, "duration", 0.0) or 0.0)
        speed = 1.0

    # MoviePy/ffmpeg can report a duration a few milliseconds longer than the
    # last readable source frame. Trim only a tiny safety margin; this is far
    # below perceptible narration timing while preventing EOF frame requests.
    safety_margin = min(0.10, max(0.0, duration * 0.002))
    safe_duration = max(0.01, duration - safety_margin)

    if abs(speed - 1.0) < 0.001:
        safe_clip = clip.set_duration(safe_duration)
        print(
            f"✅ Narration speed adjustment not needed "
            f"({duration:.2f}s; safe source duration {safe_duration:.2f}s)"
        )
        return safe_clip

    try:
        transformed = clip.fl_time(
            lambda t: min(
                t / speed,
                max(0.0, safe_duration - 0.001),
            ),
            apply_to=["audio"],
        )

        transformed_duration = safe_duration / speed
        transformed = transformed.set_duration(
            transformed_duration
        )

        print(
            f"✅ Adaptive narration speed: "
            f"{speed:.3f}x "
            f"({duration:.2f}s → {transformed_duration:.2f}s)"
        )
        return transformed
    except Exception as error:
        print(
            f"⚠️ Narration speed adjustment failed: {error}"
        )
        return clip.set_duration(safe_duration)


_KOKORO_PIPELINE = None
_KOKORO_PIPELINE_LANG = None


def _get_kokoro_pipeline(lang):
    global _KOKORO_PIPELINE, _KOKORO_PIPELINE_LANG

    if _KOKORO_PIPELINE is not None and _KOKORO_PIPELINE_LANG == lang:
        return _KOKORO_PIPELINE

    try:
        from kokoro import KPipeline
    except ImportError as error:
        raise RuntimeError("kokoro is not installed") from error

    print(f"🧠 Loading Kokoro-82M | lang={lang} | voice={KOKORO_VOICE}")
    try:
        _KOKORO_PIPELINE = KPipeline(lang_code=lang)
    except Exception as error:
        raise RuntimeError(f"Kokoro pipeline initialization failed: {error}") from error

    _KOKORO_PIPELINE_LANG = lang
    print("✅ Kokoro-82M pipeline ready")
    return _KOKORO_PIPELINE


def _generate_kokoro(text, voice_config, output_path):
    if not KOKORO_ENABLED:
        raise RuntimeError("Kokoro is disabled")

    try:
        import soundfile as sf
    except ImportError as error:
        raise RuntimeError("soundfile is not installed") from error

    voice = str(voice_config.get("voice_name") or KOKORO_VOICE).strip() or KOKORO_VOICE
    lang = str(voice_config.get("kokoro_lang") or KOKORO_LANG).strip() or KOKORO_LANG

    pipeline = _get_kokoro_pipeline(lang)

    # IMPORTANT: this is ONE Kokoro synthesis call for the entire narration.
    # Kokoro may internally tokenize/split the text for inference, but the
    # project never sends separate TTS requests or stitches generated chunks.
    try:
        generator = pipeline(text, voice=voice, speed=1.0, split_pattern=r"\n+")
        audio_parts = []
        for result in generator:
            audio = result[2] if isinstance(result, tuple) else result.audio
            if audio is None:
                continue
            if hasattr(audio, "detach"):
                audio = audio.detach().cpu().numpy()
            audio = np.asarray(audio, dtype=np.float32).reshape(-1)
            if audio.size:
                audio_parts.append(audio)
    except Exception as error:
        raise RuntimeError(f"Kokoro generation failed: {error}") from error

    if not audio_parts:
        raise RuntimeError("Kokoro returned no usable audio")

    audio = np.concatenate(audio_parts)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    sf.write(output_path, audio, KOKORO_SAMPLE_RATE, subtype="PCM_16")

    if not os.path.exists(output_path) or os.path.getsize(output_path) < 1024:
        raise RuntimeError("Kokoro returned an empty audio file")

    print(f"✅ Kokoro synthesis succeeded | voice={voice} | sample_rate={KOKORO_SAMPLE_RATE}")
    return output_path


def _edge_voice(voice_config):
    return str(voice_config.get("edge_voice") or "en-US-GuyNeural").strip() or "en-US-GuyNeural"


def _edge_rate(voice_config):
    try:
        speed = float(voice_config.get("speed", 1.0))
    except Exception:
        speed = 1.0
    pct = int(round((speed - 1.0) * 100))
    return f"{pct:+d}%"


def _generate_edge(text, voice_config, output_path):
    try:
        import edge_tts
    except ImportError as error:
        raise RuntimeError("edge-tts is not installed") from error

    voice = _edge_voice(voice_config)
    rate = _edge_rate(voice_config)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    async def _save():
        communicator = edge_tts.Communicate(text, voice, rate=rate)
        await communicator.save(output_path)

    asyncio.run(_save())

    if not os.path.exists(output_path) or os.path.getsize(output_path) < 1024:
        raise RuntimeError("Edge TTS returned no usable audio")

    print(f"✅ Edge TTS fallback succeeded | voice={voice} | rate={rate}")
    return output_path


def _synthesize_once(text, voice_config, out_path):
    last_error = None

    for attempt in range(1, TTS_RETRIES + 1):
        try:
            return _generate_kokoro(text, voice_config, out_path)
        except Exception as error:
            last_error = error
            print(f"⚠️ Kokoro attempt {attempt}/{TTS_RETRIES} failed: {type(error).__name__}: {error}")
            if attempt < TTS_RETRIES:
                time.sleep(attempt)

    if EDGE_ENABLED:
        for attempt in range(1, TTS_RETRIES + 1):
            try:
                return _generate_edge(text, voice_config, out_path)
            except Exception as error:
                last_error = error
                print(f"⚠️ Edge fallback attempt {attempt}/{TTS_RETRIES} failed: {type(error).__name__}: {error}")
                if attempt < TTS_RETRIES:
                    time.sleep(attempt)

    raise RuntimeError("All configured TTS providers failed") from last_error


def synthesize_narration(text, config, out_path):
    original_text = clean_text(text)
    if not original_text:
        raise RuntimeError("Cannot synthesize empty narration")

    tts_text = build_tts_pronunciation_text(original_text)
    voice_config = config.get("voice", {}) if isinstance(config, dict) else {}
    if not isinstance(voice_config, dict):
        voice_config = {}

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    raw_path = os.path.abspath(out_path + ".raw.wav")

    print("\n" + "=" * 80)
    print("🎙️ KOKORO TTS — SINGLE-PASS CONTINUOUS NARRATION")
    print("=" * 80)
    print(f"Provider: {voice_config.get('provider', 'kokoro')}")
    print(f"Voice: {voice_config.get('voice_name', KOKORO_VOICE)}")
    print(f"Language: {voice_config.get('kokoro_lang', KOKORO_LANG)}")
    print("Primary backend: Kokoro-82M (local, keyless)")
    print("API key: NOT REQUIRED")
    print("Session ID: NOT REQUIRED")
    print("TTS requests: 1 continuous narration")
    print("Chunking: DISABLED")
    print("Edge fallback: " + ("ENABLED" if EDGE_ENABLED else "DISABLED"))
    print(f"Original characters: {len(original_text)}")
    print(f"TTS characters: {len(tts_text)}")
    print(f"Target max duration: {TARGET_MAX_DURATION:.2f}s")
    print("Adaptive narration speed: ENABLED")
    print("Artificial gaps: DISABLED")
    print("Crossfade: DISABLED")

    processed = None
    try:
        _synthesize_once(tts_text, voice_config, raw_path)

        clip = AudioFileClip(raw_path)
        try:
            print(f"Raw narration duration: {clip.duration:.2f}s")
            processed = apply_narration_speed(clip)
            print(f"Final narration duration: {processed.duration:.2f}s")
            processed.write_audiofile(
                out_path,
                fps=SAMPLE_RATE,
                codec="libmp3lame",
                bitrate="192k",
                verbose=False,
                logger=None,
            )
        finally:
            if processed is not None and processed is not clip:
                try:
                    processed.close()
                except Exception:
                    pass
            try:
                clip.close()
            except Exception:
                pass

        return out_path
    finally:
        try:
            if os.path.exists(raw_path):
                os.remove(raw_path)
        except Exception:
            pass


def _script_narration(script):
    scenes = script.get("scene_plan", []) if isinstance(script, dict) else []
    if not isinstance(scenes, list):
        return ""
    return clean_text(
        " ".join(
            str(scene.get("narration", ""))
            for scene in scenes
            if isinstance(scene, dict)
        )
    )


def synthesize_script(script, config, out_dir):
    if not isinstance(script, dict):
        raise RuntimeError("Script must be a dictionary")
    narration = _script_narration(script)
    if not narration:
        raise RuntimeError("Script contains no scene narration")
    os.makedirs(out_dir, exist_ok=True)
    return synthesize_narration(narration, config, os.path.join(out_dir, "story.mp3"))
