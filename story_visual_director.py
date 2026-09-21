"""Build concrete, identity-first visual briefs for real-person Story Shorts.

This module deliberately does not touch narration, captions, or TTS. It enriches the
scene plan before media retrieval so archival search receives concrete, story-specific
instructions instead of generic atmosphere prompts.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List


_GENERIC = {
    "inspiring", "success", "motivation", "motivational", "person", "people",
    "story", "life", "journey", "dream", "challenge", "struggle", "achievement",
    "cinematic", "dramatic", "beautiful", "powerful", "success story",
}


def _words(value: Any) -> List[str]:
    text = str(value or "").lower()
    tokens = re.findall(r"[a-z][a-z0-9'-]{2,}", text)
    return [token for token in tokens if token not in _GENERIC]


def _sentence(scene: Dict[str, Any]) -> str:
    for key in ("narration", "voiceover", "spoken_line", "text", "script"):
        if scene.get(key):
            return str(scene[key]).strip()
    return ""


def _person(script: Dict[str, Any]) -> str:
    return str(script.get("story_person") or script.get("person") or "").strip()


def _scene_terms(scene: Dict[str, Any]) -> str:
    values = [
        scene.get("visual_focus"), scene.get("visual_action"), scene.get("must_show"),
        scene.get("visual_role"), _sentence(scene),
    ]
    terms: List[str] = []
    for value in values:
        for token in _words(value):
            if token not in terms:
                terms.append(token)
    return " ".join(terms[:12])


def _role(index: int) -> str:
    return (
        "hook and recognisable identity",
        "early life, background, or stakes",
        "specific obstacle or setback",
        "the decision or action taken",
        "the struggle in progress",
        "the turning point or breakthrough",
        "the documented outcome and lesson",
    )[min(index, 6)]


def _briefs(script: Dict[str, Any], scene: Dict[str, Any], index: int) -> List[Dict[str, Any]]:
    person = _person(script)
    terms = _scene_terms(scene)
    role = _role(index)
    identity = f"{person} authentic historical photograph or archival footage" if person else "authentic historical photograph or archival footage"
    evidence = f"{person} {terms}".strip()
    return [
        {
            "shot_purpose": "identity evidence" if index in (0, 1, 6) else "event evidence",
            "visual_focus": identity,
            "visual_action": f"Show {person} directly, or a clearly documented moment connected to {person}; prioritise the real person over atmosphere.",
            "must_show": f"Recognisable evidence of {person} and the {role}; use an authentic archival source when available.",
            "must_not_show": "Unrelated models, generic motivational stock, anonymous business people, random landscapes, or symbolic filler.",
            "search_query": identity,
            "visual_evidence_required": True,
            "identity_critical": index in (0, 1, 6),
        },
        {
            "shot_purpose": "specific narrative event",
            "visual_focus": evidence or identity,
            "visual_action": f"Depict the concrete action, place, occupation, obstacle, or period described in the narration for {role}.",
            "must_show": f"A directly relevant historical image or footage matching these terms: {evidence or person}.",
            "must_not_show": "Generic inspirational imagery or visuals that merely match the mood without depicting the narrated facts.",
            "search_query": evidence or identity,
            "visual_evidence_required": True,
            "identity_critical": False,
        },
    ]


def direct_story_visuals(script: Any) -> Any:
    """Replace weak visual prompts with two concrete evidence-led briefs per scene."""
    if not isinstance(script, dict) or not _person(script):
        return script
    scenes = script.get("scene_plan") or script.get("scenes")
    if not isinstance(scenes, list):
        return script
    for index, scene in enumerate(scenes[:7]):
        if not isinstance(scene, dict):
            continue
        briefs = _briefs(script, scene, index)
        scene["visual_evidence_required"] = True
        scene["visual_role"] = _role(index)
        scene["visuals"] = briefs
        scene["visual_briefs"] = briefs
    return script
