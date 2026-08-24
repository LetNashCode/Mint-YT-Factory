"""Mint-YT-Factory media quality policy v13.

The spoken narration is the source of truth for stock-media retrieval.
Generated visual metadata is advisory only and is never allowed to introduce
new objects, materials, settings, colors, or actions that are absent from the
spoken beat. This prevents Gemini from inventing details such as "polished
copper kettle base" and then forcing Pexels to search for them.
"""
from __future__ import annotations

import json
import os
import re


# Physical concepts that stock footage can represent directly or with a safe
# physical proxy. Queries are intentionally simple because Pexels search works
# much better with ordinary visual language than with generated prose.
_PHYSICAL_QUERY_RULES = [
    (("boiling water", "water boils", "water boiling", "boiling bubbles", "bubbles forming", "bubbles rise", "bubbles rising", "bubbles collapse", "collapsing bubbles", "hot water", "heated water"),
     ("boiling water close up", "boiling water bubbles close up", "water boiling in pot close up", "boiling pot macro")),
    (("pitch", "rising pitch", "rising tune", "whistling", "singing", "hiss", "hissing", "sound wave", "sound waves"),
     ("kettle boiling close up", "kettle steam close up", "boiling kettle on stove", "kettle spout steam", "boiling water close up")),
    (("steam", "steaming", "escaping steam", "steam jet"),
     ("kettle steam close up", "steam escaping kettle", "boiling kettle close up", "boiling water close up")),
    (("flame", "burner", "stove", "blazing hot", "very hot"),
     ("pot on gas stove close up", "pot over flame close up", "boiling pot on stove", "stove flame under pot")),
    (("cool", "cold", "still cool", "cooler layer", "higher up"),
     ("water in pot close up", "pot of water heating close up", "water surface in pot close up", "pot with water on stove")),
    (("ice", "ice cube", "freezing", "frozen", "melt", "melting"),
     ("ice cube close up", "ice melting close up", "water freezing close up", "melting ice macro")),
    (("bubble", "bubbles", "foam", "froth"),
     ("water bubbles close up", "bubbles forming in water", "bubbles popping close up", "boiling water bubbles close up")),
]

_MATERIAL_WORDS = {
    "copper", "glass", "stainless", "steel", "ceramic", "brass", "silver", "gold",
    "black", "white", "red", "blue", "green", "yellow", "rustic", "vintage",
    "polished", "wooden", "plastic", "transparent", "metallic",
}

_UNSUPPORTED_DETAIL_PATTERNS = [
    r"\b(?:polished\s+)?(?:copper|glass|stainless|steel|ceramic|brass|silver|gold)\b",
    r"\b(?:black|white|red|blue|green|yellow|rustic|vintage|wooden|plastic|transparent|metallic)\b",
    r"\b(?:glowing|artisan|camping|outdoor|indoor|kitchen|workshop|portable)\b",
]


def _clean(value, limit=500):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _narration(scene):
    return _clean(scene.get("narration"), 700).lower()


def _has_any(text, phrases):
    return any(p in text for p in phrases)


def _contextual(scene):
    text = _narration(scene)
    return _has_any(text, tuple(p for group, _ in _PHYSICAL_QUERY_RULES for p in group))


def _strip_unsupported(value, narration):
    text = _clean(value, 600)
    for pattern in _UNSUPPORTED_DETAIL_PATTERNS:
        for match in re.findall(pattern, text, flags=re.I):
            word = str(match).strip().lower()
            # Keep a detail only when that exact detail is actually spoken.
            if word and word not in narration:
                text = re.sub(re.escape(str(match)), "", text, flags=re.I)
    return _clean(text)


