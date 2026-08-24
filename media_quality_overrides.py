"""Mint-YT-Factory media quality policy.

v8: relevance-first Pexels selection with semantic stock-query translation.

The important distinction is:
- narration can describe microscopic/physical phenomena that stock footage cannot
  literally show;
- the search layer must translate those beats into the closest honest real-world
  visual (for example: cavitation -> boiling-water bubbles popping), rather than
  searching the scientific phrase literally and returning scuba/diving footage;
- Gemini remains the final visual judge;
- ordinary beats still require an 8/10 literal match;
- only explicitly registered "stockable-context" phenomena may use a 6-7/10
  contextual match, and only when Gemini says the shot is clearly relevant.
"""
from __future__ import annotations

import json
import os
import re


# Phrases that are scientifically meaningful but usually produce terrible stock
# search results.  Each rule maps the abstract beat to an honest, recognizable
# physical demonstration that Pexels actually contains.
_PHENOMENON_QUERIES = [
    (
        ("collapsing bubble", "collapsing bubbles", "implode", "implodes", "implode instantly", "slam shut", "cavitation"),
        ("boiling water bubbles popping", "close up boiling water bubbles", "boiling water bubbling in pot", "hot water bubbles popping", "boiling water close up"),
    ),
    (
        ("shockwave", "shockwaves", "sound wave", "sound waves", "acoustic instrument"),
        ("boiling water bubbles popping", "water bubbles popping close up", "kettle boiling steam close up", "boiling pot close up"),
    ),
    (
        ("microscopic drum", "microscopic drums", "tiny sound waves"),
        ("boiling water bubbles close up", "bubbles popping in boiling water", "boiling water macro close up"),
    ),
    (
        ("millions of tiny bubbles", "tiny bubbles", "vapor bubbles"),
        ("boiling water bubbles close up", "bubbles rising in boiling water", "boiling pot bubbles macro"),
    ),
]

# Contextual fallback is ONLY permitted for phenomena where the exact microscopic
# event cannot reasonably exist in a stock library.  This is deliberately narrow.
_CONTEXTUAL_PHENOMENA = (
    "collapsing bubble", "collapsing bubbles", "implode", "implodes", "cavitation",
    "shockwave", "shockwaves", "sound wave", "sound waves", "acoustic instrument",
    "microscopic drum", "microscopic drums", "tiny sound waves", "vapor bubble",
    "vapor bubbles", "millions of tiny bubbles",
)


def _text(scene, visual):
    return " ".join(
        str(x or "")
        for x in (
            visual.get("visual_focus"),
            visual.get("visual_action"),
            visual.get("must_show"),
            visual.get("spoken_line") or scene.get("narration"),
        )
    ).lower()


def _has_any(text, phrases):
    return any(p in text for p in phrases)


def _is_contextual_phenomenon(scene, visual):
    return _has_any(_text(scene, visual), _CONTEXTUAL_PHENOMENA)


def _clean_query(value):
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower())).strip()


def _expand_queries(pexels_media, scene, visual):
    """Build search queries around what can actually be filmed.

    Keep the normal semantic queries, then add explicit physical translations for
    abstract science phrases. This prevents searches such as 'collapsing vapor
    bubble' from returning divers, soap bubbles, or random underwater footage.
    """
    focus = str(visual.get("visual_focus") or "").strip().lower()
    action = str(visual.get("visual_action") or "").strip().lower()
    must = visual.get("must_show") or []
    must_text = " ".join(str(x) for x in must[:6]).lower() if isinstance(must, list) else str(must).lower()
    spoken = str(visual.get("spoken_line") or scene.get("narration") or "").strip().lower()
    raw = " ".join((focus, action, must_text, spoken))

    variants = []

    def add(q):
        q = _clean_query(q)
        if q and q not in variants:
            variants.append(q)

    # Highest-priority translations first so the Pexels candidate pool contains
    # usable footage instead of being dominated by literal scientific keywords.
    for triggers, replacements in _PHENOMENON_QUERIES:
        if _has_any(raw, triggers):
            for replacement in replacements:
                add(replacement)

    # Preserve useful ordinary-object searches as well.
    base_phrases = (focus, must_text, action)
    for phrase in base_phrases:
        cleaned = _clean_query(phrase)
        if cleaned:
            add(cleaned[:100])

    # Let the existing alias system contribute known real-world synonyms.
    aliases = getattr(pexels_media, "STOP", set())
    important = []
    for word in re.findall(r"[a-z0-9]+", raw):
        if len(word) >= 4 and word not in important and word not in aliases:
            important.append(word)
    if important:
        add(" ".join(important[:5]))
        add(" ".join(important[:8]))

    # Keep the query budget small enough for the existing aggregated Gemini QC.
    return variants[:8] or pexels_media.queries(scene, visual)


