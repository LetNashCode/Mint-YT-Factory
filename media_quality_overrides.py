"""Media policy override for Mint-YT-Factory.

Gemini is used twice during script creation: an entertainment writer pass and
an independent visual-director pass. Gemini is NOT used to inspect or verify
Pexels candidates. Pexels selection uses the visual-director fields with local
semantic ranking only.
"""
from __future__ import annotations

import contextlib
import io
import json
import os


def _local_select_factory(media):
    """Build a Pexels-only selector without Gemini candidate verification."""
    def select(scene, visual, excluded_pages=None):
        if not media.headers():
            return None
        excluded_pages = excluded_pages or set()
        required = media.tokens(media._visual_text(scene, visual))
        actions = media.action_tokens(
            f"{media.clean(visual.get('visual_action'))} "
            f"{media.clean(visual.get('spoken_line') or scene.get('narration'))}"
        )
        query_list = media.queries(scene, visual)

        videos = []
        for query in query_list:
            videos.extend(media.search("videos/search", query, {"orientation": "portrait", "size": "medium"}))
        pool = media._dedupe(videos, "video", excluded_pages)
        pool.sort(key=lambda item: media._heuristic_score(item, required, actions, "video"), reverse=True)
        for item in pool[:12]:
            link = media._video_download_url(item)
            if link:
                score = media._heuristic_score(item, required, actions, "video")
                return {
                    "video": link,
                    "kind": "video",
                    "page": item.get("url", ""),
                    "photographer": (item.get("user") or {}).get("name", ""),
                    "score": round(float(score), 2),
                    "qc_reason": "local semantic relevance ranking; Gemini visual verification disabled",
                    "query": " | ".join(query_list[:3]),
                }

        photos = []
        for query in query_list:
            photos.extend(media.search("search", query, {"orientation": "portrait", "size": "large"}))
        pool = media._dedupe(photos, "photo", excluded_pages)
        pool.sort(key=lambda item: media._heuristic_score(item, required, actions, "photo"), reverse=True)
        for item in pool[:12]:
            src = item.get("src") or {}
            link = src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
            if link:
                score = media._heuristic_score(item, required, actions, "photo")
                return {
                    "photo": link,
                    "kind": "photo",
                    "page": item.get("url", ""),
                    "photographer": item.get("photographer", "") or "",
                    "score": round(float(score), 2),
                    "qc_reason": "local semantic relevance ranking; Gemini visual verification disabled",
                    "query": " | ".join(query_list[:3]),
                }
        return None
    return select


def _clean_native_log(text: str) -> str:
    """Keep native media diagnostics but correct obsolete Gemini-QC wording."""
    replacements = {
        "Rule: Gemini verifies an aggregated Pexels candidate pool": "Rule: local semantic ranking of aggregated Pexels candidates",
        "Provider: Pexels verified VIDEO → Pexels verified PHOTO": "Provider: Pexels VIDEO → Pexels PHOTO",
        "Fallback policy: contextual Pexels match allowed at Gemini 6+/10 when no 8+ literal match exists": "Fallback policy: no unrelated fallback; local semantic relevance required",
        "Pexels could not provide a relevant Gemini-verified asset": "Pexels could not provide a sufficiently relevant asset",
        "Pexels {label} VERIFIED + selected | Gemini score=": "Pexels {label} selected | local relevance score=",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def patch_media_selection(media):
    if getattr(media, "_mint_media_policy_local", False):
        return

    media._select = _local_select_factory(media)
    original = getattr(media, "generate_media", None)
    if original is None:
        return

    def generate_media(script, output_dir, config, gim):
        # Native generate_media still contains old Gemini-oriented log strings.
        # Capture only its stdout so we can rewrite those messages without
        # changing the actual Pexels download/assembly behavior.
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                groups = original(script, output_dir, config, gim)
        except Exception:
            print(_clean_native_log(buffer.getvalue()), end="")
            raise
        print(_clean_native_log(buffer.getvalue()), end="")

        manifest = {
            "provider_order": ["pexels_video", "pexels_photo"],
            "script_gemini": "two_stage_writer_and_visual_director",
            "visual_verification": "disabled",
            "candidate_ranking": "local_semantic_heuristic",
            "gemini_candidate_qc": False,
            "unrelated_fallback": False,
        }
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "media_manifest.json"), "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)

        print("🛡️ Media policy: Pexels multi-query + local semantic ranking (Gemini visual verification DISABLED)")
        return groups

    generate_media._mint_media_policy_local = True
    media.generate_media = generate_media
