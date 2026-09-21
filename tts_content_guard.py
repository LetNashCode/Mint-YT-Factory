"""Hard verification that generated Publish Shorts audio contains the full script."""
from __future__ import annotations
import json, re, traceback
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


def _direct_decode(model, audio_path):
    """Transcribe the complete file using Whisper's native sliding-window path.

    Keep previous-text conditioning enabled so the decoder maintains context
    across the 30-second window boundary and does not silently lose a late
    scene or continuation bridge. The content gate validates the audio text;
    it must not mistake a context-reset transcription gap for missing speech.
    """
    result = model.transcribe(
        str(audio_path),
        language="en",
        task="transcribe",
        word_timestamps=False,
        fp16=False,
        temperature=0.0,
        beam_size=5,
        best_of=5,
        condition_on_previous_text=True,
        verbose=False,
    )
    return str(result.get("text") or "").strip()


def _observed_text(text):
    """Tokenize Whisper text while expanding hyphenated compounds."""
    observed = []
    for word in _WORD_RE.findall(str(text or "")):
        parts = re.split(r"[-–—]", word)
        observed.extend(part.lower() for part in parts if part)
    return observed


def _norm(word):
    return re.sub(r"[^a-z0-9]+", "", str(word).lower())


def _align(expected, observed):
    """Return LCS word indexes using a complete (n+1) x (m+1) DP table."""
    n, m = len(expected), len(observed)
    if not n or not m:
        return set()
    rows = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        a = _norm(expected[i - 1])
        for j in range(1, m + 1):
            b = _norm(observed[j - 1])
            if a and a == b:
                rows[i][j] = rows[i - 1][j - 1] + 1
            else:
                rows[i][j] = max(rows[i - 1][j], rows[i][j - 1])
    matched = set()
    i, j = n, m
    while i > 0 and j > 0:
        if _norm(expected[i - 1]) and _norm(expected[i - 1]) == _norm(observed[j - 1]) and rows[i][j] == rows[i - 1][j - 1] + 1:
            matched.add(i - 1)
            i -= 1
            j -= 1
        elif rows[i - 1][j] >= rows[i][j - 1]:
            i -= 1
        else:
            j -= 1
    return matched


def verify_narration(audio_path: str, script_path: str, *, log_prefix="🎙️"):
    scenes = _expected(script_path)
    expected = [w for scene in scenes for w in scene]
    if not expected:
        raise RuntimeError("Narration content gate: script contains no expected words.")
    best = set()
    observed_count = 0
    best_model = None
    for name in (MODEL_NAME, RETRY_MODEL_NAME):
        try:
            transcript = _direct_decode(_get_model(name), audio_path)
            observed = _observed_text(transcript)
            matched = _align(expected, observed)
            if len(matched) > len(best):
                best, observed_count, best_model = matched, len(observed), name
            coverage = len(matched) / max(1, len(expected))
            print(f"{log_prefix} Whisper {name}: observed={len(observed)} words | matched={len(matched)} ({coverage:.0%})")
            if coverage >= MIN_COVERAGE:
                break
        except Exception as exc:
            print(f"⚠️ Narration content check {name} failed: {type(exc).__name__}: {exc}")
            traceback.print_exc()
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
        hits = sum(1 for i in range(cursor, cursor + len(scene_words)) if i in best)
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
        raise RuntimeError(f"Narration content verification failed: coverage={coverage:.1%}, longest_missing_run={longest_run}, bad_scenes={[x['scene'] for x in bad_scenes]}, missing_sample={missing_words!r}")
    return {"passed": True, "coverage": coverage, "longest_missing_run": longest_run, "scene_results": scene_results, "observed_words": observed_count, "model": best_model}
