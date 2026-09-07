"""Runtime compatibility helpers for Mint-YT-Factory."""
from __future__ import annotations
import re

class AudioPath(list):
    def __init__(self, path: str): super().__init__([path])
    def __fspath__(self): return self[0]
    def __str__(self): return self[0]
    def __repr__(self): return repr(self[0])
    def endswith(self, suffix, *args): return self[0].endswith(suffix, *args)

def patch_continuation(main):
    """Hard-remove accidental model-written Scene 7 future-topic narration."""
    original = main.lock_next_topic
    if getattr(original, "_mint_scene7_continuation_guard", False):
        return

    def guarded(script, current_topic, locked_topic=None):
        scenes = script.get("scene_plan") or []
        if scenes and isinstance(scenes[-1], dict):
            scene7 = scenes[-1]
            narration = str(scene7.get("narration") or "").strip()
            # This retired/model-bleed continuation was observed in Publish Shorts.
            # Remove it before the canonical continuation is appended.
            cleaned = re.sub(
                r"(?:^|(?<=[.!?])\s+)Why\s+do\s+ice\s+cubes?\s+crack\s+in\s+water\??",
                "",
                narration,
                flags=re.IGNORECASE,
            )
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
            if cleaned != narration:
                scene7["narration"] = cleaned
                scene7["subtitle_text"] = cleaned
                print("🧹 Removed forbidden model continuation from Scene 7: ice-cube cracking")
        return original(script, current_topic, locked_topic=locked_topic)

    guarded._mint_scene7_continuation_guard = True
    main.lock_next_topic = guarded
    print("🛡️ Scene 7 continuation guard: ENABLED")

def patch_tts_result(main):
    from tts_bridge import patch
    patch(main)
    original = main.synthesize_script
    def synthesize_script(script, config, workdir):
        result = original(script, config, workdir)
        return AudioPath(str(result[0] if isinstance(result, (list, tuple)) and result else result))
    main.synthesize_script = synthesize_script
