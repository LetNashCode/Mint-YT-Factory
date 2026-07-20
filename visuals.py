"""
Fetches royalty-free stock video clips from Pixabay matching each item's
visual_keywords.

Improved version:
- Tries multiple search queries.
- Shortens overly long AI prompts.
- Never crashes if Pixabay rejects a search.
"""

import os
import re
import requests

PIXABAY_SEARCH_URL = "https://pixabay.com/api/videos/"


def clean_query(text: str) -> str:
    """Keep only the first few important words."""
    text = text.lower()

    text = re.sub(r"[^a-z0-9\s]", " ", text)

    words = text.split()

    words = [w for w in words if len(w) > 2]

    return " ".join(words[:4])


def build_queries(keywords: list[str]) -> list[str]:
    queries = []

    for kw in keywords:
        q = clean_query(kw)
        if q and q not in queries:
            queries.append(q)

    # fallback searches
    for kw in keywords:
        words = clean_query(kw).split()

        if len(words) >= 2:
            q = " ".join(words[:2])
            if q not in queries:
                queries.append(q)

        if len(words) >= 1:
            q = words[0]
            if q not in queries:
                queries.append(q)

    return queries


def find_video_clip(keywords: list, orientation: str = "portrait") -> str | None:

    queries = build_queries(keywords)

    for query in queries:

        params = {
            "key": os.environ["PIXABAY_API_KEY"],
            "q": query,
            "video_type": "film",
            "per_page": 5,
        }

        try:

            resp = requests.get(
                PIXABAY_SEARCH_URL,
                params=params,
                timeout=20,
            )

            if resp.status_code != 200:
                continue

            data = resp.json()

            hits = data.get("hits", [])

            if not hits:
                continue

            video = hits[0]

            videos = video.get("videos", {})

            for tier in ("large", "medium", "small", "tiny"):

                if tier in videos and videos[tier].get("url"):
                    return videos[tier]["url"]

        except Exception:
            continue

    return None


def download_file(url: str, out_path: str) -> str:

    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()

    with open(out_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)

    return out_path


def fetch_visuals_for_script(script: dict, config: dict, workdir: str) -> list:

    os.makedirs(workdir, exist_ok=True)

    clip_paths = []

    orientation = config["visuals"]["orientation"]

    for item in script["items"]:

        url = find_video_clip(item["visual_keywords"], orientation)

        if url is None:
            clip_paths.append(None)
            continue

        out_path = os.path.join(
            workdir,
            f"visual_{item['rank']}.mp4",
        )

        download_file(url, out_path)

        clip_paths.append(out_path)

    return clip_paths
