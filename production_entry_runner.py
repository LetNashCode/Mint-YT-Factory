"""Publish Shorts runtime shim.

Loads production_entry.py and replaces the overly broad retired-subject guard
with a narration-focused guard. The shim exists so the production entrypoint
can remain stable while a targeted runtime bug is corrected.
"""
from __future__ import annotations

import re

import production_entry as production


def _patch_script_topic_coherence_fixed(main):
    """Reject genuine retired-topic bleed without rejecting valid comparisons."""
    original = main.generate_script
    if getattr(original, "_mint_topic_coherence_guard_fixed", False):
        return

    def guarded(topic, config, research=None, extra_feedback=""):
        result = original(topic, config, research, extra_feedback=extra_feedback)
        current = str(topic or "").strip()

        # Retired-topic detection must judge spoken narration only. Visual
        # prompts can legitimately contain incidental comparison imagery.
        sentences = []
        for scene in result.get("scene_plan") or []:
            if not isinstance(scene, dict):
                continue
            narration = str(scene.get("narration") or "")
            sentences.extend(re.split(r"(?<=[.!?])\s+", narration))

        onion_mentions = []
        onion_subject = False
        comparison_markers = re.compile(
            r"\b(?:like|unlike|similar to|same as|just like|as with|compared with|compared to)\b",
            re.IGNORECASE,
        )
        subject_patterns = (
            r"\bonions?\b[^.!?]{0,90}\b(?:make|makes|cause|causes|release|releases|trigger|triggers|irritate|irritates)\b",
            r"\b(?:cutting|chopping|slicing)\s+onions?\b[^.!?]{0,90}\b(?:make|makes|cause|causes|trigger|triggers|release|releases|irritate|irritates)\b",
            r"\bonions?\b[^.!?]{0,90}\b(?:cry|tears|tear|eyes?\s+water|water(?:ing|ed)?)\b",
        )

        for sentence in sentences:
            if not re.search(r"\bonions?\b", sentence, re.IGNORECASE):
                continue
            clean = sentence.strip()
            if not clean:
                continue
            # A sentence explicitly framed as a comparison is incidental by
            # design, e.g. "like cutting onions" in an eye-watering story.
            if comparison_markers.search(clean):
                continue
            onion_mentions.append(clean)
            if any(re.search(pattern, clean, re.IGNORECASE) for pattern in subject_patterns):
                onion_subject = True

        # Do not reject a valid current-topic story because Gemini used an
        # onion comparison. Reject only genuine onion-topic narration or
        # repeated non-comparison onion discussion that indicates topic drift.
        if onion_subject or len(onion_mentions) >= 2:
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
