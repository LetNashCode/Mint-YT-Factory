"""Self-learning decision engine for Mint-YT-Factory.

V3 learns combinations of creative choices from published Shorts instead of
only ranking isolated features. It keeps the existing main.py API intact.
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
MIN_PATTERN_EVIDENCE = 2

STOP_WORDS = {
    "that","this","with","from","your","they","them","then","than","into",
    "when","where","what","which","because","while","just","really","very",
    "have","will","does","there","their","about","like","more","only","still",
    "even","gets","make","makes","made","over","under","also","actually","strange",
    "weird","thing","things","little","sudden","suddenly","part","time","way",
    "water","you","are","the","and","but","for","not","its","it's","can","how",
    "why","now","watch","ever","some","does",
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
    """Retention-first score with normalized growth signals."""
    latest = record.get("latest", {}) or {}
    views = max(0, int(latest.get("views", 0) or 0))
    retention = float(latest.get("average_view_percentage", 0) or 0)
    duration = float(latest.get("average_view_duration", 0) or 0)
    likes = max(0, int(latest.get("likes", 0) or 0))
    comments = max(0, int(latest.get("comments", 0) or 0))
    shares = max(0, int(latest.get("shares", 0) or 0))
    subs = max(0, int(latest.get("subscribers_gained", 0) or 0))
    retention_signal = min(100.0, retention if retention > 0 else duration * 3.0)
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


def _audio_duration(record: dict) -> float:
    """Read the actual rendered narration duration when the artifact exists."""
    workdir = str(record.get("workdir") or "").strip()
    if not workdir:
        return 0.0
    audio = Path(workdir) / "audio" / "story.mp3"
    if not audio.exists():
        return 0.0
    try:
        from moviepy.editor import AudioFileClip
        clip = AudioFileClip(str(audio))
        try:
            return max(0.0, float(clip.duration or 0.0))
        finally:
            clip.close()
    except Exception:
        return 0.0


def _creative_features(record: dict) -> dict[str, str]:
    script = _script_for(record) or {}
    scenes = [s for s in (script.get("scene_plan") or []) if isinstance(s, dict)]
    first = scenes[0] if scenes else {}
    narration = " ".join(str(s.get("narration", "")) for s in scenes)
    word_count = len(_words(narration))
    question_count = narration.count("?")
    purposes = [str(s.get("purpose", "")).strip() for s in scenes if s.get("purpose")]
    retention = [str(s.get("retention_purpose", "")).strip() for s in scenes if s.get("retention_purpose")]

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

    explanation_index = next((i for i, s in enumerate(scenes) if str(s.get("purpose")) == "explanation"), 2)
    payoff_index = next((i for i, s in enumerate(scenes) if str(s.get("retention_purpose")) == "payoff"), 5)
    duration = _audio_duration(record)
    wps = word_count / duration if duration > 0 else 0.0
    wps_bucket = "slow" if wps and wps < 2.4 else "natural" if wps <= 3.0 else "fast" if wps > 3.0 else "unknown"
    story_format = str(script.get("story_format") or "").strip() or "-".join(purposes[:7]) or "seven_scene_story"

    return {
        "topic_category": _topic_category(record.get("topic", "")),
        "hook_type": hook_type,
        "story_format": story_format[:80],
        "curiosity_pattern": "+".join(dict.fromkeys(retention[:4]))[:80] or "open_loop",
        "payoff_position": "early" if payoff_index <= 3 else "mid" if payoff_index <= 5 else "late",
        "explanation_position": "early" if explanation_index <= 1 else "mid" if explanation_index <= 3 else "late",
        "script_length": "short" if word_count < 105 else "medium" if word_count <= 135 else "long",
        "question_density": "high" if question_count >= 3 else "medium" if question_count >= 1 else "low",
        "narration_pace": wps_bucket,
        "visual_style": str((script.get("visual_identity") or {}).get("style", "")).strip()[:80] or "unknown",
        "voice": str((script.get("voice_style") or {}).get("tone", "")).strip()[:50] or "unknown",
        "engagement_experiment": str((script.get("engagement") or {}).get("experiment", "")).strip() or "none",
    }


def _topic_category(topic: str) -> str:
    text = str(topic or "").lower()
    categories = ("technology","food","clothing","home","body","car","weather","sound","kitchen","animals","space","nature","history","psychology","everyday")
    return next((x for x in categories if x in text), "everyday")


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


def _rows(records: list[dict], features: dict[str, str]) -> dict[str, list[float]]:
    out: dict[str, list[float]] = defaultdict(list)
    for record in records:
        values = _creative_features(record)
        score = _performance(record)
        key = " + ".join(f"{name}:{values.get(name)}" for name in features if values.get(name) not in (None, "", "unknown"))
        if key and all(values.get(name) not in (None, "", "unknown") for name in features):
            out[key].append(score)
    return out


def _rank(rows: dict[str, list[float]], minimum: int = 1) -> list[dict]:
    result = []
    for pattern, values in rows.items():
        if len(values) < minimum:
            continue
        result.append({"pattern": pattern, "score": round(sum(values) / len(values), 3), "sample_size": len(values)})
    return sorted(result, key=lambda x: (x["score"], x["sample_size"]), reverse=True)


def build_playbook(records: list[dict]) -> dict:
    usable = [r for r in records if isinstance(r, dict) and r.get("video_id") and isinstance(r.get("latest", {}), dict)]
    scored = sorted(((_performance(r), r) for r in usable), key=lambda x: x[0], reverse=True)
    count = len(scored)
    top_n = max(3, min(10, math.ceil(count * 0.25))) if count else 0
    winners = [r for _, r in scored[:top_n]]
    losers = [r for _, r in scored[-top_n:]] if count >= 4 else []
    has_live_metrics = any(any(float((r.get("latest", {}) or {}).get(k, 0) or 0) > 0 for k in ("views","likes","comments","average_view_percentage","subscribers_gained","shares")) for r in usable)

    isolated_features = ("hook_type","story_format","payoff_position","explanation_position","script_length","narration_pace")
    combo_features = ("hook_type","story_format","payoff_position","narration_pace")
    pair_features = ("hook_type","payoff_position")
    winning_patterns = _rank(_rows(winners, {x:x for x in isolated_features}), 2)[:40] if has_live_metrics else []
    weak_patterns = _rank(_rows(losers, {x:x for x in isolated_features}), 2)[:30] if has_live_metrics else []
    winning_combinations = _rank(_rows(winners, {x:x for x in combo_features}), 2)[:20] if has_live_metrics else []
    winning_hook_payoff_pairs = _rank(_rows(winners, {x:x for x in pair_features}), 2)[:12] if has_live_metrics else []

    topics = [_norm_topic(r.get("topic", "")) for r in usable if r.get("topic")]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "video_count": count,
        "learning_ready": count >= 3 and has_live_metrics,
        "metrics_available": has_live_metrics,
        "creative_learning_version": "v3",
        "objective": "maximize retention, sustainable views, shares and subscriber growth while preserving originality",
        "strategy": {"exploitation": EXPLOITATION, "adjacent_exploration": ADJACENT_EXPLORATION, "wild_exploration": WILD_EXPLORATION},
        "winning_patterns": winning_patterns,
        "weak_patterns": weak_patterns,
        "winning_combinations": winning_combinations,
        "winning_hook_payoff_pairs": winning_hook_payoff_pairs,
        "winning_topics": [r.get("topic", "") for r in winners if r.get("topic")][:10] if has_live_metrics else [],
        "avoid_topics": [r.get("topic", "") for r in losers if r.get("topic")][:10] if has_live_metrics else [],
        "used_topic_count": len(set(topics)),
        "rules": [
            "Learn combinations, not templates; never copy winning topics literally.",
            "Only repeated creative evidence with n>=2 is considered a proven pattern.",
            "Use one winning combination at a time so future performance remains interpretable.",
            "Use adjacent and wild exploration to avoid creative lock-in.",
            "Retention is primary; shares and subscriber conversion are stronger growth signals than likes.",
            "Use actual rendered narration duration when available to learn pacing.",
            "Reject exact repeats and near-duplicate topics before generation.",
        ],
    }


def score_candidate_topic(topic: str, playbook: dict | None = None) -> dict:
    """Backward-compatible modest topic prior."""
    pb = playbook or get_playbook()
    features = _pattern_features(topic)
    score = 0.0
    reasons: list[str] = []
    for group, sign in ((pb.get("winning_patterns", []), 1), (pb.get("weak_patterns", []), -1)):
        for row in group:
            pattern = str(row.get("pattern", ""))
            for key, value in features.items():
                if pattern == f"{key}:{value}":
                    sample = max(1, int(row.get("sample_size", 1) or 1))
                    confidence = min(1.0, sample / 3.0)
                    delta = abs(float(row.get("score", 0))) * 0.04 * confidence
                    score += sign * delta
                    reasons.append(("winner " if sign > 0 else "weak ") + pattern)
    return {"topic": topic, "score": round(score, 3), "features": features, "reasons": reasons[:8]}


def refresh_playbook() -> dict:
    records = _load(ANALYTICS_DIR / "videos.json", [])
    records = records if isinstance(records, list) else []
    current = _load(PLAYBOOK_PATH, {})
    playbook = build_playbook(records)
    if records and not playbook["metrics_available"] and isinstance(current, dict) and current.get("metrics_available"):
        current["generated_at"] = datetime.now(timezone.utc).isoformat()
        current["video_count"] = len(records)
        current["metrics_stale"] = True
        playbook = current
    _write(PLAYBOOK_PATH, playbook)
    print(f"🧠 Learning engine: {'READY' if playbook.get('learning_ready') else 'WARMING UP'}")
    print(f"🧠 Creative learning: {playbook.get('creative_learning_version', 'v1')}")
    print(f"🧠 Winning combinations: {len(playbook.get('winning_combinations', []))}")
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
