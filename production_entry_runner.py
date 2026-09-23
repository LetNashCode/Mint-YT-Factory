"""Publish Shorts runtime shim.

Loads production_entry.py and applies targeted runtime repairs before execution.
"""
from __future__ import annotations

import re

import production_entry as production
import stock_search
import story_archive_integration
import portrait_media_alignment

# Install the portrait alignment patch before the production entrypoint starts
# rendering. Landscape and archive videos will be contained in the 9:16 canvas.
try:
    import assemble
    portrait_media_alignment.install(assemble)
except Exception as exc:
    raise RuntimeError(f"Could not install portrait video alignment: {exc}") from exc


# Always enforce the canonical recent-media cooldown at runtime. Older versions
# of the compatibility shim returned the entire media history, which turned the
# intended 15-asset cooldown into a 726-asset hard block and made scarce topics
# fail even when older relevant stock video was available.
def _recent_historical_asset_keys() -> set[str]:
    try:
        data = stock_search._load_media_history()
        assets = data.get("assets", []) if isinstance(data, dict) else []
        records = [
            item for item in assets
            if isinstance(item, dict) and item.get("asset_key")
        ]
        records.sort(key=lambda item: float(item.get("recorded_at", 0) or 0))
        cooldown = int(getattr(stock_search, "MEDIA_REUSE_COOLDOWN", 15) or 15)
        return {str(item["asset_key"]) for item in records[-cooldown:]}
    except Exception as exc:
        print(f"⚠️ Media cooldown lookup failed; using empty recent block: {type(exc).__name__}: {exc}")
        return set()

stock_search._historical_asset_keys = _recent_historical_asset_keys
print("🛡️ Stock media-history guard: canonical recent-window helper active | window=15")


# Install the Story-specific topic/archive layer before production applies its
# stock-media monkeypatches. The wrapper then remains part of the live path.
story_archive_integration.install(production)


def _patch_stock_quota_resilience() -> None:
    """Disable vision for the current media run after a confirmed quota error."""
    original_installer = production._patch_stock_media_quality
    if getattr(original_installer, "_mint_quota_resilience", False):
        return

    def installer():
        original_installer()
        original_generate = stock_search.generate_media
        original_verify = stock_search.verify_actual
        original_fallback = stock_search._select_without_vision
        state = {"vision_disabled": False}

        def quota_error(exc: BaseException) -> bool:
            text = str(exc).lower()
            return any(token in text for token in (
                "429", "resource_exhausted", "resource exhausted", "quota exceeded", "ratelimitexceeded",
            ))

        def verify(d, items, provider, video, query, strategy):
            if state["vision_disabled"]:
                return None
            try:
                return original_verify(d, items, provider, video, query, strategy)
            except Exception as exc:
                if quota_error(exc):
                    state["vision_disabled"] = True
                    print("      🛡️ Gemini quota exhausted — vision disabled for the remainder of this media run")
                    return None
                raise

        def fallback(d, items, provider, video, query):
            """Choose a fresh candidate without requiring provider metadata to repeat the topic.

            Pexels/Pixabay video metadata is often sparse. During a Gemini quota
            outage the search query itself is the strongest semantic evidence because
            it was already generated from the locked physical subject. The previous
            runtime shim incorrectly required the full topic-term set to appear in
            provider metadata, which rejected legitimate mirror videos even when the
            query was explicitly "mirror reflection", "person facing mirror", etc.
            """
            historical = stock_search._historical_asset_keys()
            anchors = [str(x).lower() for x in d.get("anchor_terms", []) if str(x).strip()]
            query_words = [
                word for word in re.findall(r"[a-z0-9]+", str(query or "").lower())
                if len(word) > 2
            ]
            topic_subjects = [
                str(x).lower() for x in getattr(stock_search, "_mint_active_topic_terms", [])
                if str(x).strip()
            ]
            ranked = []
            for item in items:
                url = stock_search._url(item, provider, video)
                if not url:
                    continue
                key_builder = getattr(stock_search, "_asset_key", None)
                key = key_builder(item, provider, video, url) if callable(key_builder) else f"{provider}:{url}"
                if key in historical:
                    continue
                hay = " ".join(
                    str(item.get(k, ""))
                    for k in ("alt", "description", "tags", "name", "title")
                ).lower()

                # Query terms are deliberate camera-visible terms. Provider metadata
                # is supplemental evidence, not a mandatory topic gate.
                query_hits = sum(
                    1 for word in query_words
                    if re.search(r"\\b" + re.escape(word) + r"\\b", hay)
                )
                anchor_hits = sum(
                    1 for term in anchors
                    if re.search(r"\\b" + re.escape(term) + r"\\b", hay)
                    or term in str(query or "").lower()
                )
                subject_hits = sum(
                    1 for term in topic_subjects
                    if re.search(r"\\b" + re.escape(term) + r"\\b", hay)
                    or term in str(query or "").lower()
                )

                # The search query establishes the semantic floor. A physical
                # subject present in the query gets an additional boost, while
                # metadata matches improve ranking when available.
                score = min(query_hits * 1.25, 4.0)
                score += min(anchor_hits, 3.0)
                score += min(subject_hits * 1.5, 3.0)
                if any(
                    term in str(query or "").lower()
                    for term in ("mirror", "reflection", "looking in mirror", "facing mirror")
                ):
                    score += 1.5
                score += 1.0  # usable downloadable asset

                ranked.append((score, item))

            ranked.sort(key=lambda pair: pair[0], reverse=True)
            if not ranked:
                return None

            best_score, best_item = ranked[0]
            # Topic-locked deterministic queries are trusted at a lower floor than
            # generic metadata-only matches, but never accept an asset with no
            # usable URL or one blocked by the recent-15 reuse guard.
            minimum = 2.5 if query_words else 4.5
            if best_score < minimum:
                return None
            print(
                f"      🧮 Deterministic fallback accepted: score={best_score:.2f} "
                f"| query={query!r}"
            )
            return best_item

        def generate(script, output_dir, config, gim=None):
            state["vision_disabled"] = False
            return original_generate(script, output_dir, config, gim=gim)

        stock_search.verify_actual = verify
        stock_search._select_without_vision = fallback
        stock_search.generate_media = generate
        print("🛡️ Stock Gemini quota resilience: ACTIVE | quota disables vision + topic-aware fallback")

    installer._mint_quota_resilience = True
    production._patch_stock_media_quality = installer


