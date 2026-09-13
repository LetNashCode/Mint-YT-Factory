"""Fail-fast YouTube OAuth validation for production workflows."""
from __future__ import annotations

import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


def _load_credentials() -> Credentials:
    raw = os.environ.get("YOUTUBE_TOKEN_JSON", "").strip()
    if not raw:
        raise RuntimeError("Missing GitHub secret YOUTUBE_TOKEN_JSON.")
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("YOUTUBE_TOKEN_JSON is not valid JSON.") from exc
    return Credentials.from_authorized_user_info(info)


def validate_before_render() -> None:
    creds = _load_credentials()
    if creds.valid:
        print("🔐 YouTube OAuth preflight: credentials currently valid")
        return
    try:
        creds.refresh(Request())
    except Exception as exc:
        text = str(exc).lower()
        if "invalid_grant" in text or "expired or revoked" in text:
            raise RuntimeError(
                "❌ YouTube OAuth refresh token is expired or revoked. "
                "Create a fresh authorized token.json and replace the GitHub "
                "secret YOUTUBE_TOKEN_JSON, then rerun the workflow. "
                "Rendering was intentionally blocked to avoid wasting runner time."
            ) from exc
        raise RuntimeError(f"❌ YouTube OAuth preflight failed: {type(exc).__name__}: {exc}") from exc
    print("🔐 YouTube OAuth preflight: refresh SUCCESS")


if __name__ == "__main__":
    validate_before_render()
