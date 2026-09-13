"""Authoritative stock-media adapter for Mint-YT-Factory.

Gemini directs stock searches AND verifies downloaded stock candidates.
ALL Gemini calls use the single canonical model configured by stock_search.
"""
from __future__ import annotations

import re

import stock_search

GEMINI_MODEL = stock_search.GEMINI_MODEL


def _patch_story_context():
    """Make Story stock searches concrete without changing Publish routing.

    Story subjects are often historical people, so a generic "historical person"
    query is almost never useful. Build a small, searchable visual vocabulary from
    the person and scene narration. The original context function remains the
    fallback for any scene we cannot classify.
    """
    original = getattr(stock_search, "_story_context", None)
    if not original or getattr(original, "_mint_concrete_story_context", False):
        return

    def concrete_story_context(script: dict, scene_no: int) -> list[str]:
        person = str(script.get("story_person") or "").strip().lower()
        scenes = script.get("scene_plan") or []
        narration = ""
        if isinstance(scenes, list) and len(scenes) >= scene_no and isinstance(scenes[scene_no - 1], dict):
            narration = str(scenes[scene_no - 1].get("narration") or "").strip().lower()

        text = f"{person} {narration}"
        terms: list[str] = []

        def add(*phrases: str):
            for phrase in phrases:
                phrase = " ".join(str(phrase).lower().split()).strip()
                if phrase and phrase not in terms:
                    terms.append(phrase)

        # Known domains are a secondary hint; narration-specific matches below can
        # still add the exact physical situation for the individual scene.
        if re.search(r"tenzing|norgay|sherpa", text):
            add("Mount Everest", "mountain climber", "Himalayan expedition")
        elif re.search(r"wade|jordan|lebron|kobe|curry", text):
            add("basketball player", "basketball court")
        elif re.search(r"bose|einstein|tesla|curie|newton|ramanujan", text):
            add("scientist", "researcher writing")

        # Mountaineering / expedition vocabulary. These must be concrete stock
        # subjects, never abstract terms such as "mountaineering concept".
        if re.search(r"everest|himalaya|mountain|climb|climbing|summit|expedition|sherpa|nepal|snow|glacier|oxygen|rope|camp|tent|peak", text):
            add(
                "Mount Everest",
                "mountain climber",
                "Himalayan expedition",
                "mountain climbing",
                "Everest expedition",
                "Sherpa mountain climbing",
                "snow mountain climber",
                "mountain expedition camp",
            )

        if re.search(r"basketball|court|arena|game|team|nba|dribble|dunk|hoop", text):
            add("basketball court", "basketball player", "basketball game", "basketball training")
        if re.search(r"contract|signed|deal|salary|million|draft", text):
            add("sports contract", "basketball draft", "athlete signing contract")
        if re.search(r"school|college|university|campus|student|professor|lecture", text):
            add("college campus", "university lecture", "student classroom")
        if re.search(r"coach|coached|practice|train|training|workout", text):
            add("sports coach", "athlete training", "sports practice")
        if re.search(r"injur|hurt|pain|recover|recovery", text):
            add("athlete recovery", "sports injury", "athlete training")
        if re.search(r"family|mother|father|parent|brother|sister", text):
            add("family support", "family conversation")
        if re.search(r"poor|broke|money|struggle|homeless|poverty", text):
            add("struggling person", "poor neighborhood", "person working")
        if re.search(r"championship|trophy|win|victory|winner", text):
            add("sports trophy", "athlete victory", "championship celebration")
        if re.search(r"manuscript|journal|diary|letter|paper|book|wrote|writing|author", text):
            add("old manuscript", "person writing", "historical letter")
        if re.search(r"research|theory|equation|discovery|scientific", text):
            add("scientist writing", "researcher working", "scientist at desk")
        if re.search(r"laboratory|lab", text):
            add("research laboratory", "scientist laboratory")
        if re.search(r"war|soldier|battle|army|military", text):
            add("historical soldier", "military camp", "soldiers in formation")
        if re.search(r"invention|machine|workshop|factory", text):
            add("inventor workshop", "person working machine", "old workshop")

        # If the scene contains no domain signal, derive searchable words from the
        # actual narration rather than putting "historical person" first.
        if not terms:
            try:
                derived = stock_search._anchor_terms(narration, "", "", [])
            except Exception:
                derived = []
            blocked = {
                "historical", "person", "people", "story", "life", "became", "become",
                "would", "could", "because", "their", "there", "about", "years",
            }
            for word in derived:
                if word not in blocked and word not in terms:
                    add(word)
                if len(terms) >= 5:
                    break

        # Last resort only. This prevents the generic category from consuming the
        # first search slots whenever a concrete scene concept is available.
        if not terms:
            terms = original(script, scene_no)
        if not terms:
            terms = ["person"]
        return terms[:8]

    concrete_story_context._mint_concrete_story_context = True
    stock_search._story_context = concrete_story_context


_patch_story_context()


def generate_media(script: dict, output_dir: str, config: dict, gim=None):
    """Generate 7x2 stock assets using Gemini direction + visual verification."""
    print(f"🛡️ Stock media adapter: Gemini search + visual verification ENABLED ({GEMINI_MODEL}; no fallback model)")
    return stock_search.generate_media(script, output_dir, config, gim=gim)
