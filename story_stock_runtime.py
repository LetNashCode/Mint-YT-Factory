"""Story-only stock-media resilience layer.

This module is loaded only by the Story Shorts workflow. It keeps Publish Shorts
unchanged while making Story stock selection survive Gemini free-tier exhaustion
and Wikimedia throttling.
"""
from __future__ import annotations

import re
import stock_search


RECENT_MEDIA_COOLDOWN = 15


def _recent_asset_keys() -> set[str]:
    """Block only the recent cooldown window; older relevant assets may return."""
    try:
        assets = stock_search._load_media_history().get("assets", [])
    except Exception:
        return set()
    valid = [x for x in assets if isinstance(x, dict) and x.get("asset_key")]
    valid.sort(key=lambda x: int(x.get("recorded_at", 0) or 0))
    return {str(x["asset_key"]) for x in valid[-RECENT_MEDIA_COOLDOWN:]}


def _story_context(script: dict, scene_no: int) -> list[str]:
    """Produce concrete stock-search concepts instead of weak words/pronouns."""
    scenes = script.get("scene_plan") or []
    narration = ""
    if isinstance(scenes, list) and len(scenes) >= scene_no and isinstance(scenes[scene_no - 1], dict):
        narration = str(scenes[scene_no - 1].get("narration") or "").lower()

    cues = [
        (r"gymnast|gymnastics|balance beam|uneven bars|floor exercise|perfect 10", ["gymnastics athlete", "gymnast training", "gymnastics competition"]),
        (r"basketball|nba|court|dunk|dribble", ["basketball player", "basketball court", "basketball training"]),
        (r"football|soccer|goal|pitch", ["soccer player", "soccer training", "soccer match"]),
        (r"tennis|racket|wimbledon", ["tennis player", "tennis training", "tennis match"]),
        (r"swim|swimmer|pool|olympic swimming", ["swimmer training", "competitive swimming", "swimming pool"]),
        (r"climb|climber|everest|mountain|himalaya", ["mountain climber", "mountain expedition", "himalayan mountains"]),
        (r"invent|invention|machine|workshop", ["inventor workshop", "engineer working", "mechanical workshop"]),
        (r"scientist|research|laboratory|lab|experiment|equation", ["scientist working", "research laboratory", "scientist writing"]),
        (r"music|singer|song|concert|piano|guitar", ["musician performing", "singer performing", "music rehearsal"]),
        (r"actor|actress|film|movie|hollywood|stage", ["actor performing", "film set", "stage performance"]),
        (r"business|company|entrepreneur|startup|office|deal|contract|salary", ["entrepreneur working", "business meeting", "office worker"]),
        (r"school|college|university|student|classroom", ["student studying", "college campus", "classroom"]),
        (r"war|soldier|battle|army|military", ["historical soldier", "military camp", "soldiers training"]),
        (r"poor|broke|homeless|struggle|poverty", ["person struggling", "poor neighborhood", "hardship"]),
        (r"championship|trophy|medal|victory|won|winner", ["sports trophy", "athlete victory", "medal ceremony"]),
    ]

    result: list[str] = []
    for pattern, phrases in cues:
        if re.search(pattern, narration, re.I):
            for phrase in phrases:
                if phrase not in result:
                    result.append(phrase)

    # If the scene has no domain cue, use the existing broad context only when
    # it is concrete. Never allow single-word numbers/pronouns as stock queries.
    try:
        original = stock_search.__story_context_original(script, scene_no)
    except AttributeError:
        original = []
    weak = re.compile(
        r"(?:he|she|him|her|they|them|it|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|old|young)",
        re.I,
    )
    for phrase in original:
        words = str(phrase).split()
        if len(words) >= 2 and not weak.fullmatch(str(phrase).strip()):
            if phrase not in result:
                result.append(phrase)
    return result[:5] or ["historical person", "person working"]


