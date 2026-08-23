# Mint-YT-Factory learning loop

The factory learns from every published Short.

## Loop

1. Publish a Short and record its production metadata.
2. Refresh YouTube performance snapshots.
3. Build `analytics/playbook.json` from observed winners/losers.
4. Feed the playbook into topic/script generation.
5. Reject exact and near-duplicate topics.
6. Keep a 70/20/10 exploitation/adjacent-experiment/wild-experiment mix.

The learning engine never copies a winning topic. It learns the underlying pattern.

## Important

`youtube_analytics.py` uses the existing YouTube OAuth token. Basic video statistics work with the current upload credential. Retention and subscriber metrics require the YouTube Analytics API scope `yt-analytics.readonly`; when that scope is unavailable, the collector keeps the fields at zero instead of inventing data.
