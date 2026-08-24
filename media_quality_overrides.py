"""Mint-YT-Factory media quality policy.

v9: relevance-first Pexels selection with semantic stock-query translation.

The selector distinguishes between:
- ordinary beats that should have an 8/10 literal stock match;
- physical/scientific beats that cannot literally be filmed by stock footage and
  therefore need a truthful real-world proxy (for example, cavitation -> boiling
  water bubbles popping, or an invisible inside-kettle view -> transparent kettle
  / boiling-water macro).

Gemini remains the final visual judge. Contextual matching is narrow and explicit;
we never accept unrelated keyword matches merely to keep production running.
"""
from __future__ import annotations

import json
import os
import re


# Abstract/scientific descriptions that Pexels cannot reliably search literally.
# Each replacement is a real-world visual proxy that can honestly communicate the
# spoken beat without pretending that stock footage shows the microscopic event.
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
        ("millions of tiny bubbles", "tiny bubbles", "vapor bubble", "vapor bubbles"),
        ("boiling water bubbles close up", "bubbles rising in boiling water", "boiling pot bubbles macro"),
    ),
    (
        # Stock libraries almost never contain a useful view *inside the metal
        # base of a kettle*. Translate the impossible camera request into a
        # transparent-kettle / boiling-water view instead.
        ("metal base of kettle", "metal bottom of kettle", "bottom of kettle", "inside bottom of kettle", "inside kettle", "heated metal bottom", "water against heated metal", "simmering against heated metal"),
        ("glass kettle boiling water close up", "glass electric kettle bubbles close up", "boiling water in glass kettle", "kettle bubbles macro close up", "electric kettle boiling bubbles"),
    ),
    (
        ("rising tune", "rising pitch", "high pitched hiss", "high-pitched hiss", "low rumble", "deep rumble", "kettle sings", "kettle singing"),
        ("kettle boiling close up", "kettle steam close up", "boiling kettle on stove", "kettle spout steam", "boiling water close up"),
    ),
]

_CONTEXTUAL_PHENOMENA = (
    "collapsing bubble", "collapsing bubbles", "implode", "implodes", "cavitation",
    "shockwave", "shockwaves", "sound wave", "sound waves", "acoustic instrument",
    "microscopic drum", "microscopic drums", "tiny sound waves", "vapor bubble",
    "vapor bubbles", "millions of tiny bubbles", "metal base of kettle",
    "metal bottom of kettle", "bottom of kettle", "inside bottom of kettle",
    "inside kettle", "heated metal bottom", "water against heated metal",
    "simmering against heated metal", "rising pitch", "high pitched hiss",
    "high-pitched hiss", "low rumble", "deep rumble", "kettle sings", "kettle singing",
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

    # Physical proxies first. This prevents literal scientific terms from
    # dominating the candidate pool.
    for triggers, replacements in _PHENOMENON_QUERIES:
        if _has_any(raw, triggers):
            for replacement in replacements:
                add(replacement)

    # Preserve ordinary object/action searches.
    for phrase in (focus, must_text, action):
        cleaned = _clean_query(phrase)
        if cleaned:
            add(cleaned[:100])

    stop = getattr(pexels_media, "STOP", set())
    important = []
    for word in re.findall(r"[a-z0-9]+", raw):
        if len(word) >= 4 and word not in important and word not in stop:
            important.append(word)
    if important:
        add(" ".join(important[:5]))
        add(" ".join(important[:8]))

    return variants[:8] or pexels_media.queries(scene, visual)


def _install_selector(pexels_media):
    if getattr(pexels_media, "_mint_selector_v9", False):
        return

    def select(scene, visual, excluded_pages=None):
        excluded_pages = excluded_pages or set()
        if not pexels_media.headers():
            return None

        qs = _expand_queries(pexels_media, scene, visual)
        required = pexels_media.tokens(_text(scene, visual))
        actions = pexels_media.action_tokens(_text(scene, visual))
        contextual_allowed = _is_contextual_phenomenon(scene, visual)

        mode = "CONTEXTUAL SCIENCE" if contextual_allowed else "LITERAL"
        minimum = 6 if contextual_allowed else 8
        print(f"   🧭 Semantic visual search: {mode} | queries={len(qs)}")
        print(f"   🔎 Search queries: {' | '.join(qs[:6])}")

        videos = []
        for q in qs:
            videos.extend(pexels_media.search("videos/search", q, {"orientation": "portrait", "size": "medium"}))
        videos = pexels_media._dedupe(videos, "video", excluded_pages)
        videos.sort(key=lambda x: pexels_media._heuristic_score(x, required, actions, "video"), reverse=True)
        print(f"   🔎 Pexels video candidates: {len(videos)}")

        ranked = pexels_media._gemini_rank_candidates(scene, visual, videos[:12], "video") if videos else []
        for item in ranked:
            score = int(item.get("_gemini_score", 0) or 0)
            if item.get("_gemini_pass") and score >= minimum:
                link = pexels_media._video_download_url(item)
                if link:
                    return {
                        "kind": "video", "video": link, "page": item.get("url", ""),
                        "photographer": (item.get("user") or {}).get("name", "") or "",
                        "score": score, "qc_reason": item.get("_gemini_reason", ""),
                        "query": " | ".join(qs[:6]),
                    }

        photos = []
        for q in qs:
            photos.extend(pexels_media.search("search", q, {"orientation": "portrait", "size": "large"}))
        photos = pexels_media._dedupe(photos, "photo", excluded_pages)
        photos.sort(key=lambda x: pexels_media._heuristic_score(x, required, actions, "photo"), reverse=True)
        print(f"   🔎 Pexels photo candidates: {len(photos)}")

        ranked = pexels_media._gemini_rank_candidates(scene, visual, photos[:12], "photo") if photos else []
        for item in ranked:
            score = int(item.get("_gemini_score", 0) or 0)
            if item.get("_gemini_pass") and score >= minimum:
                src = item.get("src") or {}
                link = src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
                if link:
                    return {
                        "kind": "photo", "photo": link, "page": item.get("url", ""),
                        "photographer": item.get("photographer", "") or "",
                        "score": score, "qc_reason": item.get("_gemini_reason", ""),
                        "query": " | ".join(qs[:6]),
                    }

        print(f"   ❌ No Pexels asset passed the {'6/10 contextual' if contextual_allowed else '8/10 literal'} threshold")
        return None

    pexels_media._select = select
    pexels_media._mint_selector_v9 = True


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
    if getattr(original_generate, "_mint_media_policy_v9", False):
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
                "semantic_stock_query_translation": "enabled",
                "ordinary_minimum_gemini_visual_score": 8,
                "contextual_science_minimum_gemini_visual_score": 6,
                "contextual_science_only_for_registered_phenomena": True,
            }, handle, ensure_ascii=False, indent=2)
        print("🧠 Media policy v9: impossible science beats translated to honest stock proxies | Pexels VIDEO → PHOTO")
        return groups

    generate_media._mint_media_policy_v9 = True
    media.generate_media = generate_media
