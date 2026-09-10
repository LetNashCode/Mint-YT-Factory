"""Rotating performance personalities for Riddles Shorts narration."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Kokoro does not expose reliable emotion controls, so each personality combines
# a compatible voice, delivery speed, and a clear performance direction.
PERSONALITIES = (
    {"name": "mischievous", "direction": "Playful, teasing, sly and slightly cocky. Sound like you know there is a trap.", "voice_name": "af_bella", "kokoro_lang": "a", "edge_voice": "en-US-AriaNeural", "speed": 1.04},
    {"name": "angry", "direction": "Irritated and challenging, as if the listener is making an obvious mistake. Keep it fun, never hostile.", "voice_name": "am_adam", "kokoro_lang": "a", "edge_voice": "en-US-GuyNeural", "speed": 1.06},
    {"name": "happy", "direction": "Bright, upbeat and genuinely delighted by the puzzle. Use energetic conversational rhythm.", "voice_name": "af_heart", "kokoro_lang": "a", "edge_voice": "en-US-JennyNeural", "speed": 1.06},
    {"name": "seductive", "direction": "Smooth, intimate and intriguing, with controlled confidence. Seductive means stylish and mysterious, never sexual or explicit.", "voice_name": "af_nicole", "kokoro_lang": "a", "edge_voice": "en-US-AriaNeural", "speed": 0.98},
    {"name": "sick", "direction": "Tired, slightly raspy and low-energy, as if you are solving this while feeling unwell. Keep every word understandable.", "voice_name": "af_heart", "kokoro_lang": "a", "edge_voice": "en-US-GuyNeural", "speed": 0.96},
    {"name": "creepy", "direction": "Quiet, unsettling and mysterious. Leave small moments of tension before key words.", "voice_name": "am_michael", "kokoro_lang": "a", "edge_voice": "en-US-GuyNeural", "speed": 0.97},
    {"name": "confident", "direction": "Cool, certain and effortlessly challenging. Sound like a sharp host who expects the listener to keep up.", "voice_name": "am_adam", "kokoro_lang": "a", "edge_voice": "en-US-GuyNeural", "speed": 1.02},
    {"name": "nervous", "direction": "Slightly anxious and uncertain, with nervous energy around the trap. Never become difficult to understand.", "voice_name": "af_bella", "kokoro_lang": "a", "edge_voice": "en-US-AriaNeural", "speed": 1.03},
    {"name": "detective", "direction": "Observant, investigative and serious, like you are walking the listener through a tiny mystery.", "voice_name": "am_michael", "kokoro_lang": "a", "edge_voice": "en-US-GuyNeural", "speed": 1.00},
    {"name": "sleepy", "direction": "Sleepy, dry and understated, with relaxed timing. The calmness should make the puzzle more intriguing.", "voice_name": "af_heart", "kokoro_lang": "a", "edge_voice": "en-US-GuyNeural", "speed": 0.97},
    {"name": "hyped", "direction": "Excited, fast-thinking and high-energy. Make the countdown feel like a real challenge.", "voice_name": "am_adam", "kokoro_lang": "a", "edge_voice": "en-US-GuyNeural", "speed": 1.08},
    {"name": "innocent", "direction": "Sweet, curious and harmless on the surface, with a subtle sense that the puzzle is trickier than it sounds.", "voice_name": "af_bella", "kokoro_lang": "a", "edge_voice": "en-US-JennyNeural", "speed": 1.00},
)


def _history_count():
    path = Path(__file__).resolve().parent / "interactive_topic_history.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        return len(rows) if isinstance(rows, list) else 0
    except Exception:
        return 0


def choose_personality(topic: str, answer: str = "", number: int | None = None) -> dict:
    """Select a deterministic personality while changing the selection as the episode advances."""
    episode = int(number or (_history_count() + 1))
    seed = f"{topic}|{answer}|{episode}|riddle-personality-v1"
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], "big") % len(PERSONALITIES)
    return dict(PERSONALITIES[index])