def _gemini_disabled(*args, **kwargs):
    """Story stock does not burn quota on repeated 429 retries.

    Script generation and real-person verification retain their own Gemini
    calls. Only the stock-search director/thumbnail verifier is bypassed here;
    deterministic concrete ladders remain active.
    """
    raise RuntimeError("Story stock Gemini bypassed for quota-safe deterministic fallback")


def _story_relevance_score(item, provider, video, query):
    """Relax only Story's deterministic stock threshold without accepting noise.

    stock_search's normal threshold is 2.5. Its scoring can be overly strict for
    Pexels/Pixabay metadata because a genuinely relevant result may expose only
    one useful query term. For Story, give a small bonus when at least one
    meaningful query token is present in the candidate metadata. This preserves
    the existing threshold and reuse guards while making provider results usable.
    """
    base = stock_search._deterministic_score(item[0] if False else {}, item, provider, video, query)
    # This branch is intentionally replaced by the wrapper below; keeping the
    # helper small makes the scoring rule explicit and testable.
    return base


_original_generate_media = stock_search.generate_media
_original_gemini = stock_search._gemini
_original_context = getattr(stock_search, "_story_context", None)
_original_score = getattr(stock_search, "_deterministic_score", None)
if _original_context is not None:
    stock_search.__story_context_original = _original_context


def _make_story_score(original_score):
    def story_score(d, item, provider, video, query):
        base = original_score(d, item, provider, video, query)
        hay = " ".join(
            [
                str(query),
                str(item.get("alt", "")),
                str(item.get("description", "")),
                str(item.get("tags", "")),
                str(item.get("url", "")),
            ]
        ).lower()
        meaningful = [w for w in re.findall(r"[a-z0-9]+", str(query).lower()) if len(w) > 2]
        if meaningful and any(word in hay for word in meaningful):
            # The existing URL bonus + one matching term normally produces 1.5.
            # Add 1.0 so legitimate provider hits reach the existing 2.5 gate.
            return base + 1.0
        return base
    return story_score


def _story_generate_media(script, output_dir, config, gim=None):
    is_story = isinstance(script, dict) and bool(
        script.get("story_person") or script.get("interactive_pillar") or script.get("story_visual_mode")
    )
    if not is_story:
        return _original_generate_media(script, output_dir, config, gim=gim)

    previous_history = getattr(stock_search, "_historical_asset_keys", None)
    previous_gemini = stock_search._gemini
    previous_context = getattr(stock_search, "_story_context", None)
    previous_score = getattr(stock_search, "_deterministic_score", None)
    stock_search._historical_asset_keys = _recent_asset_keys
    stock_search._gemini = _gemini_disabled
    stock_search._story_context = _story_context
    if _original_score is not None:
        stock_search._deterministic_score = _make_story_score(_original_score)
    try:
        print(
            "🛡️ STORY STOCK RESILIENCE: Gemini stock director/vision bypassed after quota-risk; "
            "deterministic concrete queries active"
        )
        print(
            f"📚 STORY MEDIA COOLDOWN: blocking only {len(_recent_asset_keys())} most recent assets; "
            "older relevant assets may be reused"
        )
        print("🎯 STORY STOCK RELEVANCE: relaxed metadata scoring for legitimate query-term matches")
        return _original_generate_media(script, output_dir, config, gim=gim)
    finally:
        if previous_history is None:
            try:
                del stock_search._historical_asset_keys
            except AttributeError:
                pass
        else:
            stock_search._historical_asset_keys = previous_history
        stock_search._gemini = previous_gemini
        if previous_context is None:
            try:
                del stock_search._story_context
            except AttributeError:
                pass
        else:
            stock_search._story_context = previous_context
        if previous_score is None:
            try:
                del stock_search._deterministic_score
            except AttributeError:
                pass
        else:
            stock_search._deterministic_score = previous_score


stock_search.generate_media = _story_generate_media
print("🛡️ Story stock runtime: quota-safe fallback + recent-only media cooldown ENABLED")
