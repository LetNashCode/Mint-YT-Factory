"""Protect the Publish Shorts next-topic bridge from TTS truncation."""
from __future__ import annotations
import os
import re
import numpy as np
from moviepy.editor import AudioFileClip, concatenate_audioclips
from moviepy.audio.AudioClip import AudioArrayClip


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _split(script):
    scenes = script.get("scene_plan") or []
    full = _clean(" ".join(str(s.get("narration", "")) for s in scenes if isinstance(s, dict)))
    bridge = _clean((script.get("next_short") or {}).get("teaser", ""))
    return (full[:-len(bridge)].rstrip(), bridge) if bridge and full.endswith(bridge) else (full, "")


def patch(main):
    original = main.synthesize_script
    if getattr(original, "_mint_bridge_protected", False): return

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
        bridge_mp3 = os.path.join(workdir, "continuation_bridge.mp3")
        final_path = os.path.join(workdir, "story.mp3")
        try:
            tts._synthesize_once(tts.build_tts_pronunciation_text(story), voice, core_raw)
            tts._synthesize_once(tts.build_tts_pronunciation_text(bridge_text), voice, bridge_raw)
            core = AudioFileClip(core_raw)
            bridge = AudioFileClip(bridge_raw)
            try:
                core_done = tts.apply_narration_speed(core)
                core_done.write_audiofile(core_mp3, fps=tts.SAMPLE_RATE, codec="libmp3lame", bitrate="192k", verbose=False, logger=None)
            finally:
                try: core_done.close()
                except Exception: pass
                core.close(); bridge.close()
            core = AudioFileClip(core_mp3); bridge = AudioFileClip(bridge_raw)
            pause = AudioArrayClip(np.zeros((int(.12 * tts.SAMPLE_RATE), 2), dtype=np.float32), fps=tts.SAMPLE_RATE)
            tail = AudioArrayClip(np.zeros((int(tts.NARRATION_END_PADDING_SECONDS * tts.SAMPLE_RATE), 2), dtype=np.float32), fps=tts.SAMPLE_RATE)
            joined = concatenate_audioclips([core, pause, bridge, tail])
            try:
                joined.write_audiofile(final_path, fps=tts.SAMPLE_RATE, codec="libmp3lame", bitrate="192k", verbose=False, logger=None)
                print(f"🔒 Continuation bridge protected | bridge={bridge.duration:.2f}s | final={joined.duration:.2f}s")
            finally:
                joined.close(); core.close(); bridge.close(); pause.close(); tail.close()
            return final_path
        finally:
            for p in (core_raw, bridge_raw, core_mp3):
                try:
                    if os.path.exists(p): os.remove(p)
                except Exception: pass

    synthesize._mint_bridge_protected = True
    main.synthesize_script = synthesize
