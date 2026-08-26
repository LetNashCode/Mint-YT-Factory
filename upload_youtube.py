"""
Uploads the finished video to YouTube and applies its custom thumbnail.
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
    if value is None: value = ""
    value = unicodedata.normalize("NFKC", str(value))
    cleaned = []
    for char in value:
        category = unicodedata.category(char); codepoint = ord(char)
        if category == "Cc" and char not in ("\n", "\r", "\t"): continue
        if category == "Cf": continue
        if 0xD800 <= codepoint <= 0xDFFF: continue
        if char in ("<", ">"): continue
        if char in ("\u2028", "\u2029"): cleaned.append("\n"); continue
        cleaned.append(char)
    value = "".join(cleaned).encode("utf-8", errors="replace").decode("utf-8")
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    if max_bytes is not None:
        raw = value.encode("utf-8")
        if len(raw) > max_bytes:
            raw = raw[:max_bytes]
            while raw:
                try: value = raw.decode("utf-8"); break
                except UnicodeDecodeError: raw = raw[:-1]
            value = value.rstrip()
    return value


def _build_upload_body(title, description, hashtags, upload):
    hashtag_text = " ".join("#" + _sanitize_youtube_text(tag).replace(" ", "") for tag in hashtags if _sanitize_youtube_text(tag))
    clean_description = _sanitize_youtube_text(description)
    if hashtag_text: clean_description = (clean_description + "\n\n" + hashtag_text).strip()
    final_description = _sanitize_youtube_text(clean_description, max_bytes=MAX_YOUTUBE_DESCRIPTION_BYTES)
    clean_title = _sanitize_youtube_text(title, max_bytes=MAX_YOUTUBE_TITLE_BYTES)
    clean_tags=[]; total_tag_chars=0
    for tag in hashtags:
        clean_tag=_sanitize_youtube_text(tag, max_bytes=500)
        if not clean_tag: continue
        extra=len(clean_tag)+(1 if clean_tags else 0)
        if total_tag_chars+extra>500: break
        clean_tags.append(clean_tag); total_tag_chars+=extra
    print("YouTube description validation:")
    print(f"  Characters: {len(final_description)}")
    print(f"  UTF-8 bytes: {len(final_description.encode('utf-8'))}")
    return {"snippet":{"title":clean_title,"description":final_description,"tags":clean_tags,"categoryId":upload.get("category_id","27")},"status":{"privacyStatus":upload.get("privacy_status","public"),"selfDeclaredMadeForKids":False}}


def _is_invalid_description_error(error):
    text=str(error).lower(); return "invaliddescription" in text or "invalid video description" in text


def _upload_video_request(youtube, video_path, body):
    media=MediaFileUpload(video_path,chunksize=-1,resumable=True,mimetype="video/mp4")
    request=youtube.videos().insert(part="snippet,status",body=body,media_body=media); response=None
    while response is None:
        status,response=request.next_chunk()
        if status: print(f"Upload Progress: {int(status.progress()*100)}%")
    return response


def set_thumbnail(video_id, thumbnail_path, youtube=None):
    """Apply a 16:9 JPEG thumbnail after upload."""
    if not thumbnail_path or not os.path.exists(thumbnail_path):
        print("⚠️ No custom thumbnail found; keeping YouTube default.")
        return False
    youtube = youtube or build("youtube","v3",credentials=_get_credentials())
    media=MediaFileUpload(thumbnail_path,mimetype="image/jpeg",resumable=False)
    youtube.thumbnails().set(videoId=video_id,media_body=media).execute()
    print(f"🖼️ Custom thumbnail uploaded: {os.path.basename(thumbnail_path)}")
    return True


def post_top_level_comment(video_id, comment, youtube=None):
    """Post a topic-specific top-level engagement comment.

    Returns the created comment ID on success and raises on failure. Pinning is
    intentionally manual because the standard YouTube Data API has no supported
    pin-comment endpoint.
    """
    text = _sanitize_youtube_text(comment, max_bytes=10000)
    if not text: return None
    youtube = youtube or build("youtube","v3",credentials=_get_credentials())
    body={"snippet":{"videoId":video_id,"topLevelComment":{"snippet":{"textOriginal":text}}}}
    response=youtube.commentThreads().insert(part="snippet",body=body).execute()
    comment_id=((response.get("snippet") or {}).get("topLevelComment") or {}).get("id") or response.get("id")
    if not comment_id: raise RuntimeError("YouTube accepted the comment request but returned no comment ID.")
    print("💬 Engagement comment posted")
    print(f"   Comment ID: {comment_id}")
    print("📌 Pinning: manual (YouTube Data API has no supported pin endpoint)")
    return comment_id


def upload_video(video_path,title,description,config,thumbnail_path=None,engagement_comment=None):
    creds=_get_credentials(); youtube=build("youtube","v3",credentials=creds); upload=config["upload"]; hashtags=config["seo"]["hashtags"]
    body=_build_upload_body(title,description,hashtags,upload)
    try:
        response=_upload_video_request(youtube,video_path,body)
    except ResumableUploadError as error:
        if not _is_invalid_description_error(error): raise
        print("⚠️ YouTube rejected the description; retrying with conservative ASCII metadata...")
        ascii_description=body["snippet"]["description"].encode("ascii",errors="ignore").decode("ascii")
        retry_body={"snippet":{"title":body["snippet"]["title"].encode("ascii",errors="ignore").decode("ascii")[:100].strip(),"description":_sanitize_youtube_text(ascii_description,max_bytes=MAX_YOUTUBE_DESCRIPTION_BYTES),"tags":[tag.encode("ascii",errors="ignore").decode("ascii") for tag in body["snippet"]["tags"]],"categoryId":body["snippet"]["categoryId"]},"status":body["status"]}
        response=_upload_video_request(youtube,video_path,retry_body)
    if not response or "id" not in response: raise RuntimeError("YouTube upload returned no video ID.")
    video_id=response["id"]
    print("="*80); print("✅ VIDEO UPLOADED"); print("="*80); print(f"https://www.youtube.com/shorts/{video_id}"); print("="*80)
    if thumbnail_path:
        try: set_thumbnail(video_id,thumbnail_path,youtube)
        except Exception as exc: print(f"⚠️ Custom thumbnail upload failed: {type(exc).__name__}: {exc}")
    comment_posted=False; comment_id=None
    if engagement_comment:
        try:
            comment_id=post_top_level_comment(video_id, engagement_comment, youtube)
            comment_posted=bool(comment_id)
        except Exception as exc:
            print(f"⚠️ Engagement comment failed; video upload remains successful: {type(exc).__name__}: {exc}")
    return {"video_id":video_id,"engagement_comment_posted":comment_posted,"engagement_comment_id":comment_id}
