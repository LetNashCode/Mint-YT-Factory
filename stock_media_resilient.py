"""Failure-resilient stock-media pipeline for Mint-YT-Factory.

Uses only real Pexels/Pixabay media. Gemini directs searches and verifies
candidate visuals. Gemini failures never become an automatic acceptance of
unrelated media: the pipeline retries, reduces candidate batches, and moves
through the configured stock-provider fallbacks before failing the shot.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests

import stock_search as stock

VERIFY_MODEL = "gemini-flash-lite-latest"
VERIFY_THRESHOLD = 7.5
VERIFY_ATTEMPTS = 4
VERIFY_CANDIDATE_BATCHES = (8, 4, 2)
SEARCH_ATTEMPTS = 3
DOWNLOAD_ATTEMPTS = 3
RETRY_BASE_SECONDS = 1.5
USER_AGENT = "Mint-YT-Factory/StockMedia/9.0"


def _sleep(attempt: int) -> None:
    time.sleep(RETRY_BASE_SECONDS * (2 ** max(0, attempt - 1)))


def _gemini_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required for stock visual verification.")
    return key


def _search_with_retry(provider: str, query: str, video: bool) -> list[dict]:
    """Retry transient stock-provider failures without aborting the shot."""
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
            candidates.append({
                "provider": provider,
                "kind": "video" if video else "photo",
                "url": url,
                "page": page,
                "creator": ((item.get("user") or {}).get("name", "") if provider == "Pexels" else item.get("user", "")),
                "metadata_score": score,
                "preview": preview,
            })
    return candidates


def _load_preview(url: str) -> bytes | None:
    for attempt in range(1, 4):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
            response.raise_for_status()
            data = response.content
            if data:
                return data
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


def _verify_once(candidates: list[dict], directed: dict) -> list[dict]:
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
2. The visible action/state must match the spoken action/state.
3. A merely related object is NOT a match.
4. Reject generic people, generic food, generic water, decorative textures and attractive footage that does not illustrate the beat.
5. For invisible/internal mechanisms, accept only a truthful visible proxy that directly demonstrates the physical context.
6. Cinematic quality never compensates for subject or action mismatch.
7. Be conservative. If unsure, reject.

Return ONLY JSON:
{{"results":[{{"candidate":1,"score":0,"subject_match":0,"action_match":0,"context_match":0,"reject":true,"reason":"brief reason"}}]}}
Score 0-10. Usable means score >= {VERIFY_THRESHOLD} AND reject=false."""

    client = genai.Client(api_key=_gemini_key())
    response = client.models.generate_content(
        model=VERIFY_MODEL,
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
            item.update(
                visual_score=score,
                visual_subject_match=float(result.get("subject_match", 0) or 0),
                visual_action_match=float(result.get("action_match", 0) or 0),
                visual_context_match=float(result.get("context_match", 0) or 0),
                visual_reason=stock.clean(result.get("reason"), 400),
            )
            results.append(item)
        except (TypeError, ValueError):
            continue
    results.sort(key=lambda item: item.get("visual_score", 0), reverse=True)
    return results


def _verify_resilient(candidates: list[dict], directed: dict) -> dict | None:
    """Retry Gemini and progressively shrink the batch to isolate bad requests."""
    if not candidates:
        return None

    last_error: Exception | None = None
    for batch_size in VERIFY_CANDIDATE_BATCHES:
        batch = candidates[:batch_size]
        for attempt in range(1, VERIFY_ATTEMPTS + 1):
            try:
                verified = _verify_once(batch, directed)
                if verified:
                    return verified[0]
                # A successful Gemini call with no acceptable candidate is a
                # content rejection, not a transport failure. Let the next
                # provider try rather than repeatedly spending Gemini calls.
                print(f"      ℹ️ Gemini verified batch of {len(batch)} candidates: no acceptable visual")
                break
            except Exception as exc:
                last_error = exc
                print(f"      ⚠️ Gemini verification batch={len(batch)} attempt={attempt}/{VERIFY_ATTEMPTS}: {type(exc).__name__}")
                if attempt < VERIFY_ATTEMPTS:
                    _sleep(attempt)
        if len(batch) < len(candidates):
            print(f"      ↘️ Reducing Gemini verification batch from {len(batch)} to {max(1, batch_size // 2)}")

    if last_error:
        print(f"      ⚠️ Gemini verifier unavailable for this shot after retries: {type(last_error).__name__}")
    return None


def _download_resilient(url: str, path: str, provider: str) -> bool:
    """Download selected media with retry and cleanup between attempts."""
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
            try:
                os.remove(path)
            except OSError:
                pass
            if attempt < DOWNLOAD_ATTEMPTS:
                _sleep(attempt)
    return False


def generate_media(script: dict, output_dir: str, config: dict, gim=None):
    """Generate exactly 14 verified stock assets with resilient provider/Gemini fallbacks."""
    if not os.getenv("PEXELS_API_KEY", "").strip() and not os.getenv("PIXABAY_API_KEY", "").strip():
        raise RuntimeError("PEXELS_API_KEY or PIXABAY_API_KEY is required.")

    os.makedirs(output_dir, exist_ok=True)
    plan = stock.build_plan(script)
    used: set[str] = set()
    groups: list[list[str]] = []

    print("=" * 80)
    print("📚 STOCK MEDIA v9.0 — FAILURE-RESILIENT")
    print("Gemini: search director + strict visual verifier")
    print("Media: Pexels/Pixabay only — AI image generation DISABLED")
    print("Fallback order: Pexels VIDEO → Pixabay VIDEO → Pexels PHOTO → Pixabay PHOTO")
    print("Gemini failures: RETRY → SMALLER BATCH → NEXT PROVIDER")
    print("Unrelated fallback: DISABLED")
    print("=" * 80)

    providers = (("Pexels", True), ("Pixabay", True), ("Pexels", False), ("Pixabay", False))

    for scene_no, shots in enumerate(plan, 1):
        scene_paths: list[str] = []
        for shot_no, directed in enumerate(shots, 1):
            selected = None
            for provider, video in providers:
                if provider == "Pexels" and not os.getenv("PEXELS_API_KEY", "").strip():
                    continue
                if provider == "Pixabay" and not os.getenv("PIXABAY_API_KEY", "").strip():
                    continue

                candidates = _candidate_pool(directed, provider, video, used)
                if not candidates:
                    print(f"   ↪️ Scene {scene_no} Shot {shot_no}: {provider} {'VIDEO' if video else 'PHOTO'} — no candidates")
                    continue

                chosen = _verify_resilient(candidates, directed)
                if chosen:
                    selected = chosen
                    print(f"   ✅ Scene {scene_no} Shot {shot_no}: {provider} {chosen['kind']} VERIFIED {chosen['visual_score']:.1f}/10")
                    break
                print(f"   ↪️ Scene {scene_no} Shot {shot_no}: {provider} {'VIDEO' if video else 'PHOTO'} — no verified match")

            if not selected:
                raise RuntimeError(
                    f"No visually relevant stock asset found for Scene {scene_no} Shot {shot_no}. "
                    "All available stock providers and Gemini verification paths were exhausted; unrelated fallback remains disabled."
                )

            page = selected["page"]
            used.add(page)
            ext = "mp4" if selected["kind"] == "video" else "jpg"
            path = os.path.join(output_dir, f"scene_{scene_no:02d}_shot_{shot_no:02d}.{ext}")
            if not _download_resilient(selected["url"], path, selected["provider"]):
                # A download failure must not abort immediately. The selected
                # page is removed from this shot's used set so the caller can
                # safely retry the shot through another provider.
                used.discard(page)
                raise RuntimeError(f"Stock asset download failed for Scene {scene_no} Shot {shot_no} after retries.")

            stock._credit(path + ".credit.json", selected, directed)
            scene_paths.append(path)

        groups.append(scene_paths)

    if len(groups) != 7 or any(len(group) != 2 for group in groups):
        raise RuntimeError("Stock media contract failed: expected exactly 7 scenes × 2 assets.")
    return groups
