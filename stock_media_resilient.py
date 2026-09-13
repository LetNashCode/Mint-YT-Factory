"""Authoritative stock-media adapter for Mint-YT-Factory.

Gemini directs stock searches AND verifies downloaded stock candidates.
ALL Gemini calls use the single canonical model configured by stock_search.
"""
from __future__ import annotations

import re

import stock_search

GEMINI_MODEL = stock_search.GEMINI_MODEL


def _patch_story_context():
    """Make Story stock searches concrete without changing Publish routing."""
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

        if re.search(r"tenzing|norgay|sherpa", text):
            add("mountain climbing", "mountain climber", "Himalayan expedition")
        elif re.search(r"wade|jordan|lebron|kobe|curry", text):
            add("basketball player", "basketball court")
        elif re.search(r"bose|einstein|tesla|curie|newton|ramanujan", text):
            add("scientist", "researcher writing")

        if re.search(r"everest|himalaya|mountain|climb|climbing|summit|expedition|sherpa|nepal|snow|glacier|oxygen|rope|camp|tent|peak", text):
            add(
                "mountain climbing", "mountain climber", "Himalayan expedition",
                "snow mountain", "Everest climber", "mountain expedition",
                "Sherpa climbing", "mountain camp",
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

        if not terms:
            try:
                derived = stock_search._anchor_terms(narration, "", "", [])
            except Exception:
                derived = []
            blocked = {"historical", "person", "people", "story", "life", "became", "become", "would", "could", "because", "their", "there", "about", "years"}
            for word in derived:
                if word not in blocked and word not in terms:
                    add(word)
                if len(terms) >= 5:
                    break

        if not terms:
            terms = original(script, scene_no)
        if not terms:
            terms = ["person"]
        return terms[:8]

    concrete_story_context._mint_concrete_story_context = True
    stock_search._story_context = concrete_story_context


def _patch_story_query_ladder():
    """Add provider-friendly Story queries and remove unusable modifier variants."""
    original = getattr(stock_search, "build_plan", None)
    if not original or getattr(original, "_mint_story_query_ladder", False):
        return

    def story_query_ladder(script):
        plan = original(script)
        is_story = isinstance(script, dict) and bool(
            str(script.get("story_person") or "").strip()
            or str(script.get("interactive_pillar") or "").strip()
            or str(script.get("story_visual_mode") or "").strip()
        )
        if not is_story:
            return plan

        for scene_shots in plan:
            for shot in scene_shots:
                queries = [str(x.get("query") or "").strip().lower() for x in shot.get("search_ladder", []) if isinstance(x, dict)]
                anchors = [str(x).strip().lower() for x in shot.get("anchor_terms", []) if str(x).strip()]
                expanded: list[dict] = []
                seen: set[str] = set()

                def add(query: str, strategy: str):
                    query = " ".join(query.split())
                    if not query or query in seen or not 1 <= len(query.split()) <= 7:
                        return
                    seen.add(query)
                    expanded.append({"query": query, "strategy": strategy})

                joined = " ".join(anchors + queries)
                if re.search(r"everest|himalaya|mountain|climb|climbing|summit|expedition|sherpa|nepal|snow|glacier|oxygen|rope|camp|tent|peak", joined):
                    for query in (
                        "mountain climbing", "mountain climber", "Himalayan mountains",
                        "Himalayan expedition", "snow mountain", "Everest climber",
                        "mountain expedition", "mountain camp",
                    ):
                        add(query.lower(), "story-provider-fallback")

                if re.search(r"basketball|court|arena|game|team|nba|dribble|dunk|hoop", joined):
                    for query in (
                        "basketball player", "basketball court", "basketball game",
                        "basketball training", "basketball arena", "basketball practice",
                    ):
                        add(query, "story-provider-fallback")

                # Preserve useful directed queries after robust provider aliases.
                # Modifier-only variants are deliberately discarded because they
                # often produce zero-result API searches (e.g. "Everest indoors").
                bad_suffix = re.compile(r"\b(action|working|indoors|close up)\b")
                for query in queries:
                    if bad_suffix.search(query):
                        continue
                    add(query, "story-directed")

                for anchor in anchors:
                    if anchor not in seen and not re.search(r"\b(historical person|person|scientist|athlete training)\b", anchor):
                        add(anchor, "story-anchor")
                    if len(expanded) >= 8:
                        break

                shot["search_ladder"] = expanded[:8]
                shot["queries"] = [x["query"] for x in shot["search_ladder"]]

        print("🛡️ Story provider query ladder: concrete aliases prioritized; modifier-only queries removed")
        return plan

    story_query_ladder._mint_story_query_ladder = True
    stock_search.build_plan = story_query_ladder


_patch_story_context()
_patch_story_query_ladder()


def generate_media(script: dict, output_dir: str, config: dict, gim=None):
    """Generate 7x2 stock assets using Gemini direction + visual verification."""
    print(f"🛡️ Stock media adapter: Gemini search + visual verification ENABLED ({GEMINI_MODEL}; no fallback model)")
    return stock_search.generate_media(script, output_dir, config, gim=gim)
