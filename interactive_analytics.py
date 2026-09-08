from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATH = ROOT / "analytics" / "interactive_videos.json"
REPORT = ROOT / "analytics" / "interactive_comparison.json"


def _load(p, d):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return d


def _write(p, x):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def record(video_id, topic, pillar, title, workdir=""):
    rows = _load(PATH, [])
    rows = rows if isinstance(rows, list) else []
    if not any(isinstance(x, dict) and x.get("video_id") == video_id for x in rows):
        rows.append({
            "video_id": video_id,
            "topic": topic,
            "pillar": pillar,
            "title": title,
            "workdir": workdir,
            "latest": {},
            "snapshots": [],
        })
    _write(PATH, rows)


def refresh_live_metrics():
    """Pull current YouTube metrics into the independent riddle registry.

    This deliberately reuses the existing YouTube collector instead of creating a
    second analytics API implementation. Failures are non-fatal: creative selection
    can continue from durable history until live metrics become available.
    """
    rows = _load(PATH, [])
    rows = rows if isinstance(rows, list) else []
    ids = [str(x.get("video_id")) for x in rows if isinstance(x, dict) and x.get("video_id")]
    if not ids:
        return False
    try:
        from youtube_analytics import fetch_video_stats, fetch_analytics_metrics
        basic = fetch_video_stats(ids)
        advanced = fetch_analytics_metrics(ids)
    except Exception as exc:
        print(f"⚠️ Riddle analytics refresh unavailable: {exc}")
        return False

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        if not isinstance(row, dict):
            continue
        vid = str(row.get("video_id", ""))
        if vid not in basic:
            continue
        b = basic[vid]
        latest = {
            "views": int(b.get("views", 0)),
            "likes": int(b.get("likes", 0)),
            "comments": int(b.get("comments", 0)),
            "engagement_rate": round(((int(b.get("likes", 0)) + int(b.get("comments", 0))) / int(b.get("views", 0))) * 100, 4) if int(b.get("views", 0)) else 0.0,
            "checked_at": now,
        }
        latest.update(advanced.get(vid, {}))
        row["latest"] = latest
        snapshots = row.get("snapshots", [])
        snapshots = snapshots if isinstance(snapshots, list) else []
        snapshots.append(latest)
        row["snapshots"] = snapshots[-60:]
    _write(PATH, rows)
    build_comparison()
    print(f"📊 Riddle analytics refreshed: {len(ids)} videos")
    return True


def build_comparison():
    current = _load(ROOT / "analytics" / "videos.json", [])
    interactive = _load(PATH, [])
    groups = {"publish_shorts": current if isinstance(current, list) else []}
    for x in interactive if isinstance(interactive, list) else []:
        if isinstance(x, dict):
            groups.setdefault(x.get("pillar", "riddles"), []).append(x)

    out = {}
    for k, rows in groups.items():
        metrics = [x.get("latest", {}) for x in rows if isinstance(x, dict)]
        n = len(rows)

        def avg(name):
            return round(sum(float(m.get(name, 0) or 0) for m in metrics) / len(metrics), 2) if metrics else 0

        out[k] = {
            "videos": n,
            "avg_views": avg("views"),
            "avg_comments": avg("comments"),
            "avg_shares": avg("shares"),
            "avg_likes": avg("likes"),
            "avg_view_percentage": avg("average_view_percentage"),
        }
    _write(REPORT, out)
    return out
