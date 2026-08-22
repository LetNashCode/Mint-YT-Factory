"""Production overrides for Mint-YT-Factory.

Keeps the main pipeline entrypoint stable while fixing three runtime issues:
1. continuation teasers can inherit a stale Gemini sentence;
2. the TTS function intentionally returns [story.mp3], while main.py expects a
   path-like value during its duration check;
3. Pollinations/FLUX needs a literal visual prompt plus a strong negative prompt,
   while the old runtime image gate was retrying the same bad generation too many
   times (OCR + strict vision wrappers stacked together).

The normal main.py pipeline is still used. This module only installs safer
runtime implementations before calling main.run().
"""

from __future__ import annotations

import io
import os
import re
import time
import urllib.parse

import requests


class AudioPath(list):
    """List-compatible narration result that is also path-like."""

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


_CONTINUATION_NOISE = re.compile(
    r"\b(?:speaking of|on a related note|that brings us to|that leaves one|"
    r"which raises|which brings up|one bigger question|another question|"
    r"one more thing to wonder about|next video|next short|next topic|"
    r"coming next|stay tuned|part 2|and next|next:)\b",
    re.I,
)


def _clean(text: str) -> str:
    return " ".join(str(text or "").replace("\n", " ").split()).strip()


def _words(text: str) -> list[str]:
    return re.findall(r"\b[\w'-]+\b", _clean(text))


def _topic_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _clean(text).lower()).strip()


def _split_sentences(text: str) -> list[str]:
    return [
        x.strip()
        for x in re.split(r"(?<=[.!?])\s+", _clean(text))
        if x.strip()
    ]


def _remove_stale_teaser(text: str, canonical: str) -> str:
    """Remove Gemini's old continuation clause before inserting the locked one."""
    canonical_key = _topic_key(canonical)
    kept = []
    for sentence in _split_sentences(text):
        normalized = _topic_key(sentence)
        if canonical_key and canonical_key in normalized:
            continue
        if _CONTINUATION_NOISE.search(sentence):
            continue
        kept.append(sentence)
    return " ".join(kept).strip()


def _clean_payoff(text: str, max_words: int = 14) -> str:
    """Choose a complete current-story payoff, never a dangling teaser."""
    sentences = _split_sentences(text)
    candidates = []
    for sentence in sentences:
        if _CONTINUATION_NOISE.search(sentence):
            continue
        words = _words(sentence)
        if not words:
            continue
        if len(words) <= max_words:
            score = 0
            low = sentence.lower()
            for marker in (
                "that's", "that is", "turns out", "because", "so", "which means", "really",
            ):
                if marker in low:
                    score += 2
            if sentence.endswith((".", "!", "?")):
                score += 1
            candidates.append((score, len(words), sentence))

    if candidates:
        # Prefer a clear explanatory/payoff sentence, then the longer complete one.
        return max(candidates, key=lambda x: (x[0], x[1]))[2].rstrip(".!? ") + "."

    words = _words(text)
    if words:
        return " ".join(words[-max_words:]).rstrip(".!?") + "."
    return "And that's the weird part."


def _build_teaser(topic: str) -> str:
    return f"And next: {topic}."


