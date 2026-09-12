"""
tts.py
Mint-YT-Factory

Version 12.7 — SINGLE-PASS KOKORO PRIMARY + EDGE FALLBACK + STORY-FULL-NARRATION GUARD

Narration is synthesized as one continuous request with Kokoro-82M using the
configured voice. Story Shorts use a wider duration budget so the complete
narrative and CTA are preserved instead of being aggressively compressed.
"""

import asyncio
import os
import re
import time

import numpy as np
from moviepy.editor import AudioFileClip
from moviepy.audio.AudioClip import AudioArrayClip

TARGET_MAX_DURATION = 36.80
STORY_TARGET_MAX_DURATION = 44.20
MIN_PLAYBACK_SPEED = 0.95
MAX_PLAYBACK_SPEED = 1.10
TTS_RETRIES = 2

SAMPLE_RATE = 44100
KOKORO_SAMPLE_RATE = 24000

TRAILING_SILENCE_THRESHOLD = 0.006
TRAILING_SILENCE_KEEP_SECONDS = 0.18
TRAILING_SILENCE_MIN_SECONDS = 0.35
NARRATION_END_PADDING_SECONDS = 0.22

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


def apply_narration_speed(clip, target_duration=None):
    """Adapt playback speed without dropping any generated audio samples."""
    try:
        duration = float(clip.duration)
        target = float(target_duration) if target_duration is not None else TARGET_MAX_DURATION
        target = max(0.10, target)
        required = duration / target
        speed = min(MAX_PLAYBACK_SPEED, max(MIN_PLAYBACK_SPEED, required))
    except Exception:
        duration = float(getattr(clip, "duration", 0.0) or 0.0)
        speed = 1.0

    safe_duration = max(0.01, duration)

    if abs(speed - 1.0) < 0.001:
        safe_clip = clip.set_duration(safe_duration)
        print(f"✅ Narration speed adjustment not needed ({duration:.2f}s; full source duration preserved)")
        return safe_clip

    try:
        source_limit = max(0.0, safe_duration - 0.001)

        def _safe_time_map(t):
            return np.minimum(np.asarray(t) / speed, source_limit)

        transformed = clip.fl_time(_safe_time_map, apply_to=["audio"])
        transformed_duration = safe_duration / speed
        transformed = transformed.set_duration(transformed_duration)
        print(
            f"✅ Adaptive narration speed: {speed:.3f}x "
            f"({duration:.2f}s → {transformed_duration:.2f}s; full ending preserved)"
        )
        return transformed
    except Exception as error:
        print(f"⚠️ Narration speed adjustment failed: {error}")
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


def _trim_trailing_silence(audio, sample_rate):
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size == 0 or sample_rate <= 0:
        return audio, 0.0
    audible = np.flatnonzero(np.abs(audio) >= float(TRAILING_SILENCE_THRESHOLD))
    if audible.size == 0:
        return audio, 0.0
    last_audible = int(audible[-1])
    trailing_samples = max(0, audio.size - last_audible - 1)
    trailing_seconds = trailing_samples / float(sample_rate)
    if trailing_seconds < TRAILING_SILENCE_MIN_SECONDS:
        return audio, 0.0
    keep_samples = int(TRAILING_SILENCE_KEEP_SECONDS * sample_rate)
    end = min(audio.size, last_audible + 1 + keep_samples)
    trimmed = audio[:end]
    removed = max(0.0, (audio.size - trimmed.size) / float(sample_rate))
    return trimmed, removed


def _generate_kokoro(text, voice_config, output_path):
    if not KOKORO_ENABLED:
        raise RuntimeError("Kokoro is disabled")
    try:
        import soundfile as sf
    except ImportError as error:
        raise RuntimeError("soundfile is not installed") from error
    voice = str(voice_config.get("voice_name") or KOKORO_VOICE).strip() or KOKORO_VOICE
    lang = str(voice_config.get("kokoro_lang") or KOKORO_LANG).strip() or KOKORO_LANG
    try:
        speed = float(voice_config.get("speed", 1.0))
    except Exception:
        speed = 1.0
    speed = min(1.10, max(0.90, speed))
    pipeline = _get_kokoro_pipeline(lang)
    try:
        generator = pipeline(text, voice=voice, speed=speed, split_pattern=r"\n+")
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
    audio, removed_silence = _trim_trailing_silence(audio, KOKORO_SAMPLE_RATE)
    if removed_silence > 0:
        print(f"✂️ Trimmed {removed_silence:.2f}s of trailing TTS silence")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    sf.write(output_path, audio, KOKORO_SAMPLE_RATE, subtype="PCM_16")
    if not os.path.exists(output_path) or os.path.getsize(output_path) < 1024:
        raise RuntimeError("Kokoro returned an empty audio file")
    print(f"✅ Kokoro synthesis succeeded | voice={voice} | speed={speed:.2f}x | sample_rate={KOKORO_SAMPLE_RATE}")
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


