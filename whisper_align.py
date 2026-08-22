"""Word-accurate caption timing for Mint-YT-Factory."""

from __future__ import annotations

import json
import os
import re

import whisper

WHISPER_MODEL_NAME = "tiny.en"
WHISPER_RETRY_MODEL_NAME = "base.en"
_model = None
_retry_model = None

_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")


def _get_model(name=WHISPER_MODEL_NAME):
    global _model, _retry_model
    if name == WHISPER_RETRY_MODEL_NAME:
        if _retry_model is None:
            print(f"🎙️ Loading Whisper retry model: {name}")
            _retry_model = whisper.load_model(name)
            print(f"✅ Whisper retry model ready: {name}")
        return _retry_model

    if _model is None:
        print(f"🎙️ Loading Whisper model: {name}")
        _model = whisper.load_model(name)
        print(f"✅ Whisper model ready: {name}")
    return _model


def _clean_word(value):
    return re.sub(r"[^a-z0-9'’-]+", "", str(value or "").lower()).strip()


def _load_expected_words(audio_path):
    try:
        run_dir = os.path.dirname(os.path.dirname(os.path.abspath(audio_path)))
        script_path = os.path.join(run_dir, "script.json")
        if not os.path.isfile(script_path):
            return []
        with open(script_path, "r", encoding="utf-8") as handle:
            script = json.load(handle)
        text = " ".join(
            str(scene.get("narration", ""))
            for scene in script.get("scene_plan", [])
            if isinstance(scene, dict)
        )
        return _WORD_RE.findall(text)
    except Exception:
        return []


def _extract_whisper_words(result):
    output = []
    for segment in result.get("segments", []) or []:
        segment_start = max(0.0, float(segment.get("start", 0.0)))
        segment_end = max(segment_start + 0.05, float(segment.get("end", segment_start + 0.05)))
        for item in segment.get("words") or []:
            if not isinstance(item, dict):
                continue
            word = str(item.get("word", "")).strip()
            if not word:
                continue
            try:
                start = max(segment_start, float(item.get("start", segment_start)))
                end = max(start + 0.04, float(item.get("end", start + 0.04)))
                end = min(end, segment_end)
            except Exception:
                continue
            output.append({"word": word, "start": start, "end": end})
    output.sort(key=lambda item: (item["start"], item["end"]))
    return output


def _finalize_words(words):
    normalized = []
    previous_end = 0.0
    for item in words:
        start = max(0.0, float(item["start"]))
        end = max(start + 0.04, float(item["end"]))
        if start < previous_end:
            start = previous_end
            end = max(start + 0.04, end)
        normalized.append({"word": str(item["word"]).strip(), "start": start, "end": end})
        previous_end = end
    return normalized


def _alignment(expected, whisper_words):
    if not whisper_words:
        return [], 0.0
    if not expected:
        return _finalize_words(whisper_words), 1.0

    n, m = len(expected), len(whisper_words)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n):
        for j in range(m):
            a = _clean_word(expected[i])
            b = _clean_word(whisper_words[j]["word"])
            match = 3 if a == b else (-0.5 if a[:4] == b[:4] else -2)
            dp[i + 1][j + 1] = max(
                dp[i][j + 1] - 1,
                dp[i + 1][j] - 1,
                dp[i][j] + match,
            )

    pairs = []
    i, j = n, m
    while i > 0 and j > 0:
        a = _clean_word(expected[i - 1])
        b = _clean_word(whisper_words[j - 1]["word"])
        match = 3 if a == b else (-0.5 if a[:4] == b[:4] else -2)
        score = dp[i][j]
        if score == dp[i - 1][j - 1] + match:
            if a == b or (len(a) >= 4 and len(b) >= 4 and a[:4] == b[:4]):
                pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif score == dp[i - 1][j] - 1:
            i -= 1
        else:
            j -= 1

    pairs.reverse()
    mapped = []
    for expected_index, whisper_index in pairs:
        observed = whisper_words[whisper_index]
        mapped.append({
            "word": expected[expected_index],
            "start": observed["start"],
            "end": observed["end"],
        })

    return _finalize_words(mapped), len(mapped) / float(max(1, len(expected)))


def _transcribe(model, audio_path, expected, strong=False):
    # The narration itself is supplied as a prompt only to improve recognition.
    # It is never used as a source of timing.
    return model.transcribe(
        audio_path,
        language="en",
        task="transcribe",
        word_timestamps=True,
        fp16=False,
        temperature=0,
        best_of=3 if strong else 1,
        beam_size=5 if strong else 1,
        condition_on_previous_text=True if strong else False,
        compression_ratio_threshold=2.8,
        logprob_threshold=-1.2,
        no_speech_threshold=0.35,
        initial_prompt=" ".join(expected) if expected else None,
        verbose=False,
    )


def transcribe(audio_path):
    print("🎙️ Starting WORD-ACCURATE Whisper caption timing")
    print(f"   Model: {WHISPER_MODEL_NAME} → retry: {WHISPER_RETRY_MODEL_NAME}")
    print(f"   Audio: {audio_path}")
    print("   Word timestamps: ENABLED")
    print("   Segment-duration guessing: DISABLED")

    expected = _load_expected_words(audio_path)

    # Pass 1: tiny.en keeps normal production fast.
    result = _transcribe(_get_model(), audio_path, expected, strong=False)
    whisper_words = _extract_whisper_words(result)
    words, coverage = _alignment(expected, whisper_words)
    print(f"🔎 Whisper alignment pass 1: {len(words)}/{len(expected)} words ({coverage:.0%})")

    # TTS audio can occasionally confuse tiny.en, especially with expressive
    # voices. Retry with base.en before declaring the captions unusable.
    if coverage < 0.85:
        print("⚠️ Whisper coverage below 85%; retrying with base.en + stronger decoding")
        result = _transcribe(_get_model(WHISPER_RETRY_MODEL_NAME), audio_path, expected, strong=True)
        whisper_words = _extract_whisper_words(result)
        words, coverage = _alignment(expected, whisper_words)
        print(f"🔎 Whisper alignment pass 2: {len(words)}/{len(expected)} words ({coverage:.0%})")

    if not words:
        raise RuntimeError("Whisper word alignment produced no usable captions.")

    # Do not publish severely incomplete captions. A small number of tokenization
    # mismatches is acceptable; the timestamps still come exclusively from Whisper.
    if coverage < 0.70:
        raise RuntimeError(
            "Whisper word alignment coverage remains too low "
            f"({coverage:.0%}) after tiny.en and base.en retries."
        )

    if coverage < 0.85:
        print(f"⚠️ Caption alignment coverage: {coverage:.0%}; using matched Whisper timings only")

    print(f"✅ Word-accurate caption timing complete: {len(words)} matched words")
    print("✅ Timing source: Whisper WORD timestamps")
    print("✅ Display wording source: script.json narration")
    return words