def patch_continuation(main):
    """Replace the continuation lock with a deterministic canonical version."""

    def lock_next_topic(script, current_topic):
        from topics import (
            _PENDING_PREFIX,
            _generate_topic,
            _read_used,
            validate_topic_for_pipeline,
        )

        next_short = script.get("next_short") or {}
        candidate = _clean(next_short.get("topic"))
        if not candidate:
            raise RuntimeError("Generated script did not provide next_short.topic.")

        used = [str(current_topic)]
        used.extend(
            item for item in _read_used()
            if not str(item).startswith(_PENDING_PREFIX)
        )

        canonical = ""
        attempts = [candidate]
        for _ in range(9):
            candidate_now = attempts[-1]
            if (
                _words(candidate_now)
                and len(_words(candidate_now)) <= 7
                and validate_topic_for_pipeline(candidate_now, used=used, check_duplicate=True)
            ):
                canonical = _clean(candidate_now)
                break
            print(f"⚠️ Continuation rejected: {candidate_now}")
            replacement = _clean(_generate_topic(used))
            attempts.append(replacement)

        if not canonical:
            raise RuntimeError("Could not create a valid canonical next topic.")

        script.setdefault("next_short", {})
        script["next_short"]["topic"] = canonical
        script["next_short"]["teaser"] = _build_teaser(canonical)

        scenes = script.get("scene_plan")
        if not isinstance(scenes, list) or len(scenes) != 7:
            raise RuntimeError("Script must contain exactly 7 scenes.")

        final_scene = scenes[-1]
        original = _clean(final_scene.get("narration"))
        base = _remove_stale_teaser(original, canonical)
        payoff = _clean_payoff(base, max_words=14)
        teaser = _build_teaser(canonical)

        final_scene["narration"] = f"{payoff} {teaser}"
        final_scene["subtitle_text"] = final_scene["narration"]
        final_scene["pause_after_ms"] = 150
        final_scene["emotional_tone"] = "satisfied"
        final_scene["music_cue"] = "fade_out"
        final_scene["caption_highlights"] = [
            {"word": word, "emphasis": "strong"}
            for word in _words(canonical)[:3]
        ]
        final_scene["emphasis_word"] = _words(canonical)[0]

        canonical_key = _topic_key(canonical)
        if canonical_key not in _topic_key(final_scene["narration"]):
            raise RuntimeError("Canonical next topic was not inserted into Scene 7.")
        for scene in scenes[:6]:
            if canonical_key in _topic_key(scene.get("narration", "")):
                raise RuntimeError("Next topic appeared before Scene 7.")

        print(f"🔒 Canonical next topic: {canonical}")
        print(f"🗣️ FINAL SPOKEN TEASE: {final_scene['narration']}")
        print(f"⏱️ Scene 7 words: {len(_words(final_scene['narration']))}")
        return script, canonical

    main.lock_next_topic = lock_next_topic


def patch_tts_result(main):
    original = main.synthesize_script

    def synthesize_script(script, config, workdir):
        result = original(script, config, workdir)
        if isinstance(result, (list, tuple)) and result:
            return AudioPath(str(result[0]))
        return AudioPath(str(result))

    main.synthesize_script = synthesize_script


def _literal_visual_prompt(scene: dict, visual: dict, shot: int) -> str:
    narration = _clean(scene.get("narration"))
    spoken = _clean(visual.get("spoken_line")) or narration
    focus = _clean(visual.get("visual_focus"))
    action = _clean(visual.get("visual_action"))
    source = _clean(visual.get("image_prompt"))
    must_show = [
        _clean(x) for x in (visual.get("must_show") or [])
        if _clean(x)
    ][:6]

    # The spoken beat is the source of truth. Gemini occasionally produces a
    # weak visual_action such as "lying flat" even when the narration says
    # "sweater clinging to sock". The prompt therefore repeats the actual beat.
    parts = [
        "PHOTOREALISTIC CINEMATIC STORY FRAME.",
        f"LITERAL SPOKEN BEAT: {spoken or narration}.",
        f"Show the exact physical moment described by that sentence, not the general topic.",
    ]
    if focus:
        parts.append(f"Primary visible subject: {focus}.")
    if action:
        parts.append(f"Physical action/state: {action}.")
    if source:
        parts.append(f"Useful visual detail: {source}.")
    if must_show:
        parts.append("Visible details: " + "; ".join(must_show) + ".")

    if shot == 1:
        parts.append("Establish the exact moment clearly; the main action must be immediately obvious.")
    else:
        parts.append("Same story beat, but advance it with a different close-up, physical change, reaction, or revealed detail.")

    parts.extend([
        "Real-world materials, believable scale, natural lighting, realistic shadows and physics.",
        "No metaphorical or symbolic representation.",
        "No people unless a person is explicitly required by the spoken beat.",
        "No text, letters, numbers, labels, logos, captions, subtitles, signs, screens, UI, diagrams, arrows, formulas, charts, watermarks or decorative symbols.",
    ])
    return _clean(" ".join(parts))[:2200]


