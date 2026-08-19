"""
Uploads the finished video to YouTube.
Optimized for Educational Shorts.
"""

import json
import os
import unicodedata

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


MAX_YOUTUBE_DESCRIPTION_LENGTH = 5000


def _get_credentials():

    token_json = os.environ.get("YOUTUBE_TOKEN_JSON")

    if token_json:

        info = json.loads(token_json)

    else:

        with open("token.json", "r", encoding="utf-8") as f:

            info = json.load(f)

    return Credentials.from_authorized_user_info(info)


def _sanitize_youtube_text(value, max_length=None):
    """
    Sanitize text before sending it to the YouTube Data API.

    Research-generated descriptions can occasionally contain control
    characters, Unicode surrogates, zero-width formatting characters, or
    other characters that cause YouTube to reject body.snippet.description
    with reason=invalidDescription.
    """
    if value is None:
        value = ""

    value = str(value)

    # Normalize visually equivalent Unicode sequences.
    value = unicodedata.normalize("NFKC", value)

    cleaned = []

    for char in value:
        category = unicodedata.category(char)

        # Keep normal text, emoji/symbols, punctuation, etc.
        # Keep only the whitespace controls that are valid/useful in a
        # YouTube description.
        if category == "Cc" and char not in ("\n", "\r", "\t"):
            continue

        # Remove Unicode formatting/control characters such as zero-width
        # characters and directional formatting marks. These are not needed
        # in the public description and can make API validation brittle.
        if category == "Cf":
            continue

        # Explicitly discard surrogate code points.
        if 0xD800 <= ord(char) <= 0xDFFF:
            continue

        cleaned.append(char)

    value = "".join(cleaned)

    # Guarantee valid UTF-8 even if malformed Unicode somehow survived.
    value = value.encode("utf-8", errors="replace").decode("utf-8")

    # Normalize excessive blank lines without changing the actual content.
    while "\n\n\n" in value:
        value = value.replace("\n\n\n", "\n\n")

    value = value.strip()

    if max_length is not None:
        value = value[:max_length].rstrip()

    return value


def upload_video(
    video_path,
    title,
    description,
    config,
):

    creds = _get_credentials()

    youtube = build(
        "youtube",
        "v3",
        credentials=creds,
    )

    upload = config["upload"]

    hashtags = config["seo"]["hashtags"]

    hashtag_text = " ".join(
        "#" + _sanitize_youtube_text(tag).replace(" ", "")
        for tag in hashtags
    )

    # Sanitize the generated research/public description BEFORE adding
    # hashtags. This is the important fix for YouTube's invalidDescription
    # API error.
    clean_description = _sanitize_youtube_text(description)
    clean_hashtags = _sanitize_youtube_text(hashtag_text)

    final_description = clean_description

    if clean_hashtags:
        final_description = (
            final_description
            + "\n\n"
            + clean_hashtags
        ).strip()

    final_description = _sanitize_youtube_text(
        final_description,
        max_length=MAX_YOUTUBE_DESCRIPTION_LENGTH,
    )

    clean_title = _sanitize_youtube_text(
        title,
        max_length=100,
    )

    # Log only safe diagnostics. This makes future metadata failures much
    # easier to identify without exposing the full description in Actions.
    print("YouTube description validation:")
    print(f"  Characters: {len(final_description)}")
    print(f"  UTF-8 bytes: {len(final_description.encode('utf-8'))}")
    print("  Control characters removed: YES")
    print("  Unicode normalized: YES")
    print("  Description sanitized: YES")

    body = {

        "snippet": {

            "title": clean_title,

            "description": final_description,

            "tags": [
                _sanitize_youtube_text(tag, max_length=500)
                for tag in hashtags
                if _sanitize_youtube_text(tag)
            ],

            "categoryId": upload.get(
                "category_id",
                "27",
            ),

        },

        "status": {

            "privacyStatus": upload.get(
                "privacy_status",
                "public",
            ),

            "selfDeclaredMadeForKids": False,

        },

    }

    media = MediaFileUpload(

        video_path,

        chunksize=-1,

        resumable=True,

        mimetype="video/mp4",

    )

    request = youtube.videos().insert(

        part="snippet,status",

        body=body,

        media_body=media,

    )

    response = None

    while response is None:

        status, response = request.next_chunk()

        if status:

            print(
                f"Upload Progress: {int(status.progress()*100)}%"
            )

    video_id = response["id"]

    print("=" * 80)
    print("✅ VIDEO UPLOADED")
    print("=" * 80)
    print(f"https://www.youtube.com/shorts/{video_id}")
    print("=" * 80)

    return video_id
