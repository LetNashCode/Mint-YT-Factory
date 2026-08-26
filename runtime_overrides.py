"""Small production runtime overrides that remain provider-agnostic.

Visual generation is no longer patched here. The active media architecture is
implemented directly in pexels_media.py:
    Gemini Visual/Search Director -> Pexels -> deterministic metadata selection.

This module only keeps the continuation and TTS compatibility fixes that are
independent of the media provider.
"""
from __future__ import annotations

import re


class AudioPath(list):
    """List-compatible narration result that is also path-like."""
    def __init__(self, path: str):
        super().__init__([path])

    def __fspath__(self):
        return self[0]

    def __str__(self):
        return self[0]

    def __repr__(self):
        return repr(self[0])

    def endswith(self, suffix, *args):
        return self[0].endswith(suffix, *args)


def _clean(text: str) -> str:
    return " ".join(str(text or "").replace("\n", " ").split()).strip()


def _words(text: str) -> list[str]:
    return re.findall(r"\b[\w'-]+\b", _clean(text))


def _topic_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean(text).lower()).strip()


def _split_sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", _clean(text)) if x.strip()]


def _remove_stale_teaser(text: str, canonical: str) -> str:
    noise = re.compile(
        r"\b(?:speaking of|on a related note|that brings us to|that leaves one|"
        r"which raises|which brings up|one bigger question|another question|"
        r"one more thing to wonder about|next video|next short|next topic|"
        r"coming next|stay tuned|part 2|and next|next:)\b", re.I
    )
    canonical_key = _topic_key(canonical)
    kept = []
    for sentence in _split_sentences(text):
        normalized = _topic_key(sentence)
        if canonical_key and canonical_key in normalized:
            continue
        if noise.search(sentence):
            continue
        kept.append(sentence)
    return " ".join(kept).strip()


def _clean_payoff(text: str, max_words: int = 14) -> str:
    sentences = _split_sentences(text)
    candidates = []
    for sentence in sentences:
        if len(_words(sentence)) > max_words:
            continue
        if sentence.endswith((".", "!", "?")):
            candidates.append(sentence)
    if candidates:
        return candidates[-1].rstrip(".!? ") + "."
    words = _words(text)
    return (" ".join(words[-max_words:]).rstrip(".!?") + ".") if words else "And that's the weird part."


def _build_teaser(topic: str) -> str:
    return f"And next: {topic}."


def patch_continuation(main):
    """Keep exactly one canonical next topic in Scene 7."""
    def lock_next_topic(script, current_topic):
        from topics import _PENDING_PREFIX, _generate_topic, _read_used, validate_topic_for_pipeline

        candidate = _clean((script.get("next_short") or {}).get("topic"))
        if not candidate:
            raise RuntimeError("Generated script did not provide next_short.topic.")
        used = [str(current_topic)] + [x for x in _read_used() if not str(x).startswith(_PENDING_PREFIX)]
        canonical = ""
        for attempt in range(9):
            value = candidate if attempt == 0 else _clean(_generate_topic(used))
            if _words(value) and len(_words(value)) <= 7 and validate_topic_for_pipeline(value, used=used, check_duplicate=True):
                canonical = value
                break
            print(f"⚠️ Continuation rejected: {value}")
        if not canonical:
            raise RuntimeError("Could not create a valid canonical next topic.")

        script.setdefault("next_short", {})["topic"] = canonical
        script["next_short"]["teaser"] = _build_teaser(canonical)
        scenes = script.get("scene_plan")
        if not isinstance(scenes, list) or len(scenes) != 7:
            raise RuntimeError("Script must contain exactly 7 scenes.")
        final = scenes[-1]
        payoff = _clean_payoff(_remove_stale_teaser(final.get("narration", ""), canonical))
        final["narration"] = f"{payoff} {_build_teaser(canonical)}"
        final["subtitle_text"] = final["narration"]
        final["pause_after_ms"] = 150
        final["emotional_tone"] = "satisfied"
        final["music_cue"] = "fade_out"
        final["caption_highlights"] = [{"word": w, "emphasis": "strong"} for w in _words(canonical)[:3]]
        final["emphasis_word"] = _words(canonical)[0]

        key = _topic_key(canonical)
        if key not in _topic_key(final["narration"]):
            raise RuntimeError("Canonical next topic was not inserted into Scene 7.")
        if any(key in _topic_key(scene.get("narration", "")) for scene in scenes[:6]):
            raise RuntimeError("Next topic appeared before Scene 7.")
        print(f"🔒 Canonical next topic: {canonical}")
        print(f"🗣️ FINAL SPOKEN TEASE: {final['narration']}")
        return script, canonical

    main.lock_next_topic = lock_next_topic


def patch_tts_result(main):
    original = main.synthesize_script

    def synthesize_script(script, config, workdir):
        result = original(script, config, workdir)
        if isinstance(result, (list, tuple)) and result:
            return AudioPath(str(result[0]))
        return AudioPath(str(result))

    main.synthesize_script = synthesize_script
