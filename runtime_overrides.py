"""Runtime hardening for Mint-YT-Factory.

Keeps continuation state deterministic and makes Gemini stock verification
resilient to transient API/network disconnects.
"""
from __future__ import annotations

import re
import time


class AudioPath(list):
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


# Continuation/meta language that makes Scene 7 sound like an ad for the next Short.
# The actual continuation topic is still allowed, but must be woven into a natural sentence.
STALE_TEASER_PATTERNS = (
    r"^\s*(?:and\s+)?next\b",
    r"\bnext\s+(?:video|short|topic)\b",
    r"\bcoming\s+next\b",
    r"\bstay\s+tuned\b",
    r"\bpart\s*2\b",
    r"\bsee\s+why\b",
    r"\bsee\s+how\b",
    r"\bfind\s+out\s+why\b",
    r"\bfind\s+out\s+how\b",
    r"\bwonder\s+why\b",
    r"\bwonder\s+how\b",
    r"\bcurious\s+(?:why|how)\b",
    r"\bthat\s+brings\s+us\s+to\b",
    r"\bthat\s+leaves\s+one\b",
    r"\bwhich\s+raises\b",
    r"\bwhich\s+brings\s+up\b",
    r"\bone\s+(?:bigger|more)\s+question\b",
    r"\banother\s+question\b",
    r"\bone\s+more\s+(?:question|thing)\b",
    r"\bspeaking\s+of\b",
    r"\bon\s+a\s+related\s+note\b",
    r"\bthen\s+comes\b",
)


def _is_stale_teaser(sentence: str) -> bool:
    return any(re.search(pattern, sentence, flags=re.I) for pattern in STALE_TEASER_PATTERNS)


def _remove_stale_teaser(text: str, canonical: str) -> str:
    canonical_key = _topic_key(canonical)
    kept: list[str] = []
    for sentence in _split_sentences(text):
        normalized = _topic_key(sentence)
        if canonical_key and canonical_key in normalized:
            print(f"🧹 Removed canonical topic from pre-lock draft: {sentence}")
            continue
        if _is_stale_teaser(sentence):
            print(f"🧹 Removed stale/rejected continuation from Scene 7: {sentence}")
            continue
        kept.append(sentence)
    return _clean(" ".join(kept))


def _clean_payoff(text: str, max_words: int = 24) -> str:
    candidates = [s for s in _split_sentences(text) if not _is_stale_teaser(s)]
    if candidates:
        return candidates[-1].rstrip(".!? ") + "."
    words = _words(text)
    return (" ".join(words[-max_words:]).rstrip(".!?") + ".") if words else "And that's the weird part."


def _build_teaser(topic: str) -> str:
    """Return a seamless continuation sentence, never an explicit 'next' cue."""
    topic = _clean(topic).rstrip(".!? ")
    # These are deliberately story-like rather than CTA-like. The topic itself remains
    # the final spoken reveal, but there is no 'And next', 'see why', or 'coming up'.
    templates = (
        "And somehow, that leaves us with one wonderfully weird question: {topic}?",
        "And that makes the ordinary world a little stranger: {topic}?",
        "And just like that, another everyday mystery appears: {topic}?",
        "Which makes you look at the world a little differently: {topic}?",
    )
    # Avoid malformed double question marks when the canonical topic already contains '?'.
    template = templates[sum(ord(c) for c in topic) % len(templates)]
    suffix = "" if topic.endswith("?") else "?"
    return template.format(topic=topic)[:-1] + suffix


def _stale_visual_tokens(text: str) -> set[str]:
    stop = {
        "this", "that", "with", "from", "your", "into", "about", "what", "when", "where",
        "which", "because", "while", "then", "than", "like", "gets", "make", "makes", "made",
        "thing", "things", "single", "ordinary", "kitchen", "find", "out", "inside", "hiding",
        "chemical", "question", "next", "topic", "short", "video", "one", "more", "show", "shows",
    }
    return {w for w in re.findall(r"\b[a-z0-9]+\b", _clean(text).lower()) if len(w) >= 5 and w not in stop}


def _sanitize_final_visuals(final: dict, stale_text: str, current_topic: str) -> None:
    stale_tokens = _stale_visual_tokens(stale_text)
    if not stale_tokens:
        return
    visuals = final.get("visuals")
    if not isinstance(visuals, list):
        return
    topic_label = _clean(current_topic) or "the current topic"
    for index, visual in enumerate(visuals, 1):
        combined = " ".join(str(visual.get(k, "")) for k in ("visual_focus", "visual_action", "image_prompt", "spoken_line"))
        overlap = stale_tokens & _stale_visual_tokens(combined)
        if not overlap:
            continue
        print(f"🧹 Removed stale continuation visual from Scene 7 Shot {index}: {', '.join(sorted(overlap)[:5])}")
        visual["visual_focus"] = topic_label
        visual["visual_action"] = "show the final physical result clearly"
        visual["spoken_line"] = _clean(final.get("narration", ""))
        visual["must_show"] = [topic_label, "clear final physical state"]
        visual["must_not_show"] = ["rejected continuation topic", "unrelated object", "different mystery"]
        visual["image_prompt"] = f"Realistic stock footage or photo of {topic_label}, clearly showing the final physical result in a simple believable setting; no unrelated object or second topic."


