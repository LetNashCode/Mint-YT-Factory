"""Publish Shorts runtime shim.

Loads production_entry.py and replaces the overly broad retired-subject guard
with a narration-focused guard. The shim exists so the production entrypoint
can remain stable while a targeted runtime bug is corrected.
"""
from __future__ import annotations

import re

import production_entry as production


def _patch_script_topic_coherence_fixed(main):
    """Reject genuine retired-topic bleed without rejecting incidental comparisons."""
    original = main.generate_script
    if getattr(original, "_mint_topic_coherence_guard_fixed", False):
        return

    def guarded(topic, config, research=None, extra_feedback=""):
        result = original(topic, config, research, extra_feedback=extra_feedback)
        current = str(topic or "").strip()

        # The retired-topic guard must judge spoken narration, not visual prompts.
        # A valid story may briefly mention an old subject as a comparison
        # (e.g. "unlike cutting onions..."). That is not topic bleed.
        narration_parts = []
        for scene in result.get("scene_plan") or []:
            if not isinstance(scene, dict):
                continue
            narration_parts.append(str(scene.get("narration") or ""))

        narration = " ".join(narration_parts).lower()
        onion_count = len(re.findall(r"\bonions?\b", narration))
        onion_subject_patterns = (
            r"\bonions?\b[^.!?]{0,90}\b(?:make|makes|cause|causes|release|releases|trigger|triggers)\b",
            r"\b(?:cutting|chopping|slicing)\s+onions?\b[^.!?]{0,90}\b(?:make|makes|cause|causes|trigger|triggers)\b",
        )
        onion_is_subject = any(re.search(pattern, narration) for pattern in onion_subject_patterns)

        # Reject only when the retired subject is actually being discussed as
        # a subject of the narration, or when repeated mentions strongly imply
        # that the model has switched topics. One incidental comparison is OK.
        if onion_count >= 2 or onion_is_subject:
            raise RuntimeError(
                f"Topic coherence gate rejected retired onion subject bleed in generated Short: {current!r}"
            )

        result["topic"] = current
        return result

    guarded._mint_topic_coherence_guard_fixed = True
    main.generate_script = guarded
    print("🛡️ Script topic-coherence gate: ENABLED | retired-subject detection is narration-focused")


production._patch_script_topic_coherence = _patch_script_topic_coherence_fixed
production.main_entry()
