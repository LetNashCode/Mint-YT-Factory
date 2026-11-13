"""Meta social publishing for Mint-YT-Factory.

Publishes the same finished Short as an Instagram Reel and Facebook Page Reel.
Credentials are supplied only through environment variables / GitHub Actions secrets.

Social policy:
  - YouTube is the primary publication and is handled by main.py.
  - Each enabled Meta destination gets up to 4 total attempts (initial + 3 retries).
  - A failure on Instagram never prevents Facebook from being attempted.
  - A failure on Facebook never prevents Instagram from being attempted.
  - In strict mode, the workflow fails only after all attempts for the failed
    enabled destinations are exhausted. Successful destinations are never retried.
  - YouTube publication state is preserved when Meta publishing fails so a later
    workflow run resumes the social work instead of regenerating the Short.
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
MAX_SOCIAL_ATTEMPTS = 4


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
    response = requests.post(url, data=data, headers=headers, files=files, timeout=timeout)
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


def prepare_social_video(video_path: str, output_dir: str, attempt: int = 1, force: bool = False) -> str:
    """Create a conservative Meta-compatible Reel derivative.

    Attempt 1 uses a normal 1080x1920 H.264 Main encode. Retries deliberately
    regenerate the file rather than blindly uploading the exact same binary.
    Later attempts use a lower bitrate and Baseline profile to give Meta a
    materially different, simpler input when its processor rejects the first
    encode with ProcessingFailedError.
    """
    source = Path(video_path)
    if not source.is_file():
        raise RuntimeError(f"Social source video not found: {source}")
    out = Path(output_dir) / "social_reel.mp4"
    if out.is_file() and out.stat().st_size >= 1024 and not force:
        print(f"♻️ Reusing existing social derivative: {out}")
        return str(out)

    out.parent.mkdir(parents=True, exist_ok=True)
    if attempt <= 1:
        profile, level, bitrate, maxrate, preset = "main", "4.1", "8M", "10M", "medium"
    elif attempt == 2:
        profile, level, bitrate, maxrate, preset = "baseline", "4.0", "6M", "8M", "fast"
    elif attempt == 3:
        profile, level, bitrate, maxrate, preset = "baseline", "4.0", "5M", "7M", "fast"
    else:
        # Last-resort compatibility encode: lower bitrate, conservative GOP,
        # stereo AAC and baseline H.264 for Meta's video processor.
        profile, level, bitrate, maxrate, preset = "baseline", "4.0", "3M", "4M", "veryfast"

    tmp = out.with_name(f"social_reel.attempt{attempt}.tmp.mp4")
    cmd = [
        "ffmpeg", "-y", "-i", str(source),
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", "scale=1080:1920:flags=lanczos,setsar=1",
        "-c:v", "libx264", "-preset", preset,
        "-pix_fmt", "yuv420p", "-profile:v", profile,
        "-level:v", level, "-r", "30", "-fps_mode", "cfr",
        "-g", "60", "-keyint_min", "60", "-sc_threshold", "0", "-bf", "0",
        "-b:v", bitrate, "-maxrate", maxrate, "-bufsize", "16M",
        # Meta's published Reels spec calls for AAC at 48 kHz. Disable MP4
        # edit lists as some otherwise-valid files are rejected by rupload.
        "-c:a", "aac", "-ac", "2", "-ar", "48000", "-b:a", "128k",
        "-use_editlist", "0", "-video_track_timescale", "90000",
        "-avoid_negative_ts", "make_zero",
        "-metadata:s:v:0", "rotate=0", "-movflags", "+faststart",
        str(tmp),
    ]
    print(f"📱 Preparing Meta Reel derivative | attempt {attempt}/{MAX_SOCIAL_ATTEMPTS} | {profile} {level} | {bitrate} video")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not tmp.is_file() or tmp.stat().st_size < 1024:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise RuntimeError("Social video transcode failed: " + (result.stderr or result.stdout)[-1500:])

    # Validate the exact derivative before sending it to Meta. This catches
    # unsupported codecs, dimensions, frame rates, missing audio and oversized
    # files locally instead of returning a vague ProcessingFailedError.
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "stream=codec_type,codec_name,width,height,pix_fmt,r_frame_rate,sample_rate,channels,start_time",
            "-show_entries", "format=duration,size", "-of", "json", str(tmp),
        ],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("Social derivative ffprobe failed: " + (probe.stderr or probe.stdout)[-1000:])
    try:
        metadata = json.loads(probe.stdout or "{}")
        streams = metadata.get("streams") or []
        video = next(s for s in streams if s.get("codec_type") == "video")
        audio = next(s for s in streams if s.get("codec_type") == "audio")
        duration = float((metadata.get("format") or {}).get("duration") or 0)
        size = int((metadata.get("format") or {}).get("size") or tmp.stat().st_size)
    except (ValueError, TypeError, StopIteration):
        tmp.unlink(missing_ok=True)
        raise RuntimeError("Social derivative failed the MP4 stream metadata check")
    if (
        video.get("codec_name") != "h264"
        or (int(video.get("width") or 0), int(video.get("height") or 0)) != (1080, 1920)
        or video.get("pix_fmt") != "yuv420p"
        or audio.get("codec_name") != "aac"
        or int(audio.get("channels") or 0) != 2
        or int(audio.get("sample_rate") or 0) != 48000
        or not 3 <= duration <= 900
        or size > 300 * 1024 * 1024
    ):
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            "Social derivative is not Meta-compatible: "
            f"video={video.get('codec_name')} {video.get('width')}x{video.get('height')} "
            f"{video.get('pix_fmt')} | audio={audio.get('codec_name')} "
            f"{audio.get('channels')}ch @ {audio.get('sample_rate')}Hz "
            f"| duration={duration:.2f}s | size={size}"
        )
    print(
        f"🔎 Meta derivative validated: H.264 1080x1920 yuv420p + AAC stereo "
        f"| AAC 48kHz | {duration:.2f}s | {size / (1024 * 1024):.1f} MB",
        flush=True,
    )
    tmp.replace(out)
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
        data={"media_type": "REELS", "upload_type": "resumable", "caption": caption,
              "share_to_feed": "true", "access_token": token},
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
            upload_url, data=handle,
            headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size),
                     "Content-Length": str(size),
                     # Meta's resumable RUpload endpoint expects a binary body;
                     # video/mp4 here can trigger ProcessingFailedError before
                     # Instagram accepts the uploaded MP4 for processing.
                     "Content-Type": "application/octet-stream"},
            timeout=REQUEST_TIMEOUT,
        )
    if not response.ok:
        raise _error(response, "Instagram resumable upload")

    print("⏳ Instagram Reel: waiting for processing")
    status = ""
    for _ in range(POLL_ATTEMPTS):
        payload = _get(f"{graph}/{container_id}", params={"fields": "status_code,status", "access_token": token})
        status = str(payload.get("status_code") or "").upper()
        if status == "FINISHED":
            break
        if status in {"ERROR", "EXPIRED"}:
            raise RuntimeError(f"Instagram container processing failed: {payload}")
        time.sleep(POLL_SECONDS)
    else:
        raise RuntimeError(f"Instagram container did not finish processing; last status={status!r}")

    published = _post(f"{graph}/{user_id}/media_publish", data={"creation_id": container_id, "access_token": token})
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
    session = _post(f"{graph}/{page_id}/video_reels", data={"upload_phase": "start", "access_token": token})
    video_id = str(session.get("video_id") or "").strip()
    upload_url = str(session.get("upload_url") or "").strip()
    if not video_id or not upload_url:
        raise RuntimeError("Facebook Reel start returned no video_id/upload_url.")

    size = os.path.getsize(video_path)
    print("📤 Facebook Reel: uploading video binary")
    with open(video_path, "rb") as handle:
        response = requests.post(
            upload_url, data=handle,
            headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size),
                     "Content-Type": "application/octet-stream"},
            timeout=REQUEST_TIMEOUT,
        )
    if not response.ok:
        raise _error(response, "Facebook Reel binary upload")

    print("📘 Facebook Reel: publishing")
    finished = _post(
        f"{graph}/{page_id}/video_reels",
        data={"video_id": video_id, "upload_phase": "finish", "video_state": "PUBLISHED",
              "title": str(title or "")[:255], "description": caption, "access_token": token},
    )
    reel_id = str(finished.get("id") or finished.get("video_id") or video_id).strip()
    print(f"✅ FACEBOOK REEL PUBLISHED | video_id={reel_id}")
    return {"status": "published", "video_id": reel_id}


def _state_path(output_dir: str) -> Path:
    return Path(output_dir) / "publish_state.json"


def _load_publish_state(output_dir: str) -> dict:
    path = _state_path(output_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_publish_state(output_dir: str, state: dict) -> None:
    state["updated_at"] = int(time.time())
    _state_path(output_dir).write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _attempt_social(name: str, fn, video_path: str, title: str, description: str, config: dict, output_dir: str, state: dict) -> dict:
    """Attempt one social destination up to four total times."""
    previous = state.get(name) or {}
    if str(previous.get("status") or "").lower() == "published":
        print(f"♻️ {name.title()} already published; skipping duplicate upload.")
        return previous

    last_error = None
    for attempt in range(1, MAX_SOCIAL_ATTEMPTS + 1):
        try:
            if attempt == 1:
                social_video = prepare_social_video(video_path, output_dir, attempt=1, force=False)
            else:
                print(f"🔁 {name.title()} retry {attempt - 1}/3 — regenerating Meta video derivative")
                social_video = prepare_social_video(video_path, output_dir, attempt=attempt, force=True)
            state["social_video"] = social_video
            _save_publish_state(output_dir, state)
            result = fn(social_video, title, description, config)
            state[name] = result
            _save_publish_state(output_dir, state)
            return result
        except Exception as exc:
            last_error = exc
            state[name] = {
                "status": "failed",
                "attempt": attempt,
                "max_attempts": MAX_SOCIAL_ATTEMPTS,
                "error": f"{type(exc).__name__}: {exc}",
            }
            _save_publish_state(output_dir, state)
            print(f"⚠️ {name.title()} attempt {attempt}/{MAX_SOCIAL_ATTEMPTS} failed: {type(exc).__name__}: {exc}")
            if attempt < MAX_SOCIAL_ATTEMPTS:
                # A new container is created on every attempt. Give Meta's
                # video processor time to recover between non-retriable 400s.
                retry_delays = (15, 45, 90)
                time.sleep(retry_delays[min(attempt - 1, len(retry_delays) - 1)])

    raise RuntimeError(f"{name.title()} failed after {MAX_SOCIAL_ATTEMPTS} attempts: {last_error}")


def publish_social_reels(video_path: str, title: str, description: str, config: dict, output_dir: str) -> dict:
    """Publish enabled Meta destinations with three retries per destination."""
    state = _load_publish_state(output_dir)

    # main.py writes a compact top-level state immediately after YouTube upload.
    # Promote that durable fact into the per-platform state without overwriting
    # anything already known about Instagram/Facebook.
    existing_youtube_id = str(state.get("video_id") or "").strip()
    if existing_youtube_id and bool(state.get("uploaded")):
        state["youtube"] = {
            "status": "published",
            "enabled": True,
            "video_id": existing_youtube_id,
        }
        state["status"] = "partial"
        _save_publish_state(output_dir, state)
    else:
        state.setdefault("youtube", {"status": "pending", "enabled": True})

    state.setdefault("instagram", {"status": "pending"})
    state.setdefault("facebook", {"status": "pending"})

    result = {
        "instagram": None,
        "facebook": None,
        "strict": _enabled(_env("SOCIAL_PUBLISH_STRICT")),
        "updated_at": int(time.time()),
    }

    # Story Shorts has a strict three-platform publication contract:
    # YouTube + Instagram + Facebook must all be confirmed. Missing credentials
    # are a publication failure, never a successful "skipped" destination.
    ig_enabled = bool(_env("INSTAGRAM_USER_ID") and _env("INSTAGRAM_ACCESS_TOKEN"))
    fb_enabled = bool(_env("FACEBOOK_PAGE_ID") and _env("FACEBOOK_PAGE_ACCESS_TOKEN"))
    missing = []
    if not ig_enabled:
        missing.append("instagram")
        result["instagram"] = {"status": "failed", "reason": "Instagram credentials not configured"}
        state["instagram"] = result["instagram"]
    if not fb_enabled:
        missing.append("facebook")
        result["facebook"] = {"status": "failed", "reason": "Facebook credentials not configured"}
        state["facebook"] = result["facebook"]
    if missing:
        state["status"] = "partial"
        state["uploaded"] = True
        _save_publish_state(output_dir, state)
        status_path = Path(output_dir) / "social_publish_status.json"
        status_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        raise RuntimeError("Required social platforms are not configured: " + ", ".join(missing))

    failures = []
    for name, fn, enabled in (
        ("instagram", _upload_instagram, ig_enabled),
        ("facebook", _upload_facebook, fb_enabled),
    ):
        if not enabled:
            result[name] = {"status": "skipped", "reason": "not configured"}
            state[name] = result[name]
            _save_publish_state(output_dir, state)
            continue

        try:
            result[name] = _attempt_social(name, fn, video_path, title, description, config, output_dir, state)
        except Exception as exc:
            failures.append(name)
            result[name] = state.get(name) or {
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
            print(f"🛑 {name.title()} exhausted all {MAX_SOCIAL_ATTEMPTS} attempts.")
            # Continue to the other social destination; one platform's failure
            # must not prevent the other from getting its full retry budget.

    status_path = Path(output_dir) / "social_publish_status.json"
    try:
        status_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"⚠️ Could not save social publish status: {exc}")

    if failures:
        # Keep the artifact resumable whenever any enabled social destination
        # is still failed. YouTube stays durably marked as published.
        state["status"] = "partial"
        state["uploaded"] = True
        _save_publish_state(output_dir, state)
        if result["strict"]:
            raise RuntimeError(
                f"Strict social publishing failed after {MAX_SOCIAL_ATTEMPTS} attempts "
                f"({MAX_SOCIAL_ATTEMPTS - 1} retries) for: " + ", ".join(failures)
            )
        print(
            f"⚠️ Social publishing had failures after {MAX_SOCIAL_ATTEMPTS} attempts "
            "but YouTube publication remains successful."
        )
        return result

    state["status"] = "uploaded"
    state["uploaded"] = True
    _save_publish_state(output_dir, state)
    return result
