"""Failure-resilient stock-media pipeline for Mint-YT-Factory.

Pexels and Pixabay are the only media providers. Gemini directs searches,
expands stock vocabulary, and verifies candidate relevance. It never generates
images. No unrelated-media fallback is permitted.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests
import stock_search as stock
import stock_query_expander

VERIFY_MODELS = ("gemini-3.5-flash-lite", "gemini-2.5-flash-lite")
VERIFY_THRESHOLD = 7.5
VERIFY_ATTEMPTS = 3
VERIFY_CANDIDATE_BATCHES = (8, 4, 2)
SEARCH_ATTEMPTS = 3
DOWNLOAD_ATTEMPTS = 3
RETRY_BASE_SECONDS = 1.5
USER_AGENT = "Mint-YT-Factory/StockMedia/11.4"


def _sleep(attempt: int) -> None:
    time.sleep(RETRY_BASE_SECONDS * (2 ** max(0, attempt - 1)))


def _gemini_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required for stock visual verification.")
    return key


def _search_with_retry(provider: str, query: str, video: bool) -> list[dict]:
    fn = stock.pexels if provider == "Pexels" else stock.pixabay
    for attempt in range(1, SEARCH_ATTEMPTS + 1):
        try:
            results = fn(query, video)
            if results:
                return results
            print(f"      ↻ {provider} {'VIDEO' if video else 'PHOTO'} search returned no results ({attempt}/{SEARCH_ATTEMPTS})")
        except Exception as exc:
            print(f"      ⚠️ {provider} search {attempt}/{SEARCH_ATTEMPTS}: {type(exc).__name__}: {exc}")
        if attempt < SEARCH_ATTEMPTS:
            _sleep(attempt)
    return []


def _candidate_pool(directed: dict, provider: str, video: bool, used: set[str]) -> list[dict]:
    raw: list[dict] = []
    for query in directed.get("queries", []):
        raw.extend(_search_with_retry(provider, query, video))
    ranked = stock.rank(raw, directed, provider, video, used)
    candidates = []
    for score, item, page in ranked:
        preview = stock._preview(item, provider, video)
        url = stock._url(item, provider, video)
        if preview and url:
            creator = ((item.get("user") or {}).get("name", "") if provider == "Pexels" else item.get("user", ""))
            candidates.append({"provider": provider, "kind": "video" if video else "photo", "url": url,
                              "page": page, "creator": creator, "metadata_score": score, "preview": preview})
    return candidates


def _load_preview(url: str) -> bytes | None:
    for attempt in range(1, 4):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
            response.raise_for_status()
            if response.content:
                return response.content
        except Exception as exc:
            if attempt == 3:
                print(f"      ⚠️ Preview download failed after retries: {type(exc).__name__}")
            else:
                _sleep(attempt)
    return None


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?", "", str(text or "").strip(), flags=re.I).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise RuntimeError("Gemini returned invalid visual-verification JSON.")
        return json.loads(match.group(0))


def _verify_once(candidates: list[dict], directed: dict, model: str) -> list[dict]:
    from google import genai
    from google.genai import types

    usable: list[dict] = []
    parts: list[Any] = []
    for candidate in candidates:
        data = _load_preview(str(candidate.get("preview") or ""))
        if not data:
            continue
        parts.append(types.Part.from_bytes(data=data, mime_type="image/jpeg"))
        parts.append(types.Part.from_text(text=f"CANDIDATE {len(usable) + 1}"))
        usable.append(candidate)
    if not usable:
        return []

    prompt = f"""You are the FINAL VISUAL VERIFIER for a YouTube Short.
Judge ONLY what is actually visible in each candidate.

SPOKEN BEAT:
{directed.get('spoken_beat', '')}
IDEAL VISUAL:
{directed.get('casting_brief', '')}
MUST MATCH:
{json.dumps(directed.get('must_match', []), ensure_ascii=False)}
AVOID:
{json.dumps(directed.get('avoid', []), ensure_ascii=False)}

Rules:
1. The visible subject must be the actual subject spoken about.
2. The visible action/state should match the spoken action/state when that state is realistically available as stock.
3. A merely related object is NOT a match.
4. Reject generic people, generic food, generic water, decorative textures and attractive footage that does not illustrate the beat.
5. For short-lived or hard-to-film intermediate states, accept a DIRECTLY CAUSAL visible progression with the SAME subject. Example: if the beat says a popcorn kernel is heating in a pan, popcorn cooking/popping in that pan is acceptable evidence of the heating stage. Do not accept generic corn, corn fields, unrelated food, or generic kitchen footage.
6. For invisible/internal mechanisms, accept only a truthful visible proxy directly demonstrating the physical context: cut-open object, visible steam, boiling, swelling, cracking, bursting, or immediate physical result.
7. Cinematic quality never compensates for subject or context mismatch.
8. Be conservative. If the candidate is merely aesthetically related, reject it.

