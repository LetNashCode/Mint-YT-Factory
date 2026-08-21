"""Mint-YT-Factory runtime quality layer.

Current development mode is entertainment-first. This layer only reinforces
storytelling and literal visual relevance at runtime; it does not perform or
require research.
"""

import importlib.abc
import importlib.machinery
import sys

VIRAL_SCRIPT_RULES = r'''

============================================================
ENTERTAINMENT-FIRST QUALITY LAYER
============================================================

Write like a clever friend showing the viewer something weird.

- Hook immediately.
- Use conversational, slightly quirky spoken English.
- Keep sentences punchy and varied.
- Every scene must reveal something new.
- Prefer relatable human-scale examples.
- Avoid textbook, lecture and newsreader language.
- Avoid generic intros and filler.
- Do not force jokes.
- Make the payoff feel earned.
- Finish the current story before the continuation hook.
'''

VIRAL_IMAGE_RULES = r'''

============================================================
LITERAL STORY VISUALS
============================================================

The image must show what the narration is actually talking about.

Prefer recognizable real-world scenes, people, animals, objects, hands,
physical actions, reactions, before/after states and visible consequences.

Avoid generic laboratories, textbook diagrams, arrows, equations, charts,
abstract particles, glowing effects, empty rooms and static portraits unless
the narration genuinely requires them.

Shot 1 establishes the moment.
Shot 2 must reveal or demonstrate something new.

Use bright believable lighting and varied compositions.

Every visual prompt must clearly identify the subject, action, location and
important visible detail.

No text, captions, labels, logos, watermarks or UI inside generated images.
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
                return old_builder(*args, **kwargs) + " " + VIRAL_IMAGE_RULES
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