def patch_visuals(generate_images):
    """Replace stacked OCR/strict wrappers with one clean provider call.

    The existing generate_images() function still performs its batch Gemini
    relevance guard after all 14 images. We only replace the low-level provider
    call so a bad image is not retried 15 times by nested wrappers.
    """

    def build_prompt(scene, visual, script=None, scene_index=1, visual_index=1, correction=""):
        prompt = _literal_visual_prompt(scene, visual, visual_index)
        if correction:
            prompt += f" Correction from visual QC: {correction}."
        return prompt[:2200]

    def generate_image(prompt, width, height, seed):
        base_url = "https://image.pollinations.ai/prompt/"
        current_api = os.environ.get("POLLINATIONS_API_KEY")
        use_current_api = bool(current_api)
        if use_current_api:
            base_url = "https://gen.pollinations.ai/image/"

        # FLUX negative_prompt is supported by the current Pollinations image
        # API; the legacy endpoint simply ignores unknown query parameters.
        negative = (
            "text, letters, words, numbers, labels, logos, watermark, subtitle, caption, "
            "UI, phone screen, diagram, chart, infographic, arrows, equations, "
            "random person, unrelated object, generic laboratory, abstract glowing particles, "
            "fantasy symbolism, illustration, cartoon, duplicated objects"
        )

        encoded = urllib.parse.quote(str(prompt), safe="")
        params = {
            "model": "flux",
            "width": int(width),
            "height": int(height),
            "seed": int(seed),
            "nologo": "true",
            "private": "true",
            "enhance": "false",
            "negative_prompt": negative,
        }
        query = urllib.parse.urlencode(params)
        url = f"{base_url}{encoded}?{query}"

        headers = {
            "User-Agent": "Mint-YT-Factory/visual-engine-v2",
            "Accept": "image/png,image/jpeg,image/webp,*/*",
        }
        if current_api:
            headers["Authorization"] = f"Bearer {current_api}"

        last_error = None
        for attempt in range(3):
            attempt_seed = int(seed) + attempt * 100003
            params["seed"] = attempt_seed
            url = f"{base_url}{encoded}?{urllib.parse.urlencode(params)}"
            try:
                print(f"🎨 FLUX visual attempt {attempt + 1}/3 | seed={attempt_seed} | size={width}x{height}")
                response = requests.get(url, headers=headers, timeout=180)
                if response.status_code != 200:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
                data = response.content
                if len(data) < 10000:
                    raise RuntimeError("Generated image response is suspiciously small.")
                print(f"✅ FLUX image generated: {len(data):,} bytes")
                return data
            except Exception as exc:
                last_error = exc
                print(f"⚠️ FLUX attempt failed: {type(exc).__name__}: {exc}")
                if attempt < 2:
                    time.sleep(2)

        raise RuntimeError(f"FLUX image generation failed after 3 attempts: {last_error}")

    generate_images.build_prompt = build_prompt
    generate_images.generate_image = generate_image
    # One final batch vision check is enough. Do not stack OCR + per-image
    # vision gates around the provider call.
    generate_images.VISUAL_GUARD_MIN_SCORE = 7
    generate_images.VISUAL_GUARD_MAX_REGENERATIONS = 10
    print("🛡️ Visual runtime: single provider retry loop + batch Gemini relevance QC")


def patch_story_style():
    """Make the active entertainment generator more human and less textbook-like."""
    try:
        import generate_script as active
    except Exception:
        return

    existing = getattr(active, "SYSTEM_PROMPT", "")
    if not existing or "MINT FUN-FIRST STYLE OVERRIDE" in existing:
        return

    active.SYSTEM_PROMPT = existing + r"""

MINT FUN-FIRST STYLE OVERRIDE
- The viewer should feel like a clever friend is showing them a weird trick of everyday life.
- Prefer funny personification, vivid verbs and concrete household scenes over scientific vocabulary.
- Translate mechanisms into ordinary language. Example: say "tiny electric tug-of-war" before using "electrical charge".
- Avoid strings of technical nouns such as "charges, particles, molecules, electrons" unless the joke or explanation genuinely needs them.
- Never spend more than one short sentence on the mechanism before returning to something the viewer can picture.
- Use at least one playful or surprising image/comparison when it fits naturally.
- Keep every sentence easy to say aloud and easy to visualize.
- The payoff should feel like a satisfying "ohhh" moment, not a classroom conclusion.
- Visuals must show the funny physical consequence, not an abstract explanation of why it happens.
"""
    print("🎭 Story style: fun-first / human / visual / low-jargon")


def main_entry():
    import main
    import generate_images

    patch_story_style()
    patch_continuation(main)
    patch_tts_result(main)
    patch_visuals(generate_images)

    print("🧩 Runtime fixes loaded: continuation + TTS path + visual generation")
    main.run(dry_run=False)


if __name__ == "__main__":
    main_entry()
