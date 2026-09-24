"""Hybrid Story Shorts media routing.

Visual hierarchy:
1. Verified real-person archival video.
2. Verified contextual archival video.
3. Reusable historical photographs with cinematic motion.
No YouTube downloads, generic stock, or unchecked media are used.

The renderer already supports still images with motion, so photographs are a
first-class fallback rather than a static emergency placeholder.
"""
from __future__ import annotations

import json
from pathlib import Path

import story_real_video_media as real_video
import story_archival_media as archival

_LAST_GROUPS = []


def _is_content_availability_failure(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return any(marker in text for marker in (
        "insufficient verified real footage",
        "no real video candidates found",
        "story video search budget exhausted",
    ))


def discover(person: str, audit: list | None = None) -> list[dict]:
    """Return discovery evidence from real video first, then archival media."""
    audit = audit if audit is not None else []
    try:
        found = real_video.discover(person, audit)
    except Exception as exc:
        found = []
        audit.append({"provider": "real_video", "error": type(exc).__name__})
    if found:
        return found

    # Metadata-only archival fallback. This does not download anything and
    # therefore remains safe for preflight.
    probe_script = {"story_person": person}
    probe_scene = {"visuals": []}
    found = []
    for want_video in (True, False):
        try:
            found.extend(archival._candidate_pool(probe_script, probe_scene, want_video))
        except Exception as exc:
            audit.append({
                "provider": "Wikimedia archival " + ("video" if want_video else "photo"),
                "error": type(exc).__name__,
            })
    if found:
        audit.append({"provider": "Wikimedia archival fallback", "candidates": len(found)})
    return found


def _cleanup_partial(output_dir: str) -> None:
    root = Path(output_dir)
    if not root.exists():
        return
    for path in root.glob("scene_*_shot_*.*"):
        try:
            path.unlink()
        except OSError:
            pass


def _record_audit(output_dir: str, mode: str, groups: list[dict], fallback_reason: str = "") -> None:
    path = Path(output_dir) / "story_media_route.json"
    payload = {
        "schema_version": 1,
        "mode": mode,
        "fallback_reason": fallback_reason[:1000],
        "groups": [
            {
                "scene": row.get("scene"),
                "shot": row.get("shot"),
                "type": row.get("type"),
                "provider": row.get("provider"),
                "source_url": row.get("source_url") or row.get("origin_url"),
                "asset_key": row.get("asset_key"),
            }
            for row in groups
        ],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def generate_media(script: dict, output_dir: str, config: dict, gim=None) -> list[dict]:
    """Use verified real video when available; otherwise use archival video/photo media."""
    global _LAST_GROUPS
    _LAST_GROUPS = []

    try:
        groups = real_video.generate_media(script, output_dir, config, gim=gim)
        _LAST_GROUPS = groups
        _record_audit(output_dir, "real_video", groups)
        print(f"🎞️ Story media route: VERIFIED_REAL_VIDEO ({len(groups)} shots)", flush=True)
        return groups
    except Exception as exc:
        if not _is_content_availability_failure(exc):
            # Provider/verifier failures must fail closed. Never disguise an
            # identity-verification outage as a valid archival fallback.
            raise
        reason = str(exc)
        print(
            "🖼️ Story real-person footage unavailable; switching to archival "
            "video/photo fallback (no generic stock).",
            flush=True,
        )
        _cleanup_partial(output_dir)
        groups = archival.generate_media(script, output_dir, config, gim=gim)
        _LAST_GROUPS = groups
        _record_audit(output_dir, "archival_video_or_photo", groups, reason)
        print(f"🖼️ Story media route: ARCHIVAL_VIDEO_OR_PHOTO ({len(groups)} shots)", flush=True)
        return groups


def source_credits() -> str:
    rows = _LAST_GROUPS or []
    lines = []
    seen = set()
    for row in rows:
        url = str(row.get("source_url") or row.get("origin_url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        provider = str(row.get("provider") or "Archival source").strip()
        creator = str(row.get("creator") or "").strip()
        suffix = f" — {creator}" if creator else ""
        lines.append(f"\\nSource: {provider}{suffix} {url}")
    return "".join(lines)
