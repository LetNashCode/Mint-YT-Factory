"""Recover and publish a completed Story render restored from a prior workflow artifact."""
from __future__ import annotations
import glob, json, os
from interactive_main import load_config, _title, save
from upload_youtube import upload_video
from social_publish import publish_social_reels
from interactive_topics import record_topic
from interactive_analytics import record as record_analytics


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
    number = int(script.get("story_number") or 0)
    title = _title(pillar, person)
    description = f"A remarkable true story about {person} — the struggle, turning point, and moment that changed everything.\n\nWhat would you have done in {person}'s situation? 👇\n\nSubscribe and follow for more powerful stories about people who faced setbacks, made difficult choices, and changed their lives.\n\n#StoryShorts #TrueStory #Inspiration #Shorts"
    engagement = (script.get("engagement") or {}).get("comment") or f"What would you have done in {person}'s situation? 👇"
    config = dict(load_config() or {})
    result = upload_video(final, title, description, config, engagement_comment=engagement)
    video_id = result if isinstance(result, str) else str(result.get("video_id") or result.get("id") or "") if isinstance(result, dict) else ""
    if not video_id:
        raise RuntimeError("Recovered Story render upload returned no video ID")
    social = publish_social_reels(final, title, description, config, workdir)
    if any(isinstance(v, dict) and str(v.get("status", "")).lower() == "failed" for v in (social or {}).values()):
        print("⚠️ Recovered Story video uploaded to YouTube, but one or more social uploads failed")
    record_topic(topic, pillar, title, video_id, workdir, person=person)
    save(script, os.path.join(workdir, "script.json"))
    record_analytics(video_id, topic, pillar, title, workdir, person=person)
    print(f"♻️ Recovered and published completed Story render: {final}")
    return True


if __name__ == "__main__":
    recover()
