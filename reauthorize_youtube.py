"""Re-authorize Mint-YT-Factory's YouTube OAuth token with read + upload scopes.

Run locally with the existing YOUTUBE_TOKEN_JSON environment variable:
    python reauthorize_youtube.py

The script prints a fresh token JSON. Replace the GitHub Actions secret
YOUTUBE_TOKEN_JSON with that JSON. Do not commit the token.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def main() -> None:
    raw = os.environ.get("YOUTUBE_TOKEN_JSON", "").strip()
    if not raw:
        path = Path("youtube_token.json")
        if path.exists():
            raw = path.read_text(encoding="utf-8")
    if not raw:
        raise SystemExit(
            "YOUTUBE_TOKEN_JSON is missing. Export your current token JSON first."
        )

    current = json.loads(raw)
    client_id = current.get("client_id")
    client_secret = current.get("client_secret")
    if not client_id or not client_secret:
        raise SystemExit(
            "The current token JSON does not contain client_id/client_secret. "
            "Use the OAuth client credentials from Google Cloud Console instead."
        )

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    token = json.loads(credentials.to_json())

    print("\n=== NEW YOUTUBE_TOKEN_JSON ===")
    print(json.dumps(token, ensure_ascii=False))
    print("=== END TOKEN ===\n")
    print("Replace the GitHub Actions secret YOUTUBE_TOKEN_JSON with the JSON above.")
    print("Never commit this token to the repository.")


if __name__ == "__main__":
    main()
