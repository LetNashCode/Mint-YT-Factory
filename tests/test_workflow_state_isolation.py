import json
import os
import subprocess
import sys


def _profile_paths(profile):
    env = os.environ.copy()
    env["MINT_WORKFLOW_PROFILE"] = profile
    code = """
import json
from pathlib import Path
import factory_content_memory as memory
import learning_context as context
import learning_engine as engine
import topic_history as topics
import youtube_analytics as analytics
root = Path.cwd()
print(json.dumps({
    "memory": str(memory.HISTORY.relative_to(root)),
    "memory_state": str(memory.BOOTSTRAP_STATE.relative_to(root)),
    "learning_analytics": str(engine.ANALYTICS_DIR.relative_to(root)),
    "learning_playbook": str(context.PLAYBOOK.relative_to(root)),
    "analytics_registry": str(analytics.REGISTRY_PATH.relative_to(root)),
    "analytics_used_topics": str(analytics.USED_TOPICS_PATH.relative_to(root)),
    "topic_history": str(topics._HISTORY_PATH.relative_to(root)),
}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_story_profile_uses_only_story_state_paths():
    paths = _profile_paths("story")
    assert paths == {
        "memory": "analytics/story/topic_history.json",
        "memory_state": "analytics/story/factory_memory_state.json",
        "learning_analytics": "analytics/story",
        "learning_playbook": "analytics/story/playbook.json",
        "analytics_registry": "analytics/story/videos.json",
        "analytics_used_topics": "analytics/story/used_topics.json",
        "topic_history": "analytics/story/topic_history.json",
    }


def test_publish_profile_keeps_legacy_publish_state_paths():
    paths = _profile_paths("publish")
    assert paths == {
        "memory": "analytics/topic_history.json",
        "memory_state": "analytics/factory_memory_state.json",
        "learning_analytics": "analytics",
        "learning_playbook": "analytics/playbook.json",
        "analytics_registry": "analytics/videos.json",
        "analytics_used_topics": "used_topics.json",
        "topic_history": "analytics/topic_history.json",
    }
