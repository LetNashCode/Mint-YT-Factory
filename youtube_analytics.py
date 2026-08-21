"""Lightweight YouTube performance collector for Mint-YT-Factory.

This module intentionally uses the YouTube Data API first so it works with the
existing upload OAuth token. It records public performance metrics without
requiring the separate YouTube Analytics OAuth scope.

Collected metrics:
- views
- likes
- comments
- publish date
- per-video engagement rates

The registry is durable in analytics/videos.json and the optimizer-facing
summary is written to analytics/summary.json.

A later phase can add the YouTube Analytics API for retention curves once the
channel OAuth token has been authorized with yt-analytics.readonly.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parent
ANALYTICS_DIR = ROOT / "analytics"
REGISTRY_PATH = ANALYTICS_DIR / "videos.json"
SUMMARY_PATH = ANALYTICS_DIR / "summary.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _credentials() -> Credentials:
    token_json = os.environ.get("YOUTUBE_TOKEN_JSON")
    if not token_json:
        raise RuntimeError("YOUTUBE_TOKEN_JSON is missing.")
    info = json.loads(token_json)
    return Credentials.from_authorized_user_info(info)


def _youtube_service():
    return build("youtube", "v3", credentials=_credentials(), cache_discovery=False)


def fetch_video_stats(video_ids: list[str]) -> dict[str, dict]:
    """Fetch current public Data API statistics for up to 50 videos per call."""
    if not video_ids:
        return {}

    youtube = _youtube_service()
    result: dict[str, dict] = {}

    for start in range(0, len(video_ids), 50):
        batch = [x for x in video_ids[start:start + 50] if x]
        response = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(batch),
            maxResults=50,
        ).execute()

        for item in response.get("items", []):
            stats = item.get("statistics", {})
            snippet = item.get("snippet", {})
            result[item["id"]] = {
                "title": snippet.get("title", ""),
                "published_at": snippet.get("publishedAt"),
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "duration": item.get("contentDetails", {}).get("duration"),
            }

    return result


def record_upload(video_id: str, topic: str, title: str, workdir: str = "") -> None:
    """Register a newly published Short without making upload depend on analytics."""
    records = _load_json(REGISTRY_PATH, [])
    if not isinstance(records, list):
        records = []

    for record in records:
        if isinstance(record, dict) and record.get("video_id") == video_id:
            return

    records.append({
        "video_id": video_id,
        "topic": str(topic or "").strip(),
        "title": str(title or "").strip(),
        "workdir": str(workdir or "").strip(),
        "published_at": _utc_now(),
        "latest": {
            "views": 0,
            "likes": 0,
            "comments": 0,
        },
        "snapshots": [],
    })
    _write_json(REGISTRY_PATH, records)
    print(f"📊 Analytics registry: recorded {video_id}")


def _engagement_rate(views: int, likes: int, comments: int) -> float:
    if views <= 0:
        return 0.0
    return round(((likes + comments) / views) * 100, 4)


def refresh_registry() -> dict:
    """Refresh all registered videos and rebuild the optimizer summary."""
    records = _load_json(REGISTRY_PATH, [])
    if not isinstance(records, list):
        records = []

    records = [x for x in records if isinstance(x, dict) and x.get("video_id")]
    if not records:
        summary = {
            "generated_at": _utc_now(),
            "video_count": 0,
            "optimization_ready": False,
            "reason": "Need at least 3 published videos before optimizing content.",
            "totals": {"views": 0, "likes": 0, "comments": 0},
            "averages": {"views": 0, "likes": 0, "comments": 0, "engagement_rate": 0},
            "top_videos": [],
            "topic_performance": [],
        }
        _write_json(SUMMARY_PATH, summary)
        return summary

    stats = fetch_video_stats([str(x["video_id"]) for x in records])
    now = _utc_now()

    for record in records:
        video_id = str(record["video_id"])
        current = stats.get(video_id)
        if not current:
            continue

        record["title"] = current.get("title") or record.get("title", "")
        record["published_at"] = current.get("published_at") or record.get("published_at")
        latest = {
            "views": int(current.get("views", 0)),
            "likes": int(current.get("likes", 0)),
            "comments": int(current.get("comments", 0)),
            "engagement_rate": _engagement_rate(
                int(current.get("views", 0)),
                int(current.get("likes", 0)),
                int(current.get("comments", 0)),
            ),
            "checked_at": now,
        }
        record["latest"] = latest
        snapshots = record.get("snapshots", [])
        if not isinstance(snapshots, list):
            snapshots = []
        snapshots.append(latest)
        # Keep the registry compact while preserving the trend history.
        record["snapshots"] = snapshots[-30:]

    _write_json(REGISTRY_PATH, records)

    totals = {
        "views": sum(int(x.get("latest", {}).get("views", 0)) for x in records),
        "likes": sum(int(x.get("latest", {}).get("likes", 0)) for x in records),
        "comments": sum(int(x.get("latest", {}).get("comments", 0)) for x in records),
    }
    count = len(records)
    avg_views = totals["views"] / count if count else 0
    avg_likes = totals["likes"] / count if count else 0
    avg_comments = totals["comments"] / count if count else 0
    avg_engagement = (
        sum(float(x.get("latest", {}).get("engagement_rate", 0)) for x in records) / count
        if count else 0
    )

    ranked = sorted(
        records,
        key=lambda x: int(x.get("latest", {}).get("views", 0)),
        reverse=True,
    )

    topic_rows = []
    for record in ranked:
        topic_rows.append({
            "topic": str(record.get("topic", "")).strip(),
            "video_id": record.get("video_id"),
            "title": record.get("title", ""),
            "views": int(record.get("latest", {}).get("views", 0)),
            "likes": int(record.get("latest", {}).get("likes", 0)),
            "comments": int(record.get("latest", {}).get("comments", 0)),
            "engagement_rate": float(record.get("latest", {}).get("engagement_rate", 0)),
        })

    optimization_ready = count >= 3
    summary = {
        "generated_at": now,
        "video_count": count,
        "optimization_ready": optimization_ready,
        "reason": "" if optimization_ready else "Need at least 3 published videos before optimizing content.",
        "totals": totals,
        "averages": {
            "views": round(avg_views, 2),
            "likes": round(avg_likes, 2),
            "comments": round(avg_comments, 2),
            "engagement_rate": round(avg_engagement, 4),
        },
        "top_videos": topic_rows[:10],
        "topic_performance": topic_rows[:20],
        "optimization_rules": [
            "Do not copy a winning topic literally; learn the pattern behind it.",
            "Favor concrete everyday mysteries over broad academic subjects.",
            "Prefer hooks that create an immediate curiosity gap.",
            "Do not sacrifice story quality merely to chase views.",
        ] if optimization_ready else [],
    }
    _write_json(SUMMARY_PATH, summary)

    print("=" * 80)
    print("📊 YOUTUBE PERFORMANCE REFRESH")
    print("=" * 80)
    print(f"Tracked videos: {count}")
    print(f"Total views: {totals['views']:,}")
    print(f"Average views/video: {avg_views:,.0f}")
    print(f"Optimization ready: {'YES' if optimization_ready else 'NO'}")
    print(f"Saved: {SUMMARY_PATH}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    if not args.refresh:
        parser.error("Use --refresh")
    refresh_registry()


if __name__ == "__main__":
    main()
