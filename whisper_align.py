"""Fast caption timing for Mint-YT-Factory.

Whisper provides sentence/segment timing on CPU. The verified narration text
is authoritative; words are distributed across each Whisper segment instead
of using Whisper's expensive word_timestamps alignment pass.
"""

from __future__ import annotations

import json
import os
import re

import whisper

WHISPER_MODEL_NAME = "tiny.en"
_model = None


def _get_model():
    global _model
    if _model is None:
        print("🎙️ Loading Whisper model: tiny.en")
        _model = whisper.load_model(WHISPER_MODEL_NAME)
        print("✅ Whisper model ready: tiny.en")
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
        return re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*", text)
    except Exception:
        return []


def _segment_words(segment):
    return re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*", str(segment.get("text", "")))


def _build_words_from_segments(result, expected):
    segments = result.get("segments", []) or []
    if not segments:
        return []

    # Use verified narration wording whenever possible. Match expected words
    # to Whisper segment text by simple sequential normalization.
    expected_index = 0
    output = []

    for segment in segments:
        try:
            start = max(0.0, float(segment.get("start", 0.0)))
            end = max(start + 0.08, float(segment.get("end", start + 0.08)))
        except Exception:
            continue

        observed = _segment_words(segment)
        count = len(observed)
        if count == 0:
            continue

        if expected:
            remaining = len(expected) - expected_index
            take = min(count, remaining)
            words = expected[expected_index:expected_index + take]
            expected_index += take
        else:
            words = observed

        if not words:
            continue

        # Allocate the segment duration by character weight. This gives short
        # words less screen time and long words more, without expensive word
        # timestamp alignment.
        weights = [max(1, len(_clean_word(word))) for word in words]
        total_weight = sum(weights)
        duration = end - start
        cursor = start

        for index, word in enumerate(words):
            share = duration * weights[index] / total_weight
            item_end = end if index == len(words) - 1 else cursor + share
            output.append({
                "word": word,
                "start": cursor,
                "end": max(cursor + 0.05, item_end),
            })
            cursor = item_end

    # If Whisper's segmentation omitted a few expected words, append them over
    # the remaining narration duration rather than silently losing captions.
    if expected_index < len(expected):
        last_end = output[-1]["end"] if output else 0.0
        tail = expected[expected_index:]
        duration = max(0.05, (result.get("segments", [])[-1].get("end", last_end) if result.get("segments") else last_end) - last_end)
        weights = [max(1, len(_clean_word(word))) for word in tail]
        total_weight = sum(weights) or 1
        cursor = last_end
        for index, word in enumerate(tail):
            share = duration * weights[index] / total_weight
            item_end = cursor + share
            output.append({"word": word, "start": cursor, "end": max(cursor + 0.05, item_end)})
            cursor = item_end

    normalized = []
    previous_start = -0.05
    for item in output:
        start = max(0.0, float(item["start"]))
        end = max(start + 0.05, float(item["end"]))
        if start < previous_start + 0.05:
            start = previous_start + 0.05
            end = max(end, start + 0.05)
        normalized.append({"word": str(item["word"]).strip(), "start": start, "end": end})
        previous_start = start
    return normalized


def transcribe(audio_path):
    print("🎙️ Starting FAST Whisper caption timing")
    print(f"   Model: {WHISPER_MODEL_NAME}")
    print(f"   Audio: {audio_path}")

    model = _get_model()
    result = model.transcribe(
        audio_path,
        language="en",
        task="transcribe",
        word_timestamps=False,
        fp16=False,
        temperature=0,
        best_of=1,
        beam_size=1,
        condition_on_previous_text=False,
        compression_ratio_threshold=2.4,
        logprob_threshold=-1.0,
        no_speech_threshold=0.55,
        verbose=False,
    )

    expected = _load_expected_words(audio_path)
    words = _build_words_from_segments(result, expected)

    if not words:
        raise RuntimeError("Whisper returned no usable caption timings.")

    print(f"✅ Fast caption timing complete: {len(words)} words")
    return words
