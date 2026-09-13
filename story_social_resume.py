"""Resume Story Shorts social publishing from a durable GitHub Actions artifact."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from interactive_analytics import record as record_analytics
from interactive_topics import record_topic, save_pending_story, _load_history
from social_publish import publish_social_reels

QUEUE = Path("story_social_queue.json")


def _load_queue() -> dict | None:
    if not QUEUE.is_file():
        return None
    try:
        data = json.loads(QUEUE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and data.get("video_id") and data.get("run_id") else None
    except Exception as exc:
        raise RuntimeError(f"Invalid Story social queue: {exc}") from exc


def _find_final(root: Path) -> Path:
    matches = list(root.rglob("final.mp4"))
    if not matches:
        raise RuntimeError(f"Recovered Story artifact contains no final.mp4: {root}")
    matches.sort(key=lambda p: p.stat().st_size, reverse=True)
    return matches[0]


def _already_recorded(video_id: str) -> bool:
    for row in _load_history():
        if isinstance(row, dict) and str(row.get("video_id") or "") == str(video_id):
            return True
    return False


def main() -> int:
    queue = _load_queue()
    if not queue:
        print("ℹ️ No durable Story social queue; starting a new Story Short.")
        return 0

    run_id = str(queue["run_id"])
    artifact = str(queue.get("artifact_name") or f"story-shorts-{run_id}")
    if not os.environ.get("GH_TOKEN"):
        raise RuntimeError("GH_TOKEN is required to recover a pending Story social artifact.")

    root = Path(tempfile.mkdtemp(prefix="story-social-resume-"))
    try:
        print(f"♻️ RESUMING STORY SOCIAL PUBLISH | YouTube={queue['video_id']} | source run={run_id}")
        command = ["gh", "run", "download", run_id, "-R", os.environ.get("GITHUB_REPOSITORY", "LetNashCode/Mint-YT-Factory"), "-n", artifact, "-D", str(root)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError("Could not download pending Story artifact: " + (result.stderr or result.stdout)[-2000:])
        final = _find_final(root)

        with open("config.yaml", encoding="utf-8") as handle:
            config = dict(yaml.safe_load(handle) or {})
        social = publish_social_reels(final, str(queue.get("title") or ""), str(queue.get("description") or ""), config, str(final.parent))
        failures = [name for name, payload in social.items() if isinstance(payload, dict) and str(payload.get("status") or "").lower() == "failed"]
        if failures:
            raise RuntimeError("Story social resume still has failed destinations: " + ", ".join(failures))

        video_id = str(queue["video_id"])
        if not _already_recorded(video_id):
            record_topic(str(queue.get("topic") or ""), str(queue.get("pillar") or ""), str(queue.get("title") or ""), video_id, str(queue.get("workdir") or ""), person=str(queue.get("person") or ""))
            save_pending_story(str(queue.get("pillar") or ""), str(queue.get("topic") or ""), str(queue.get("person") or ""), int(queue.get("number") or 0))
            record_analytics(video_id, str(queue.get("topic") or ""), str(queue.get("pillar") or ""), str(queue.get("title") or ""), str(queue.get("workdir") or ""), person=str(queue.get("person") or ""))
            print("📊 Recovered Story analytics/state recorded.")
        else:
            print("ℹ️ Story sequence already recorded; no duplicate state written.")

        QUEUE.unlink(missing_ok=True)
        print("✅ Story social queue completed; no new Story generated in this run.")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
