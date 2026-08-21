"""Word-accurate caption timing for Mint-YT-Factory.

Whisper is used for REAL word-level timestamps. The narration text stored in
script.json remains authoritative for the exact words displayed on screen.

The previous implementation used sentence/segment timestamps and then guessed
where each word occurred by character length. That caused captions to drift
away from the spoken audio, especially around pauses and short words.
"""

from __future__ import annotations

import json
import os
import re

import whisper

WHISPER_MODEL_NAME = "tiny.en"
_model = None


_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")


def _get_model():
    global _model
    if _model is None:
        print(f"🎙️ Loading Whisper model: {WHISPER_MODEL_NAME}")
        _model = whisper.load_model(WHISPER_MODEL_NAME)
        print(f"✅ Whisper model ready: {WHISPER_MODEL_NAME}")
    return _model


def _clean_word(value):
    return re.sub(r"[^a-z0-9'’-]+", "", str(value or "").lower()).strip()


def _load_expected_words(audio_path):
    """Load the exact narration words that were sent to TTS."""
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
    """Extract REAL Whisper word timestamps from every segment."""
    output = []

    for segment in result.get("segments", []) or []:
        segment_start = max(0.0, float(segment.get("start", 0.0)))
        segment_end = max(segment_start + 0.05, float(segment.get("end", segment_start + 0.05)))

        segment_words = segment.get("words") or []

        # Some Whisper builds can return a segment without word entries.
        # We deliberately do NOT invent word positions here.
        for item in segment_words:
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

            output.append({
                "word": word,
                "start": start,
                "end": end,
            })

    output.sort(key=lambda item: (item["start"], item["end"]))
    return output


def _finalize_words(words):
    """Make timings safe for the one-word-at-a-time renderer."""
    normalized = []
    previous_end = 0.0

    for item in words:
        start = max(0.0, float(item["start"]))
        end = max(start + 0.04, float(item["end"]))

        # Never let a word overlap the preceding word.
        if start < previous_end:
            start = previous_end
            end = max(start + 0.04, end)

        normalized.append({
            "word": str(item["word"]).strip(),
            "start": start,
            "end": end,
        })
        previous_end = end

    return normalized


def _map_expected_words(expected, whisper_words):
    """Use Whisper timing but the exact script wording.

    In the normal case the counts match and this is a direct 1:1 mapping.
    If Whisper inserts/omits a token, we keep its REAL timestamps and use a
    conservative sequential alignment instead of returning guessed timings.
    """
    if not whisper_words:
        return []

    if not expected:
        return _finalize_words(whisper_words)

    # Best case: TTS narration and Whisper tokenization have the same count.
    # This gives us exact script words with exact audio-derived timestamps.
    if len(expected) == len(whisper_words):
        mapped = []
        for expected_word, observed in zip(expected, whisper_words):
            mapped.append({
                "word": expected_word,
                "start": observed["start"],
                "end": observed["end"],
            })
        return _finalize_words(mapped)

    # More robust fallback: align normalized tokens using dynamic programming.
    # This handles occasional Whisper punctuation/token differences without
    # falling back to character-weight timing.
    n = len(expected)
    m = len(whisper_words)
    dp = [[0] * (m + 1) for _ in range(n + 1)]

    for i in range(n):
        for j in range(m):
            a = _clean_word(expected[i])
            b = _clean_word(whisper_words[j]["word"])
            match = 2 if a == b else -1
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
        match = 2 if a == b else -1
        score = dp[i][j]

        if score == dp[i - 1][j - 1] + match:
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

    # If alignment is badly degraded, fail loudly rather than generating
    # captions that visibly disagree with the narration.
    coverage = len(mapped) / float(max(1, len(expected)))
    if coverage < 0.85:
        raise RuntimeError(
            "Whisper word alignment coverage is too low "
            f"({coverage:.0%}). Refusing to generate drifting captions."
        )

    return _finalize_words(mapped)


def transcribe(audio_path):
    print("🎙️ Starting WORD-ACCURATE Whisper caption timing")
    print(f"   Model: {WHISPER_MODEL_NAME}")
    print(f"   Audio: {audio_path}")
    print("   Word timestamps: ENABLED")
    print("   Segment-duration guessing: DISABLED")

    model = _get_model()
    expected = _load_expected_words(audio_path)

    # Supplying the actual narration as an initial prompt improves recognition
    # consistency without using the prompt to fabricate timing.
    prompt = " ".join(expected) if expected else None

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
        initial_prompt=prompt,
        verbose=False,
    )

    whisper_words = _extract_whisper_words(result)
    if not whisper_words:
        raise RuntimeError("Whisper returned no usable word-level timestamps.")

    words = _map_expected_words(expected, whisper_words)
    if not words:
        raise RuntimeError("Whisper word alignment produced no usable captions.")

    print(f"✅ Word-accurate caption timing complete: {len(words)} words")
    print("✅ Timing source: Whisper WORD timestamps")
    print("✅ Display wording source: script.json narration")
    return words
