"""
Uploads the finished video to YouTube.
Optimized for Educational Shorts.
"""

import json
import os

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def _get_credentials():

    token_json = os.environ.get("YOUTUBE_TOKEN_JSON")

    if token_json:

        info = json.loads(token_json)

    else:

        with open("token.json", "r", encoding="utf-8") as f:

            info = json.load(f)

    return Credentials.from_authorized_user_info(info)


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
        "#" + tag.replace(" ", "")
        for tag in hashtags
    )

    final_description = (
        description.strip()
        + "\n\n"
        + hashtag_text
    )

    body = {

        "snippet": {

            "title": title[:100],

            "description": final_description[:5000],

            "tags": hashtags,

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
