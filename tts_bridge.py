"""Protect the Publish Shorts continuation bridge without truncating narration."""
from __future__ import annotations
import os
import re
import numpy as np
from moviepy.editor import AudioFileClip, concatenate_audioclips
from moviepy.audio.AudioClip import AudioArrayClip

MAX_FINAL_NARRATION_SECONDS = 44.95
FINAL_DURATION_SAFETY_MARGIN_SECONDS = 0.15
PROTECTED_PAUSE_SECONDS = 0.035
PROTECTED_MAX_PLAYBACK_SPEED = 1.25


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _split(script):
    scenes = script.get("scene_plan") or []
    full = _clean(" ".join(str(s.get("narration", "")) for s in scenes if isinstance(s, dict)))
    bridge = _clean((script.get("next_short") or {}).get("teaser", ""))
    return (full[:-len(bridge)].rstrip(), bridge) if bridge and full.endswith(bridge) else (full, "")


def _trim_edges(clip, threshold=0.006, keep=0.035):
    duration = float(clip.duration or 0)
    if duration <= 0.05:
        return clip
    try:
        fps = 24000
        samples = np.asarray(clip.to_soundarray(fps=fps))
        if samples.ndim == 1:
            samples = samples[:, None]
        level = np.max(np.abs(samples), axis=1)
        active = np.flatnonzero(level >= threshold)
        if active.size == 0:
            return clip
        start = max(0.0, active[0] / fps - keep)
        end = min(duration, (active[-1] + 1) / fps + keep)
        if end - start < duration - 0.02:
            return clip.subclip(start, end)
    except Exception as error:
        print(f"⚠️ Edge trim skipped: {type(error).__name__}: {error}")
    return clip


def _core_budget(bridge_duration):
    return max(0.10, MAX_FINAL_NARRATION_SECONDS - max(0.0, float(bridge_duration or 0.0)) - PROTECTED_PAUSE_SECONDS - 0.22 - FINAL_DURATION_SAFETY_MARGIN_SECONDS)


def _fit_core_duration(clip, target_duration):
    """Speed up only the story core when the protected bridge leaves less room."""
    duration = float(clip.duration or 0.0)
    target = max(0.10, float(target_duration))
    if duration <= target + 0.02:
        return clip.set_duration(duration)
    speed = min(PROTECTED_MAX_PLAYBACK_SPEED, max(1.0, duration / target))
    source_limit = max(0.0, duration - 0.001)

    def time_map(t):
        return np.minimum(np.asarray(t) / speed, source_limit)

    fitted = clip.fl_time(time_map, apply_to=["audio"]).set_duration(duration / speed)
    print(f"✅ Protected core speed: {speed:.3f}x ({duration:.2f}s → {fitted.duration:.2f}s)")
    return fitted


def patch(main):
    original = main.synthesize_script
    if getattr(original, "_mint_bridge_protected", False):
        return

    def synthesize(script, config, workdir):
        import tts
        story, bridge_text = _split(script)
        if not bridge_text:
            return original(script, config, workdir)
        voice = config.get("voice", {}) if isinstance(config, dict) else {}
        os.makedirs(workdir, exist_ok=True)
        core_raw = os.path.join(workdir, "story_core.raw.wav")
        bridge_raw = os.path.join(workdir, "continuation_bridge.raw.wav")
        core_mp3 = os.path.join(workdir, "story_core.mp3")
        final_path = os.path.join(workdir, "story.mp3")
        core = bridge = core_done = None
        try:
            tts._synthesize_once(tts.build_tts_pronunciation_text(bridge_text), voice, bridge_raw)
            bridge = _trim_edges(AudioFileClip(bridge_raw))
            target_core = _core_budget(bridge.duration)
            print(f"🎯 Dynamic protected narration budget | bridge={bridge.duration:.2f}s | core_target={target_core:.2f}s | final_ceiling={MAX_FINAL_NARRATION_SECONDS:.2f}s")
            tts._synthesize_once(tts.build_tts_pronunciation_text(story), voice, core_raw)
            core = _trim_edges(AudioFileClip(core_raw))
            core_done = _fit_core_duration(core, target_core)
            core_done.write_audiofile(core_mp3, fps=tts.SAMPLE_RATE, codec="libmp3lame", bitrate="192k", verbose=False, logger=None)
            core_done.close(); core_done = None
            core.close(); core = None
            core = _trim_edges(AudioFileClip(core_mp3))
            pause = AudioArrayClip(np.zeros((int(PROTECTED_PAUSE_SECONDS * tts.SAMPLE_RATE), 2), dtype=np.float32), fps=tts.SAMPLE_RATE)
            tail = AudioArrayClip(np.zeros((int(tts.NARRATION_END_PADDING_SECONDS * tts.SAMPLE_RATE), 2), dtype=np.float32), fps=tts.SAMPLE_RATE)
            final_duration = float(core.duration or 0.0) + PROTECTED_PAUSE_SECONDS + float(bridge.duration or 0.0) + tts.NARRATION_END_PADDING_SECONDS
            if final_duration > MAX_FINAL_NARRATION_SECONDS + 0.01:
                raise RuntimeError(f"Protected narration still exceeds ceiling: final={final_duration:.2f}s > ceiling={MAX_FINAL_NARRATION_SECONDS:.2f}s")
            joined = concatenate_audioclips([core, pause, bridge, tail])
            try:
                joined.write_audiofile(final_path, fps=tts.SAMPLE_RATE, codec="libmp3lame", bitrate="192k", verbose=False, logger=None)
                print(f"🔒 Continuation bridge protected | bridge={bridge.duration:.2f}s | core={core.duration:.2f}s | final={joined.duration:.2f}s")
            finally:
                joined.close(); core.close(); bridge.close(); pause.close(); tail.close()
            return final_path
        finally:
            for clip in (core_done, core, bridge):
                if clip is not None:
                    try: clip.close()
                    except Exception: pass
            for path in (core_raw, bridge_raw, core_mp3):
                try:
                    if os.path.exists(path): os.remove(path)
                except Exception: pass

    synthesize._mint_bridge_protected = True
    main.synthesize_script = synthesize