def synthesize_narration(text, config, out_path, target_duration=None):
    original_text = clean_text(text)
    if not original_text:
        raise RuntimeError("Cannot synthesize empty narration")
    tts_text = build_tts_pronunciation_text(original_text)
    voice_config = config.get("voice", {}) if isinstance(config, dict) else {}
    if not isinstance(voice_config, dict):
        voice_config = {}
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    raw_path = os.path.abspath(out_path + ".raw.wav")
    effective_target = float(target_duration) if target_duration is not None else TARGET_MAX_DURATION
    print("\n" + "=" * 80)
    print("🎙️ KOKORO TTS — SINGLE-PASS CONTINUOUS NARRATION")
    print("=" * 80)
    print(f"Provider: {voice_config.get('provider', 'kokoro')}")
    print(f"Voice: {voice_config.get('voice_name', KOKORO_VOICE)}")
    print(f"Target max core duration: {effective_target:.2f}s")
    print("Adaptive narration speed: ENABLED")
    processed = None
    final_narration = None
    try:
        _synthesize_once(tts_text, voice_config, raw_path)
        clip = AudioFileClip(raw_path)
        try:
            print(f"Raw narration duration: {clip.duration:.2f}s")
            processed = apply_narration_speed(clip, target_duration=effective_target)
            print(f"Processed narration duration: {processed.duration:.2f}s")
            sample_count = max(1, int(round(NARRATION_END_PADDING_SECONDS * SAMPLE_RATE)))
            silence = np.zeros((sample_count, 2), dtype=np.float32)
            silence_clip = AudioArrayClip(silence, fps=SAMPLE_RATE)
            final_narration = __import__("moviepy.editor", fromlist=["concatenate_audioclips"]).concatenate_audioclips([processed, silence_clip])
            print(f"Final narration duration: {final_narration.duration:.2f}s (includes natural end tail)")
            final_narration.write_audiofile(out_path, fps=SAMPLE_RATE, codec="libmp3lame", bitrate="192k", verbose=False, logger=None)
        finally:
            if final_narration is not None:
                try: final_narration.close()
                except Exception: pass
            if processed is not None and processed is not clip:
                try: processed.close()
                except Exception: pass
            try: clip.close()
            except Exception: pass
        return out_path
    finally:
        try:
            if os.path.exists(raw_path): os.remove(raw_path)
        except Exception: pass


def _script_narration(script):
    scenes = script.get("scene_plan", []) if isinstance(script, dict) else []
    if not isinstance(scenes, list):
        return ""
    return clean_text(" ".join(str(scene.get("narration", "")) for scene in scenes if isinstance(scene, dict)))


def _is_story_script(script):
    if not isinstance(script, dict):
        return False
    return bool(
        str(script.get("story_person", "")).strip()
        or str(script.get("interactive_pillar", "")).strip()
        or str(script.get("story_visual_mode", "")).strip()
    )


def _apply_riddle_personality(script, config):
    """Apply an episode-specific performance personality without changing the script text."""
    if not isinstance(script, dict):
        return config
    if not str(script.get("riddle_creative_profile", "")).strip():
        return config
    try:
        from riddle_personality import choose_personality
        personality = choose_personality(
            str(script.get("topic", "")),
            str(script.get("answer", "")),
            script.get("number"),
        )
    except Exception as error:
        print(f"⚠️ Riddle personality selection skipped: {type(error).__name__}: {error}")
        return config

    effective = dict(config or {})
    voice = dict(effective.get("voice") or {})
    for key in ("voice_name", "kokoro_lang", "edge_voice", "speed"):
        if personality.get(key) is not None:
            voice[key] = personality[key]
    voice["personality"] = personality["name"]
    voice["personality_direction"] = personality["direction"]
    effective["voice"] = voice
    script["riddle_personality"] = personality["name"]
    script["riddle_personality_direction"] = personality["direction"]
    script["riddle_personality_version"] = "v1_rotating_performance"
    print(
        f"🎭 Riddle narration personality: {personality['name']} | "
        f"voice={personality.get('voice_name')} | speed={float(personality.get('speed', 1.0)):.2f}x"
    )
    return effective


def synthesize_script(script, config, out_dir):
    if not isinstance(script, dict):
        raise RuntimeError("Script must be a dictionary")
    narration = _script_narration(script)
    if not narration:
        raise RuntimeError("Script contains no narration")
    os.makedirs(out_dir, exist_ok=True)
    output_path = os.path.join(out_dir, "story.mp3")
    effective_config = _apply_riddle_personality(script, config)
    target = STORY_TARGET_MAX_DURATION if _is_story_script(script) else TARGET_MAX_DURATION
    print(f"🎬 TTS narration mode: {'STORY FULL-NARRATION' if _is_story_script(script) else 'STANDARD'} | target={target:.2f}s")
    return synthesize_narration(narration, effective_config, output_path, target_duration=target)
