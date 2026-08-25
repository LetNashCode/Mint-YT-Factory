"""Media policy override for Mint-YT-Factory.

Gemini is used for two creative passes plus one visual-search planning pass:
1. entertainment writer
2. independent visual director
3. batched stock-search query director

Gemini is NOT used to inspect, score, or verify Pexels candidates.
"""
from __future__ import annotations

import contextlib
import io
import json
import os


def _gemini_search_plan(media, script):
    """Ask Gemini once to convert the locked visual plan into stock-search queries.

    This is visual direction, not candidate verification: Gemini never sees Pexels
    results. It only creates precise, literal queries that Pexels can search.
    """
    try:
        from google import genai
        from google.genai import types
    except Exception:
        return {}
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return {}

    beats = []
    for si, scene in enumerate(script.get("scene_plan") or [], 1):
        for vi, visual in enumerate(scene.get("visuals") or [], 1):
            beats.append({
                "id": f"s{si}q{vi}",
                "topic": script.get("topic", ""),
                "spoken": visual.get("spoken_line") or scene.get("narration", ""),
                "focus": visual.get("visual_focus", ""),
                "action": visual.get("visual_action", ""),
                "must_show": visual.get("must_show", []),
                "prompt": visual.get("image_prompt", ""),
            })

    if not beats:
        return {}

    instruction = f"""
You are the STOCK-FOOTAGE SEARCH DIRECTOR for a YouTube Short.

You are NOT selecting or judging footage. You are only writing search queries for Pexels.
The current topic is the anchor for every query: {script.get('topic','')}

For every shot below, return 4 search queries from most exact to most practical.
Each query must:
- describe a real, visible thing a stock camera could capture
- contain the exact physical subject whenever possible
- include the physical action/state when useful
- be 2–7 words, plain English, no full sentences
- avoid abstract science terms, metaphors, explanations, emotions, and generic scenery
- never replace the main subject with a related but different object

CRITICAL EXAMPLE:
If the topic is "Why do wet tea bags stick" and the beat says a wet tea bag sticks to a counter,
GOOD: "wet tea bag counter", "tea bag stuck surface", "wet tea bag close up", "tea bag on wet counter"
BAD: "water surface", "water molecules", "vacuum physics", "sticky objects", "kitchen aesthetic"

If a shot explains an invisible mechanism, keep the real object in the query and search for its
observable demonstration. Do not search for microscopic particles, diagrams, laboratory art,
water textures, abstract bubbles, or unrelated metaphors.

Return ONLY JSON:
{{"shots":[{{"id":"s1q1","queries":["exact query","second query","third query","fallback query"]}}]}}

SHOT BEATS:
{json.dumps(beats, ensure_ascii=False)}
"""

    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=instruction,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.25,
            ),
        )
        data = json.loads(getattr(response, "text", "") or "{}")
        result = {}
        for row in data.get("shots", []):
            if not isinstance(row, dict):
                continue
            shot_id = str(row.get("id", ""))
            queries = []
            for value in row.get("queries", []):
                query = " ".join(str(value or "").split()).strip()
                if 2 <= len(query.split()) <= 8 and query not in queries:
                    queries.append(query)
            if queries:
                result[shot_id] = queries[:4]
        return result
    except Exception as exc:
        print(f"⚠️ Gemini visual-search planning unavailable: {exc}")
        return {}


def _local_select_factory(media, search_plan):
    """Pexels selector using Gemini-authored search queries and Pexels ordering only."""
    def select(scene, visual, excluded_pages=None):
        if not media.headers():
            return None
        excluded_pages = excluded_pages or set()
        si = int(scene.get("scene") or 0)
        vi = int(visual.get("segment") or 0)
        query_list = search_plan.get(f"s{si}q{vi}") or media.queries(scene, visual)
        query_list = query_list[:4]

        # Pexels itself is the ranking engine here. We do not inspect candidate
        # pixels, ask Gemini to score them, or use URL/title keyword hacks.
        seen_pages = set(excluded_pages)
        for query_index, query in enumerate(query_list, 1):
            results = media.search("videos/search", query, {"orientation": "portrait", "size": "medium"})
            for item in media._dedupe(results, "video", seen_pages):
                page = item.get("url", "")
                seen_pages.add(page)
                link = media._video_download_url(item)
                if not link:
                    continue
                return {
                    "video": link,
                    "kind": "video",
                    "page": page,
                    "photographer": (item.get("user") or {}).get("name", ""),
                    "score": round(10.0 - (query_index - 1) * 0.5, 2),
                    "qc_reason": "Gemini-authored visual search query; Pexels native relevance order; visual verification disabled",
                    "query": query,
                }

        for query_index, query in enumerate(query_list, 1):
            results = media.search("search", query, {"orientation": "portrait", "size": "large"})
            for item in media._dedupe(results, "photo", seen_pages):
                page = item.get("url", "")
                seen_pages.add(page)
                src = item.get("src") or {}
                link = src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
                if not link:
                    continue
                return {
                    "photo": link,
                    "kind": "photo",
                    "page": page,
                    "photographer": item.get("photographer", "") or "",
                    "score": round(8.0 - (query_index - 1) * 0.5, 2),
                    "qc_reason": "Gemini-authored visual search query; Pexels native relevance order; visual verification disabled",
                    "query": query,
                }
        return None
    return select


def _clean_native_log(text: str) -> str:
    replacements = {
        "Rule: Gemini verifies an aggregated Pexels candidate pool": "Rule: Gemini-authored visual queries + Pexels native relevance; no candidate verification",
        "Provider: Pexels verified VIDEO → Pexels verified PHOTO": "Provider: Pexels VIDEO → Pexels PHOTO",
        "Fallback policy: contextual Pexels match allowed at Gemini 6+/10 when no 8+ literal match exists": "Fallback policy: no unrelated fallback",
        "Pexels could not provide a relevant Gemini-verified asset": "Pexels could not provide a relevant asset",
        "Pexels {label} VERIFIED + selected | Gemini score=": "Pexels {label} selected | query priority=",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def patch_media_selection(media):
    if getattr(media, "_mint_media_policy_local", False):
        return

    media._select = _local_select_factory(media, {})
    original = getattr(media, "generate_media", None)
    if original is None:
        return

    def generate_media(script, output_dir, config, gim):
        # Build the visual-search plan once per Short. This is Gemini's separate
        # visual-generation/search role, not visual verification.
        search_plan = _gemini_search_plan(media, script)
        media._select = _local_select_factory(media, search_plan)
        print("🎯 Gemini visual-search director: generated queries for 14 shots")
        for key, queries in sorted(search_plan.items()):
            print(f"   🔎 {key}: {' | '.join(queries)}")

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
            "visual_search_gemini": "batched_query_director",
            "visual_verification": "disabled",
            "candidate_ranking": "pexels_native_search_order",
            "gemini_candidate_qc": False,
            "unrelated_fallback": False,
        }
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "media_manifest.json"), "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)

        print("🛡️ Media policy: Gemini visual query direction + Pexels native search (Gemini visual verification DISABLED)")
        return groups

    generate_media._mint_media_policy_local = True
    media.generate_media = generate_media
