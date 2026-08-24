"""Mint-YT-Factory media quality policy v11.

Relevance-first Pexels selection with a dedicated physical-proxy path for
boiling/heating/bubble beats. Numeric Gemini score is authoritative.
"""
from __future__ import annotations
import json, os, re

_PHENOMENON_QUERIES = [
    (("collapsing bubble", "collapsing bubbles", "implode", "implodes", "cavitation"), ("boiling water bubbles popping", "close up boiling water bubbles", "boiling water bubbling in pot", "hot water bubbles popping", "boiling water close up")),
    (("shockwave", "shockwaves", "sound wave", "sound waves"), ("boiling water bubbles popping", "water bubbles popping close up", "kettle boiling steam close up", "boiling pot close up")),
    (("microscopic drum", "tiny sound waves"), ("boiling water bubbles close up", "bubbles popping in boiling water", "boiling water macro close up")),
    (("millions of tiny bubbles", "tiny bubbles", "vapor bubble", "vapor bubbles"), ("boiling water bubbles close up", "bubbles rising in boiling water", "boiling pot bubbles macro")),
    (("metal base of kettle", "metal bottom of kettle", "bottom of kettle", "inside bottom of kettle", "inside kettle", "heated metal bottom"), ("glass kettle boiling water close up", "glass electric kettle bubbles close up", "boiling water in glass kettle", "kettle bubbles macro close up", "electric kettle boiling bubbles")),
    (("rising tune", "rising pitch", "high pitched hiss", "high-pitched hiss", "low rumble", "deep rumble", "kettle sings", "kettle singing", "piercing shriek", "shriek", "steam jet", "steam jets", "escaping steam", "kettle lid"), ("kettle boiling close up", "kettle steam close up", "boiling kettle on stove", "kettle spout steam", "kettle lid steam", "steam escaping kettle", "boiling water close up")),
    # Generic physical beats. These must be treated as contextual because stock
    # footage cannot literally show the sound/heat event described by narration.
    (("boiling water", "boiling bubbles", "bubbles forming", "bubbles at the bottom", "bubbles on the bottom", "large bubbles forming", "small bubbles forming", "hot water bubbling", "heated water", "water heating", "bottom of the pot", "base of the pot", "base of pot"), ("boiling water close up", "boiling water bubbles close up", "bubbles forming in boiling water", "water boiling in pot close up", "boiling pot macro", "kettle boiling close up")),
]
_CONTEXTUAL_PHENOMENA = tuple(x for group in _PHENOMENON_QUERIES for x in group[0])


def _text(scene, visual):
    return " ".join(str(x or "") for x in (visual.get("visual_focus"), visual.get("visual_action"), visual.get("must_show"), visual.get("spoken_line") or scene.get("narration"))).lower()


def _has_any(text, phrases):
    return any(p in text for p in phrases)


def _is_contextual_phenomenon(scene, visual):
    text = _text(scene, visual)
    # Explicit registered phenomena first, then safe generic physical proxies.
    if _has_any(text, _CONTEXTUAL_PHENOMENA):
        return True
    # A beat describing water heating/boiling and bubbles is inherently a
    # physical-proxy beat even when Gemini writes awkward wording such as
    # "bottom of glass pot". Do not force Pexels to find that exact phrase.
    generic = ("boiling", "bubbles", "bubble", "heating water", "heated water", "hot water")
    return _has_any(text, generic) and _has_any(text, ("water", "pot", "kettle", "bottom", "base"))


def _clean_query(value):
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower())).strip()