def _sanitize_visual(scene, visual):
    """Make generated visual metadata subordinate to the narration."""
    if not isinstance(visual, dict):
        return visual

    narration = _narration(scene)
    spoken = _clean(visual.get("spoken_line"), 500).lower()
    authoritative = narration or spoken

    # Never let unsupported generated detail become part of search semantics.
    for key in ("visual_focus", "visual_action", "image_prompt"):
        visual[key] = _strip_unsupported(visual.get(key), authoritative)

    must = visual.get("must_show")
    if isinstance(must, list):
        cleaned = []
        for item in must:
            item = _strip_unsupported(item, authoritative)
            if item:
                cleaned.append(item)
        visual["must_show"] = cleaned[:6]

    # The spoken line itself must always be the primary semantic beat.
    visual["visual_contract_note"] = "Narration is authoritative; generated visual metadata cannot add unsupported details."
    return visual


def _clean_query(value):
    # Search text is deliberately reduced to ordinary visual words.
    words = re.findall(r"[a-z0-9]+", str(value or "").lower())
    stop = {
        "this", "that", "with", "from", "your", "into", "about", "just", "they", "them", "their",
        "very", "have", "will", "what", "when", "where", "which", "because", "while", "then", "than",
        "like", "gets", "make", "makes", "made", "thing", "things", "exact", "physical", "show", "showing",
        "scene", "shot", "visible", "action", "state", "realistic", "cinematic", "photo", "photograph",
        "video", "image", "someone", "something", "close", "camera", "natural", "looking", "moment",
        "also", "really", "tiny", "microscopic", "single", "entire", "every", "time", "next", "remember",
        "designed", "actually", "basically", "literally", "nobody", "touched", "cursed", "higher", "lower",
    }
    result = []
    for word in words:
        if len(word) >= 4 and word not in stop and word not in result:
            result.append(word)
    return " ".join(result[:8])


def _expand_queries(pm, scene, visual):
    """Build searches from narration first; visual metadata is only a fallback."""
    visual = _sanitize_visual(scene, visual)
    narration = _narration(scene)
    spoken = _clean(visual.get("spoken_line") or narration, 500).lower()
    raw = f"{narration} {spoken}".strip()
    variants = []

    def add(query):
        query = _clean_query(query)
        if query and query not in variants:
            variants.append(query)

    # 1. Strong semantic proxy rules based ONLY on what is spoken.
    for triggers, replacements in _PHYSICAL_QUERY_RULES:
        if _has_any(raw, triggers):
            for query in replacements:
                add(query)

    # 2. Preserve literal nouns explicitly spoken by the narrator.
    literal_words = []
    for word in re.findall(r"[a-z0-9]+", raw):
        if len(word) >= 4 and word not in literal_words:
            literal_words.append(word)
    if literal_words:
        add(" ".join(literal_words[:6]))
        add(" ".join(literal_words[:8]))

    # 3. Only if the narration gave us no useful physical concept do we use the
    # generated focus/action, and even then strip unsupported detail first.
    if not variants:
        focus = _clean(visual.get("visual_focus"), 140)
        action = _clean(visual.get("visual_action"), 140)
        add(f"{focus} {action}")
        add(focus)

    return variants[:8] or ["everyday object close up"]


def _text(scene, visual):
    # IMPORTANT: ranking must judge what is actually spoken, not hallucinated
    # visual metadata. This is the second half of the relevance fix.
    return _clean(scene.get("narration") or visual.get("spoken_line"), 800)


