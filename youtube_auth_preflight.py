"""Fail-fast YouTube OAuth validation for scheduled production workflows."""
from __future__ import annotations


def validate_before_render() -> None:
    from upload_youtube import validate_youtube_auth
    validate_youtube_auth()
    print("🔐 YouTube authentication preflight PASSED — safe to start rendering")


if __name__ == "__main__":
    validate_before_render()
