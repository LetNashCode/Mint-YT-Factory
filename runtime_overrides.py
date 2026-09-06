"""Runtime compatibility helpers for Mint-YT-Factory."""
from __future__ import annotations

class AudioPath(list):
    def __init__(self, path: str): super().__init__([path])
    def __fspath__(self): return self[0]
    def __str__(self): return self[0]
    def __repr__(self): return repr(self[0])
    def endswith(self, suffix, *args): return self[0].endswith(suffix, *args)

def patch_continuation(main):
    print("Continuation runtime override disabled; using main.py canonical lock")

def patch_tts_result(main):
    from tts_bridge import patch
    patch(main)
    original = main.synthesize_script
    def synthesize_script(script, config, workdir):
        result = original(script, config, workdir)
        return AudioPath(str(result[0] if isinstance(result, (list, tuple)) and result else result))
    main.synthesize_script = synthesize_script
