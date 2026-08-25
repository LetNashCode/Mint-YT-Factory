"""Media compatibility layer for Mint-YT-Factory.

The production Pexels selector already performs aggregated candidate search and
Gemini visual QC. This module must NOT replace that selector with a local-only
heuristic because doing so can accept visually unrelated stock footage.
"""
from __future__ import annotations

import json
import os


def patch_media_selection(media):
    """Keep the native Pexels + Gemini visual-QC selector intact.

    Older versions of this override replaced ``pexels_media._select`` with a
    narration-keyword heuristic. That bypassed Gemini visual verification and
    caused unrelated fallback assets (for example onions for a candle scene)
    to pass production. The native selector already aggregates searches,
    ranks candidates, verifies the actual preview images with Gemini, and
    refuses candidates below its relevance threshold.
    """
    original = getattr(media, "generate_media", None)
    if original is None:
        return

    if getattr(original, "_mint_media_policy_native_gemini", False):
        return

    def generate_media(script, output_dir, config, gim):
        groups = original(script, output_dir, config, gim)

        manifest = {
            "provider_order": ["pexels_video", "pexels_photo"],
            "gemini_calls": "native_aggregated_candidate_qc",
            "visual_verification": "gemini",
            "ranking": "heuristic_prefilter_then_gemini_visual_qc",
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
            "🛡️ Media policy: native Pexels aggregated search + "
            "Gemini visual verification ENABLED"
        )
        return groups

    generate_media._mint_media_policy_native_gemini = True
    media.generate_media = generate_media
