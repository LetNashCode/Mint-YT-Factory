"""Single-pass Publish Shorts narration protection.

The Publish pipeline must synthesize the complete narration with one provider and
one voice. Older versions synthesized the core narration and Scene 7 bridge in
separate TTS passes, which could create an audible narrator/prosody jump even
when both passes were configured with the same voice.
"""
from __future__ import annotations

import os

MAX_FINAL_NARRATION_SECONDS = 44.50


def _clean(value):
    import re
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _split(script):
    scenes = script.get("scene_plan") or []
    full = _clean(
        " ".join(
            str(s.get("narration", ""))
            for s in scenes
            if isinstance(s, dict)
        )
    )
    bridge = _clean((script.get("next_short") or {}).get("teaser", ""))
    return (full[:-len(bridge)].rstrip(), bridge) if bridge and full.endswith(bridge) else (full, "")


def patch(main):
    original = main.synthesize_script
    if getattr(original, "_mint_bridge_protected", False):
        return

    def synthesize(script, config, workdir):
        import tts

        scenes = script.get("scene_plan") or []
        narration = _clean(
            " ".join(
                str(s.get("narration", ""))
                for s in scenes
                if isinstance(s, dict)
            )
        )
        if not narration:
            return original(script, config, workdir)

        os.makedirs(workdir, exist_ok=True)
        final_path = os.path.join(workdir, "story.mp3")
        voice = config.get("voice", {}) if isinstance(config, dict) else {}

        print(
            "🔒 Publish narration single-pass lock | "
            f"provider={voice.get('provider', 'kokoro')} | "
            f"voice={voice.get('voice_name', tts.KOKORO_VOICE)} | "
            f"words={len(narration.split())}"
        )

        # CRITICAL: synthesize the COMPLETE narration in one provider/voice pass.
        # Do not synthesize the current-topic core and continuation bridge
        # independently; that can produce an audible narrator/prosody change.
        tts.synthesize_narration(
            narration,
            config,
            final_path,
            target_duration=MAX_FINAL_NARRATION_SECONDS,
        )
        print(
            "🔒 Publish narration single-pass complete | "
            f"voice={voice.get('voice_name', tts.KOKORO_VOICE)}"
        )
        return final_path

    synthesize._mint_bridge_protected = True
    main.synthesize_script = synthesize
