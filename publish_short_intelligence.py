"""Lightweight, explainable quality signals for Publish Shorts.

These heuristics are advisory, not virality predictors. The LLM critic and
actual channel analytics remain the primary creative-quality decisions.
"""
from __future__ import annotations

import re

GENERIC_OPENERS = (
    "did you know", "today we're going to", "in this video",
    "let's talk about", "the reason is", "what is", "what are",
)
CONCRETE_VERBS = {
    "sticks", "stuck", "squeaks", "fog", "drips", "leaks", "spills", "melts",
    "freezes", "fizzes", "pops", "cracks", "snaps", "rises", "falls", "bounces",
    "shakes", "spins", "whistles", "browns", "clings", "wrinkles", "swells",
    "shrinks", "glows", "steams", "bubbles", "rusts", "splashes", "boils",
    "burns", "opens", "closes", "bends", "breaks", "appears", "turns", "changes",
}
CURIOSITY_CUES = {
    "but", "actually", "instead", "except", "until", "why", "how", "impossible",
    "suddenly", "secret", "hidden", "wrong", "really", "never", "without",
}
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "with", "from", "into", "your",
    "you", "that", "this", "why", "what", "when", "where", "how", "does",
    "did", "is", "are", "to", "of", "for", "it", "its", "they", "their",
    "have", "has", "will", "can", "could", "would", "just", "about", "then",
}


def score_hook(text: str) -> dict:
    """Return a transparent 0–10 hook heuristic with reasons; never predicts virality."""
    hook = re.sub(r"\s+", " ", str(text or "")).strip()
    words = re.findall(r"[\w'-]+", hook.lower())
    word_count = len(words)
    tokens = set(re.findall(r"[a-z0-9]+", hook.lower()))
    meaningful = [word for word in words if word not in STOPWORDS]
    reasons = []

    brevity = 2.0 if 8 <= word_count <= 22 else 1.0 if 6 <= word_count <= 30 else 0.0
    if word_count > 22:
        reasons.append("Trim the opening so the surprise arrives sooner.")
    elif word_count < 8:
        reasons.append("Give the opening enough context to make the curiosity clear.")

    specificity = 2.0 if len(meaningful) >= 4 and (tokens & CONCRETE_VERBS) else 1.0 if len(meaningful) >= 4 else 0.0
    if specificity < 2:
        reasons.append("Lead with a more concrete, observable situation or action.")

    curiosity = 2.0 if "?" in hook or tokens & CURIOSITY_CUES else 1.0 if any(x in hook.lower() for x in ("you", "your")) else 0.0
    if curiosity == 0:
        reasons.append("Create an immediate question or information gap.")

    uniqueness = 2.0 if len(set(meaningful[:8])) >= min(6, len(meaningful[:8])) and len(meaningful) >= 5 else 1.0
    if uniqueness < 2:
        reasons.append("Avoid repetitive or templated wording.")

    opener = hook.lower()
    naturalness = 2.0 if hook and not any(opener.startswith(prefix) for prefix in GENERIC_OPENERS) else 0.0
    if naturalness == 0:
        reasons.append("Replace the generic announcement with the surprising moment itself.")

    total = round(brevity + specificity + curiosity + uniqueness + naturalness, 1)
    return {
        "score": total,
        "max_score": 10,
        "word_count": word_count,
        "components": {
            "brevity": brevity,
            "specificity": specificity,
            "curiosity_gap": curiosity,
            "wording_variety": uniqueness,
            "direct_open": naturalness,
        },
        "reasons": reasons,
        "is_heuristic": True,
    }


def competitor_outlier_brief(entries: list[dict], min_channel_videos: int = 4) -> list[dict]:
    """Rank public video entries by views / their channel median, with a sample-size guard."""
    by_channel: dict[str, list[dict]] = {}
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        channel = str(entry.get("channel") or entry.get("uploader") or "").strip()
        title = str(entry.get("title") or "").strip()
        try:
            views = int(entry.get("view_count") or entry.get("views") or 0)
        except (TypeError, ValueError):
            continue
        if channel and title and views > 0:
            by_channel.setdefault(channel, []).append({"channel": channel, "title": title, "views": views})

    ranked = []
    for channel, rows in by_channel.items():
        if len(rows) < min_channel_videos:
            continue
        sorted_views = sorted(row["views"] for row in rows)
        middle = len(sorted_views) // 2
        median = sorted_views[middle] if len(sorted_views) % 2 else (sorted_views[middle - 1] + sorted_views[middle]) / 2
        if median <= 0:
            continue
        for row in rows:
            multiple = row["views"] / median
            if multiple >= 1.5:
                ranked.append({
                    "title": row["title"],
                    "channel": channel,
                    "views": row["views"],
                    "channel_median_views": int(median),
                    "outlier_multiple": round(multiple, 2),
                })
    return sorted(ranked, key=lambda row: (row["outlier_multiple"], row["views"]), reverse=True)[:8]