def _install_selector(pexels_media):
    if getattr(pexels_media, "_mint_selector_v8", False):
        return

    def select(scene, visual, excluded_pages=None):
        excluded_pages = excluded_pages or set()
        if not pexels_media.headers():
            return None

        qs = _expand_queries(pexels_media, scene, visual)
        required = pexels_media.tokens(_text(scene, visual))
        actions = pexels_media.action_tokens(_text(scene, visual))
        contextual_allowed = _is_contextual_phenomenon(scene, visual)

        print(
            f"   🧭 Semantic visual search: {'CONTEXTUAL SCIENCE' if contextual_allowed else 'LITERAL'} | "
            f"queries={len(qs)}"
        )
        print(f"   🔎 Search queries: {' | '.join(qs[:6])}")

        videos = []
        for q in qs:
            videos.extend(
                pexels_media.search(
                    "videos/search", q, {"orientation": "portrait", "size": "medium"}
                )
            )
        videos = pexels_media._dedupe(videos, "video", excluded_pages)
        videos.sort(
            key=lambda x: pexels_media._heuristic_score(x, required, actions, "video"),
            reverse=True,
        )
        print(f"   🔎 Pexels video candidates: {len(videos)}")

        selected = (
            pexels_media._gemini_rank_candidates(scene, visual, videos[:12], "video")
            if videos
            else []
        )

        minimum = 6 if contextual_allowed else 8
        for item in selected:
            score = int(item.get("_gemini_score", 0) or 0)
            if item.get("_gemini_pass") and score >= minimum:
                link = pexels_media._video_download_url(item)
                if link:
                    return {
                        "kind": "video",
                        "video": link,
                        "page": item.get("url", ""),
                        "photographer": (item.get("user") or {}).get("name", "") or "",
                        "score": score,
                        "qc_reason": item.get("_gemini_reason", ""),
                        "query": " | ".join(qs[:6]),
                    }

        photos = []
        for q in qs:
            photos.extend(
                pexels_media.search(
                    "search", q, {"orientation": "portrait", "size": "large"}
                )
            )
        photos = pexels_media._dedupe(photos, "photo", excluded_pages)
        photos.sort(
            key=lambda x: pexels_media._heuristic_score(x, required, actions, "photo"),
            reverse=True,
        )
        print(f"   🔎 Pexels photo candidates: {len(photos)}")

        selected = (
            pexels_media._gemini_rank_candidates(scene, visual, photos[:12], "photo")
            if photos
            else []
        )
        for item in selected:
            score = int(item.get("_gemini_score", 0) or 0)
            if item.get("_gemini_pass") and score >= minimum:
                src = item.get("src") or {}
                link = (
                    src.get("portrait")
                    or src.get("large2x")
                    or src.get("large")
                    or src.get("original")
                )
                if link:
                    return {
                        "kind": "photo",
                        "photo": link,
                        "page": item.get("url", ""),
                        "photographer": item.get("photographer", "") or "",
                        "score": score,
                        "qc_reason": item.get("_gemini_reason", ""),
                        "query": " | ".join(qs[:6]),
                    }

        print(
            f"   ❌ No Pexels asset passed the {'6/10 contextual' if contextual_allowed else '8/10 literal'} threshold"
        )
        return None

    pexels_media._select = select
    pexels_media._mint_selector_v8 = True


def _assert_complete(groups):
    if len(groups) != 7:
        raise RuntimeError(
            f"Media contract failed: expected 7 scene groups, found {len(groups)}"
        )
    for si, paths in enumerate(groups, 1):
        if len(paths) != 2:
            raise RuntimeError(
                f"Media contract failed: Scene {si} has {len(paths)} paths"
            )
        if any(not os.path.exists(p) for p in paths):
            raise RuntimeError(
                f"Media contract failed: Scene {si} has missing assets"
            )


def patch_media_selection(media):
    original_generate = media.generate_media
    if getattr(original_generate, "_mint_media_policy_v8", False):
        return

    import pexels_media

    _install_selector(pexels_media)

    def generate_media(script, output_dir, config, gim):
        groups = original_generate(script, output_dir, config, gim)
        _assert_complete(groups)
        with open(
            os.path.join(output_dir, "media_manifest.json"), "w", encoding="utf-8"
        ) as handle:
            json.dump(
                {
                    "provider_order": [
                        "pexels_verified_video",
                        "pexels_verified_photo",
                    ],
                    "gemini_calls": "one_per_shot_for_pexels_only",
                    "post_selection_gemini_qc": False,
                    "pollinations": "disabled",
                    "semantic_stock_query_translation": "enabled",
                    "ordinary_minimum_gemini_visual_score": 8,
                    "contextual_science_minimum_gemini_visual_score": 6,
                    "contextual_science_only_for_registered_phenomena": True,
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )
        print(
            "🧠 Media policy v8: semantic stock translation | Pexels VIDEO → PHOTO | "
            "8/10 literal, narrow 6/10 contextual science fallback"
        )
        return groups

    generate_media._mint_media_policy_v8 = True
    media.generate_media = generate_media
