"""Quality checks for person-specific Story Shorts archival media."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_GENERIC = {
    "show", "real", "authentic", "documented", "specific", "related", "matching",
    "visual", "image", "footage", "archival", "historical", "photograph", "photo",
    "video", "person", "story", "inspiring", "motivation", "motivational",
}


def _words(value: Any) -> set[str]:
    return {
        word.lower() for word in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", str(value or ""))
        if word.lower() not in _GENERIC
    }


def relevance_score(person: str, query: str, title: str = "", description: str = "", cues: Any = ()) -> float:
    """Return a deterministic 0-10 metadata relevance score."""
    person_words = _words(person)
    query_words = _words(query)
    metadata_words = _words(f"{title} {description}")
    cue_words = _words(cues)
    score = 0.0
    if person_words and person_words.issubset(metadata_words):
        score += 5.0
    elif person_words and person_words & metadata_words:
        score += 2.0
    score += min(2.0, len(query_words & metadata_words) * 0.5)
    score += min(3.0, len(cue_words & metadata_words) * 0.75)
    return round(min(10.0, score), 2)


def validate_groups(groups: list[dict], expected: int = 14) -> None:
    if len(groups) != expected:
        raise RuntimeError(f"Expected {expected} archival assets, got {len(groups)}")
    identities = []
    for group in groups:
        identity = str(group.get("source_url") or group.get("asset_key") or "").strip()
        if not identity:
            raise RuntimeError("Archival asset has no source identity")
        identities.append(identity)
        if float(group.get("score", 0)) < 5.0:
            raise RuntimeError(f"Archival asset failed relevance threshold: {identity}")
    if len(identities) != len(set(identities)):
        raise RuntimeError("Duplicate archival asset detected")


def write_audit_report(rows: list[dict], output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
