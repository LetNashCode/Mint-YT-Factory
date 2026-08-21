"""Mint-YT-Factory runtime quality layer.

Entertainment-first development mode.
This layer reinforces story quality and literal visual relevance without
bringing research back into the generation pipeline.
"""

import importlib.abc
import importlib.machinery
import sys

VIRAL_SCRIPT_RULES = r'''

============================================================
ENTERTAINMENT-FIRST QUALITY LAYER
============================================================

Write like a clever friend showing the viewer something weird.

- Hook immediately with a surprising concrete observation.
- Use conversational, playful, slightly quirky spoken English.
- Keep sentences punchy and varied; avoid dense explanatory paragraphs.
- Use everyday comparisons instead of scientific terminology whenever possible.
- Every scene must reveal a new piece of the story, not repeat the previous point.
- Build curiosity before explaining the answer.
- Use a visible cause -> consequence -> reveal progression.
- Make the strongest surprising detail land near the end.
- Do not sound like a documentary narrator, textbook, teacher or research paper.
- Avoid phrases such as "the scientific reason", "the mechanism", "according to",
  "this phenomenon", "in other words", and other lecture-style filler unless truly needed.
- Do not force jokes. Quirkiness should come from the observation and wording.
- Finish the current story before the continuation hook.
'''

VIRAL_IMAGE_RULES = r'''

============================================================
ENTERTAINMENT-FIRST LITERAL STORY VISUALS
============================================================

The image must make the narration understandable with SOUND OFF.

CORE RULE:
Show the thing being talked about, doing the thing being talked about.
Never replace a concrete subject with a generic representation of its category.

Examples:
- "cold glass gets wet" -> show a cold drinking glass visibly covered in droplets.
- "phone gets hot while charging" -> show a person holding a charging phone and reacting to its warmth.
- "onions make you cry" -> show someone cutting an onion with watery eyes.
- "bread rises" -> show dough visibly puffed before/after baking.

VISUAL STORY RULES:
- Each shot has ONE obvious subject and ONE obvious action/change.
- Prefer people, hands, animals, objects, food, machines, streets, homes and believable locations.
- Prefer visible actions, reactions, transformations, comparisons and consequences.
- Shot 1 establishes the moment; Shot 2 must advance it with a different action,
  physical state, reaction, revealed detail or useful perspective.
- Never create two near-identical stills merely by changing camera angle.
- Every second visual should add information or emotional movement.
- Use varied, bright, believable lighting appropriate to the actual location.
- Vary framing: close action, medium interaction, wider context, overhead detail,
  side view and environmental shots when useful.

ANTI-TEXTBOOK HARD RULES:
- Never turn a normal explanation into an infographic or scientific diagram.
- No arrows, equations, charts, graphs, labeled parts, schematic drawings,
  anatomy diagrams, textbook cross-sections, UI panels or fake microscopic worlds.
- Do not invent invisible particles, forces, receptors, pathways or internal structures.
- Do not use generic glowing particles to represent an idea.
- Do not use generic laboratories unless the narration explicitly requires a lab.
- Do not use a scientific illustration style for an everyday topic.
- Do not make every image blue, dark, sterile, centered or laboratory-like.

IMAGE PROMPT QUALITY:
Every generated prompt must explicitly communicate:
WHO/WHAT is visible + WHAT it is doing + WHERE it is + WHAT changes + WHAT the viewer notices.
Keep the physical event concrete and immediately recognizable.

NO GENERATED TEXT:
No captions, subtitles, labels, logos, watermarks, signs with readable text or UI.
'''


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
        if old_builder and not getattr(old_builder, "_mint_visual", False):
            def wrapped(*args, **kwargs):
                prompt = old_builder(*args, **kwargs)

                # Remove legacy style wording that can pull an everyday shot
                # toward a textbook/science-illustration look. Keep explicit
                # location and subject descriptions intact.
                replacements = (
                    ("scientific illustration and realistic 3d render", "cinematic real-world render"),
                    ("scientific illustration", "cinematic real-world scene"),
                    ("science textbook aesthetic", "entertaining documentary aesthetic"),
                    ("scientific diagram", "literal real-world scene"),
                )
                for old, new in replacements:
                    prompt = prompt.replace(old, new)

                return prompt + " " + VIRAL_IMAGE_RULES

            wrapped._mint_visual = True
            module.build_prompt = wrapped
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
    TARGETS = {"generate_script", "generate_images", "tts"}

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
