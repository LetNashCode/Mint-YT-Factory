"""Commercial-safe reaction SFX layer.

The viral "faaa" reaction is deliberately NOT downloaded from random meme
soundboard sites. Instead we generate an original, short human-like reaction
from synthesis primitives. This keeps the asset commercially safer while
preserving the comedic role of the sound.
"""
from __future__ import annotations

import math
import os
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent / "assets" / "sfx" / "reaction"
SAMPLE_RATE = 44100


def _write_wav(path: Path, samples: np.ndarray):
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())


def _faaa():
    """Original exaggerated 'faaaah' reaction; not sampled from a meme."""
    duration = 0.62
    t = np.arange(int(SAMPLE_RATE * duration)) / SAMPLE_RATE
    # Human-ish voiced buzz with a descending pitch and a breathy noise layer.
    f0 = 210.0 - 80.0 * (t / duration)
    phase = 2 * math.pi * np.cumsum(f0) / SAMPLE_RATE
    voice = (
        0.48 * np.sin(phase)
        + 0.22 * np.sin(2 * phase + 0.2)
        + 0.10 * np.sin(3 * phase)
    )
    rng = np.random.default_rng(240824)
    breath = rng.normal(0, 1, len(t)) * 0.055
    envelope = np.minimum(t / 0.055, 1.0) * np.minimum((duration - t) / 0.18, 1.0)
    envelope = np.clip(envelope, 0, 1)
    return (voice + breath) * envelope


def _huh():
    duration = 0.38
    t = np.arange(int(SAMPLE_RATE * duration)) / SAMPLE_RATE
    f0 = 155 + 170 * (t / duration)
    phase = 2 * math.pi * np.cumsum(f0) / SAMPLE_RATE
    env = np.minimum(t / 0.035, 1) * np.minimum((duration - t) / 0.08, 1)
    return 0.52 * np.sin(phase) * np.clip(env, 0, 1)


def ensure_reaction_assets():
    ROOT.mkdir(parents=True, exist_ok=True)
    files = {"faaa": _faaa, "huh": _huh}
    paths = {}
    for name, generator in files.items():
        path = ROOT / f"{name}.wav"
        if not path.exists() or path.stat().st_size < 1000:
            _write_wav(path, generator())
            print(f"🔊 Created original reaction SFX: {path}")
        paths[name] = str(path)
    return paths


if __name__ == "__main__":
    ensure_reaction_assets()
