"""Reliable word-level caption timing for Mint-YT-Factory.

Whisper provides spoken-word anchors. The aligner then reconstructs the full
script word sequence between those anchors, so a missed Whisper word can never
make captions silently disappear or jump ahead of the narration.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import wave

import whisper

WHISPER_MODEL_NAME = "base.en"
WHISPER_RETRY_MODEL_NAME = "tiny.en"
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
        print(f"🎙️ Loading Whisper caption model: {name}")
        _model = whisper.load_model(name)
        print(f"✅ Whisper caption model ready: {name}")
    return _model


def _clean_word(value):
    return re.sub(r"[^a-z0-9'’-]+", "", str(value or "").lower()).strip()


def _load_expected_words(audio_path):
    try:
        run_dir = os.path.dirname(os.path.dirname(os.path.abspath(audio_path)))
        script_path = os.path.join(run_dir, "script.json")
        with open(script_path, "r", encoding="utf-8") as handle:
            script = json.load(handle)
        text = " ".join(str(scene.get("narration", "")) for scene in script.get("scene_plan", []) if isinstance(scene, dict))
        return _WORD_RE.findall(text)
    except Exception as error:
        print(f"⚠️ Could not load expected narration words: {error}")
        return []


def _audio_duration(audio_path):
    try:
        with contextlib.closing(wave.open(audio_path, "rb")) as wav_file:
            return wav_file.getnframes() / float(wav_file.getframerate())
    except Exception:
        try:
            from moviepy.editor import AudioFileClip
            clip = AudioFileClip(audio_path)
            duration = float(clip.duration)
            clip.close()
            return duration
        except Exception:
            return 36.0


def _extract_whisper_words(result):
    observed = []
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
                end = min(segment_end, max(start + 0.04, float(item.get("end", start + 0.04))))
                observed.append({"word": word, "start": start, "end": end})
            except Exception:
                continue
    return sorted(observed, key=lambda item: (item["start"], item["end"]))


def _finalize(words, duration):
    result = []
    previous_end = 0.0
    for item in words:
        start = max(0.0, min(float(item["start"]), duration))
        end = max(start + 0.04, min(float(item["end"]), duration))
        if start < previous_end:
            start = previous_end
            end = max(start + 0.04, end)
        if start >= duration:
            start = max(0.0, duration - 0.04)
            end = duration
        end = min(duration, end)
        result.append({"word": str(item["word"]).strip(), "start": start, "end": max(start + 0.04, end)})
        previous_end = result[-1]["end"]
    return result


def _alignment(expected, observed):
    if not expected or not observed:
        return [], 0.0
    n, m = len(expected), len(observed)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n):
        a = _clean_word(expected[i])
        for j in range(m):
            b = _clean_word(observed[j]["word"])
            match = 4 if a == b else (1 if len(a) >= 4 and len(b) >= 4 and a[:4] == b[:4] else -2)
            dp[i + 1][j + 1] = max(dp[i][j + 1] - 1, dp[i + 1][j] - 1, dp[i][j] + match)
    pairs = []
    i, j = n, m
    while i and j:
        a = _clean_word(expected[i - 1]); b = _clean_word(observed[j - 1]["word"])
        match = 4 if a == b else (1 if len(a) >= 4 and len(b) >= 4 and a[:4] == b[:4] else -2)
        score = dp[i][j]
        if score == dp[i - 1][j - 1] + match:
            if a == b or (len(a) >= 4 and len(b) >= 4 and a[:4] == b[:4]):
                pairs.append((i - 1, j - 1))
            i -= 1; j -= 1
        elif score == dp[i - 1][j] - 1:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    mapped = [{"expected_index": a, "word": expected[a], "start": observed[b]["start"], "end": observed[b]["end"]} for a, b in pairs]
    return mapped, len(mapped) / float(max(1, n))


def _word_weight(word):
    letters = len(re.sub(r"[^A-Za-z]", "", word))
    punctuation_bonus = 0.55 if str(word).endswith((".", "!", "?")) else 0.0
    return max(1.0, letters * 0.78 + punctuation_bonus)


def _fill_gap(expected, left_index, right_index, left_time, right_time, output):
    indexes = list(range(left_index, right_index))
    if not indexes:
        return
    weights = [_word_weight(expected[index]) for index in indexes]
    total = sum(weights) or 1.0
    cursor = left_time
    span = max(0.04, right_time - left_time)
    for index, weight in zip(indexes, weights):
        word_span = span * weight / total
        output.append({"expected_index": index, "word": expected[index], "start": cursor, "end": min(right_time, cursor + word_span)})
        cursor += word_span


def _reconstruct_full_timeline(expected, anchors, duration):
    """Keep Whisper's real anchors while filling every missed script word."""
    if not expected:
        return []
    if not anchors:
        weights = [_word_weight(word) for word in expected]
        total = sum(weights) or 1.0
        cursor = 0.0
        result = []
        for word, weight in zip(expected, weights):
            span = duration * weight / total
            result.append({"word": word, "start": cursor, "end": min(duration, cursor + span)})
            cursor += span
        return _finalize(result, duration)

    anchors = sorted(anchors, key=lambda item: item["expected_index"])
    output = []
    first = anchors[0]
    _fill_gap(expected, 0, first["expected_index"], 0.0, first["start"], output)
    output.append({"expected_index": first["expected_index"], "word": first["word"], "start": first["start"], "end": first["end"]})
    for current, following in zip(anchors, anchors[1:]):
        _fill_gap(expected, current["expected_index"] + 1, following["expected_index"], current["end"], following["start"], output)
        output.append({"expected_index": following["expected_index"], "word": following["word"], "start": following["start"], "end": following["end"]})
    last = anchors[-1]
    _fill_gap(expected, last["expected_index"] + 1, len(expected), last["end"], duration, output)
    output.sort(key=lambda item: item["expected_index"])
    return _finalize(output, duration)


