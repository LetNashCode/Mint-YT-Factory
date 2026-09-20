"""Generate concise, curiosity-driven titles for Story Shorts."""
from __future__ import annotations

import re


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" .:|-\n\t")


def optimize_title(original_title: str, person: str, topic: str = "", pillar: str = "") -> str:
    """Create a compelling but non-misleading title from the story metadata."""
    name = _clean(person)
    premise = _clean(topic)
    if ":" in premise:
        premise = _clean(premise.split(":", 1)[1])

    lower = premise.lower()
    templates = []
    if any(word in lower for word in ("rejected", "rejection", "failed", "failure", "turned down")):
        templates.extend([
            f"{name} Was Rejected… Then Everything Changed",
            f"The Rejection That Changed {name}'s Life",
        ])
    elif any(word in lower for word in ("burned", "fire", "destroyed", "lost everything")):
        templates.extend([
            f"{name} Lost Everything—Then Started Again",
            f"When {name}'s World Fell Apart",
        ])
    elif any(word in lower for word in ("before", "struggled", "difficult", "poverty", "poor")):
        templates.extend([
            f"Before the Fame: {name}'s Untold Struggle",
            f"What {name} Went Through Before Success",
        ])
    elif any(word in lower for word in ("decision", "choice", "turning point", "left")):
        templates.extend([
            f"The Decision That Changed {name}'s Life",
            f"One Choice Changed Everything for {name}",
        ])
    templates.extend([
        f"The Untold Turning Point in {name}'s Story",
        f"How {name} Overcame the Impossible",
        f"The Moment Everything Changed for {name}",
    ])

    # Keep titles compact for mobile display and avoid empty/invalid output.
    for candidate in templates:
        candidate = _clean(candidate)
        if 20 <= len(candidate) <= 95:
            return candidate
    fallback = _clean(original_title) or f"The Remarkable Story of {name}"
    return fallback[:95].rstrip(" .:-")
