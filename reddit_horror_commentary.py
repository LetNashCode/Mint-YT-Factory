"""Reddit horror commentary Shorts pipeline.

Media acquisition uses Reddit OAuth listing metadata and the official
reddit_video dash_url/hls_url/fallback_url fields. It does not guess CDN
filenames. Reddit API credentials are required in production.
"""
from __future__ import annotations
import json, os, re, subprocess, tempfile, time
from pathlib import Path
from urllib.parse import urljoin
import requests
from google import genai
from google.genai import types
from tts import synthesize_narration

MODEL_NAME = "gemini-flash-lite-latest"
ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / os.getenv("REDDIT_HORROR_OUTPUT_DIR", "artifacts/reddit-horror")
SUBREDDITS = ["ScaryVideos", "creepy", "Paranormal", "Ghosts", "OddlyTerrifying"]
USER_AGENT = os.getenv("REDDIT_USER_AGENT", "Mint-YT-Factory/2.0 by reddit-horror-bot")


def clean(v, limit=4000):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:limit]


def run(cmd):
    print("$", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True)


def reddit_token():
    cid, secret = os.getenv("REDDIT_CLIENT_ID", "").strip(), os.getenv("REDDIT_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        raise RuntimeError("REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are required. Create a Reddit OAuth script app and add both GitHub secrets.")
    r = requests.post("https://www.reddit.com/api/v1/access_token", auth=(cid, secret), data={"grant_type": "client_credentials"}, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    token = r.json().get("access_token")
    if not token: raise RuntimeError("Reddit OAuth returned no access token.")
    return token


def api_candidates():
    token = reddit_token()
    headers = {"Authorization": f"bearer {token}", "User-Agent": USER_AGENT}
    posts = []
    for sub in SUBREDDITS:
        try:
            r = requests.get(f"https://oauth.reddit.com/r/{sub}/top", params={"t":"week", "limit":50, "raw_json":1}, headers=headers, timeout=30)
            r.raise_for_status()
            for child in r.json().get("data", {}).get("children", []):
                d = child.get("data", {})
                rv = (d.get("secure_media") or {}).get("reddit_video") or (d.get("media") or {}).get("reddit_video")
                if d.get("stickied") or not rv: continue
                media = {k: rv.get(k) for k in ("dash_url", "hls_url", "fallback_url", "scrubber_media_url") if rv.get(k)}
                if not media: continue
                posts.append({"id": d.get("id"), "title": clean(d.get("title"),800), "subreddit": sub, "source_url": "https://www.reddit.com" + d.get("permalink", ""), "media": media, "score": d.get("score",0), "author": (d.get("author") or "[unknown]")})
            print(f"📡 Reddit API loaded r/{sub}")
        except Exception as exc:
            print(f"⚠️ Reddit API failed for r/{sub}: {type(exc).__name__}: {exc}")
    return sorted(posts, key=lambda p: int(p.get("score",0) or 0), reverse=True)


def parse_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try: return json.loads(text, strict=False)
    except json.JSONDecodeError as e:
        m = re.search(r"\{.*\}", text, re.S)
        if m: return json.loads(m.group(0), strict=False)
        raise RuntimeError(f"Gemini returned invalid JSON: {e}") from e


def generate_commentary(post):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key: raise RuntimeError("GEMINI_API_KEY is required.")
    prompt = f"Create an original transformative 45-60 second English YouTube Short commentary about this Reddit horror video. Do not claim it is authentic or paranormal as fact. Use a first-second hook, explain what to watch for, add commentary, and end with a question. Return JSON only with video_title, hook, narration, description_intro, tags. Narration 75-120 words. Title: {post['title']}"
    res = genai.Client(api_key=key).models.generate_content(model=MODEL_NAME, contents=prompt, config=types.GenerateContentConfig(response_mime_type="application/json", temperature=.75))
    data = parse_json(getattr(res, "text", ""))
    for f in ("video_title","hook","narration","description_intro","tags"):
        if f not in data: raise RuntimeError(f"Commentary is missing {f!r}.")
    return data


def download_video(post, destination):
    media = post["media"]
    # Prefer DASH/HLS manifests: Reddit commonly separates audio and video.
    for key in ("dash_url", "hls_url", "fallback_url"):
        url = media.get(key)
        if not url: continue
        try:
            if key in ("dash_url", "hls_url"):
                temp = destination.with_suffix(".manifest")
                r = requests.get(url, headers={"User-Agent":USER_AGENT}, timeout=60)
                r.raise_for_status(); temp.write_bytes(r.content)
                run(["ffmpeg","-y","-protocol_whitelist","file,http,https,tcp,tls,crypto","-i",str(temp),"-c","copy",str(destination)])
                temp.unlink(missing_ok=True)
            else:
                r = requests.get(url, headers={"User-Agent":USER_AGENT}, timeout=90)
                r.raise_for_status(); destination.write_bytes(r.content)
            if destination.exists() and destination.stat().st_size > 10000:
                print(f"🎞️ Downloaded Reddit media via {key}"); return
        except Exception as exc:
            print(f"⚠️ {key} failed: {type(exc).__name__}: {exc}")
            destination.unlink(missing_ok=True)
    raise RuntimeError("Reddit media URLs were unavailable or inaccessible.")


def render(script, source, audio, output, work):
    from PIL import Image, ImageDraw, ImageFont
    image=Image.new("RGB",(1080,1920),"black"); draw=ImageDraw.Draw(image)
    try: font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",66)
    except OSError: font=ImageFont.load_default()
    words=clean(script["hook"],180).split(); lines=[]; cur=""
    for w in words:
        c=f"{cur} {w}".strip()
        if cur and draw.textbbox((0,0),c,font=font)[2]>940: lines.append(cur); cur=w
        else: cur=c
    if cur: lines.append(cur)
    y=(1920-len(lines)*90)//2
    for line in lines:
        b=draw.textbbox((0,0),line,font=font); draw.text(((1080-b[2]+b[0])//2,y),line,fill="white",font=font); y+=90
    png=work/"hook.png"; image.save(png); hook=work/"hook.mp4"
    run(["ffmpeg","-y","-loop","1","-i",str(png),"-t","2.5","-r","30","-an","-c:v","libx264","-pix_fmt","yuv420p",str(hook)])
    normalized=work/"source.mp4"; run(["ffmpeg","-y","-i",str(source),"-t","55","-vf","scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30","-an","-c:v","libx264","-preset","veryfast","-pix_fmt","yuv420p",str(normalized)])
    concat=work/"concat.txt"; concat.write_text(f"file '{hook.as_posix()}'\nfile '{normalized.as_posix()}'\n")
    joined=work/"joined.mp4"; run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-c","copy",str(joined)])
    run(["ffmpeg","-y","-stream_loop","-1","-i",str(joined),"-i",str(audio),"-map","0:v:0","-map","1:a:0","-t","60","-r","30","-c:v","libx264","-preset","veryfast","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-shortest",str(output)])


def main():
    OUTPUT_DIR.mkdir(parents=True,exist_ok=True); posts=api_candidates()
    if not posts: raise RuntimeError("No Reddit video posts with official media metadata were found.")
    with tempfile.TemporaryDirectory(prefix="reddit-horror-") as td:
        work=Path(td); source=work/"reddit-source.mp4"; selected=script=None
        for post in posts[:20]:
            try:
                print(f"📈 Trying r/{post['subreddit']}: {post['title']}"); download_video(post,source); script=generate_commentary(post); selected=post; break
            except Exception as exc:
                print(f"⚠️ Skipping candidate: {type(exc).__name__}: {exc}"); source.unlink(missing_ok=True)
        if not selected: raise RuntimeError("No Reddit video could be downloaded from the authorized API metadata.")
        audio=work/"narration.mp3"; synthesize_narration(clean(script["narration"],6000),{"voice":{"provider":"kokoro","voice_name":os.getenv("MINT_KOKORO_VOICE","af_heart"),"kokoro_lang":os.getenv("MINT_KOKORO_LANG","a"),"speed":1.0}},str(audio),target_duration=50.0)
        output=OUTPUT_DIR/"reddit-horror-commentary.mp4"; render(script,source,audio,output,work)
    description=f"{script['description_intro']}\n\nOriginal Reddit post: {selected['source_url']}\nOriginal creator: u/{selected.get('author') or '[unknown]'}\n\nCommentary and editing added by our channel."
    metadata={"video_title":script["video_title"],"reddit_post":selected["source_url"],"subreddit":selected["subreddit"],"score":selected.get("score",0),"description":description,"gemini_model":MODEL_NAME,"generated_at":int(time.time())}
    (OUTPUT_DIR/"metadata.json").write_text(json.dumps(metadata,indent=2,ensure_ascii=False))
    if os.getenv("REDDIT_HORROR_AUTO_UPLOAD","true").lower() in {"1","true","yes"}:
        from upload_youtube import upload_video
        config={"upload":{"privacy_status":os.getenv("REDDIT_HORROR_PRIVACY_STATUS","public"),"category_id":"24"},"seo":{"hashtags":script["tags"]}}
        metadata["youtube_video_id"]=upload_video(str(output),clean(script["video_title"],90),description,config,engagement_comment="Was this video paranormal, unexplained, or something else?")
        (OUTPUT_DIR/"metadata.json").write_text(json.dumps(metadata,indent=2,ensure_ascii=False))
    print(f"REDDIT_HORROR_OUTPUT={output}")

if __name__ == "__main__": main()
