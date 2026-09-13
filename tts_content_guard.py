"""Hard verification that generated Publish Shorts audio contains the full script.

Whisper is used here as an acceptance test only. Caption reconstruction remains
separate; it must never make missing narration look present.
"""
from __future__ import annotations

import contextlib
import json
import re
import wave
from pathlib import Path

import whisper

MODEL_NAME = "base.en"
RETRY_MODEL_NAME = "tiny.en"
MIN_COVERAGE = 0.90
MIN_SCENE_COVERAGE = 0.80
MAX_MISSING_RUN = 7
_model = None
_retry_model = None
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")
_STOP = {"the","a","an","and","or","but","to","of","in","on","at","for","is","are","was","were","it","this","that","with","as","by","from","so","do","does","did","how","why","what","you","your","they","their","we","our"}


def _get_model(name):
    global _model, _retry_model
    if name == RETRY_MODEL_NAME:
        if _retry_model is None:
            _retry_model = whisper.load_model(name)
        return _retry_model
    if _model is None:
        _model = whisper.load_model(name)
    return _model


def _expected(script_path):
    data = json.loads(Path(script_path).read_text(encoding="utf-8"))
    scenes = data.get("scene_plan") or []
    return [[w.lower() for w in _WORD_RE.findall(str(s.get("narration") or ""))] for s in scenes if isinstance(s, dict)]


def _audio_duration(path):
    try:
        with contextlib.closing(wave.open(str(path), "rb")) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def _observed(result):
    # The content gate only needs transcript text. Word-level timestamps are
    # deliberately disabled because Whisper's optional alignment path is more
    # fragile than ordinary transcription and adds no value to this check.
    words = []
    for seg in result.get("segments", []) or []:
        text = str(seg.get("text") or "")
        tokens = _WORD_RE.findall(text)
        if tokens:
            words.extend(x.lower() for x in tokens)
    if not words:
        text = str(result.get("text") or "")
        words = [w.lower() for w in _WORD_RE.findall(text)]
    return words


def _norm(word):
    word = re.sub(r"[^a-z0-9]+", "", word.lower())
    if word.endswith("'s"):
        word = word[:-2]
    return word


def _align(expected, observed):
    n, m = len(expected), len(observed)
    if not n or not m:
        return set()
    # Bounded banded LCS-like alignment. Exact words are preferred; small
    # filler differences do not erase the fact that a whole phrase is absent.
    prev = [0] * (m + 1)
    rows = []
    for i in range(n):
        cur = [0] * (m + 1)
        a = _norm(expected[i])
        for j in range(m):
            if a and a == _norm(observed[j]):
                cur[j + 1] = prev[j] + 1
            else:
                cur[j + 1] = max(prev[j + 1], cur[j])
        rows.append(cur)
        prev = cur
    matched = set()
    i, j = n, m
    while i and j:
        if _norm(expected[i - 1]) and _norm(expected[i - 1]) == _norm(observed[j - 1]) and rows[i - 1][j - 1] + 1 == rows[i][j]:
            matched.add(i - 1); i -= 1; j -= 1
        elif rows[i - 1][j] >= rows[i][j - 1]:
            i -= 1
        else:
            j -= 1
    return matched


def verify_narration(audio_path: str, script_path: str, *, log_prefix="🎙️") -> dict:
    scenes = _expected(script_path)
    expected = [w for scene in scenes for w in scene]
    if not expected:
        raise RuntimeError("Narration content gate: script contains no expected words.")
    best = set()
    observed_count = 0
    best_model = None
    for name in (MODEL_NAME, RETRY_MODEL_NAME):
        try:
            result = _get_model(name).transcribe(
                str(audio_path), language="en", task="transcribe", word_timestamps=False,
                fp16=False, temperature=0, best_of=3 if name == MODEL_NAME else 1,
                beam_size=5 if name == MODEL_NAME else 1,
                condition_on_previous_text=False, compression_ratio_threshold=2.8,
                logprob_threshold=-1.2, no_speech_threshold=0.35, verbose=False,
            )
            observed = _observed(result)
            matched = _align(expected, observed)
            if len(matched) > len(best):
                best, observed_count, best_model = matched, len(observed), name
            coverage = len(matched) / max(1, len(expected))
            if coverage >= MIN_COVERAGE:
                break
        except Exception as exc:
            print(f"⚠️ Narration content check {name} failed: {type(exc).__name__}: {exc}")

    missing = [i for i in range(len(expected)) if i not in best]
    longest_run = 0
    current = 0
    for i in range(len(expected)):
        if i in best:
            current = 0
        else:
            current += 1
            longest_run = max(longest_run, current)

    scene_results = []
    cursor = 0
    for number, scene_words in enumerate(scenes, 1):
        indexes = range(cursor, cursor + len(scene_words))
        hits = sum(1 for i in indexes if i in best)
        coverage = hits / max(1, len(scene_words))
        scene_results.append({"scene": number, "expected_words": len(scene_words), "matched_words": hits, "coverage": round(coverage, 4)})
        cursor += len(scene_words)

    coverage = len(best) / max(1, len(expected))
    bad_scenes = [x for x in scene_results if x["coverage"] < MIN_SCENE_COVERAGE]
    passed = coverage >= MIN_COVERAGE and longest_run <= MAX_MISSING_RUN and not bad_scenes
    print(f"{log_prefix} CONTENT CHECK: {len(best)}/{len(expected)} words matched ({coverage:.0%}) | longest missing run={longest_run} | model={best_model or 'none'}")
    for item in scene_results:
        print(f"   Scene {item['scene']}: {item['matched_words']}/{item['expected_words']} ({item['coverage']:.0%})")
    if not passed:
        missing_words = " ".join(expected[i] for i in missing[:20])
        raise RuntimeError(
            f"Narration content verification failed: coverage={coverage:.1%}, longest_missing_run={longest_run}, "
            f"bad_scenes={[x['scene'] for x in bad_scenes]}, missing_sample={missing_words!r}"
        )
    return {"passed": True, "coverage": coverage, "longest_missing_run": longest_run, "scene_results": scene_results, "observed_words": observed_count, "model": best_model}
