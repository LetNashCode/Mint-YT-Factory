"""Mint-YT-Factory runtime quality layer.

This module is intentionally a runtime patch layer so production behavior can
be improved without duplicating the main pipeline.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import io
import os
import re
import sys

SCRIPT_RULES = r"""
ENTERTAINMENT + COHERENCE HARD RULES

Write like a clever friend showing the viewer one weird everyday thing.
The story must be understandable with the sound on and still visually
understandable with sound off.

ENDING CONTRACT:
- Scene 7 MUST finish the current story before the teaser.
- The payoff must answer the hook in plain English.
- Never end on a dangling clause, "so basically...", "which means...", or an
  unfinished "and that's why...".
- The final sentence is the ONLY continuation teaser.
- The teaser must be short and natural, not a CTA.
- Scene 7 must contain a complete payoff and a complete teaser.
- Do not introduce a new fact in the payoff that was not explained earlier.

VISUAL CONTRACT:
Every visual is one literal physical moment. It must identify the exact
subject, exact action/state, real-world setting, and visible consequence/detail.
Never turn narration into symbolic art, diagrams, particles, energy waves,
generic science imagery, unrelated people, generic rooms or landscapes.
Every shot must be directly defensible from the words being spoken.
"""

_EMOJI = {
    "fire":"🔥","hot":"🔥","burn":"🔥","burning":"🔥",
    "cold":"🥶","ice":"🧊","freeze":"🥶","frozen":"🥶",
    "water":"💧","rain":"🌧️","cloud":"☁️","sun":"☀️","sunlight":"☀️",
    "moon":"🌙","star":"⭐","stars":"⭐","earth":"🌍","world":"🌍",
    "space":"🚀","rocket":"🚀","heart":"❤️","love":"❤️","happy":"😊",
    "smile":"😊","sad":"😢","cry":"😭","laugh":"😂","funny":"😂",
    "shock":"😱","shocked":"😱","surprise":"😲","surprised":"😲",
    "idea":"💡","think":"🤔","thinking":"🤔","brain":"🧠",
    "danger":"⚠️","warning":"⚠️","dangerous":"⚠️","money":"💰",
    "rich":"💰","cash":"💵","buy":"🛒","food":"🍔","eat":"🍴",
    "coffee":"☕","drink":"🥤","dog":"🐶","cat":"🐱","bird":"🐦",
    "fish":"🐟","tree":"🌳","leaf":"🍃","flower":"🌸","plant":"🌱",
    "light":"💡","dark":"🌑","night":"🌙","day":"☀️","fast":"⚡",
    "speed":"⚡","electric":"⚡","power":"⚡","magic":"✨","secret":"🤫",
    "hidden":"🕵️","look":"👀","watch":"👀","see":"👀","eyes":"👀",
    "hand":"✋","stop":"🛑","go":"🚀","up":"⬆️","down":"⬇️",
    "science":"🔬","experiment":"🧪","question":"❓","why":"❓","answer":"💡",
    "true":"✅","wrong":"❌","yes":"✅","no":"❌","win":"🏆","winner":"🏆",
}


def _emoji_for_word(word):
    token = str(word or "").strip().lower().strip(".,!?;:'\"()[]{}")
    if token in _EMOJI:
        return _EMOJI[token]
    for suffix in ("ing", "ed", "s"):
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            root = token[:-len(suffix)]
            if root in _EMOJI:
                return _EMOJI[root]
    return None


def _word_size(word, index, frame_size):
    width, _ = frame_size
    base = max(62, min(172, int(round(150.0 * width / 2160.0))))
    seed = sum(ord(ch) for ch in str(word)) + index * 17
    return int(base * (0.86, 1.0, 1.16)[seed % 3])


def _clean_words(words):
    result = []
    if not isinstance(words, list):
        return result
    for item in words:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        if not word:
            continue
        try:
            start = max(0.0, float(item.get("start", 0.0)))
            end = max(start + 0.05, float(item.get("end", start + 0.05)))
        except Exception:
            continue
        result.append({"word": word, "start": start, "end": end})
    return sorted(result, key=lambda x: x["start"])


def _patch_assemble(module):
    old_transcribe = getattr(module, "transcribe", None)
    if old_transcribe is not None:
        module._mint_raw_transcribe = old_transcribe

    def build(narration_path, script, frame_size):
        raw = getattr(module, "_mint_raw_transcribe", None)
        if raw is None:
            raise RuntimeError("Raw Whisper transcriber unavailable.")
        words = _clean_words(raw(narration_path))
        if not words:
            raise RuntimeError("Whisper returned no usable word timestamps.")

        from moviepy.editor import TextClip
        width, height = frame_size
        safe_left = width * 0.06
        safe_right = width * 0.80
        safe_center = (safe_left + safe_right) / 2.0
        center_y = height * 0.60
        max_word_width = safe_right - safe_left
        clips = []

        for index, item in enumerate(words):
            word = item["word"]
            start = item["start"]
            duration = min(max(0.05, item["end"] - start), 1.20)
            size = _word_size(word, index, frame_size)
            color = "#FFD54A" if index % 4 != 2 else "#FFFFFF"
            old_size = getattr(module, "CAPTION_FONT_SIZE", 78)
            module.CAPTION_FONT_SIZE = size
            try:
                clip = module._make_word_clip(word, color)
            finally:
                module.CAPTION_FONT_SIZE = old_size

            if clip.w > max_word_width:
                size = max(50, int(size * max_word_width / float(clip.w) * 0.94))
                module.CAPTION_FONT_SIZE = size
                try:
                    clip = module._make_word_clip(word, color)
                finally:
                    module.CAPTION_FONT_SIZE = old_size

            x = max(safe_left, min(safe_center - clip.w / 2.0, safe_right - clip.w))
            y = center_y - clip.h / 2.0
            clips.append(clip.set_start(start).set_duration(duration).set_position((x, y)))

            emoji = _emoji_for_word(word)
            if emoji:
                try:
                    esize = max(36, int(size * 0.58))
                    eclip = TextClip(
                        emoji, fontsize=esize, font="DejaVu-Sans", color="white",
                        stroke_color="black", stroke_width=max(1, int(esize * 0.035)),
                        method="label",
                    )
                    ex = safe_center - eclip.w / 2.0
                    ey = y - eclip.h - max(10, int(size * 0.16))
                    clips.append(eclip.set_start(start).set_duration(duration).set_position((ex, ey)))
                except Exception:
                    pass

        print(f"🎬 Captions: {len(words)} timed words / safe lane 6%-80% / center 60%")
        return clips

    module.build_captions = build
    module.CAPTION_VERTICAL_POSITION = 0.60


def _patch_video_quality(module):
    try:
        cls = getattr(module, "CompositeVideoClip", None)
        original = getattr(cls, "write_videofile", None) if cls else None
        if not original or getattr(original, "_mint_quality", False):
            return

        def write(self, filename, *args, **kwargs):
            kwargs.setdefault("bitrate", "68M")
            kwargs.setdefault("audio_bitrate", "384k")
            kwargs.setdefault("codec", "libx264")
            kwargs.setdefault("audio_codec", "aac")
            kwargs.setdefault("preset", "medium")
            kwargs.setdefault("threads", 4)
            params = kwargs.setdefault("ffmpeg_params", [])
            for flag, value in (
                ("-pix_fmt", "yuv420p"),
                ("-movflags", "+faststart"),
                ("-profile:v", "high"),
                ("-level:v", "5.2"),
                ("-color_primaries", "bt709"),
                ("-color_trc", "bt709"),
                ("-colorspace", "bt709"),
            ):
                if flag not in params:
                    params.extend([flag, value])
            print("🎥 Production encoding: H.264 / 68 Mbps / 384 kbps AAC")
            return original(self, filename, *args, **kwargs)

        write._mint_quality = True
        cls.write_videofile = write
    except Exception as exc:
        print(f"⚠️ Video quality patch skipped: {exc}")


def _ocr_has_text(data):
    try:
        import pytesseract
        from PIL import Image
        image = Image.open(io.BytesIO(data)).convert("RGB")
        text = pytesseract.image_to_string(image, config="--psm 11")
        tokens = re.findall(r"[A-Za-z]{3,}", text or "")
        return len(tokens) >= 2, "OCR detected readable text: " + " ".join(tokens[:8])
    except Exception:
        return False, ""


def _patch_images(module):
    old_build = getattr(module, "build_prompt", None)
    if old_build and not getattr(old_build, "_mint_hard_visuals", False):
        def build(*args, **kwargs):
            prompt = str(old_build(*args, **kwargs) or "")
            hard = """
