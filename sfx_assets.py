"""Local meme-SFX asset registry for Mint-YT-Factory.

This module intentionally does not download audio from the web at runtime.
Drop approved meme clips into assets/sfx/meme and the pipeline will use only
those clips. Missing categories fall back to generated meme-style stingers so
production never silently switches back to generic stock SFX.
"""
from __future__ import annotations
from pathlib import Path
import os

SFX_ROOT = Path(__file__).resolve().parent / "assets" / "sfx" / "meme"

# Category -> preferred local filenames. Add more files without changing code.
MEME_LIBRARY = {
    "vine_boom": ("vine_boom.mp3", "vine_boom.wav"),
    "bruh": ("bruh.mp3", "bruh.wav"),
    "metal_pipe": ("metal_pipe.mp3", "metal_pipe.wav"),
    "record_scratch": ("record_scratch.mp3", "record_scratch.wav"),
    "dramatic_reveal": ("dramatic_reveal.mp3", "dramatic_reveal.wav"),
    "windows_error": ("windows_error.mp3", "windows_error.wav"),
    "sad_trombone": ("sad_trombone.mp3", "sad_trombone.wav"),
    "crowd_gasp": ("crowd_gasp.mp3", "crowd_gasp.wav"),
    "cartoon_boing": ("cartoon_boing.mp3", "cartoon_boing.wav"),
    "crickets": ("crickets.mp3", "crickets.wav"),
    "airhorn": ("airhorn.mp3", "airhorn.wav"),
    "faaa": ("faaa.mp3", "faaa.wav"),
}

def ensure_sfx_assets(force: bool = False) -> dict:
    """Return available local meme clips by category.

    force is accepted for backwards compatibility. No network download occurs.
    """
    del force
    SFX_ROOT.mkdir(parents=True, exist_ok=True)
    result = {}
    for category, names in MEME_LIBRARY.items():
        found = []
        for name in names:
            path = SFX_ROOT / name
            if path.exists() and path.stat().st_size > 1024:
                found.append(str(path))
        result[category] = found
        print(f"😂 Meme SFX: {category} {len(found)} local asset(s)")
    total = sum(len(v) for v in result.values())
    print(f"😂 Meme-only SFX library ready: {total} clips in {SFX_ROOT}")
    return result

if __name__ == "__main__":
    ensure_sfx_assets()
