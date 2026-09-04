"""Meta social publishing for Mint-YT-Factory.

Publishes the same finished Short as an Instagram Reel and Facebook Page Reel.
Credentials are supplied only through environment variables / GitHub Actions secrets.

Required Instagram variables:
  INSTAGRAM_USER_ID
  INSTAGRAM_ACCESS_TOKEN

Required Facebook variables:
  FACEBOOK_PAGE_ID
  FACEBOOK_PAGE_ACCESS_TOKEN

Optional:
  META_GRAPH_API_VERSION (default: v23.0)
  SOCIAL_PUBLISH_STRICT=true to fail the pipeline if an enabled social upload fails.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import requests

DEFAULT_API_VERSION = "v23.0"
REQUEST_TIMEOUT = 180
POLL_SECONDS = 5
POLL_ATTEMPTS = 60


def _env(name: str) -> str:
    return str(os.environ.get(name) or "").strip()


def _enabled(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _api_version() -> str:
    value = _env("META_GRAPH_API_VERSION") or DEFAULT_API_VERSION
    return value if value.startswith("v") else f"v{value}"


def _error(response: requests.Response, context: str) -> RuntimeError:
    try:
        detail = json.dumps(response.json(), ensure_ascii=False)
    except Exception:
        detail = response.text
    return RuntimeError(f"{context} failed ({response.status_code}): {detail[:1500]}")


def _post(url, *, data=None, headers=None, files=None, timeout=REQUEST_TIMEOUT):
    response = requests.post(
        url, data=data, headers=headers, files=files,
        timeout=timeout,
    )
    if not response.ok:
        raise _error(response, url)
    return response.json()


def _get(url, *, params=None, headers=None, timeout=REQUEST_TIMEOUT):
    response = requests.get(url, params=params, headers=headers, timeout=timeout)
    if not response.ok:
        raise _error(response, url)
    return response.json()


def _clean_caption(title: str, description: str, config: dict | None = None, limit: int = 2100) -> str:
    title = " ".join(str(title or "").split())
    description = str(description or "").strip()
    tags = []
    for tag in ((config or {}).get("seo") or {}).get("hashtags") or []:
        tag = str(tag or "").strip().lstrip("#").replace(" ", "")
        if tag:
            tags.append("#" + tag)
    parts = [x for x in (title, description, " ".join(tags[:12])) if x]
    caption = "\n\n".join(parts).strip()
    return caption[:limit]


def prepare_social_video(video_path: str, output_dir: str) -> str:
    """Create an Instagram/Facebook-friendly 1080x1920 H.264/AAC copy.

    The production master is 2160x3840 at a very high bitrate. Instagram Reels
    publishing is more reliable with a <=1920-wide H.264 MP4 and a moderate
    bitrate, so social platforms receive a separate derivative while YouTube
    keeps the untouched 4K master.
    """
    source = Path(video_path)
    if not source.is_file():
        raise RuntimeError(f"Social source video not found: {source}")
    out = Path(output_dir) / "social_reel.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(source),
        "-vf", "scale=1080:1920:flags=lanczos",
        "-c:v", "libx264", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-level:v", "4.2", "-r", "60",
        "-b:v", "12M", "-maxrate", "16M", "-bufsize", "24M",
        "-c:a", "aac", "-ar", "48000", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out),
    ]
    print("📱 Preparing 1080x1920 Meta Reel derivative")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not out.is_file() or out.stat().st_size < 1024:
        raise RuntimeError("Social video transcode failed: " + (result.stderr or result.stdout)[-1500:])
    return str(out)


def _upload_instagram(video_path: str, title: str, description: str, config: dict) -> dict:
    user_id = _env("INSTAGRAM_USER_ID")
    token = _env("INSTAGRAM_ACCESS_TOKEN")
    if not user_id or not token:
        return {"status": "skipped", "reason": "INSTAGRAM_USER_ID or INSTAGRAM_ACCESS_TOKEN not configured"}

    version = _api_version()
    graph_base = _env("INSTAGRAM_GRAPH_BASE") or "https://graph.facebook.com"
    graph = graph_base.rstrip("/") + "/" + version
    caption = _clean_caption(title, description, config)

    print("📸 Instagram Reel: creating resumable media container")
    container = _post(
        f"{graph}/{user_id}/media",
        data={
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption,
            "share_to_feed": "true",
            "access_token": token,
        },
    )
    container_id = str(container.get("id") or "").strip()
    upload_url = str(container.get("uri") or container.get("upload_url") or "").strip()
    if not container_id:
        raise RuntimeError("Instagram container creation returned no container ID.")
    if not upload_url:
        upload_url = f"https://rupload.facebook.com/ig-api-upload/{version}/{container_id}"

    size = os.path.getsize(video_path)
    print("📤 Instagram Reel: uploading video binary")
    with open(video_path, "rb") as handle:
        response = requests.post(
            upload_url,
            data=handle,
            headers={
                "Authorization": f"OAuth {token}",
                "offset": "0",
                "file_size": str(size),
                "Content-Type": "video/mp4",
            },
            timeout=REQUEST_TIMEOUT,
        )
    if not response.ok:
        raise _error(response, "Instagram resumable upload")

    print("⏳ Instagram Reel: waiting for processing")
    status = ""
    for _ in range(POLL_ATTEMPTS):
        payload = _get(
            f"{graph}/{container_id}",
            params={"fields": "status_code,status", "access_token": token},
        )
        status = str(payload.get("status_code") or "").upper()
        if status == "FINISHED":
            break
        if status in {"ERROR", "EXPIRED"}:
            raise RuntimeError(f"Instagram container processing failed: {payload}")
        time.sleep(POLL_SECONDS)
    else:
        raise RuntimeError(f"Instagram container did not finish processing; last status={status!r}")

    published = _post(
        f"{graph}/{user_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
    )
    media_id = str(published.get("id") or "").strip()
    if not media_id:
        raise RuntimeError("Instagram publish returned no media ID.")
    print(f"✅ INSTAGRAM REEL PUBLISHED | media_id={media_id}")
    return {"status": "published", "media_id": media_id, "container_id": container_id}


def _upload_facebook(video_path: str, title: str, description: str, config: dict) -> dict:
    page_id = _env("FACEBOOK_PAGE_ID")
    token = _env("FACEBOOK_PAGE_ACCESS_TOKEN")
    if not page_id or not token:
        return {"status": "skipped", "reason": "FACEBOOK_PAGE_ID or FACEBOOK_PAGE_ACCESS_TOKEN not configured"}

    version = _api_version()
    graph = f"https://graph.facebook.com/{version}"
    caption = _clean_caption(title, description, config)

    print("📘 Facebook Reel: starting upload session")
    session = _post(
        f"{graph}/{page_id}/video_reels",
        data={"upload_phase": "start", "access_token": token},
    )
    video_id = str(session.get("video_id") or "").strip()
    upload_url = str(session.get("upload_url") or "").strip()
    if not video_id or not upload_url:
        raise RuntimeError("Facebook Reel start returned no video_id/upload_url.")

    size = os.path.getsize(video_path)
    print("📤 Facebook Reel: uploading video binary")
    with open(video_path, "rb") as handle:
        response = requests.post(
            upload_url,
            data=handle,
            headers={
                "Authorization": f"OAuth {token}",
                "offset": "0",
                "file_size": str(size),
                "Content-Type": "application/octet-stream",
            },
            timeout=REQUEST_TIMEOUT,
        )
    if not response.ok:
        raise _error(response, "Facebook Reel binary upload")

    print("📘 Facebook Reel: publishing")
    finished = _post(
        f"{graph}/{page_id}/video_reels",
        data={
            "video_id": video_id,
            "upload_phase": "finish",
            "video_state": "PUBLISHED",
            "title": str(title or "")[:255],
            "description": caption,
            "access_token": token,
        },
    )
    reel_id = str(finished.get("id") or finished.get("video_id") or video_id).strip()
    print(f"✅ FACEBOOK REEL PUBLISHED | video_id={reel_id}")
    return {"status": "published", "video_id": reel_id}


def publish_social_reels(video_path: str, title: str, description: str, config: dict, output_dir: str) -> dict:
    """Publish enabled Meta destinations without exposing secrets in logs."""
    result = {
        "instagram": None,
        "facebook": None,
        "strict": _enabled(_env("SOCIAL_PUBLISH_STRICT")),
        "updated_at": int(time.time()),
    }

    ig_enabled = bool(_env("INSTAGRAM_USER_ID") and _env("INSTAGRAM_ACCESS_TOKEN"))
    fb_enabled = bool(_env("FACEBOOK_PAGE_ID") and _env("FACEBOOK_PAGE_ACCESS_TOKEN"))
    if not ig_enabled and not fb_enabled:
        print("📱 Meta social publishing: DISABLED (no Instagram/Facebook credentials configured)")
        result["instagram"] = {"status": "skipped", "reason": "not configured"}
        result["facebook"] = {"status": "skipped", "reason": "not configured"}
        return result

    social_video = prepare_social_video(video_path, output_dir)
    result["social_video"] = social_video

    failures = []
    for name, fn, enabled in (
        ("instagram", _upload_instagram, ig_enabled),
        ("facebook", _upload_facebook, fb_enabled),
    ):
        if not enabled:
            result[name] = {"status": "skipped", "reason": "not configured"}
            continue
        try:
            result[name] = fn(social_video, title, description, config)
        except Exception as exc:
            result[name] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            failures.append(name)
            print(f"⚠️ {name.title()} publishing failed: {type(exc).__name__}: {exc}")

    status_path = Path(output_dir) / "social_publish_status.json"
    try:
        status_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"⚠️ Could not save social publish status: {exc}")

    if failures and result["strict"]:
        raise RuntimeError("Strict social publishing failed for: " + ", ".join(failures))
    if failures:
        print("⚠️ Social publishing had failures but YouTube publication remains successful.")
    return result
