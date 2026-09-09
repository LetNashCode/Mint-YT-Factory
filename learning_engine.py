"""Self-learning decision engine for Mint-YT-Factory.

V2 learns creative patterns from the actual generated script metadata instead of
only topic text. It remains backward compatible with the existing main.py API.
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ANALYTICS_DIR = ROOT / "analytics"
PLAYBOOK_PATH = ANALYTICS_DIR / "playbook.json"
USED_TOPICS_PATH = ROOT / "used_topics.json"

EXPLOITATION = 0.70
ADJACENT_EXPLORATION = 0.20
WILD_EXPLORATION = 0.10

STOP_WORDS = {
    "that","this","with","from","your","they","them","then","than","into",
    "when","where","what","which","because","while","just","really","very",
    "have","will","does","there","their","about","like","more","only","still",
    "even","gets","make","makes","made","over","under","also","actually","strange",
    "weird","thing","things","little","sudden","suddenly","part","time","way",
    "water","you","are","the","and","but","for","not","its","it's","can","how",
    "why","now","watch","ever","some","your","they","their","what","does",
}


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _norm_topic(value: str) -> str:
    return " ".join(str(value or "").lower().strip().replace("?", "").split())


def _words(value: str) -> list[str]:
    return re.findall(r"\b[\w'-]+\b", str(value or ""))


def _performance(record: dict) -> float:
    """Retention-first creative score; views are deliberately capped in influence."""
    latest = record.get("latest", {}) or {}
    views = max(0, int(latest.get("views", 0) or 0))
    retention = float(latest.get("average_view_percentage", 0) or 0)
    duration = float(latest.get("average_view_duration", 0) or 0)
    likes = max(0, int(latest.get("likes", 0) or 0))
    comments = max(0, int(latest.get("comments", 0) or 0))
    shares = max(0, int(latest.get("shares", 0) or 0))
    subs = max(0, int(latest.get("subscribers_gained", 0) or 0))

    if retention <= 0 and duration <= 0:
        retention_signal = 0.0
    else:
        retention_signal = min(100.0, retention if retention > 0 else duration * 3.0)

    # Normalize interaction rates so high-distribution videos do not dominate.
    like_rate = min(10.0, likes / max(views, 1) * 100.0)
    comment_rate = min(5.0, comments / max(views, 1) * 100.0)
    share_rate = min(5.0, shares / max(views, 1) * 100.0)
    sub_rate = min(10.0, subs / max(views, 1) * 100.0)
    view_signal = min(10.0, math.log1p(views) / 2.0)

    return round(
        0.52 * retention_signal
        + 2.2 * sub_rate
        + 1.5 * share_rate
        + 0.8 * comment_rate
        + 0.35 * like_rate
        + 0.25 * view_signal,
        4,
    )


def _script_for(record: dict) -> dict | None:
    workdir = str(record.get("workdir") or "").strip()
    if not workdir:
        return None
    path = Path(workdir) / "script.json"
    return _load(path, None) if path.exists() else None


def _content_tokens(text: str) -> set[str]:
    return {
        w.lower() for w in re.findall(r"[a-z0-9]+", str(text or "").lower())
        if len(w) >= 4 and w.lower() not in STOP_WORDS
    }


def _topic_category(topic: str) -> str:
    text = str(topic or "").lower()
    categories = (
        "technology", "food", "clothing", "home", "body", "car", "weather",
        "sound", "kitchen", "animals", "space", "nature", "history", "psychology",
        "everyday",
    )
    return next((x for x in categories if x in text), "everyday")


def _creative_features(record: dict) -> dict[str, str]:
    """Extract stable, model-authored creative features from script.json."""
    script = _script_for(record) or {}
    scenes = script.get("scene_plan") or []
    scenes = [s for s in scenes if isinstance(s, dict)]
    first = scenes[0] if scenes else {}
    retention = [str(s.get("retention_purpose", "")).strip() for s in scenes if s.get("retention_purpose")]
    purposes = [str(s.get("purpose", "")).strip() for s in scenes if s.get("purpose")]

    hook_text = str(first.get("narration", ""))
    hook_lower = hook_text.lower()
    if "?" in hook_text:
        hook_type = "question_hook"
    elif re.search(r"\b(never|impossible|secret|actually|turns out|but here's|except)\b", hook_lower):
        hook_type = "contradiction_or_reveal_hook"
    elif re.search(r"\b(looks|seems|appears|watch|notice|you've)\b", hook_lower):
        hook_type = "observation_hook"
    else:
        hook_type = "curiosity_claim_hook"

    narration = " ".join(str(s.get("narration", "")) for s in scenes)
    word_count = len(_words(narration))
    question_count = narration.count("?")
    scene_words = [len(_words(s.get("narration", ""))) for s in scenes]
    explanation_index = next((i for i, s in enumerate(scenes) if str(s.get("purpose")) == "explanation"), 2)
    payoff_index = next((i for i, s in enumerate(scenes) if str(s.get("retention_purpose")) == "payoff"), 5)
    story_format = str(script.get("story_format") or "").strip()
    if not story_format:
        story_format = "-".join(purposes[:7]) or "seven_scene_story"

    return {
        "topic_category": _topic_category(record.get("topic", "")),
        "hook_type": hook_type,
        "story_format": story_format[:100],
        "curiosity_pattern": "+".join(dict.fromkeys(retention[:4]))[:100] or "open_loop",
        "payoff_position": "early" if payoff_index <= 3 else "mid" if payoff_index <= 5 else "late",
        "explanation_position": "early" if explanation_index <= 1 else "mid" if explanation_index <= 3 else "late",
        "script_length": "short" if word_count < 105 else "medium" if word_count <= 135 else "long",
        "question_density": "high" if question_count >= 3 else "medium" if question_count >= 1 else "low",
        "visual_style": str((script.get("visual_identity") or {}).get("style", "")).strip()[:100] or "unknown",
        "music_type": str((script.get("music") or {}).get("search", "")).strip()[:100] or "unknown",
        "voice": str((script.get("voice_style") or {}).get("tone", "")).strip()[:100] or "unknown",
        "engagement_experiment": str((script.get("engagement") or {}).get("experiment", "")).strip() or "none",
    }


def _pattern_features(topic: str) -> dict:
    text = str(topic or "").lower()
    words = re.findall(r"[a-z0-9]+", text)
    return {
        "topic_category": _topic_category(text),
        "hook_type": "why_question" if text.startswith("why") else "how_question" if text.startswith("how") else "curiosity",
        "topic_length": "short" if len(words) <= 5 else "medium" if len(words) <= 7 else "long",
    }


def _topic_similarity(a: str, b: str) -> float:
    sa, sb = set(_norm_topic(a).split()), set(_norm_topic(b).split())
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def build_playbook(records: list[dict]) -> dict:
    usable = [r for r in records if isinstance(r, dict) and r.get("video_id") and isinstance(r.get("latest", {}), dict)]
    scored = sorted(((_performance(r), r) for r in usable), key=lambda x: x[0], reverse=True)
    count = len(scored)
    top_n = max(3, min(10, math.ceil(count * 0.25))) if count else 0
    winners = [r for _, r in scored[:top_n]]
    losers = [r for _, r in scored[-top_n:]] if count >= 4 else []

    def pattern_rows(items: list[dict]) -> dict[str, list[float]]:
        out: dict[str, list[float]] = defaultdict(list)
        for record in items:
            features = _creative_features(record)
            score = _performance(record)
            for key, value in features.items():
                if value and value != "unknown":
                    out[f"{key}:{value}"].append(score)
        return out

    def ranked(rows: dict[str, list[float]]) -> list[dict]:
        result = []
        for key, values in rows.items():
            result.append({
                "pattern": key,
                "score": round(sum(values) / len(values), 3),
                "sample_size": len(values),
            })
        return sorted(result, key=lambda x: (x["sample_size"] >= 2, x["score"]), reverse=True)

    topics = [_norm_topic(r.get("topic", "")) for r in usable if r.get("topic")]
    has_live_metrics = any(
        any(float((r.get("latest", {}) or {}).get(k, 0) or 0) > 0 for k in (
            "views", "likes", "comments", "average_view_percentage", "subscribers_gained", "shares"
        )) for r in usable
    )

    winning_patterns = ranked(pattern_rows(winners))[:30] if has_live_metrics else []
    weak_patterns = ranked(pattern_rows(losers))[:30] if has_live_metrics else []
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "video_count": count,
        "learning_ready": count >= 3 and has_live_metrics,
        "metrics_available": has_live_metrics,
        "creative_learning_version": "v2",
        "objective": "maximize retention, sustainable views, shares and subscriber growth while preserving originality",
        "strategy": {
            "exploitation": EXPLOITATION,
            "adjacent_exploration": ADJACENT_EXPLORATION,
            "wild_exploration": WILD_EXPLORATION,
        },
        "winning_patterns": winning_patterns,
        "weak_patterns": weak_patterns,
        "winning_topics": [r.get("topic", "") for r in winners if r.get("topic")][:10] if has_live_metrics else [],
        "avoid_topics": [r.get("topic", "") for r in losers if r.get("topic")][:10] if has_live_metrics else [],
        "used_topic_count": len(set(topics)),
        "rules": [
            "Learn creative patterns, never copy winning topics literally.",
            "Retention is the primary signal; views alone are not a quality verdict.",
            "Use shares and subscriber conversion as stronger growth signals than likes.",
            "Prefer concrete everyday mysteries with an immediate curiosity gap.",
            "Preserve controlled exploration so the model does not overfit.",
            "Reject exact repeats and near-duplicate topics before generation.",
            "Prefer patterns with at least 2 observations before treating them as strong evidence.",
        ],
    }


def score_candidate_topic(topic: str, playbook: dict | None = None) -> dict:
    """Score a candidate using both legacy topic features and learned creative patterns."""
    pb = playbook or get_playbook()
    features = _pattern_features(topic)
    score = 0.0
    reasons: list[str] = []

    # Topic-level prior remains deliberately modest.
    for group, sign in ((pb.get("winning_patterns", []), 1), (pb.get("weak_patterns", []), -1)):
        for row in group:
            pattern = str(row.get("pattern", ""))
            for key, value in features.items():
                if pattern == f"{key}:{value}":
                    sample = int(row.get("sample_size", 1) or 1)
                    confidence = min(1.0, sample / 3.0)
                    delta = abs(float(row.get("score", 0))) * 0.08 * confidence
                    score += sign * delta
                    reasons.append(("winner " if sign > 0 else "weak ") + pattern)

    return {
        "topic": topic,
        "score": round(score, 3),
        "features": features,
        "reasons": reasons[:8],
    }


def refresh_playbook() -> dict:
    records = _load(ANALYTICS_DIR / "videos.json", [])
    records = records if isinstance(records, list) else []
    current = _load(PLAYBOOK_PATH, {})
    playbook = build_playbook(records)

    # Never erase a useful learned playbook just because an API refresh temporarily
    # returned no advanced metrics.
    if records and not playbook["metrics_available"] and isinstance(current, dict) and current.get("metrics_available"):
        current["generated_at"] = datetime.now(timezone.utc).isoformat()
        current["video_count"] = len(records)
        current["metrics_stale"] = True
        playbook = current

    _write(PLAYBOOK_PATH, playbook)
    print(f"🧠 Learning engine: {'READY' if playbook.get('learning_ready') else 'WARMING UP'}")
    print(f"🧠 Creative learning: {playbook.get('creative_learning_version', 'v1')}")
    print(f"🧠 Playbook saved: {PLAYBOOK_PATH}")
    return playbook


def get_playbook() -> dict:
    data = _load(PLAYBOOK_PATH, {})
    return data if isinstance(data, dict) else {}


def get_used_topics() -> list[str]:
    raw = _load(USED_TOPICS_PATH, [])
    result: list[str] = []
    if not isinstance(raw, list):
        return result
    for item in raw:
        if isinstance(item, str) and not item.startswith("__MINT_ANALYTICS__::"):
            result.append(item)
        elif isinstance(item, dict) and item.get("topic"):
            result.append(str(item["topic"]))
    return result


def topic_is_duplicate(topic: str, threshold: float = 0.62) -> bool:
    candidate = _norm_topic(topic)
    if not candidate:
        return True
    return any(_topic_similarity(candidate, old) >= threshold for old in get_used_topics())


if __name__ == "__main__":
    refresh_playbook()
