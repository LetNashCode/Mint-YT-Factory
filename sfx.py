"""
sfx.py — Mint-YT-Factory

Free, dependency-light sound-design layer.

The system does not download copyrighted YouTube audio and does not require
an external paid SFX API. It creates short original procedural effects locally
from simple waveforms, then gives assemble.py one cue per scene.
"""
from __future__ import annotations

import math
import os
import random
import struct
import wave

SAMPLE_RATE = 44100

# Deliberately restrained: sound design should punctuate the story, not fight it.
EFFECTS = {
    "pop": (0.18, 0.55),
    "click": (0.10, 0.38),
    "whoosh": (0.42, 0.48),
    "impact": (0.28, 0.62),
    "sparkle": (0.45, 0.40),
    "glass_ting": (0.55, 0.42),
    "boing": (0.42, 0.42),
    "suspense": (0.70, 0.28),
    "reveal": (0.38, 0.58),
    "tap": (0.12, 0.35),
}


def _clean(text):
    return " ".join(str(text or "").split()).strip()


def _write_wav(path, samples):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = b"".join(struct.pack("<h", max(-32767, min(32767, int(x)))) for x in samples)
        wf.writeframes(frames)


def _envelope(i, n, attack=0.015, release=0.18):
    t = i / max(1, n)
    a = min(1.0, t / attack)
    r = min(1.0, (1.0 - t) / release)
    return min(a, r, 1.0)


def _tone(freq, duration, volume=0.5, decay=3.0, slide=0.0):
    n = max(1, int(duration * SAMPLE_RATE))
    out = []
    phase = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        f = max(25.0, freq + slide * (i / max(1, n - 1)))
        phase += 2 * math.pi * f / SAMPLE_RATE
        env = _envelope(i, n) * math.exp(-decay * t)
        out.append(32767 * volume * env * math.sin(phase))
    return out


def _noise(duration, volume=0.25, decay=5.0, seed=7):
    rng = random.Random(seed)
    n = max(1, int(duration * SAMPLE_RATE))
    return [32767 * volume * _envelope(i, n) * math.exp(-decay * i / SAMPLE_RATE) * rng.uniform(-1, 1) for i in range(n)]


def _effect_samples(kind):
    if kind == "pop":
        return _tone(180, 0.18, 0.58, 8, 520)
    if kind == "click" or kind == "tap":
        return _tone(1450, 0.08, 0.42, 25, -500)
    if kind == "whoosh":
        n = int(0.42 * SAMPLE_RATE)
        noise = _noise(0.42, 0.20, 2.2, 11)
        out = []
        phase = 0.0
        for i, x in enumerate(noise):
            p = i / max(1, n - 1)
            f = 180 + 1050 * p
            phase += 2 * math.pi * f / SAMPLE_RATE
            out.append(x + 32767 * 0.11 * math.sin(phase) * (p ** 0.8) * (1-p*0.15))
        return out
    if kind == "impact":
        low = _tone(72, 0.28, 0.72, 5, -30)
        hit = _noise(0.28, 0.22, 13, 13)
        return [a + b for a, b in zip(low, hit)]
    if kind == "sparkle":
        parts = [0.0] * int(0.45 * SAMPLE_RATE)
        for freq, start in [(880, 0.0), (1320, 0.10), (1760, 0.20), (2200, 0.30)]:
            tone = _tone(freq, 0.22, 0.18, 7, 80)
            offset = int(start * SAMPLE_RATE)
            for i, v in enumerate(tone):
                if offset + i < len(parts): parts[offset + i] += v
        return parts
    if kind == "glass_ting":
        return _tone(2100, 0.55, 0.30, 4.8, -260)
    if kind == "boing":
        return _tone(260, 0.42, 0.46, 2.6, 520)
    if kind == "suspense":
        return _tone(130, 0.70, 0.20, 1.2, 260)
    return _tone(440, 0.25, 0.2, 6)


def _choose_effect(narration, scene_index):
    """Choose an original cue from the spoken beat, not the broad topic."""
    text = _clean(narration).lower()
    if scene_index == 0:
        return "pop", 180
    if any(x in text for x in ("glass", "window", "mirror", "reflection")):
        return "glass_ting", 220
    if any(x in text for x in ("crack", "break", "snap", "hit", "bang")):
        return "impact", 180
    if any(x in text for x in ("suddenly", "but then", "except", "actually", "turns out")):
        return "reveal", 180
    if any(x in text for x in ("weird", "strange", "ridiculous", "funny", "odd")):
        return "boing", 180
    if any(x in text for x in ("question", "wonder", "why", "how")) and scene_index >= 4:
        return "suspense", 250
    if any(x in text for x in ("tiny", "little", "touch", "tap", "finger", "screen", "button")):
        return "tap", 160
    if scene_index in (1, 2):
        return "whoosh", 160
    if scene_index == 5:
        return "reveal", 180
    if scene_index == 6:
        return "sparkle", 120
    return "pop", 160


def generate_sfx(script, output_dir):
    scenes = script.get("scene_plan", []) if isinstance(script, dict) else []
    if len(scenes) != 7:
        raise RuntimeError("SFX generation requires exactly 7 scenes.")

    os.makedirs(output_dir, exist_ok=True)
    paths = []
    plan = []

    print("=" * 80)
    print("🔊 GENERATING STORY-AWARE SFX")
    print("=" * 80)
    print("Mode: FREE LOCAL PROCEDURAL SFX")
    print("Source: original generated waveforms — no external SFX download")

    for index, scene in enumerate(scenes):
        narration = _clean(scene.get("narration", ""))
        kind, at_ms = _choose_effect(narration, index)
        filename = f"scene_{index+1}_{kind}.wav"
        path = os.path.join(output_dir, filename)
        _write_wav(path, _effect_samples(kind))

        scene["sfx_cue"] = {
            "type": kind,
            "at_ms": at_ms,
            "intensity": "subtle" if index not in (0, 5) else "medium",
            "reason": "beat selected from spoken narration",
        }
        paths.append(path)
        plan.append({"scene": index + 1, "type": kind, "at_ms": at_ms})
        print(f"Scene {index+1}: {kind} @ {at_ms}ms")

    script["sfx_plan"] = plan
    return paths
