"""Automatic Reddit horror-video commentary Shorts pipeline."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from google import genai
from google.genai import types
from tts import synthesize_narration

MODEL_NAME = "gemini-flash-lite-latest"
ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / os.getenv("REDDIT_HORROR_OUTPUT_DIR", "artifacts/reddit-horror")
SUBREDDITS = ["ScaryVideos", "creepy", "Paranormal", "Ghosts", "OddlyTerrifying"]
USER_AGENT = "Mint-YT-Factory/1.3"
ATOM = "{http://www.w3.org/2005/Atom}"


def clean(value: object, limit: int = 4000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def run(command: list[str]) -> None:
    print("$", " ".join(map(str, command)))
    subprocess.run(command, check=True)


def extract_media_links(entry: ET.Element) -> list[str]:
    raw = " ".join(entry.itertext())
    links = re.findall(r"https?://[^\s<>\"']+", raw)
    for node in entry.findall(f"{ATOM}link"):
        href = node.attrib.get("href", "")
        if href:
            links.append(href)
    result: list[str] = []
    for link in links:
        link = link.rstrip(".,);\"]'")
        if "v.redd.it/" in link or re.search(r"\.(?:mp4|webm|mov)(?:\?|$)", link, re.I):
            if link not in result:
                result.append(link)
    return result


def rss_candidates() -> list[dict]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml"}
    posts: list[dict] = []
    for subreddit in SUBREDDITS:
        try:
            response = requests.get(f"https://www.reddit.com/r/{subreddit}/.rss?limit=50", headers=headers, timeout=30)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            for entry in root.findall(f"{ATOM}entry"):
                title = entry.findtext(f"{ATOM}title", "")
                link_node = entry.find(f"{ATOM}link")
                link = link_node.attrib.get("href", "") if link_node is not None else ""
                entry_id = entry.findtext(f"{ATOM}id", "")
                updated = entry.findtext(f"{ATOM}updated", "") or ""
                if title and link:
                    posts.append({"id": entry_id or link, "title": clean(title, 800), "subreddit": subreddit, "source_url": link, "media_urls": extract_media_links(entry), "score": 0, "updated": updated, "author": "[unknown]"})
            print(f"📡 RSS loaded for r/{subreddit}")
        except Exception as exc:
            print(f"⚠️ RSS request failed for r/{subreddit}: {type(exc).__name__}: {exc}")
    return list({str(p["id"]): p for p in posts}.values())


def json_candidates() -> list[dict]:
    posts: list[dict] = []
    for subreddit in SUBREDDITS:
        try:
            response = requests.get(f"https://www.reddit.com/r/{subreddit}/top.json?t=week&limit=50", headers={"User-Agent": USER_AGENT}, timeout=30)
            response.raise_for_status()
            for child in response.json().get("data", {}).get("children", []):
                data = child.get("data", {})
                if data.get("stickied"):
                    continue
                permalink = data.get("permalink", "")
                posts.append({**data, "source_url": f"https://www.reddit.com{permalink}" if permalink else data.get("url", "")})
        except Exception as exc:
            print(f"⚠️ JSON request failed for r/{subreddit}: {type(exc).__name__}: {exc}")
    return posts


def reddit_candidates() -> list[dict]:
    posts = rss_candidates()
    if not posts:
        posts = json_candidates()
    return sorted(posts, key=lambda p: (int(p.get("score", 0) or 0), p.get("updated", "")), reverse=True)


def parse_gemini_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as first_error:
        try:
            return json.loads(text, strict=False)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.S)
            if match:
                try:
                    return json.loads(match.group(0), strict=False)
                except json.JSONDecodeError:
                    pass
            raise RuntimeError(f"Gemini returned invalid JSON: {first_error}") from first_error


def generate_commentary(post: dict) -> dict:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is required.")
    prompt = f"""Create an original, suspenseful, transformative commentary script for a 45-60 second English YouTube Short about this Reddit horror video. Do not claim footage is authentic or paranormal as fact. Use a strong first-second hook, explain what viewers should watch for, add thoughtful commentary, and end with a question. Return JSON only with these fields: video_title, hook, narration, description_intro, tags. Keep narration 75-120 words. Reddit title: {clean(post.get('title'), 800)}. Subreddit: r/{clean(post.get('subreddit'), 100)}. Post URL: {post.get('source_url')}"""
    response = genai.Client(api_key=key).models.generate_content(model=MODEL_NAME, contents=prompt, config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.75))
    text = getattr(response, "text", "")
    if not text:
        raise RuntimeError("Gemini returned no commentary script.")
    result = parse_gemini_json(text)
    for field in ("video_title", "hook", "narration", "description_intro", "tags"):
        if field not in result:
            raise RuntimeError(f"Commentary is missing {field!r}.")
    return result


def download_direct(url: str, destination: Path) -> bool:
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60, stream=True)
        response.raise_for_status()
        if "text/html" in response.headers.get("content-type", "").lower():
            return False
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
        return destination.exists() and destination.stat().st_size > 10_000
    except Exception as exc:
        print(f"⚠️ Direct media download failed for {url}: {type(exc).__name__}: {exc}")
        return False


def download_video(post: dict, destination: Path) -> None:
    for media_url in post.get("media_urls", []):
        if download_direct(media_url, destination):
            print(f"🎞️ Downloaded direct media URL: {media_url}")
            return
    try:
        run(["yt-dlp", "--no-playlist", "--merge-output-format", "mp4", "-o", str(destination), post["source_url"]])
        if destination.exists() and destination.stat().st_size > 10_000:
            return
    except subprocess.CalledProcessError as exc:
        print(f"⚠️ yt-dlp could not access Reddit post: exit {exc.returncode}")
    raise RuntimeError("Unable to download Reddit media. Reddit blocked direct media and yt-dlp extraction.")


def render(script: dict, source: Path, audio: Path, output: Path, work: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (1080, 1920), "black")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 66)
    except OSError:
        font = ImageFont.load_default()
    lines, current = [], ""
    for word in clean(script["hook"], 180).split():
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > 940:
            lines.append(current); current = word
        else:
            current = candidate
    if current: lines.append(current)
    y = (1920 - len(lines) * 90) // 2
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        draw.text(((1080 - (box[2] - box[0])) // 2, y), line, fill="white", font=font); y += 90
    png = work / "hook.png"; image.save(png)
    hook_video = work / "hook.mp4"
    run(["ffmpeg", "-y", "-loop", "1", "-i", str(png), "-t", "2.5", "-r", "30", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(hook_video)])
    normalized = work / "source.mp4"
    run(["ffmpeg", "-y", "-i", str(source), "-t", "55", "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30", "-an", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(normalized)])
    concat = work / "concat.txt"; concat.write_text(f"file '{hook_video.as_posix()}'\nfile '{normalized.as_posix()}'\n", encoding="utf-8")
    joined = work / "joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(joined)])
    run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(joined), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-t", "60", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", str(output)])


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    posts = reddit_candidates()
    if not posts:
        raise RuntimeError("No Reddit posts were discovered through RSS or JSON.")
    with tempfile.TemporaryDirectory(prefix="reddit-horror-") as temp:
        work = Path(temp)
        selected = None; script = None; source = work / "reddit-source.mp4"
        for post in posts[:20]:
            try:
                print(f"📈 Trying Reddit candidate: r/{post.get('subreddit')} title={post.get('title')}")
                download_video(post, source)
                selected = post
                script = generate_commentary(post)
                break
            except Exception as exc:
                print(f"⚠️ Skipping candidate: {type(exc).__name__}: {exc}")
                if source.exists(): source.unlink()
        if not selected or not script:
            raise RuntimeError("No downloadable Reddit video was found among the discovered candidates.")
        audio = work / "narration.mp3"
        synthesize_narration(clean(script["narration"], 6000), {"voice": {"provider": "kokoro", "voice_name": os.getenv("MINT_KOKORO_VOICE", "af_heart"), "kokoro_lang": os.getenv("MINT_KOKORO_LANG", "a"), "speed": 1.0}}, str(audio), target_duration=50.0)
        output = OUTPUT_DIR / "reddit-horror-commentary.mp4"; render(script, source, audio, output, work)
    description = f"{script['description_intro']}\n\nOriginal Reddit post: {selected['source_url']}\nOriginal creator: u/{selected.get('author') or '[unknown]'}\n\nCommentary and editing added by our channel."
    metadata = {"video_title": script["video_title"], "reddit_post": selected["source_url"], "subreddit": selected.get("subreddit"), "score": selected.get("score", 0), "description": description, "gemini_model": MODEL_NAME, "generated_at": int(time.time())}
    (OUTPUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    if os.getenv("REDDIT_HORROR_AUTO_UPLOAD", "true").lower() in {"1", "true", "yes"}:
        from upload_youtube import upload_video
        config = {"upload": {"privacy_status": os.getenv("REDDIT_HORROR_PRIVACY_STATUS", "public"), "category_id": "24"}, "seo": {"hashtags": script["tags"]}}
        metadata["youtube_video_id"] = upload_video(str(output), clean(script["video_title"], 90), description, config, engagement_comment="Was this video paranormal, unexplained, or something else?")
        (OUTPUT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"REDDIT_HORROR_OUTPUT={output}")


if __name__ == "__main__":
    main()