def _transcribe(model, audio_path, strong=False):
    return model.transcribe(audio_path, language="en", task="transcribe", word_timestamps=True, fp16=False, temperature=0,
                            best_of=3 if strong else 1, beam_size=5 if strong else 1, condition_on_previous_text=False,
                            compression_ratio_threshold=2.8, logprob_threshold=-1.2, no_speech_threshold=0.35,
                            initial_prompt=None, verbose=False)


def transcribe(audio_path):
    print("🎙️ Starting FULL-SEQUENCE Whisper caption timing")
    print(f"   Primary model: {WHISPER_MODEL_NAME} → retry: {WHISPER_RETRY_MODEL_NAME}")
    expected = _load_expected_words(audio_path)
    duration = _audio_duration(audio_path)
    if not expected:
        raise RuntimeError("Caption timing could not load narration text from script.json.")

    best_anchors = []
    best_coverage = 0.0
    for model_name, strong in ((WHISPER_MODEL_NAME, True), (WHISPER_RETRY_MODEL_NAME, False)):
        try:
            result = _transcribe(_get_model(model_name), audio_path, strong)
            observed = _extract_whisper_words(result)
            anchors, coverage = _alignment(expected, observed)
            print(f"🔎 Whisper {model_name}: {len(anchors)}/{len(expected)} anchors ({coverage:.0%})")
            if coverage > best_coverage:
                best_anchors, best_coverage = anchors, coverage
            if coverage >= 0.90:
                break
        except Exception as error:
            print(f"⚠️ Whisper {model_name} failed: {type(error).__name__}: {error}")

    timeline = _reconstruct_full_timeline(expected, best_anchors, duration)
    if len(timeline) != len(expected):
        raise RuntimeError(f"Caption reconstruction failed: expected {len(expected)} words, got {len(timeline)}")
    if best_coverage < 0.90:
        print(f"⚠️ Whisper anchor coverage {best_coverage:.0%}; reconstructed all {len(timeline)} captions between speech anchors.")
    else:
        print(f"✅ Whisper timing locked: all {len(timeline)} script words have timestamps.")
    return timeline
