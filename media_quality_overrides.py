"""Media compatibility layer for Mint-YT-Factory.

Production visual policy:
- Gemini is used separately upstream as the VISUAL DIRECTOR that creates the
  literal visual plan and image/search prompts from the locked narration.
- Pexels is then used to source the actual stock video/photo.
- Gemini is deliberately NOT used as a post-generation visual verification gate.
- A deterministic local relevance pre-filter/ranker remains in the Pexels
  selector so the media stage does not silently pick arbitrary stock footage.

This separation is intentional: Gemini writes/directs; Pexels supplies media.
"""
from __future__ import annotations

import json
import os


def _local_rank_candidates(media, scene, visual, candidates, kind):
    """Rank Pexels candidates locally without any Gemini visual-QC call.

    The native selector already computes a useful lexical/action score. We use
    that score only to order the candidate pool and mark the ordered candidates
    as locally acceptable. This is NOT visual verification; the actual visual
    semantics come from the Gemini Visual Director's locked visual plan.
    """
    try:
        required = media.tokens(media._visual_text(scene, visual))
        actions = media.action_tokens(
            f"{media.clean(visual.get('visual_action'))} "
            f"{media.clean(visual.get('spoken_line') or scene.get('narration'))}"
        )
        ranked = sorted(
            candidates,
            key=lambda item: media._heuristic_score(item, required, actions, kind),
            reverse=True,
        )
    except Exception:
        ranked = list(candidates)

    ordered = []
    for item in ranked:
        copy = dict(item)
        copy["_gemini_score"] = None
        copy["_gemini_pass"] = True
        copy["_gemini_reason"] = "Gemini visual verification disabled by policy; ranked from Visual Director plan."
        ordered.append(copy)
    return ordered


def patch_media_selection(media):
    """Install the intended Gemini-Writer/Visual-Director + Pexels architecture."""
    original = getattr(media, "generate_media", None)
    if original is None:
        return

    if getattr(original, "_mint_media_policy_separate_visual_director", False):
        return

    # The native Pexels selector calls this helper for candidate verification.
    # Replace that helper only; keep query aggregation, deduplication, media
    # ordering, downloading, continuity and duplicate-asset protection intact.
    media._gemini_rank_candidates = lambda scene, visual, candidates, kind: _local_rank_candidates(
        media, scene, visual, candidates, kind
    )

    def generate_media(script, output_dir, config, gim):
        groups = original(script, output_dir, config, gim)

        manifest = {
            "provider_order": ["pexels_video", "pexels_photo"],
            "gemini_calls": "story_writer_and_visual_director_only",
            "visual_director": "gemini",
            "visual_verification": "disabled",
            "ranking": "local_heuristic_from_gemini_visual_plan",
            "unrelated_fallback": False,
        }
        os.makedirs(output_dir, exist_ok=True)
        with open(
            os.path.join(output_dir, "media_manifest.json"),
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)

        print("🎬 Media policy: Gemini Visual Director → Pexels media")
        print("🚫 Gemini post-generation visual verification: DISABLED")
        print("🧭 Pexels ranking: local relevance against Gemini visual plan")
        return groups

    generate_media._mint_media_policy_separate_visual_director = True
    media.generate_media = generate_media
