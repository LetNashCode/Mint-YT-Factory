"""Runtime hardening for Mint-YT-Factory.

Continuation is authored by Gemini and only validated here. Runtime code must
never manufacture a canned Scene 7 bridge because that makes every ending feel
like the same template.
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


# These phrases make a continuation sound like an advertisement or an editor's
# instruction. Gemini is free to use natural connective language not listed here.
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
    r"\bthat\s+brings\s+us\s+to\b",
    r"\bthat\s+leaves\s+us\s+with\b",
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
        visual["must_not_show"] = ["future continuation topic", "unrelated object", "different mystery"]
        visual["image_prompt"] = f"Realistic stock footage or photo of {topic_label}, clearly showing the final physical result in a simple believable setting; no unrelated object or second topic."


def _validate_gemini_bridge(sentence: str, canonical: str) -> tuple[bool, str]:
    """Validate a Gemini-authored final bridge without replacing it."""
    sentence = _clean(sentence)
    key = _topic_key(canonical)
    if not sentence or not key or key not in _topic_key(sentence):
        return False, "canonical next topic missing from Gemini bridge"
    if any(re.search(pattern, sentence, re.I) for pattern in STALE_TEASER_PATTERNS):
        return False, "explicit next-topic/CTA language detected"
    words = _words(sentence)
    if len(words) < 5 or len(words) > 30:
        return False, "bridge sentence is outside the natural 5-30 word range"
    return True, "ok"


def patch_continuation(main):
    """Lock one continuation topic; Gemini must author the final bridge."""
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
        scenes = script.get("scene_plan")
        if not isinstance(scenes, list) or len(scenes) != 7:
            raise RuntimeError("Script must contain exactly 7 scenes.")

        final = scenes[-1]
        original_final = _clean(final.get("narration", ""))
        sentences = _split_sentences(original_final)
        key = _topic_key(canonical)

        # Remove only accidental/generated future-topic sentences from the draft.
        # The actual Gemini-authored bridge is preserved if it already passes.
        matches = [s for s in sentences if key in _topic_key(s)]
        if len(matches) > 1:
            raise RuntimeError("Gemini placed the continuation topic in more than one Scene 7 sentence.")

        if matches:
            bridge = matches[0]
            if bridge != sentences[-1]:
                raise RuntimeError("Gemini continuation topic must be in the final Scene 7 sentence.")
            valid, reason = _validate_gemini_bridge(bridge, canonical)
            if not valid:
                raise RuntimeError(f"Gemini-authored Scene 7 bridge rejected: {reason}")
            payoff_source = original_final
        else:
            # Gemini may have returned a next_short teaser separately. That is not
            # sufficient: spoken Scene 7 must contain the actual Gemini-authored bridge.
            raise RuntimeError("Gemini did not author a Scene 7 final bridge containing the locked next topic.")

        # Reject stale future-topic language anywhere in Scene 7 without silently
        # manufacturing a replacement sentence.
        stale_matches = [s for s in _split_sentences(payoff_source) if _is_stale_teaser(s) and key not in _topic_key(s)]
        if stale_matches:
            raise RuntimeError("Scene 7 contains stale explicit continuation language: " + " | ".join(stale_matches))

        final["subtitle_text"] = final["narration"]
        final["pause_after_ms"] = 150
        final["emotional_tone"] = "satisfied"
        final["music_cue"] = "fade_out"
        final["caption_highlights"] = [{"word": w, "emphasis": "strong"} for w in _words(canonical)[:3]]
        final["emphasis_word"] = _words(canonical)[0]
        _sanitize_final_visuals(final, original_final, current_topic)

        if key not in _topic_key(final["narration"]):
            raise RuntimeError("Canonical next topic was not inserted into Scene 7.")
        if any(key in _topic_key(scene.get("narration", "")) for scene in scenes[:6]):
            raise RuntimeError("Next topic appeared before Scene 7.")

        print(f"🔒 Canonical next topic: {canonical}")
        print(f"🗣️ GEMINI FINAL BRIDGE: {final['narration']}")
        return script, canonical

    main.lock_next_topic = lock_next_topic


def _install_gemini_verifier_resilience():
    """Make transient Gemini verification disconnects non-fatal."""
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