HARD VISUAL CONTRACT:
This is a literal documentary-style STORY FRAME.
ONLY show the exact subject, action, setting and physical consequence stated in
this spoken beat. Do not invent another person, object, location or metaphor.
NO readable text anywhere: no phone UI, no fake app screen, no labels, no signs,
no letters, no numbers, no logos, no watermarks, no subtitles.
NO abstract glowing particles, energy beams, diagrams, charts, equations or
generic science imagery unless the spoken beat literally requires it.
If a phone is shown, its screen must be blank/neutral with no readable UI.
If dust is discussed, visibly show dust on the relevant surface.
"""
            return prompt + hard
        build._mint_hard_visuals = True
        module.build_prompt = build

    old_generate = getattr(module, "generate_image", None)
    if old_generate and not getattr(old_generate, "_mint_ocr_gate", False):
        def generate(prompt, width, height, seed):
            last = None
            for attempt in range(3):
                p = str(prompt)
                if attempt:
                    p += f" REGENERATION {attempt}: Make the literal physical subject and action unmistakable. No text."
                data = old_generate(p, width, height, seed + attempt * 7777)
                bad, reason = _ocr_has_text(data)
                if not bad:
                    return data
                print(f"⚠️ IMAGE OCR GATE: {reason}")
                last = data
            print("⚠️ IMAGE OCR GATE: provider kept producing text; using last image.")
            return last
        generate._mint_ocr_gate = True
        module.generate_image = generate

    if hasattr(module, "VISUAL_GUARD_MIN_SCORE"):
        module.VISUAL_GUARD_MIN_SCORE = 8
    if hasattr(module, "VISUAL_GUARD_MAX_REGENERATIONS"):
        module.VISUAL_GUARD_MAX_REGENERATIONS = max(int(getattr(module, "VISUAL_GUARD_MAX_REGENERATIONS", 4)), 10)


def _better_payoff(narration, max_words=18):
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", str(narration or "").strip()) if x.strip()]
    candidates = []
    for sentence in sentences:
        lower = sentence.lower()
        if re.search(r"\b(next video|coming next|stay tuned|part 2)\b", lower):
            continue
        words = re.findall(r"\b[\w'-]+\b", sentence)
        if 5 <= len(words) <= max_words:
            score = 0
            if re.search(r"\b(so|that's|that is|because|which means|turns out|basically)\b", lower):
                score += 3
            if sentence.endswith((".", "!", "?")):
                score += 1
            if len(words) >= 7:
                score += 1
            candidates.append((score, sentence))
    if candidates:
        return max(candidates, key=lambda x: x[0])[1].rstrip(".!? ") + "."
    return "And that's the part most people miss."


def _patch_main(module):
    old = getattr(module, "_compact_payoff", None)
    if old and not getattr(old, "_mint_better_ending", False):
        _better_payoff._mint_better_ending = True
        module._compact_payoff = _better_payoff

    old_lock = getattr(module, "lock_next_topic", None)
    if old_lock and not getattr(old_lock, "_mint_ending_guard", False):
        def lock(script, current_topic):
            result = old_lock(script, current_topic)
            if isinstance(result, tuple) and len(result) == 2:
                s, next_topic = result
                scenes = s.get("scene_plan", [])
                if scenes:
                    final = scenes[-1]
                    narration = str(final.get("narration", "")).strip()
                    sentences = [x for x in re.split(r"(?<=[.!?])\s+", narration) if x.strip()]
                    if len(sentences) < 2:
                        raise RuntimeError("Ending quality gate failed: Scene 7 has no separate payoff and teaser.")
                    teaser = sentences[-1]
                    if next_topic.lower() not in teaser.lower():
                        raise RuntimeError("Ending quality gate failed: teaser is not the locked next topic.")
                    payoff = " ".join(sentences[:-1]).strip()
                    if len(re.findall(r"\b[\w'-]+\b", payoff)) < 5:
                        raise RuntimeError("Ending quality gate failed: payoff is too short.")
                    final["narration"] = f"{payoff.rstrip('.!?')} {teaser.strip()}".strip()
                    final["subtitle_text"] = final["narration"]
                    print("✅ Scene 7 ending gate: payoff + teaser are structurally separate.")
            return result
        lock._mint_ending_guard = True
        module.lock_next_topic = lock


def _patch_script(module):
    old_builder = getattr(module, "_build_system_prompt", None)
    if old_builder and not getattr(old_builder, "_mint_hard_story", False):
        def build():
            return old_builder() + SCRIPT_RULES
        build._mint_hard_story = True
        module._build_system_prompt = build

    old_generate = getattr(module, "generate_script", None)
    if old_generate and not getattr(old_generate, "_mint_script_gate", False):
        def generate(topic, config, research=None):
            for attempt in range(3):
                script = old_generate(topic, config, research)
                scenes = script.get("scene_plan", []) if isinstance(script, dict) else []
                if len(scenes) == 7 and all(str(x.get("narration", "")).strip() for x in scenes if isinstance(x, dict)):
                    final = str(scenes[-1].get("narration", "")).strip()
                    if final and re.search(r"[.!?]$", final):
                        return script
                print("⚠️ Script quality gate: invalid storyboard/ending; regenerating.")
            raise RuntimeError("Script quality gate failed after 3 attempts.")
        generate._mint_script_gate = True
        module.generate_script = generate


def _patch(module):
    name = getattr(module, "__name__", "")
    if name == "generate_script":
        _patch_script(module)
    elif name == "generate_images":
        _patch_images(module)
    elif name == "assemble":
        _patch_assemble(module)
        _patch_video_quality(module)
    elif name == "main":
        _patch_main(module)
    elif name == "tts":
        module.NARRATION_SPEED = 1.0


class _Loader(importlib.abc.Loader):
    def __init__(self, loader):
        self.loader = loader
    def create_module(self, spec):
        creator = getattr(self.loader, "create_module", None)
        return creator(spec) if creator else None
    def exec_module(self, module):
        self.loader.exec_module(module)
        _patch(module)


class _Finder(importlib.abc.MetaPathFinder):
    TARGETS = {"generate_script", "generate_images", "tts", "assemble", "main"}
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in self.TARGETS:
            return None
        try:
            sys.meta_path.remove(self)
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        finally:
            sys.meta_path.insert(0, self)
        if spec is None or spec.loader is None:
            return None
        spec.loader = _Loader(spec.loader)
        return spec


if not any(isinstance(x, _Finder) for x in sys.meta_path):
    sys.meta_path.insert(0, _Finder())
