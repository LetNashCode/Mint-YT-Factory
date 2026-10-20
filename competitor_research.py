"""Best-effort public YouTube outlier research for Publish Shorts topic ideation.

No login, cookies, channel credentials, or downloads are used. Research is
bounded and optional: topic generation continues normally when search fails.
"""
from __future__ import annotations

from publish_short_intelligence import competitor_outlier_brief


SEARCHES = (
    "why everyday things happen",
    "everyday mysteries explained",
    "things you never noticed everyday objects",
)


def collect_competitor_outliers(max_results_per_query: int = 18) -> list[dict]:
    try:
        from yt_dlp import YoutubeDL
    except Exception as exc:
        print(f"ℹ️ Public competitor research unavailable: {type(exc).__name__}")
        return []

    entries = []
    seen = set()
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "ignoreerrors": True,
        "extract_flat": False,
        "socket_timeout": 6,
        "retries": 0,
        "playlistend": max(4, min(int(max_results_per_query), 25)),
    }
    for query in SEARCHES:
        try:
            with YoutubeDL(options) as ydl:
                result = ydl.extract_info(f"ytsearch{options['playlistend']}:{query}", download=False)
            for entry in (result or {}).get("entries") or []:
                if not isinstance(entry, dict):
                    continue
                video_id = str(entry.get("id") or "").strip()
                if not video_id or video_id in seen:
                    continue
                seen.add(video_id)
                channel = str(entry.get("channel") or entry.get("uploader") or "").strip()
                title = str(entry.get("title") or "").strip()
                try:
                    views = int(entry.get("view_count") or 0)
                except (TypeError, ValueError):
                    views = 0
                if channel and title and views > 0:
                    entries.append({"id": video_id, "channel": channel, "title": title, "view_count": views})
        except Exception as exc:
            print(f"ℹ️ Public competitor search skipped ({query}): {type(exc).__name__}")
    ranked = competitor_outlier_brief(entries, min_channel_videos=4)
    if ranked:
        print(f"🔎 Competitor research found {len(ranked)} channel-relative outliers from {len(entries)} public videos")
    else:
        print(f"ℹ️ Competitor research had insufficient same-channel samples ({len(entries)} public videos); continuing without it")
    return ranked
