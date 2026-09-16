"""Resilient entry point for the automatic Movie Trivia pipeline.

The PlayPhrase website is dynamic and may expose no <video> element or may trigger
browser timeouts. The underlying capture function remains fail-closed, while this
runner converts an individual query failure into a skipped query so the remaining
queries can still be attempted.
"""
from __future__ import annotations

import movie_trivia_main as pipeline


_original_capture = pipeline.capture_playphrase_clip


def _safe_capture(query, output_path):
    try:
        return _original_capture(query, output_path)
    except Exception as exc:  # noqa: BLE001 - browser failures must not abort query rotation
        print(
            f"⚠️ PlayPhrase query failed and will be skipped: {query!r} "
            f"({type(exc).__name__}: {exc})"
        )
        return False


pipeline.capture_playphrase_clip = _safe_capture


if __name__ == "__main__":
    pipeline.main()
