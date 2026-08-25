"""Media policy override for Mint-YT-Factory.

The production architecture intentionally uses Gemini twice during script
creation (entertainment writer + visual director), but does NOT use Gemini to
verify/rank Pexels candidates. Pexels selection is therefore local and
semantic: the Visual Director's concrete focus/action drives multiple Pexels
queries, followed by deterministic relevance ranking.
"""
from __future__ import annotations

import json
import os


def _local_select_factory(media):
    """Build a Pexels-only selector without any Gemini visual verification."""

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

        # Aggregate several formulations before ranking. This keeps search
        # recall high without making a provider verification call per query.
        videos = []
        for query in query_list:
            videos.extend(
                media.search(
                    "videos/search",
                    query,
                    {"orientation": "portrait", "size": "medium"},
                )
            )

        pool = media._dedupe(videos, "video", excluded_pages)
        pool.sort(
            key=lambda item: media._heuristic_score(
                item, required, actions, "video"
            ),
            reverse=True,
        )

        for item in pool[:12]:
            link = media._video_download_url(item)
            if not link:
                continue
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
            photos.extend(
                media.search(
                    "search",
                    query,
                    {"orientation": "portrait", "size": "large"},
                )
            )

        pool = media._dedupe(photos, "photo", excluded_pages)
        pool.sort(
            key=lambda item: media._heuristic_score(
                item, required, actions, "photo"
            ),
            reverse=True,
        )

        for item in pool[:12]:
            src = item.get("src") or {}
            link = (
                src.get("portrait")
                or src.get("large2x")
                or src.get("large")
                or src.get("original")
            )
            if not link:
                continue
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


def patch_media_selection(media):
    """Replace the old Gemini-Pexels verifier with the requested local policy."""
    if getattr(media, "_mint_media_policy_local", False):
        return

    media._select = _local_select_factory(media)

    original = getattr(media, "generate_media", None)
    if original is None:
        return

    def generate_media(script, output_dir, config, gim):
        groups = original(script, output_dir, config, gim)
        manifest = {
            "provider_order": ["pexels_video", "pexels_photo"],
            "script_gemini": "two_stage_writer_and_visual_director",
            "visual_verification": "disabled",
            "candidate_ranking": "local_semantic_heuristic",
            "gemini_candidate_qc": False,
            "unrelated_fallback": False,
        }
        os.makedirs(output_dir, exist_ok=True)
        with open(
            os.path.join(output_dir, "media_manifest.json"),
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)

        print(
            "🛡️ Media policy: Pexels multi-query + local semantic ranking "
            "(Gemini visual verification DISABLED)"
        )
        return groups

    generate_media._mint_media_policy_local = True
    media.generate_media = generate_media
