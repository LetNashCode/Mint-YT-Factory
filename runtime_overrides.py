"""Production runtime compatibility and continuation hardening."""
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


STALE_TEASER_PATTERNS = (
    r"\bfind out (?:what|why|how)\b",
    r"\bthat brings us to\b",
    r"\bthat leaves one\b",
    r"\bwhich raises\b",
    r"\bwhich brings up\b",
    r"\bone bigger question\b",
    r"\banother question\b",
    r"\bone more question\b",
    r"\bone more thing to wonder\b",
    r"\bspeaking of\b",
    r"\bon a related note\b",
    r"\bcoming next\b",
    r"\bnext video\b",
    r"\bnext short\b",
    r"\bnext topic\b",
    r"\bstay tuned\b",
    r"\bpart 2\b",
    r"\bhiding inside that ordinary\b",
)

VISUAL_STOPWORDS = {
    "this", "that", "with", "from", "your", "into", "about", "what", "when", "where",
    "which", "because", "while", "then", "than", "like", "gets", "make", "makes", "made",
    "thing", "things", "single", "ordinary", "kitchen", "find", "out", "inside", "hiding",
    "chemical", "weapon", "question", "next", "topic", "short", "video", "one", "more",
}


def _remove_stale_teaser(text: str, canonical: str) -> str:
    canonical_key = _topic_key(canonical)
    kept: list[str] = []
    for sentence in _split_sentences(text):
        normalized = _topic_key(sentence)
        if canonical_key and canonical_key in normalized:
            continue
        if any(re.search(pattern, sentence, flags=re.I) for pattern in STALE_TEASER_PATTERNS):
            print(f"🧹 Removed stale/rejected continuation from Scene 7: {sentence}")
            continue
        kept.append(sentence)
    cleaned = " ".join(kept).strip()
    cleaned = re.sub(r"(?:^|\s)And\.\s*$", ".", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"\s+And\.\s+", ". ", cleaned, flags=re.I)
    return cleaned


def _clean_payoff(text: str, max_words: int = 24) -> str:
    sentences = _split_sentences(text)
    candidates = []
    for sentence in sentences:
        if any(re.search(pattern, sentence, flags=re.I) for pattern in STALE_TEASER_PATTERNS):
            continue
        if sentence.endswith((".", "!", "?")) and len(_words(sentence)) <= max_words:
            candidates.append(sentence)
    if candidates:
        return candidates[-1].rstrip(".!? ") + "."
    words = _words(text)
    return (" ".join(words[-max_words:]).rstrip(".!?") + ".") if words else "And that's the weird part."


def _build_teaser(topic: str) -> str:
    return f"And next: {topic}."


def _stale_visual_tokens(text: str) -> set[str]:
    return {
        word for word in re.findall(r"\b[a-z0-9]+\b", _clean(text).lower())
        if len(word) >= 5 and word not in VISUAL_STOPWORDS
    }


def _sanitize_final_visuals(final: dict, stale_text: str, current_topic: str) -> None:
    """Remove visual contracts that were generated from a rejected continuation.

    This specifically closes the failure seen when a rejected topic appeared in
    Scene 7 narration and its corresponding object also survived in Shot 2.
    """
    stale_tokens = _stale_visual_tokens(stale_text)
    if not stale_tokens:
        return

    visuals = final.get("visuals")
    if not isinstance(visuals, list):
        return

    topic_words = _words(current_topic)
    topic_label = " ".join(topic_words[-4:]) if topic_words else current_topic
    for index, visual in enumerate(visuals, 1):
        combined = " ".join(str(visual.get(key, "")) for key in (
            "visual_focus", "visual_action", "image_prompt", "spoken_line"
        ))
        overlap = stale_tokens & _stale_visual_tokens(combined)
        if not overlap:
            continue
        print(
            f"🧹 Removed stale continuation visual from Scene 7 Shot {index}: "
            f"{', '.join(sorted(overlap)[:5])}"
        )
        visual["visual_focus"] = topic_label
        visual["visual_action"] = "show the final physical result clearly"
        visual["spoken_line"] = _clean(final.get("narration", ""))
        visual["must_show"] = [topic_label, "clear final physical state"]
        visual["must_not_show"] = ["rejected continuation topic", "unrelated object", "different mystery"]
        visual["image_prompt"] = (
            f"Clear stock footage or photo of {topic_label}, showing the final physical result "
            "in a simple realistic setting; no unrelated object or second topic."
        )


def patch_continuation(main):
    """Keep exactly one canonical next topic and prevent rejected topics leaking into Scene 7."""
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
        original_final = _clean(final.get("narration", ""))
        payoff_source = _remove_stale_teaser(original_final, canonical)
        payoff = _clean_payoff(payoff_source)
        final["narration"] = f"{payoff} {_build_teaser(canonical)}"
        final["subtitle_text"] = final["narration"]
        final["pause_after_ms"] = 150
        final["emotional_tone"] = "satisfied"
        final["music_cue"] = "fade_out"
        final["caption_highlights"] = [{"word": w, "emphasis": "strong"} for w in _words(canonical)[:3]]
        final["emphasis_word"] = _words(canonical)[0]

        _sanitize_final_visuals(final, original_final, current_topic)

        key = _topic_key(canonical)
        if key not in _topic_key(final["narration"]):
            raise RuntimeError("Canonical next topic was not inserted into Scene 7.")
        if any(key in _topic_key(scene.get("narration", "")) for scene in scenes[:6]):
            raise RuntimeError("Next topic appeared before Scene 7.")

        teaser = _build_teaser(canonical)
        if final["narration"].count(teaser) != 1:
            raise RuntimeError("Scene 7 does not contain exactly one canonical continuation teaser.")
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
