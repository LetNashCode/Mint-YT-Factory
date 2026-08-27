"""Runtime compatibility helpers for Mint-YT-Factory.

Continuation ownership lives in main.py. This module must never replace the
canonical continuation lock with an older validator, because doing so can
reintroduce stale Scene 7 teaser failures.
"""
from __future__ import annotations


class AudioPath(list):
    def __init__(self, path: str):
        super().__init__([path])

    def __fspath__(self):
        return self[0]

    def __str__(self):
        return self[0]

    def __repr__(self):
        return repr(self[0])

    def endswith(self, suffix, *args):
        return self[0].endswith(suffix, *args)


def patch_continuation(main):
    """Do not override main.lock_next_topic.

    main.py already owns canonical-topic locking, Scene 7 cleanup, and the
    deterministic natural bridge. The previous override was stale and could
    reject valid scripts after main.py had already repaired them.
    """
    print("🛡️ Continuation runtime override: DISABLED; using main.py canonical lock")


def patch_tts_result(main):
    """Keep the historical AudioPath compatibility wrapper."""
    original = main.synthesize_script

    def synthesize_script(script, config, workdir):
        result = original(script, config, workdir)
        return AudioPath(str(result[0] if isinstance(result, (list, tuple)) and result else result))

    main.synthesize_script = synthesize_script
