"""Recover and publish a completed Story render restored from a prior workflow artifact."""
from __future__ import annotations
import glob, json, os, sys
from interactive_main import load_config, _title, save
from upload_youtube import upload_video\nimport story_visual_upgrade
from social_publish import publish_social_reels
from interactive_topics import record_topic
from interactive_analytics import record as record_analytics
from publication_state import save as save_publication_state


def _load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return default


def _already_recorded(person):
    history = _load("story_topic_history.json", []) or []
    return any(str(x.get("person", "")).strip().casefold() == str(person).strip().casefold() for x in history if isinstance(x, dict))


def recover() -> bool:
    candidates = []
    for manifest_path in glob.glob("output/interactive/*/render_manifest.json"):
        manifest = _load(manifest_path, {}) or {}
        if manifest.get("status") != "complete":
            continue
        workdir = os.path.dirname(manifest_path)
        script_path = os.path.join(workdir, "script.json")
        script = _load(script_path, {}) or {}
        final = os.path.join(workdir, "final.mp4")
        person = manifest.get("person") or script.get("story_person")
        if not person or not os.path.isfile(final) or os.path.getsize(final) <= 0 or _already_recorded(person):
            continue
        candidates.append((os.path.getmtime(manifest_path), workdir, script, final, person))
    if not candidates:
        return False
    _, workdir, script, final, person = sorted(candidates, reverse=True)[0]
    pillar = script.get("interactive_pillar") or "impossible_odds"
    topic = script.get("topic") or f"The story of {person}"
    # Recovery must re-run the exact same final quality gate immediately before
    # publication. The render manifest is checkpointed before this point in the
    # normal pipeline, so a crash can leave a complete-looking render that was
    # never quality-validated.
    from final_video_quality_gate import validate as validate_final_render
    validate_final_render(final)
    print(f"✅ Recovered Story final quality gate passed: {final}")
    from story_youtube_metadata import build_story_metadata
    title, description, story_tags = build_story_metadata(script)
    description += story_visual_upgrade.source_credits() if "story_visual_upgrade" in globals() else ""
    engagement = (script.get("engagement") or {}).get("comment") or f"What would you have done in {person}'s situation? 👇"
    config = dict(load_config() or {})
    seo = dict(config.get("seo") or {})
    seo["hashtags"] = ["storyshorts", "truestory", "inspiration", "shorts"]
    config["seo"] = seo
    upload = dict(config.get("upload") or {})
    upload["_youtube_tags"] = list(story_tags)
    config["upload"] = upload
    result = upload_video(final, title, description, config, engagement_comment=engagement)
    video_id = result if isinstance(result, str) else str(result.get("video_id") or result.get("id") or "") if isinstance(result, dict) else ""
    if not video_id:
        save_publication_state(".story_publication_status.json", {"status": "upload_failed", "video_id": "", "reason": "Recovered Story render upload returned no video ID"})
        raise RuntimeError("Recovered Story render upload returned no video ID")
    save_publication_state(".story_publication_status.json", {
        "status": "youtube_uploaded",
        "video_id": video_id,
        "youtube_url": f"https://www.youtube.com/shorts/{video_id}",
    })
    social = publish_social_reels(final, title, description, config, workdir)
    required = ("instagram", "facebook")
    failures = [name for name in required if not isinstance((social or {}).get(name), dict) or str((social or {})[name].get("status", "")).lower() != "published"]
    if failures:
        queue = {
            "schema_version": 1,
            "run_id": str(os.environ.get("GITHUB_RUN_ID") or ""),
            "artifact_name": f"story-shorts-{os.environ.get('GITHUB_RUN_ID','')}",
            "workdir": workdir,
            "final_relative": os.path.relpath(final, "."),
            "video_id": video_id,
            "topic": topic,
            "pillar": pillar,
            "person": person,
            "number": int(script.get("story_number") or 0),
            "title": title,
            "description": description,
        }
        with open("story_social_queue.json", "w", encoding="utf-8") as handle:
            json.dump(queue, handle, indent=2, ensure_ascii=False)
        save_publication_state(".story_publication_status.json", {
            "status": "social_failed",
            "video_id": video_id,
            "youtube_url": f"https://www.youtube.com/shorts/{video_id}",
            "reason": "Failed social destinations: " + ", ".join(failures),
        })
        raise RuntimeError("Recovered Story social publishing failed: " + ", ".join(failures))
    record_topic(topic, pillar, title, video_id, workdir, person=person)
    save(script, os.path.join(workdir, "script.json"))
    record_analytics(video_id, topic, pillar, title, workdir, person=person)
    save_publication_state(".story_publication_status.json", {
        "status": "complete",
        "video_id": video_id,
        "youtube_url": f"https://www.youtube.com/shorts/{video_id}",
        "platforms": {
            "youtube": {"status": "published", "video_id": video_id},
            "instagram": dict(social.get("instagram") or {}),
            "facebook": dict(social.get("facebook") or {}),
        },
    })
    print(f"♻️ Recovered and published completed Story render: {final}")
    return True


if __name__ == "__main__":
    # Exit 0 only when recovery completed publication, 1 when no recovery
    # candidate exists, and 2 for an actual recovery/publication failure.
    try:
        recovered = recover()
    except Exception as exc:
        print(f"❌ Story render recovery failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
    sys.exit(0 if recovered else 1)
