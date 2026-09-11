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
    """Make Publish continuation production-owned and transactional."""
    original_lock = main.lock_next_topic
    if getattr(original_lock, "_mint_scene7_continuation_guard", False):
        return

    import topics

    def _clean(value):
        return topics._clean_topic(value)

    def _validate_and_hold(next_topic, current_topic):
        candidate = _clean(next_topic)
        raw_items = topics._read_used()
        committed = [
            x for x in raw_items
            if not (isinstance(x, str) and x.startswith(topics._PENDING_PREFIX))
        ]
        used = [current_topic]
        used.extend(committed)
        if not topics.validate_topic_for_pipeline(candidate, used=used, check_duplicate=True):
            candidate = topics._generate_topic(used)
            print(f"🛠️ Repaired invalid continuation topic without persisting early: {candidate}")
        if not candidate:
            raise RuntimeError("Continuation topic is empty.")
        if len(candidate.split()) > 7:
            raise RuntimeError(f"Generated next topic is too long: {candidate}")
        main._mint_reserved_next_topic = candidate
        print(f"🔐 Continuation topic held until YouTube publication: {candidate}")
        return candidate

    def guarded_reserve(next_short, current_topic=""):
        return _validate_and_hold(next_short, current_topic)

    def deferred_save(next_short):
        candidate = _clean(next_short)
        held = str(getattr(main, "_mint_reserved_next_topic", "") or "").strip()
        if held and topics._key(candidate) != topics._key(held):
            raise RuntimeError(
                f"Publish continuation changed before publication: {candidate!r} != {held!r}"
            )
        main._mint_reserved_next_topic = candidate or held
        print(f"🔗 Continuation queued in memory; waiting for atomic publication commit: {main._mint_reserved_next_topic}")
        return main._mint_reserved_next_topic

    def atomic_commit(topic):
        current = _clean(topic)
        next_topic = _clean(getattr(main, "_mint_reserved_next_topic", ""))
        if not next_topic:
            raise RuntimeError("Refusing to commit Publish Shorts topic without a locked continuation topic.")

        raw_items = topics._read_used()
        committed = [
            x for x in raw_items
            if not (isinstance(x, str) and x.startswith(topics._PENDING_PREFIX))
        ]
        current_key = topics._key(current)
        if not any(topics._key(x) == current_key for x in committed):
            committed.append(current)

        # Validate the successor against the final committed state and then write
        # current + exact successor in ONE atomic used_topics.json replacement.
        if not topics.validate_topic_for_pipeline(
            next_topic,
            used=[current] + committed,
            check_duplicate=True,
        ):
            raise RuntimeError(f"Locked continuation became invalid before commit: {next_topic}")
        committed.append(topics._PENDING_PREFIX + next_topic)
        topics._write_used(committed)
        print(f"📌 Atomic topic progression committed: current={current} | next={next_topic}")
        main._mint_reserved_next_topic = ""
        return True

    # IMPORTANT: reserve_next_short is called before TTS/stock/render/upload.
    # It must not publish the successor into persistent topic state yet, otherwise
    # a failed render can make the following run skip the unpublished current topic.
    main.reserve_next_short = guarded_reserve
    main.save_next_short = deferred_save
    main.commit_topic = atomic_commit

    def guarded(script, current_topic, locked_topic=None):
        scenes = script.get("scene_plan") or []
        if scenes and isinstance(scenes[-1], dict):
            scene7 = scenes[-1]
            narration = str(scene7.get("narration") or "").strip()
            # Remove only the specific legacy/model continuation observed in Publish Shorts.
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
        result = original_lock(script, current_topic, locked_topic=locked_topic)
        locked = str((result[0].get("next_short") or {}).get("topic") or "").strip() if isinstance(result, tuple) else ""
        held = str(getattr(main, "_mint_reserved_next_topic", "") or "").strip()
        if held and locked and topics._key(held) != topics._key(locked):
            raise RuntimeError(f"Canonical continuation changed: held={held!r} locked={locked!r}")
        return result

    guarded._mint_scene7_continuation_guard = True
    main.lock_next_topic = guarded
    main._mint_reserved_next_topic = ""
    print("🛡️ Scene 7 continuation guard: ENABLED | successor persistence deferred until successful YouTube publication")

def patch_tts_result(main):
    from tts_bridge import patch
    patch(main)
    original = main.synthesize_script
    def synthesize_script(script, config, workdir):
        result = original(script, config, workdir)
        return AudioPath(str(result[0] if isinstance(result, (list, tuple)) and result else result))
    main.synthesize_script = synthesize_script
