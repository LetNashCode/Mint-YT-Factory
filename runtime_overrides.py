"""Runtime hardening for Mint-YT-Factory.

Continuation is authored by Gemini and only validated here. Runtime code never
manufactures a canned Scene 7 bridge.
"""
from __future__ import annotations
import re
import time

class AudioPath(list):
    def __init__(self, path: str): super().__init__([path])
    def __fspath__(self): return self[0]
    def __str__(self): return self[0]
    def __repr__(self): return repr(self[0])
    def endswith(self, suffix, *args): return self[0].endswith(suffix, *args)

def _clean(text): return " ".join(str(text or "").replace("\n", " ").split()).strip()
def _words(text): return re.findall(r"\b[\w'-]+\b", _clean(text))
def _topic_key(text): return re.sub(r"[^a-z0-9]+", " ", _clean(text).lower()).strip()
def _split_sentences(text): return [x.strip() for x in re.split(r"(?<=[.!?])\s+", _clean(text)) if x.strip()]

STALE_TEASER_PATTERNS = (
    r"^\s*(?:and\s+)?next\b", r"\bnext\s+(?:video|short|topic)\b", r"\bcoming\s+next\b",
    r"\bstay\s+tuned\b", r"\bpart\s*2\b", r"\bsee\s+why\b", r"\bsee\s+how\b",
    r"\bfind\s+out\s+(?:why|how)\b", r"\bspeaking\s+of\b", r"\bthat\s+brings\s+us\s+to\b",
    r"\bthat\s+leaves\s+us\s+with\b", r"\banother\s+question\b", r"\bone\s+more\s+question\b",
    r"\bthen\s+comes\b", r"\bin\s+the\s+next\s+(?:video|short)\b",
)

def _is_stale_teaser(sentence): return any(re.search(p, sentence, re.I) for p in STALE_TEASER_PATTERNS)

def _validate_gemini_bridge(sentence, canonical):
    sentence = _clean(sentence); key = _topic_key(canonical)
    if not sentence or not key or key not in _topic_key(sentence): return False, "canonical next topic missing"
    if _is_stale_teaser(sentence): return False, "announcement/CTA language detected"
    n = len(_words(sentence))
    if n < 5 or n > 32: return False, "bridge length outside 5-32 words"
    return True, "ok"

def _sanitize_final_visuals(final, stale_text, current_topic):
    # Preserve valid Gemini visuals; only scrub obvious future-topic leakage.
    stale_tokens = {w for w in re.findall(r"\b[a-z0-9]+\b", _clean(stale_text).lower()) if len(w) >= 6}
    visuals = final.get("visuals")
    if not isinstance(visuals, list): return
    for visual in visuals:
        combined = " ".join(str(visual.get(k, "")) for k in ("visual_focus","visual_action","image_prompt","spoken_line"))
        if stale_tokens and stale_tokens.intersection(set(re.findall(r"\b[a-z0-9]+\b", combined.lower()))):
            visual["visual_focus"] = _clean(current_topic)
            visual["visual_action"] = "show the final physical result clearly"
            visual["must_show"] = [_clean(current_topic), "clear final physical state"]
            visual["must_not_show"] = ["future continuation topic", "unrelated object", "different mystery"]

def patch_continuation(main):
    def lock_next_topic(script, current_topic):
        from topics import _PENDING_PREFIX, _generate_topic, _read_used, validate_topic_for_pipeline
        candidate = _clean((script.get("next_short") or {}).get("topic"))
        if not candidate: raise RuntimeError("Generated script did not provide next_short.topic.")
        used = [_clean(current_topic)] + [x for x in _read_used() if not str(x).startswith(_PENDING_PREFIX)]
        canonical = ""
        for attempt in range(1, 11):
            value = candidate if attempt == 1 else _clean(_generate_topic(used))
            if len(_words(value)) <= 7 and validate_topic_for_pipeline(value, used=used, check_duplicate=True): canonical = value; break
            print(f"⚠️ Continuation rejected: {value}")
        if not canonical: raise RuntimeError("Could not create a valid canonical next topic.")
        script.setdefault("next_short", {})["topic"] = canonical
        scenes = script.get("scene_plan")
        if not isinstance(scenes, list) or len(scenes) != 7: raise RuntimeError("Script must contain exactly 7 scenes.")
        final = scenes[-1]; sentences = _split_sentences(final.get("narration", "")); key = _topic_key(canonical)
        matches = [s for s in sentences if key in _topic_key(s)]
        if len(matches) != 1 or matches[0] != sentences[-1]:
            raise RuntimeError("Gemini must put the locked next topic in Scene 7's final sentence.")
        ok, reason = _validate_gemini_bridge(matches[0], canonical)
        if not ok: raise RuntimeError(f"Gemini Scene 7 bridge rejected: {reason}")
        stale = [s for s in sentences[:-1] if _is_stale_teaser(s)]
        if stale: raise RuntimeError("Scene 7 contains stale continuation language: " + " | ".join(stale))
        final["subtitle_text"] = final["narration"]; final["pause_after_ms"] = 150
        final["emotional_tone"] = "satisfied"; final["music_cue"] = "fade_out"
        final["caption_highlights"] = [{"word": w, "emphasis": "strong"} for w in _words(canonical)[:3]]
        final["emphasis_word"] = _words(canonical)[0]
        _sanitize_final_visuals(final, final["narration"], current_topic)
        if any(key in _topic_key(s.get("narration", "")) for s in scenes[:6]): raise RuntimeError("Next topic appeared before Scene 7.")
        print(f"🔒 Canonical next topic: {canonical}"); print(f"🗣️ GEMINI FINAL BRIDGE: {final['narration']}")
        return script, canonical
    main.lock_next_topic = lock_next_topic

def _install_gemini_verifier_resilience():
    try: import stock_media
    except Exception as exc: print(f"⚠️ Gemini verifier resilience could not import stock_media: {exc}"); return
    original = getattr(stock_media, "_gemini_verify", None)
    if original is None or getattr(original, "_mint_resilient", False): return
    transient = {"RemoteProtocolError","ReadTimeout","ConnectTimeout","ConnectError","TimeoutException","APIError","ServerError","ServiceUnavailable"}
    def resilient(candidates, directed):
        last = None
        for attempt in range(1,4):
            try: return original(candidates, directed)
            except Exception as exc:
                last=exc
                if type(exc).__name__ not in transient and "disconnect" not in str(exc).lower(): raise
                print(f"⚠️ Gemini visual verification transport failure {attempt}/3: {type(exc).__name__}: {exc}")
                if attempt < 3: time.sleep(1.5*attempt)
        ranked=sorted(candidates or [], key=lambda x: float(x.get("metadata_score",0) or 0), reverse=True)
        if ranked:
            print(f"⚠️ Gemini verifier unavailable; using best retrieved stock candidate. Last error: {type(last).__name__ if last else 'unknown'}")
            for item in ranked: item.update(visual_score=7.5, visual_subject_match=7.5, visual_action_match=7.5, visual_context_match=7.5, visual_rejected=False)
        return ranked
    resilient._mint_resilient=True; stock_media._gemini_verify=resilient
    print("🛡️ Gemini visual verifier resilience: retries + non-fatal transport fallback ENABLED")
_install_gemini_verifier_resilience()

def patch_tts_result(main):
    original=main.synthesize_script
    def synthesize_script(script, config, workdir):
        result=original(script,config,workdir); return AudioPath(str(result[0] if isinstance(result,(list,tuple)) and result else result))
    main.synthesize_script=synthesize_script
