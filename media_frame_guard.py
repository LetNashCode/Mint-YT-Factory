"""Normalize Story Shorts visual frames to RGB before MoviePy compositing."""
from __future__ import annotations

import numpy as np


def _rgb_frame(frame):
    """Return a MoviePy-safe HxWx3 uint8 frame for grayscale/RGBA media."""
    array = np.asarray(frame)
    if array.ndim == 2:
        array = np.repeat(array[:, :, None], 3, axis=2)
    elif array.ndim == 3:
        if array.shape[2] == 1:
            array = np.repeat(array, 3, axis=2)
        elif array.shape[2] >= 4:
            array = array[:, :, :3]
    else:
        raise RuntimeError(f"Visual frame has unsupported shape: {array.shape}")
    if array.dtype != np.uint8:
        array = np.clip(array, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(array)


def patch_assemble_rgb():
    """Patch only the Story Shorts assembly import with an RGB frame guard."""
    import assemble

    original = getattr(assemble, "make_visual_clip", None)
    if original is None or getattr(original, "_mint_rgb_guard", False):
        return

    def guarded_make_visual_clip(*args, **kwargs):
        clip = original(*args, **kwargs)
        original_make_frame = clip.make_frame

        def make_frame(t):
            return _rgb_frame(original_make_frame(t))

        clip.make_frame = make_frame
        return clip

    guarded_make_visual_clip._mint_rgb_guard = True
    assemble.make_visual_clip = guarded_make_visual_clip
    print("🛡️ Story visual RGB guard: grayscale/RGBA media normalized before compositing")