def _install_selector(pm):
    if getattr(pm, "_mint_selector_v13", False):
        return

    def select(scene, visual, excluded_pages=None):
        excluded_pages = excluded_pages or set()
        if not pm.headers():
            return None

        visual = _sanitize_visual(scene, visual)
        qs = _expand_queries(pm, scene, visual)
        required = pm.tokens(_text(scene, visual))
        actions = pm.action_tokens(_text(scene, visual))
        contextual = _contextual(scene)
        # Contextual means the narration describes a physical process whose
        # exact microscopic state may not exist in stock footage. It still must
        # be visually relevant; 6/10 is the minimum contextual acceptance.
        minimum = 6 if contextual else 8

        print(f"   🧭 Semantic visual search: {'NARRATION-DRIVEN PHYSICAL PROXY' if contextual else 'NARRATION-DRIVEN LITERAL'} | queries={len(qs)}")
        print(f"   🔎 Search queries: {' | '.join(qs[:6])}")

        videos = []
        for q in qs:
            videos.extend(pm.search("videos/search", q, {"orientation": "portrait", "size": "medium"}))
        videos = pm._dedupe(videos, "video", excluded_pages)
        videos.sort(key=lambda x: pm._heuristic_score(x, required, actions, "video"), reverse=True)
        print(f"   🔎 Pexels video candidates: {len(videos)}")

        ranked = pm._gemini_rank_candidates(scene, visual, videos[:12], "video") if videos else []
        for item in ranked:
            score = int(item.get("_gemini_score", 0) or 0)
            if score >= minimum:
                link = pm._video_download_url(item)
                if link:
                    return {
                        "kind": "video", "video": link, "page": item.get("url", ""),
                        "photographer": (item.get("user") or {}).get("name", "") or "",
                        "score": score, "qc_reason": item.get("_gemini_reason", ""),
                        "query": " | ".join(qs[:6]),
                    }

        photos = []
        for q in qs:
            photos.extend(pm.search("search", q, {"orientation": "portrait", "size": "large"}))
        photos = pm._dedupe(photos, "photo", excluded_pages)
        photos.sort(key=lambda x: pm._heuristic_score(x, required, actions, "photo"), reverse=True)
        print(f"   🔎 Pexels photo candidates: {len(photos)}")

        ranked = pm._gemini_rank_candidates(scene, visual, photos[:12], "photo") if photos else []
        for item in ranked:
            score = int(item.get("_gemini_score", 0) or 0)
            if score >= minimum:
                src = item.get("src") or {}
                link = src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
                if link:
                    return {
                        "kind": "photo", "photo": link, "page": item.get("url", ""),
                        "photographer": item.get("photographer", "") or "", "score": score,
                        "qc_reason": item.get("_gemini_reason", ""), "query": " | ".join(qs[:6]),
                    }

        print(f"   ❌ No Pexels asset passed the {minimum}/10 narration relevance threshold")
        return None

    pm._select = select
    pm._mint_selector_v13 = True


def _assert_complete(groups):
    if len(groups) != 7:
        raise RuntimeError(f"Media contract failed: expected 7 scene groups, found {len(groups)}")
    for si, paths in enumerate(groups, 1):
        if len(paths) != 2:
            raise RuntimeError(f"Media contract failed: Scene {si} has {len(paths)} paths")
        if any(not os.path.exists(p) for p in paths):
            raise RuntimeError(f"Media contract failed: Scene {si} has missing assets")


def patch_media_selection(media):
    original_generate = media.generate_media
    if getattr(original_generate, "_mint_media_policy_v13", False):
        return

    import pexels_media
    _install_selector(pexels_media)

    def generate_media(script, output_dir, config, gim):
        groups = original_generate(script, output_dir, config, gim)
        _assert_complete(groups)
        with open(os.path.join(output_dir, "media_manifest.json"), "w", encoding="utf-8") as handle:
            json.dump({
                "provider_order": ["pexels_verified_video", "pexels_verified_photo"],
                "gemini_calls": "one_per_shot_for_pexels_only",
                "post_selection_gemini_qc": False,
                "pollinations": "disabled",
                "semantic_stock_query_translation": "narration_authoritative_v13",
                "ordinary_minimum_gemini_visual_score": 8,
                "contextual_physical_minimum_gemini_visual_score": 6,
                "generated_visual_metadata": "advisory_only",
                "narration_authoritative": True,
            }, handle, ensure_ascii=False, indent=2)
        print("🧠 Media policy v13: narration-authoritative retrieval + hallucinated visual detail blocked")
        return groups

    generate_media._mint_media_policy_v13 = True
    media.generate_media = generate_media