def _patch_script_topic_coherence_fixed(main):
    """Reject genuine retired-topic bleed without rejecting valid comparisons."""
    original = main.generate_script
    if getattr(original, "_mint_topic_coherence_guard_fixed", False):
        return

    def guarded(topic, config, research=None, extra_feedback=""):
        feedback = extra_feedback or ""
        if "95-105 core narration words" in feedback:
            feedback = feedback.replace(
                "make the core narration 95-105 words and never exceed 112 words",
                "make the complete narration 100-110 words including the locked continuation; keep the core narration concise and never exceed 112 core words",
            )
        if "Target 95-105 core narration words" in feedback:
            feedback = feedback.replace(
                "Target 95-105 core narration words and never exceed 112 core words.",
                "Target 100-110 complete narration words including the locked continuation, with 90-105 core words and never more than 112 core words.",
            )
        result = original(topic, config, research, extra_feedback=feedback)
        current = str(topic or "").strip()
        sentences = []
        for scene in result.get("scene_plan") or []:
            if isinstance(scene, dict):
                sentences.extend(re.split(r"(?<=[.!?])\s+", str(scene.get("narration") or "")))
        onion_mentions = []
        onion_subject = False
        comparison_markers = re.compile(r"\b(?:like|unlike|similar to|same as|just like|as with|compared with|compared to)\b", re.I)
        subject_patterns = (
            r"\bonions?\b[^.!?]{0,90}\b(?:make|makes|cause|causes|release|releases|trigger|triggers|irritate|irritates)\b",
            r"\b(?:cutting|chopping|slicing)\s+onions?\b[^.!?]{0,90}\b(?:make|makes|cause|causes|trigger|triggers)\b",
            r"\bonions?\b[^.!?]{0,90}\b(?:cry|tears|tear|eyes?\s+water|water(?:ing|ed)?)\b",
        )
        for sentence in sentences:
            if not re.search(r"\bonions?\b", sentence, re.I):
                continue
            clean_sentence = sentence.strip()
            if not clean_sentence or comparison_markers.search(clean_sentence):
                continue
            onion_mentions.append(clean_sentence)
            if any(re.search(pattern, clean_sentence, re.I) for pattern in subject_patterns):
                onion_subject = True
        if onion_subject or len(onion_mentions) >= 2:
            raise RuntimeError(f"Topic coherence gate rejected retired onion subject bleed in generated Short: {current!r}")
        result["topic"] = current
        return result

    guarded._mint_topic_coherence_guard_fixed = True
    main.generate_script = guarded
    print("🛡️ Script topic-coherence gate: ENABLED | retired-subject detection is narration-focused")


_patch_stock_quota_resilience()
production._patch_script_topic_coherence = _patch_script_topic_coherence_fixed
production.main_entry()