def patch_continuation(main):
    """Lock exactly one continuation topic and weave it into Scene 7 naturally."""
    def lock_next_topic(script, current_topic):
        from topics import _PENDING_PREFIX, _generate_topic, _read_used, validate_topic_for_pipeline

        candidate = _clean((script.get("next_short") or {}).get("topic"))
        if not candidate:
            raise RuntimeError("Generated script did not provide next_short.topic.")

        used = [_clean(current_topic)] + [x for x in _read_used() if not str(x).startswith(_PENDING_PREFIX)]
        canonical = ""
        for attempt in range(1, 11):
            value = candidate if attempt == 1 else _clean(_generate_topic(used))
            if len(_words(value)) <= 7 and validate_topic_for_pipeline(value, used=used, check_duplicate=True):
                canonical = value
                break
            print(f"⚠️ Continuation rejected: {value}")

        if not canonical:
            raise RuntimeError("Could not create a valid canonical next topic.")

        script.setdefault("next_short", {})["topic"] = canonical
        # Keep metadata useful, but do not use it as spoken narration.
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

        # Exactly one sentence contains the continuation topic, and it is the final sentence.
        sentences = _split_sentences(final["narration"])
        teaser_matches = [s for s in sentences if key in _topic_key(s)]
        stale_matches = [s for s in sentences if _is_stale_teaser(s) and key not in _topic_key(s)]
        if len(teaser_matches) != 1 or stale_matches or not sentences or teaser_matches[0] != sentences[-1]:
            raise RuntimeError("Scene 7 continuation integrity failed: continuation must be one seamless final sentence with no explicit next/teaser cue.")

        print(f"🔒 Canonical next topic: {canonical}")
        print(f"🗣️ FINAL SPOKEN TEASE: {final['narration']}")
        return script, canonical

    main.lock_next_topic = lock_next_topic


def _install_gemini_verifier_resilience():
    """Make transient Gemini verification disconnects non-fatal.

    We retry transient transport failures. If Gemini remains unavailable, use
    deterministic metadata ranking only for the already-retrieved stock
    candidates. We never invent or download an unrelated/AI asset.
    """
    try:
        import stock_media
    except Exception as exc:
        print(f"⚠️ Gemini verifier resilience could not import stock_media: {exc}")
        return

    original = getattr(stock_media, "_gemini_verify", None)
    if original is None or getattr(original, "_mint_resilient", False):
        return

    transient_names = {
        "RemoteProtocolError", "ReadTimeout", "ConnectTimeout", "ConnectError",
        "TimeoutException", "APIError", "ServerError", "ServiceUnavailable",
    }

    def resilient(candidates, directed):
        last = None
        for attempt in range(1, 4):
            try:
                return original(candidates, directed)
            except Exception as exc:
                last = exc
                name = type(exc).__name__
                if name not in transient_names and "disconnect" not in str(exc).lower():
                    raise
                print(f"⚠️ Gemini visual verification transport failure {attempt}/3: {name}: {exc}")
                if attempt < 3:
                    time.sleep(1.5 * attempt)

        ranked = sorted(candidates or [], key=lambda x: float(x.get("metadata_score", 0) or 0), reverse=True)
        if ranked:
            print(f"⚠️ Gemini verifier unavailable after retries; using best retrieved stock candidate (no unrelated/AI fallback). Last error: {type(last).__name__ if last else 'unknown'}")
            for item in ranked:
                item["visual_score"] = 7.5
                item["visual_subject_match"] = 7.5
                item["visual_action_match"] = 7.5
                item["visual_context_match"] = 7.5
                item["visual_rejected"] = False
                item["visual_reason"] = "Gemini verification temporarily unavailable; deterministic stock relevance fallback used."
            return ranked
        return []

    resilient._mint_resilient = True
    stock_media._gemini_verify = resilient
    print("🛡️ Gemini visual verifier resilience: retries + non-fatal transport fallback ENABLED")


_install_gemini_verifier_resilience()


def patch_tts_result(main):
    original = main.synthesize_script

    def synthesize_script(script, config, workdir):
        result = original(script, config, workdir)
        if isinstance(result, (list, tuple)) and result:
            return AudioPath(str(result[0]))
        return AudioPath(str(result))

    main.synthesize_script = synthesize_script