Return ONLY JSON:
{{"results":[{{"candidate":1,"score":0,"subject_match":0,"action_match":0,"context_match":0,"reject":true,"reason":"brief reason"}}]}}
Score 0-10. Usable means score >= {VERIFY_THRESHOLD} AND reject=false."""

    client = genai.Client(api_key=_gemini_key())
    response = client.models.generate_content(
        model=model,
        contents=parts + [types.Part.from_text(text=prompt)],
        config=types.GenerateContentConfig(temperature=0),
    )
    payload = _parse_json(getattr(response, "text", "") or "")
    results: list[dict] = []
    for result in payload.get("results", []):
        try:
            index = int(result.get("candidate", 0)) - 1
            score = float(result.get("score", 0) or 0)
            if not 0 <= index < len(usable) or bool(result.get("reject", True)) or score < VERIFY_THRESHOLD:
                continue
            item = dict(usable[index])
            item.update(visual_score=score,
                        visual_subject_match=float(result.get("subject_match", 0) or 0),
                        visual_action_match=float(result.get("action_match", 0) or 0),
                        visual_context_match=float(result.get("context_match", 0) or 0),
                        visual_reason=stock.clean(result.get("reason"), 400))
            results.append(item)
        except (TypeError, ValueError):
            continue
    results.sort(key=lambda item: item.get("visual_score", 0), reverse=True)
    return results


def _verify_resilient(candidates: list[dict], directed: dict) -> list[dict]:
    if not candidates:
        return []
    all_verified: list[dict] = []
    cursor = 0
    for batch_size in VERIFY_CANDIDATE_BATCHES:
        batch = candidates[cursor:cursor + batch_size]
        cursor += len(batch)
        if not batch:
            break
        batch_done = False
        for model in VERIFY_MODELS:
            for attempt in range(1, VERIFY_ATTEMPTS + 1):
                try:
                    verified = _verify_once(batch, directed, model)
                    if verified:
                        all_verified.extend(verified)
                        print(f"      ✅ Gemini verified {len(verified)}/{len(batch)} candidates with {model}")
                    else:
                        print(f"      ℹ️ Gemini {model} verified batch of {len(batch)}: no acceptable visual")
                    batch_done = True
                    break
                except Exception as exc:
                    print(f"      ⚠️ Gemini verification model={model} batch={len(batch)} attempt={attempt}/{VERIFY_ATTEMPTS}: {type(exc).__name__}")
                    if attempt < VERIFY_ATTEMPTS:
                        _sleep(attempt)
            if batch_done:
                break
            print(f"      ↪️ Visual verifier fallback: {model} → next model")
        if not batch_done:
            print("      ❌ All visual-verifier models failed for this batch")

    best_by_page: dict[str, dict] = {}
    for item in all_verified:
        page = str(item.get("page", ""))
        if page and (page not in best_by_page or float(item.get("visual_score", 0)) > float(best_by_page[page].get("visual_score", 0))):
            best_by_page[page] = item
    return sorted(best_by_page.values(), key=lambda item: item.get("visual_score", 0), reverse=True)


def _search_and_verify(directed: dict, provider: str, video: bool, used: set[str]):
    candidates = _candidate_pool(directed, provider, video, used)
    if candidates:
        verified = _verify_resilient(candidates, directed)
        if verified:
            return verified, directed, False

    print(f"   🧠 {provider} {'VIDEO' if video else 'PHOTO'}: normal vocabulary failed — expanding search vocabulary")
    try:
        expanded = stock_query_expander.expand(directed)
    except Exception as exc:
        print(f"   ⚠️ Semantic search expansion failed: {type(exc).__name__}: {exc}")
        return [], directed, False

    fallbacks = expanded.get("semantic_fallback_queries", [])
    if not fallbacks:
        return [], expanded, False
    print(f"   🔎 Semantic alternatives: {' | '.join(fallbacks)}")
    fallback_directed = dict(expanded)
    fallback_directed["queries"] = fallbacks
    candidates = _candidate_pool(fallback_directed, provider, video, used)
    if not candidates:
        return [], fallback_directed, True
    verified = _verify_resilient(candidates, fallback_directed)
    return verified, fallback_directed, True


def _download_resilient(url: str, path: str, provider: str) -> bool:
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120, stream=True)
            response.raise_for_status()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        handle.write(chunk)
            if os.path.getsize(path) <= 10_000:
                raise RuntimeError("downloaded file is unexpectedly small")
            return True
        except Exception as exc:
            print(f"      ⚠️ {provider} download {attempt}/{DOWNLOAD_ATTEMPTS}: {type(exc).__name__}: {exc}")
            try: os.remove(path)
            except OSError: pass
            if attempt < DOWNLOAD_ATTEMPTS:
                _sleep(attempt)
    return False


def _credit(path: str, chosen: dict, directed: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"provider": chosen["provider"], "type": chosen["kind"], "page": chosen.get("page", ""),
                   "creator": chosen.get("creator", ""), "search_queries": directed.get("queries", []),
                   "search_mode": directed.get("search_mode", ""), "metadata_score": chosen.get("metadata_score", 0),
                   "gemini_visual_score": chosen.get("visual_score", 0), "visual_reason": chosen.get("visual_reason", "")},
                  handle, ensure_ascii=False, indent=2)


def generate_media(script: dict, output_dir: str, config: dict, gim=None):
    """Generate exactly 14 assets from Pexels/Pixabay only."""
    if not os.getenv("PEXELS_API_KEY", "").strip() and not os.getenv("PIXABAY_API_KEY", "").strip():
        raise RuntimeError("PEXELS_API_KEY or PIXABAY_API_KEY is required.")
    os.makedirs(output_dir, exist_ok=True)
    plan = stock.build_plan(script)
    used: set[str] = set()
    groups: list[list[str]] = []

    print("=" * 80)
    print("📚 VISUAL MEDIA v11.4 — PEXELS + PIXABAY ONLY + SEMANTIC SEARCH")
    print("Gemini: search direction + semantic vocabulary + visual verification ONLY")
    print("Image generation: DISABLED")
    print("Allowed media: Pexels VIDEO → Pixabay VIDEO → Pexels PHOTO → Pixabay PHOTO")
    print("Generated-image fallback: DISABLED")
    print("Unrelated-media fallback: DISABLED")
    print("Causal visual proxy: ENABLED for hard-to-film intermediate states")
    print("Verifier model fallback: gemini-3.5-flash-lite → gemini-2.5-flash-lite")
    print("=" * 80)

    providers = (("Pexels", True), ("Pixabay", True), ("Pexels", False), ("Pixabay", False))
    for scene_no, shots in enumerate(plan, 1):
        scene_paths: list[str] = []
        for shot_no, directed in enumerate(shots, 1):
            selected = None
            chosen_directed = directed
            rejected_pages: set[str] = set()
            for provider, video in providers:
                if provider == "Pexels" and not os.getenv("PEXELS_API_KEY", "").strip():
                    continue
                if provider == "Pixabay" and not os.getenv("PIXABAY_API_KEY", "").strip():
                    continue
                verified, search_directed, expanded_used = _search_and_verify(directed, provider, video, used | rejected_pages)
                if not verified:
                    print(f"   ↪️ Scene {scene_no} Shot {shot_no}: {provider} {'VIDEO' if video else 'PHOTO'} — no verified match")
                    continue
                for chosen in verified:
                    page = str(chosen.get("page", ""))
                    if not page or page in rejected_pages or page in used:
                        continue
                    ext = "mp4" if chosen["kind"] == "video" else "jpg"
                    path = os.path.join(output_dir, f"scene_{scene_no:02d}_shot_{shot_no:02d}.{ext}")
                    mode_label = "semantic " if expanded_used else ""
                    print(f"   🎯 Scene {scene_no} Shot {shot_no}: trying {mode_label}verified {provider} {chosen['kind']} {chosen['visual_score']:.1f}/10")
                    if _download_resilient(chosen["url"], path, chosen["provider"]):
                        selected = chosen, path
                        chosen_directed = search_directed
                        break
                    rejected_pages.add(page)
                if selected:
                    break
            if not selected:
                raise RuntimeError(f"No usable visually relevant Pexels/Pixabay media found for Scene {scene_no} Shot {shot_no}. Generation is disabled by design; refusing to substitute unrelated or AI-generated media.")
            chosen, path = selected
            used.add(chosen["page"])
            _credit(path + ".credit.json", chosen, chosen_directed)
            scene_paths.append(path)
        groups.append(scene_paths)

    if len(groups) != 7 or any(len(group) != 2 for group in groups):
        raise RuntimeError("Visual media contract failed: expected exactly 7 scenes × 2 assets.")
    return groups
