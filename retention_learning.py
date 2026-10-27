"""Retention-driven, workflow-isolated guidance for the next script generation."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATHS = {
    "publish": ROOT / "analytics" / "videos.json",
    "story": ROOT / "analytics" / "story_videos.json",
    "wisdom": ROOT / "analytics" / "everyday_wisdom" / "videos.json",
}
TARGET_APV = 70.0
MIN_VIEWS = 50
MIN_MATURE_VIDEOS = 5


def _load(path: Path):
    try:
        value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        return value if isinstance(value, list) else []
    except (OSError, ValueError, TypeError):
        return []


def _dt(value):
    try:
        result = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except (TypeError, ValueError):
        return None


def _mature_rows(records, now=None):
    now = now or datetime.now(timezone.utc)
    eligible = []
    for record in records:
        if not isinstance(record, dict):
            continue
        latest = record.get("latest") or {}
        if not isinstance(latest, dict):
            continue
        try:
            apv = float(latest.get("average_view_percentage") or 0)
            views = int(latest.get("analytics_views") or latest.get("views") or 0)
        except (TypeError, ValueError):
            continue
        published = _dt(record.get("published_at"))
        checked = _dt(latest.get("checked_at"))
        if apv <= 0 or views < MIN_VIEWS or published is None or checked is None:
            continue
        age_hours = (now - published.astimezone(timezone.utc)).total_seconds() / 3600
        metric_age = (now - checked.astimezone(timezone.utc)).total_seconds() / 3600
        if age_hours < 24 or metric_age < 0 or metric_age > 72:
            continue
        eligible.append({
            "title": str(record.get("title") or "")[:100],
            "topic": str(record.get("topic") or "")[:120],
            "apv": apv,
            "views": views,
            "duration": float(latest.get("average_view_duration") or 0),
            "hook": str(record.get("hook_text") or record.get("opening_hook") or "")[:180],
            "hook_type": str(record.get("hook_type") or record.get("hook_mechanism") or ""),
            "structure": str(record.get("story_format") or record.get("interactive_pillar") or record.get("creative_strategy") or ""),
            "payoff": str(record.get("payoff_type") or ""),
        })
    return eligible


def build_retention_guidance(profile: str, records=None) -> str:
    """Return concise evidence-based prompt guidance; fail open if data is thin."""
    profile = str(profile or "publish").strip().lower()
    if profile in {"everyday_wisdom", "wisdom_shorts"}:
        profile = "wisdom"
    if profile not in PATHS:
        profile = "publish"
    rows = _mature_rows(records if records is not None else _load(PATHS[profile]))
    if len(rows) < MIN_MATURE_VIDEOS:
        return (
            f"RETENTION LEARNING ({profile}): warming up; only {len(rows)} mature, "
            f"usable videos are available (need {MIN_MATURE_VIDEOS}). Do not infer winners "
            "from thin data. Write an original script with a concrete opening, steady "
            "information progression, and a satisfying payoff."
        )
    rows.sort(key=lambda row: row["apv"], reverse=True)
    cohort = max(2, min(3, len(rows) // 3))
    winners, weaker = rows[:cohort], rows[-cohort:]
    avg = sum(row["apv"] for row in rows) / len(rows)
    lines = [
        f"RETENTION LEARNING — {profile.upper()} WORKFLOW ONLY",
        f"Mature videos with fresh retention data: {len(rows)}; average viewed: {avg:.1f}%; target: {TARGET_APV:.0f}% APV.",
        "Treat these as correlations, not proof of causation. Compare similar lengths/topics where possible.",
        "HIGHER-RETENTION EXAMPLES (learn the structure; never copy topic or wording):",
    ]
    for row in winners:
        detail = f"{row['apv']:.1f}% APV, {row['views']} views"
        creative = ", ".join(x for x in (row["hook_type"], row["structure"], row["payoff"]) if x)
        lines.append(f"- {row['title'] or row['topic']}: {detail}" + (f"; creative={creative}" if creative else "") + (f"; hook={row['hook']}" if row["hook"] else ""))
    lines.append("LOWER-RETENTION EXAMPLES (look for fixable weaknesses, do not automatically ban a topic):")
    for row in weaker:
        detail = f"{row['apv']:.1f}% APV, {row['views']} views"
        creative = ", ".join(x for x in (row["hook_type"], row["structure"], row["payoff"]) if x)
        lines.append(f"- {row['title'] or row['topic']}: {detail}" + (f"; creative={creative}" if creative else "") + (f"; hook={row['hook']}" if row["hook"] else ""))
    lines += [
        "ADAPT THIS SCRIPT:",
        "- Make the first spoken sentence concrete and immediately relevant; avoid generic introductions.",
        "- Establish an information gap, then deliver meaningful new information throughout the middle.",
        "- Remove repeated explanations and filler; make the payoff clear and earned.",
        "- Prefer a pattern only when the topic naturally supports it; keep the topic, wording, and examples original.",
        "- Preserve this workflow's format rules and factual accuracy.",
        "- Explore a different approach when evidence is mixed; do not overfit to one video.",
    ]
    return "\n".join(lines)
