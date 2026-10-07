"""Story Shorts-only YouTube metadata builder.

This module is intentionally isolated from Publish Shorts and Everyday Wisdom.
It creates metadata from the current Story subject/person/premise only.
"""
from __future__ import annotations

import re


_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "about", "into",
    "before", "after", "when", "where", "what", "would", "could", "should",
    "their", "there", "they", "them", "have", "has", "had", "was", "were",
    "being", "story", "remarkable", "true", "person",
}


def _clean(value: object, limit: int = 500) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value[:limit].rstrip(" .-")


def _terms(*values: object) -> list[str]:
    words: list[str] = []
    for value in values:
        for word in re.findall(r"[A-Za-z]{3,}", str(value or "").lower()):
            if word in _STOPWORDS:
                continue
            if word not in words:
                words.append(word)
    return words


def _add_unique(items: list[str], value: object) -> None:
    tag = re.sub(r"[^A-Za-z0-9 -]", "", str(value or "")).strip().lower()
    if tag and tag not in items:
        items.append(tag)


def build_story_metadata(script: dict) -> tuple[str, str, list[str]]:
    """Return title, description and YouTube tags for one Story Short."""
    from story_title_optimizer import optimize_title

    person = _clean(script.get("story_person") or script.get("person"), 120)
    topic = _clean(script.get("topic"), 220)
    pillar = _clean(script.get("interactive_pillar") or script.get("pillar"), 100)
    original_title = _clean(script.get("title"), 120)

    title = optimize_title(
        original_title or f"The Remarkable Story of {person}",
        person,
        topic,
        pillar,
    )
    title = _clean(title, 95)

    terms = _terms(person, topic, pillar)

    tags: list[str] = []
    # Exact entities/premise first: these are the strongest truthful search terms.
    for value in (
        person,
        topic,
        f"{person} story" if person else "",
        f"{person} biography" if person else "",
        f"{topic} story" if topic else "",
        "true story",
        "inspiring story",
        "life story",
        "human stories",
        "story shorts",
        *terms,
    ):
        _add_unique(tags, value)

    # YouTube's total tag field has a 500-character limit. Keep a safe margin.
    while sum(len(tag) for tag in tags) + max(0, len(tags) - 1) > 450:
        tags.pop()

    description_parts = [
        f"{person}: {topic}." if person and topic else (
            f"The story of {person}." if person else topic or "A remarkable true story."
        ),
        (
            f"This Short tells the true story behind {person}'s journey — "
            "the setback, turning point, and decision that shaped what came next."
            if person
            else
            "A concise true story about struggle, change, and the moment everything shifted."
        ),
    ]

    engagement = _clean((script.get("engagement") or {}).get("comment"), 220)
    if engagement:
        description_parts.append(engagement)

    description_parts.append(
        "Subscribe and follow for more true stories about people, setbacks, "
        "turning points, and the choices that changed their lives."
    )

    # Keep hashtags short and entity/premise-specific. The upload layer also
    # places configured tags in the description, so avoid a second hashtag wall.
    hashtags: list[str] = []
    for value in ("storyshorts", "truestory", "inspiration", "shorts"):
        _add_unique(hashtags, value)
    description_parts.append(" ".join("#" + tag for tag in hashtags))

    description = "\n\n".join(part for part in description_parts if part).strip()
    return title[:95].rstrip(" .:-"), description[:2000], tags
