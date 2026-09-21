"""Create scene-aware, evidence-led visual briefs for real-person Story Shorts."""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List

_GENERIC = {
    "inspiring", "success", "motivation", "motivational", "person", "people",
    "story", "life", "journey", "dream", "challenge", "struggle", "achievement",
    "cinematic", "dramatic", "beautiful", "powerful", "storyteller", "everything",
    "show", "real", "authentic", "documented", "specific", "related", "matching",
    "visual", "image", "footage", "archival", "historical", "photograph",
}


def _tokens(value: Any) -> List[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", str(value or ""))
    generic = {x.lower() for x in _GENERIC}
    result: List[str] = []
    for word in words:
        if word.lower() not in generic and word.lower() not in {x.lower() for x in result}:
            result.append(word)
    return result


def _person(script: Dict[str, Any]) -> str:
    return str(script.get("story_person") or script.get("person") or "").strip()


def _narration(scene: Dict[str, Any]) -> str:
    for key in ("narration", "voiceover", "spoken_line", "text", "script"):
        value = scene.get(key)
        if value:
            return str(value).strip()
    return ""


def _scene_cues(scene: Dict[str, Any]) -> List[str]:
    """Extract factual cues, avoiding instruction-heavy visual descriptions."""
    candidates = []
    for key in (
        "event", "event_name", "location", "place", "occupation", "job",
        "obstacle", "setback", "action", "turning_point", "achievement",
        "visual_subject", "visual_focus", "visual_action",
    ):
        value = scene.get(key)
        if value:
            candidates.append(value)

    if not candidates:
        candidates.append(_narration(scene))

    words: List[str] = []
    for value in candidates:
        for word in _tokens(value):
            if len(words) >= 6:
                return words
            if word.lower() not in {x.lower() for x in words}:
                words.append(word)
    return words


def _role(index: int) -> str:
    return (
        "opening identity",
        "early life or starting circumstances",
        "documented obstacle or setback",
        "decision or concrete action",
        "work or persistence in progress",
        "turning point or breakthrough",
        "documented result and lasting lesson",
    )[min(index, 6)]


def _query(person: str, cues: List[str], index: int, identity: bool = False) -> str:
    if identity:
        return f"{person} historical photograph".strip()
    suffix = " ".join(cues[:5]).strip()
    return f"{person} {suffix}".strip() if suffix else f"{person} historical photograph".strip()


def _base_brief(person: str, role: str, query: str, identity: bool) -> Dict[str, Any]:
    return {
        "shot_purpose": "identity evidence" if identity else "specific narrative context",
        "visual_focus": f"{person} — {role}",
        "visual_action": (
            f"Use a clearly identified archival image or footage of {person}."
            if identity else
            f"Show a documented place, event, occupation, action, or circumstance connected to {person}'s {role} stage."
        ),
        "must_show": f"Evidence relevant to {person} and the story stage: {role}.",
        "must_not_show": (
            "Unrelated models, generic motivational stock, anonymous business people, random landscapes, "
            "symbolic filler, or visuals that only match the mood."
        ),
        "search_query": query,
        "visual_evidence_required": True,
        "identity_critical": identity,
    }


def _preserved_plan(scene: Dict[str, Any]) -> Any:
    """Return the original visual plan without mutating or discarding it."""
    for key in ("visuals", "visual_briefs", "visual_plan", "visual_description", "visual_prompt"):
        value = scene.get(key)
        if value:
            return copy.deepcopy(value)
    return None


def _merge_original_context(brief: Dict[str, Any], original_plan: Any) -> Dict[str, Any]:
    """Keep model-generated visual context available to downstream/debug tooling."""
    if original_plan is not None:
        brief["original_visual_plan"] = original_plan
    return brief


def _briefs(script: Dict[str, Any], scene: Dict[str, Any], index: int) -> List[Dict[str, Any]]:
    person = _person(script)
    role = _role(index)
    cues = _scene_cues(scene)
    original_plan = _preserved_plan(scene)

    first_is_identity = index in (0, 1, 6)
    identity_query = _query(person, [], index, identity=True)
    context_query = _query(person, cues, index, identity=False)

    first = _base_brief(person, role, identity_query if first_is_identity else context_query, first_is_identity)
    second = _base_brief(person, role, context_query, False)
    second["shot_purpose"] = "specific narrative event or setting"
    second["visual_focus"] = f"Documented context for {person}: {' '.join(cues[:5]) or role}"
    second["must_show"] = (
        f"A directly relevant archival asset connected to {person} and these factual cues: "
        f"{' '.join(cues[:5]) or role}."
    )

    return [
        _merge_original_context(first, original_plan),
        _merge_original_context(second, original_plan),
    ]


def direct_story_visuals(script: Any) -> Any:
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
        # Preserve the original model-generated plan in each enriched brief,
        # while exposing the normalized two-shot structure downstream expects.
        scene["visuals"] = briefs
        scene["visual_briefs"] = briefs
    return script
