"""Mint-YT-Factory runtime quality layer.

Entertainment-first development mode.
Research and claim verification remain disabled.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import sys


VIRAL_SCRIPT_RULES = r'''

============================================================
ENTERTAINMENT-FIRST STORY ENGINE
============================================================

Write like a clever friend showing the viewer something weird.

HOOK AND STORY:
- Hook immediately with a concrete curiosity or surprising statement.
- Use conversational, slightly quirky spoken English.
- Keep sentences punchy and varied.
- Never sound like a textbook, lecture, encyclopedia or newsreader.
- Avoid generic intros and filler.
- Do not force jokes. Entertainment comes from the situation and payoff.
- Build one clear curiosity from beginning to payoff.
- Finish the current story before the continuation hook.

ACTION-FIRST STORYBOARD:
- Every scene must advance the story.
- Every visual prompt must describe a concrete visible moment, not merely a topic.
- Prefer an action, interaction, reaction, transformation, comparison or consequence.
- If a person is relevant, show the person physically doing the narrated action.
- If an object is relevant, show it being handled, used, changed or compared.
- For a process, show setup -> action -> consequence -> payoff.
- Shot 1 establishes the action or situation.
- Shot 2 reveals a different action, consequence, reaction, detail or state.
- Never create two pretty variations of the same still.
- Do not make generic hero shots when the narration describes an action.

CHARACTER CONTINUITY:
- If the same person appears in multiple shots, keep the same approximate age,
  hair, clothing and physical appearance.
- Do not introduce a different person merely to make another image attractive.
- If a person is not needed, do not add one.

VISUAL STORY QUALITY:
- The viewer should understand the basic visual idea with sound OFF.
- Use recognizable real-world environments and physical objects.
- Prefer hands interacting with objects, close physical actions, reactions,
  before/after states and visible cause-and-effect.
- Avoid abstract explanations, diagrams and decorative imagery.
- Avoid generic laboratory imagery unless the story genuinely takes place there.
'''


VIRAL_IMAGE_RULES = r'''

============================================================
ACTION-FIRST IMAGE GENERATION — HARD OVERRIDE
============================================================

The generated image is a STORY FRAME, not a decorative illustration.

PRIMARY RULE:
Show the exact physical action or visible consequence described by the main
visual prompt. The viewer must understand what is happening from the image alone.

ACTION REQUIREMENT:
- Show WHO/WHAT is present.
- Show WHAT they are physically doing.
- Show WHERE the action happens.
- Show the important visible change or consequence.
- Make the action visually obvious through pose, hand placement, object state,
  before/after condition or physical interaction.

EXAMPLES:
BAD: "A loaf of bread on a kitchen counter."
GOOD: "A person's hand actively placing the same loaf of bread onto a refrigerator shelf."
BAD: "A refrigerator in a kitchen."
GOOD: "A person opening the refrigerator door and reaching toward the loaf of bread inside."
BAD: "Stale bread."
GOOD: "The same loaf being squeezed by a hand, visibly dry and crumbly compared with its earlier soft state."

SHOT PROGRESSION:
- Shot 1 establishes the situation/action.
- Shot 2 MUST reveal something new: a changed physical state, consequence,
  reaction, closer useful detail, different action or newly revealed information.
- Do not simply change the camera angle while showing the same thing.

STYLE OVERRIDE:
If earlier metadata says "scientific illustration", "scientific diagram",
"textbook", "infographic", or similar, IGNORE that presentation style unless
the narration genuinely requires a diagram. Render the scene as a believable
cinematic photograph or realistic 3D scene instead.

REAL-WORLD DEFAULT:
Use recognizable homes, kitchens, streets, offices, bedrooms, shops,
workbenches and everyday environments whenever appropriate.

PEOPLE:
When narration describes a human action, show believable hands/body posture
performing that action. Maintain character appearance when the same person is visible again.

NO DECORATIVE SCIENCE:
Do not add particles, arrows, energy fields, microscopic structures, equations,
charts, diagrams, glowing effects or scientific equipment unless explicitly
required by the actual narration.

NO TEXT:
Do not render captions, subtitles, labels, logos, watermarks, UI or readable
text into generated images.

COMPOSITION:
Use varied framing and viewpoints, but composition must serve the action.
Prefer medium action shots, over-the-shoulder views, useful close-ups of hands
and objects, side views and consequence shots over empty wide shots.
'''


# ---------------------------------------------------------------------------
# Caption grouping
# ---------------------------------------------------------------------------

def _group_caption_words(words, group_size=3):
    """Convert word-level timing into compact three-word kinetic caption groups."""
    if not isinstance(words, list):
        return words

    clean = []
    for item in words:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        if not word:
            continue
        try:
            start = float(item.get("start", 0.0))
            end = float(item.get("end", start + 0.05))
        except Exception:
            continue
        clean.append({
            "word": word,
            "start": start,
            "end": max(end, start + 0.05),
        })

    grouped = []
    for index in range(0, len(clean), group_size):
        chunk = clean[index:index + group_size]
        if not chunk:
            continue
        grouped.append({
            "word": " ".join(item["word"] for item in chunk),
            "start": chunk[0]["start"],
            "end": chunk[-1]["end"],
            "words": chunk,
        })
    return grouped


# ---------------------------------------------------------------------------
# Production video quality
# ---------------------------------------------------------------------------

def _patch_video_quality(module):
    """Force the final renderer to use the configured production quality.

    YouTube has no hard upload bitrate ceiling for normal uploads. For SDR
    4K60, YouTube currently recommends 53–68 Mbps, so the factory uses 68 Mbps
    rather than wasting bandwidth on an unnecessary 100 Mbps encode.
    """
    try:
        video_class = getattr(module, "CompositeVideoClip", None)
        if video_class is None:
            return

        original = getattr(video_class, "write_videofile", None)
        if original is None or getattr(original, "_mint_quality", False):
            return

        def production_write(self, filename, *args, **kwargs):
            kwargs.setdefault("bitrate", "68M")
            kwargs.setdefault("audio_bitrate", "384k")
            kwargs.setdefault("codec", "libx264")
            kwargs.setdefault("audio_codec", "aac")
            kwargs.setdefault("preset", "medium")
            kwargs.setdefault("threads", 4)
            kwargs.setdefault("ffmpeg_params", [
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-profile:v", "high",
                "-level:v", "5.2",
                "-color_primaries", "bt709",
                "-color_trc", "bt709",
                "-colorspace", "bt709",
            ])

            print("🎥 Production encoding: H.264 High / 68 Mbps / 384 kbps AAC")
            print("🎥 Production pixel format: yuv420p / BT.709 / Fast Start")

            return original(self, filename, *args, **kwargs)

        production_write._mint_quality = True
        video_class.write_videofile = production_write

    except Exception as error:
        print(f"⚠️ Production video quality patch skipped: {error}")


def _patch(module):
    name = getattr(module, "__name__", "")

    if name == "generate_script":
        old_builder = getattr(module, "_build_system_prompt", None) or getattr(module, "build_system_prompt", None)
        if old_builder and not getattr(old_builder, "_mint_entertainment", False):
            def wrapped():
                return old_builder() + VIRAL_SCRIPT_RULES
            wrapped._mint_entertainment = True
            if hasattr(module, "_build_system_prompt"):
                module._build_system_prompt = wrapped
            else:
                module.build_system_prompt = wrapped
        return

    if name == "generate_images":
        old_builder = getattr(module, "build_prompt", None)
        if old_builder and not getattr(old_builder, "_mint_action_visuals", False):
            def wrapped(*args, **kwargs):
                prompt = old_builder(*args, **kwargs)
                if not isinstance(prompt, str):
                    prompt = str(prompt or "")

                replacements = (
                    ("scientific illustration and realistic 3d render", "cinematic photograph / realistic 3D render"),
                    ("scientific illustration", "cinematic photograph"),
                    ("science textbook aesthetic", "entertaining documentary aesthetic"),
                    ("scientific diagram", "literal real-world scene"),
                    ("textbook diagram", "literal real-world scene"),
                )
                for old, new in replacements:
                    prompt = prompt.replace(old, new)

                return prompt + " " + VIRAL_IMAGE_RULES
            wrapped._mint_action_visuals = True
            module.build_prompt = wrapped
        return

    if name == "assemble":
        old_transcribe = getattr(module, "transcribe", None)
        if old_transcribe and not getattr(old_transcribe, "_mint_three_word", False):
            def grouped_transcribe(*args, **kwargs):
                words = old_transcribe(*args, **kwargs)
                grouped = _group_caption_words(words, 3)
                print(f"🎬 Kinetic captions: {len(words)} words -> {len(grouped)} three-word groups")
                return grouped
            grouped_transcribe._mint_three_word = True
            module.transcribe = grouped_transcribe

        _patch_video_quality(module)
        return

    if name == "tts":
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
    TARGETS = {"generate_script", "generate_images", "tts", "assemble"}

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in self.TARGETS:
            return None
        try:
            sys.meta_path.remove(self)
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        finally:
            if self not in sys.meta_path:
                sys.meta_path.insert(0, self)
        if spec is not None and spec.loader is not None:
            spec.loader = _Loader(spec.loader)
        return spec


if not any(isinstance(item, _Finder) for item in sys.meta_path):
    sys.meta_path.insert(0, _Finder())