def _expand_queries(pm, scene, visual):
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

    # Physical proxies first. Never let an awkward generated object phrase such
    # as "bottom of glass pot" dominate search when the real beat is boiling water.
    for triggers, replacements in _PHENOMENON_QUERIES:
        if _has_any(raw, triggers):
            for q in replacements:
                add(q)

    # For generic boiling/bubble beats, deliberately avoid material-specific
    # searches. This improves relevance and keeps the visual truthful.
    if _has_any(raw, ("boiling", "bubbles", "bubble", "hot water", "heated water")) and _has_any(raw, ("water", "pot", "kettle")):
        for q in ("boiling water close up", "boiling water bubbles close up", "water boiling in pot close up", "boiling pot macro"):
            add(q)

    # Preserve ordinary object/action searches, but cap them after the physical
    # proxy queries so they cannot crowd out the useful candidates.
    for phrase in (focus, action):
        q = _clean_query(phrase)
        if q:
            add(q[:100])

    stop = getattr(pm, "STOP", set())
    important = []
    for word in re.findall(r"[a-z0-9]+", raw):
        if len(word) >= 4 and word not in important and word not in stop:
            important.append(word)
    if important:
        add(" ".join(important[:5]))
        add(" ".join(important[:8]))

    return variants[:8] or pm.queries(scene, visual)


def _acceptable(item, minimum):
    return int(item.get("_gemini_score", 0) or 0) >= minimum


def _install_selector(pm):
    if getattr(pm, "_mint_selector_v11", False):
        return

    def select(scene, visual, excluded_pages=None):
        excluded_pages = excluded_pages or set()
        if not pm.headers():
            return None

        qs = _expand_queries(pm, scene, visual)
        required = pm.tokens(_text(scene, visual))
        actions = pm.action_tokens(_text(scene, visual))
        contextual = _is_contextual_phenomenon(scene, visual)
        minimum = 6 if contextual else 8

        print(f"   🧭 Semantic visual search: {'CONTEXTUAL PHYSICAL PROXY' if contextual else 'LITERAL'} | queries={len(qs)}")
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
            if _acceptable(item, minimum):
                link = pm._video_download_url(item)
                if link:
                    return {"kind": "video", "video": link, "page": item.get("url", ""), "photographer": (item.get("user") or {}).get("name", "") or "", "score": score, "qc_reason": item.get("_gemini_reason", ""), "query": " | ".join(qs[:6])}

        photos = []
        for q in qs:
            photos.extend(pm.search("search", q, {"orientation": "portrait", "size": "large"}))
        photos = pm._dedupe(photos, "photo", excluded_pages)
        photos.sort(key=lambda x: pm._heuristic_score(x, required, actions, "photo"), reverse=True)
        print(f"   🔎 Pexels photo candidates: {len(photos)}")

        ranked = pm._gemini_rank_candidates(scene, visual, photos[:12], "photo") if photos else []
        for item in ranked:
            score = int(item.get("_gemini_score", 0) or 0)
            if _acceptable(item, minimum):
                src = item.get("src") or {}
                link = src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
                if link:
                    return {"kind": "photo", "photo": link, "page": item.get("url", ""), "photographer": item.get("photographer", "") or "", "score": score, "qc_reason": item.get("_gemini_reason", ""), "query": " | ".join(qs[:6])}

        print(f"   ❌ No Pexels asset passed the {'6/10 contextual' if contextual else '8/10 literal'} threshold")
        return None

    pm._select = select
    pm._mint_selector_v11 = True


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
    if getattr(original_generate, "_mint_media_policy_v11", False):
        return
    import pexels_media
    _install_selector(pexels_media)

    def generate_media(script, output_dir, config, gim):
        groups = original_generate(script, output_dir, config, gim)
        _assert_complete(groups)
        with open(os.path.join(output_dir, "media_manifest.json"), "w", encoding="utf-8") as h:
            json.dump({
                "provider_order": ["pexels_verified_video", "pexels_verified_photo"],
                "gemini_calls": "one_per_shot_for_pexels_only",
                "post_selection_gemini_qc": False,
                "pollinations": "disabled",
                "semantic_stock_query_translation": "enabled",
                "ordinary_minimum_gemini_visual_score": 8,
                "contextual_science_minimum_gemini_visual_score": 6,
                "physical_proxy_beats": "boiling_heating_bubbles",
            }, h, ensure_ascii=False, indent=2)
        print("🧠 Media policy v11: physical boiling/bubble proxy path enabled | numeric Gemini score controls acceptance")
        return groups

    generate_media._mint_media_policy_v11 = True
    media.generate_media = generate_media
