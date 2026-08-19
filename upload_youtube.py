"""
Uploads the finished video to YouTube.
Optimized for Educational Shorts.
"""

import json
import os
import re
import unicodedata

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import ResumableUploadError
from googleapiclient.http import MediaFileUpload


# YouTube's API limit is 5,000 BYTES, not 5,000 Python characters.
MAX_YOUTUBE_DESCRIPTION_BYTES = 5000
MAX_YOUTUBE_TITLE_BYTES = 100


def _get_credentials():

    token_json = os.environ.get("YOUTUBE_TOKEN_JSON")

    if token_json:

        info = json.loads(token_json)

    else:

        with open("token.json", "r", encoding="utf-8") as f:

            info = json.load(f)

    return Credentials.from_authorized_user_info(info)


def _sanitize_youtube_text(value, max_bytes=None):
    """
    Sanitize metadata according to the YouTube video resource rules.

    YouTube descriptions/titles accept valid UTF-8 but reject < and >.
    Descriptions are limited to 5000 BYTES, so truncation is byte-aware.
    """
    if value is None:
        value = ""

    value = str(value)
    value = unicodedata.normalize("NFKC", value)

    cleaned = []

    for char in value:
        category = unicodedata.category(char)
        codepoint = ord(char)

        # Remove control characters except useful whitespace.
        if category == "Cc" and char not in ("\n", "\r", "\t"):
            continue

        # Remove zero-width/directional formatting characters.
        if category == "Cf":
            continue

        # Explicitly discard Unicode surrogate code points.
        if 0xD800 <= codepoint <= 0xDFFF:
            continue

        # YouTube metadata rejects angle brackets.
        if char in ("<", ">"):
            continue

        # Remove Unicode line/paragraph separators as a conservative API-safe
        # normalization. Normal newlines remain supported.
        if char in ("\u2028", "\u2029"):
            cleaned.append("\n")
            continue

        cleaned.append(char)

    value = "".join(cleaned)
    value = value.encode("utf-8", errors="replace").decode("utf-8")

    # Normalize excessive blank lines.
    value = re.sub(r"\n{3,}", "\n\n", value)
    value = value.strip()

    if max_bytes is not None:
        raw = value.encode("utf-8")

        if len(raw) > max_bytes:
            raw = raw[:max_bytes]

            # Never leave a partial UTF-8 sequence.
            while raw:
                try:
                    value = raw.decode("utf-8")
                    break
                except UnicodeDecodeError:
                    raw = raw[:-1]

            value = value.rstrip()

    return value


def _build_upload_body(title, description, hashtags, upload):

    hashtag_text = " ".join(
        "#" + _sanitize_youtube_text(tag).replace(" ", "")
        for tag in hashtags
        if _sanitize_youtube_text(tag)
    )

    clean_description = _sanitize_youtube_text(description)

    if hashtag_text:
        clean_description = (
            clean_description + "\n\n" + hashtag_text
        ).strip()

    final_description = _sanitize_youtube_text(
        clean_description,
        max_bytes=MAX_YOUTUBE_DESCRIPTION_BYTES,
    )

    clean_title = _sanitize_youtube_text(
        title,
        max_bytes=MAX_YOUTUBE_TITLE_BYTES,
    )

    # YouTube also limits the combined tag value to 500 characters.
    clean_tags = []
    total_tag_chars = 0

    for tag in hashtags:
        clean_tag = _sanitize_youtube_text(tag, max_bytes=500)

        if not clean_tag:
            continue

        # Commas between tags count toward the YouTube limit.
        extra = len(clean_tag) + (1 if clean_tags else 0)

        if total_tag_chars + extra > 500:
            break

        clean_tags.append(clean_tag)
        total_tag_chars += extra

    print("YouTube description validation:")
    print(f"  Characters: {len(final_description)}")
    print(f"  UTF-8 bytes: {len(final_description.encode('utf-8'))}")
    print("  YouTube byte limit: 5000")
    print("  Angle brackets removed: YES")
    print("  Control characters removed: YES")
    print("  Unicode normalized: YES")
    print("  Description sanitized: YES")

    return {
        "snippet": {
            "title": clean_title,
            "description": final_description,
            "tags": clean_tags,
            "categoryId": upload.get("category_id", "27"),
        },
        "status": {
            "privacyStatus": upload.get("privacy_status", "public"),
            "selfDeclaredMadeForKids": False,
        },
    }


def _is_invalid_description_error(error):
    text = str(error).lower()
    return "invaliddescription" in text or "invalid video description" in text


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

    body = _build_upload_body(
        title,
        description,
        hashtags,
        upload,
    )

    media = MediaFileUpload(
        video_path,
        chunksize=-1,
        resumable=True,
        mimetype="video/mp4",
    )

    def _start_request(request_body):
        return youtube.videos().insert(
            part="snippet,status",
            body=request_body,
            media_body=media,
        )

    request = _start_request(body)
    response = None

    try:
        while response is None:
            status, response = request.next_chunk()

            if status:
                print(
                    f"Upload Progress: {int(status.progress()*100)}%"
                )

    except ResumableUploadError as error:

        # If YouTube still rejects the description, perform one final
        # conservative retry using ASCII-only metadata. This protects the
        # upload pipeline from unusual Unicode introduced by research titles,
        # source metadata, or generated text.
        if not _is_invalid_description_error(error):
            raise

        print("⚠️ YouTube rejected the description as invalid.")
        print("🔧 Retrying once with conservative ASCII metadata...")

        ascii_description = (
            body["snippet"]["description"]
            .encode("ascii", errors="ignore")
            .decode("ascii")
        )

        ascii_description = _sanitize_youtube_text(
            ascii_description,
            max_bytes=MAX_YOUTUBE_DESCRIPTION_BYTES,
        )

        ascii_title = (
            body["snippet"]["title"]
            .encode("ascii", errors="ignore")
            .decode("ascii")
        )

        ascii_tags = [
            tag.encode("ascii", errors="ignore").decode("ascii")
            for tag in body["snippet"]["tags"]
        ]

        retry_body = {
            "snippet": {
                "title": ascii_title[:100].strip(),
                "description": ascii_description,
                "tags": ascii_tags,
                "categoryId": body["snippet"]["categoryId"],
            },
            "status": body["status"],
        }

        print(
            f"  Retry description bytes: "
            f"{len(ascii_description.encode('utf-8'))}"
        )

        request = _start_request(retry_body)
        response = None

        while response is None:
            status, response = request.next_chunk()

            if status:
                print(
                    f"Upload Progress: {int(status.progress()*100)}%"
                )

    if not response or "id" not in response:
        raise RuntimeError(
            "YouTube upload returned no video ID."
        )

    video_id = response["id"]

    print("=" * 80)
    print("✅ VIDEO UPLOADED")
    print("=" * 80)
    print(f"https://www.youtube.com/shorts/{video_id}")
    print("=" * 80)

    return video_id
