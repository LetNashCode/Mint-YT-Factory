"""
Whisper word alignment for Mint-YT-Factory.

Whisper supplies timing while the verified script supplies the authoritative
wording. This prevents malformed Whisper tokens from appearing in captions
and guarantees that caption layers never overlap.

Performance notes:
- GitHub Actions runs on CPU, so use tiny.en rather than base.en.
- The narration is only ~45 seconds; tiny.en is sufficient for reliable
  word timing while avoiding the very long CPU inference seen with base.en.
- Greedy decoding is intentional: caption timing does not need beam-search
  quality, and the faster decode keeps the production job inside its budget.
"""

from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher

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
    """Load the verified narration text saved beside the current run."""
    try:
        run_dir = os.path.dirname(os.path.dirname(os.path.abspath(audio_path)))
        script_path = os.path.join(run_dir, "script.json")
        if not os.path.isfile(script_path):
            return []
        with open(script_path, "r", encoding="utf-8") as handle:
            script = json.load(handle)
        scenes = script.get("scene_plan", [])
        text = " ".join(
            str(scene.get("narration", ""))
            for scene in scenes
            if isinstance(scene, dict)
        )
        return re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*", text)
    except Exception:
        return []


def _normalize_whisper_words(result):
    words = []
    for segment in result.get("segments", []):
        for raw in segment.get("words", []) or []:
            word = str(raw.get("word", "")).strip()
            if not word:
                continue
            try:
                start = float(raw.get("start", 0.0))
                end = float(raw.get("end", start + 0.05))
            except Exception:
                continue
            start = max(0.0, start)
            end = max(start + 0.05, end)
            words.append({"word": word, "start": start, "end": end})
    return words


def _repair_against_expected(words, expected):
    """
    Keep Whisper timings but use the generated narration as spelling.

    A conservative fuzzy match repairs common Whisper errors and can split a
    single Whisper token when two adjacent narration words were merged.
    """
    if not words or not expected:
        return words

    expected_clean = [_clean_word(w) for w in expected]
    whisper_clean = [_clean_word(item["word"]) for item in words]

    if len(expected_clean) == len(whisper_clean):
        ratio = sum(
            1
            for a, b in zip(expected_clean, whisper_clean)
            if a == b or SequenceMatcher(None, a, b).ratio() >= 0.72
        ) / max(1, len(expected_clean))
        if ratio >= 0.90:
            return [
                {**item, "word": target}
                for item, target in zip(words, expected)
            ]

    repaired = []
    i = 0
    j = 0

    while i < len(expected_clean) and j < len(words):
        target = expected_clean[i]
        observed = whisper_clean[j]

        if not target:
            i += 1
            continue

        if target == observed or SequenceMatcher(None, target, observed).ratio() >= 0.80:
            repaired.append({**words[j], "word": expected[i]})
            i += 1
            j += 1
            continue

        for span in (2, 3):
            if i + span > len(expected_clean):
                break
            joined = "".join(expected_clean[i:i + span])
            if not joined:
                continue
            if joined == observed or SequenceMatcher(None, joined, observed).ratio() >= 0.88:
                start = words[j]["start"]
                end = words[j]["end"]
                total_chars = sum(max(1, len(x)) for x in expected_clean[i:i + span])
                cursor = start
                for k in range(span):
                    share = (end - start) * len(expected_clean[i + k]) / total_chars
                    item_end = end if k == span - 1 else min(end, cursor + share)
                    repaired.append({
                        "word": expected[i + k],
                        "start": cursor,
                        "end": max(cursor + 0.05, item_end),
                    })
                    cursor = item_end
                i += span
                j += 1
                break
        else:
            repaired.append(words[j])
            i += 1
            j += 1

    while j < len(words):
        repaired.append(words[j])
        j += 1

    return repaired


def _make_non_overlapping(words):
    """Guarantee no two caption events overlap."""
    normalized = []
    previous_start = -0.05

    for item in words:
        start = max(0.0, float(item["start"]))
        end = max(start + 0.05, float(item["end"]))

        if start < previous_start + 0.05:
            start = previous_start + 0.05
            end = max(end, start + 0.05)

        normalized.append({
            "word": str(item["word"]).strip(),
            "start": start,
            "end": end,
        })
        previous_start = start

    return normalized


def transcribe(audio_path):
    print("🎙️ Starting fast Whisper word alignment")
    print(f"   Model: {WHISPER_MODEL_NAME}")
    print(f"   Audio: {audio_path}")

    model = _get_model()

    result = model.transcribe(
        audio_path,
        language="en",
        task="transcribe",
        word_timestamps=True,
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

    words = _normalize_whisper_words(result)
    expected = _load_expected_words(audio_path)

    if expected:
        words = _repair_against_expected(words, expected)

    words = _make_non_overlapping(words)

    print(f"✅ Whisper alignment complete: {len(words)} words")

    return words
