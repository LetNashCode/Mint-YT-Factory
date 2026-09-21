"""Create concise, evidence-led visual briefs for real-person Story Shorts."""
from __future__ import annotations

import re
from typing import Any, Dict, List

_GENERIC = {
    "inspiring", "success", "motivation", "motivational", "person", "people",
    "story", "life", "journey", "dream", "challenge", "struggle", "achievement",
    "cinematic", "dramatic", "beautiful", "powerful", "storyteller", "everything",
}


def _tokens(value: Any) -> List[str]:
    return [x for x in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", str(value or ""))
            if x.lower() not in _GENERIC]


def _person(script: Dict[str, Any]) -> str:
    return str(script.get("story_person") or script.get("person") or "").strip()


def _narration(scene: Dict[str, Any]) -> str:
    for key in ("narration", "voiceover", "spoken_line", "text", "script"):
        if scene.get(key):
            return str(scene[key]).strip()
    return ""


def _cue(scene: Dict[str, Any]) -> str:
    """Extract a compact search cue without injecting long instruction text."""
    candidates = [scene.get("visual_focus"), scene.get("visual_action"), scene.get("must_show"), _narration(scene)]
    words: List[str] = []
    for value in candidates:
        for word in _tokens(value):
            lower = word.lower()
            if lower not in {w.lower() for w in words} and len(words) < 8:
                words.append(word)
    return " ".join(words)


def _role(index: int) -> str:
    return (
        "recognisable identity and opening hook",
        "early life or starting circumstances",
        "specific documented obstacle or setback",
        "decision or concrete action",
        "work, persistence, or conflict in progress",
        "turning point or breakthrough",
        "documented result and lasting lesson",
    )[min(index, 6)]


def _briefs(script: Dict[str, Any], scene: Dict[str, Any], index: int) -> List[Dict[str, Any]]:
    person = _person(script)
    cue = _cue(scene)
    role = _role(index)
    identity_query = f"{person} historical photograph".strip()
    event_query = f"{person} {cue}".strip() or identity_query
    return [
        {
            "shot_purpose": "identity evidence" if index in (0, 1, 6) else "person-specific context",
            "visual_focus": f"Authentic archival image or footage of {person}",
            "visual_action": f"Show the real {person} or a documented moment connected to the {role}.",
            "must_show": f"{person}; authentic archival source; clear connection to the story stage: {role}.",
            "must_not_show": "Unrelated models, generic motivational stock, anonymous business people, random landscapes, or symbolic filler.",
            "search_query": identity_query,
            "visual_evidence_required": True,
            "identity_critical": index in (0, 1, 6),
        },
        {
            "shot_purpose": "specific narrative event",
            "visual_focus": f"Documented event or setting related to {person}: {cue or role}",
            "visual_action": f"Depict the concrete event, occupation, place, obstacle, or action for the {role} stage.",
            "must_show": f"A directly relevant archival image or footage matching: {event_query}.",
            "must_not_show": "Visuals that only match the mood without depicting the narrated facts.",
            "search_query": event_query,
            "visual_evidence_required": True,
            "identity_critical": False,
        },
    ]


def direct_story_visuals(script: Any) -> Any:
    if not isinstance(script, dict) or not _person(script):
        return script
    scenes = script.get("scene_plan") or script.get("scenes")
    if not isinstance(scenes, list):
        return script
    for index, scene in enumerate(scenes[:7]):
        if isinstance(scene, dict):
            briefs = _briefs(script, scene, index)
            scene["visual_evidence_required"] = True
            scene["visual_role"] = _role(index)
            scene["visuals"] = briefs
            scene["visual_briefs"] = briefs
    return script
