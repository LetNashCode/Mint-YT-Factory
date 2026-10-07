from __future__ import annotations

import json
from pathlib import Path

import yaml

from portrait_export_guard import ensure_portrait_export
from upload_youtube import upload_video


def main() -> None:
    candidates = sorted(
        Path("output").glob("*/final.mp4"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        print("Curious upload rescue: no final.mp4 found.")
        return

    video = candidates[0]
    workdir = video.parent
    script_path = workdir / "script.json"
    state_path = workdir / "publish_state.json"

    if not script_path.exists():
        print("Curious upload rescue: script.json missing.")
        return

    script = json.loads(script_path.read_text(encoding="utf-8"))
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    if state.get("video_id") or state.get("uploaded"):
        print("Curious upload rescue: YouTube already published.")
        return

    config = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8"))
    config["upload"] = dict(config.get("upload") or {})
    config["upload"]["auto_upload"] = True
    config["upload"]["privacy_status"] = "public"
    config["seo"] = dict(config.get("seo") or {})
    config["seo"]["hashtags"] = ["shorts", "curious", "facts", "science", "knowledge", "mintfever"]

    title = str(script.get("title") or script.get("topic") or "Curious Short").strip()[:70]
    description = str(
        script.get("description")
        or (str(script.get("topic") or "").strip() + "\n\nFollow Mint Fever for more curious everyday stories.")
    ).strip()

    thumbnail = workdir / "thumbnail.jpg"
    thumbnail_path = str(thumbnail) if thumbnail.exists() else None

    final_video = str(ensure_portrait_export(str(video)))
    video_id = upload_video(
        final_video,
        title,
        description,
        config,
        thumbnail_path=thumbnail_path,
    )

    state.update(
        {
            "status": "youtube_published",
            "uploaded": True,
            "video_id": video_id,
            "topic": script.get("topic", ""),
        }
    )
    state_path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"CURIOUS YOUTUBE UPLOAD RESCUE COMPLETE | {video_id}")


if __name__ == "__main__":
    main()
