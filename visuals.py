"""
visuals.py
Multi-source visual fetcher
"""

import os
import re
import requests

PIXABAY_SEARCH_URL = "https://pixabay.com/api/videos/"
PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"

_used_urls = set()


def _clean(text):
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return " ".join([w for w in text.split() if len(w) > 2])


def _score(width, height, duration):
    score = 0

    # Prefer portrait clips
    if height >= width:
        score += 50

    # Prefer HD
    if width >= 1920:
        score += 30
    elif width >= 1280:
        score += 20

    # Prefer longer clips
    if duration >= 10:
        score += 20
    elif duration >= 5:
        score += 10

    return score


def _pixabay(query):
    try:

        r = requests.get(
            PIXABAY_SEARCH_URL,
            params={
                "key": os.environ["PIXABAY_API_KEY"],
                "q": _clean(query),
                "video_type": "film",
                "per_page": 15,
            },
            timeout=30,
        )

        if r.status_code != 200:
            return []

        candidates = []

        for hit in r.json().get("hits", []):

            videos = hit.get("videos", {})

            for tier in ("large", "medium", "small", "tiny"):

                if tier not in videos:
                    continue

                v = videos[tier]

                candidates.append({
                    "url": v["url"],
                    "width": v.get("width", 0),
                    "height": v.get("height", 0),
                    "duration": hit.get("duration", 0),
                })

                break

        return candidates

    except Exception:
        return []


def _pexels(query):
    try:

        r = requests.get(
            PEXELS_SEARCH_URL,
            headers={
                "Authorization": os.environ["PEXELS_API_KEY"]
            },
            params={
                "query": query,
                "per_page": 15,
            },
            timeout=30,
        )

        if r.status_code != 200:
            return []

        candidates = []

        for video in r.json().get("videos", []):

            files = video.get("video_files", [])

            if not files:
                continue

            best = max(files, key=lambda x: x.get("width", 0))

            candidates.append({
                "url": best["link"],
                "width": best.get("width", 0),
                "height": best.get("height", 0),
                "duration": video.get("duration", 0),
            })

        return candidates

    except Exception:
        return []


def _search(query):

    results = []

    results.extend(_pixabay(query))
    results.extend(_pexels(query))

    results.sort(
        key=lambda x: _score(
            x["width"],
            x["height"],
            x["duration"],
        ),
        reverse=True,
    )

    for item in results:

        if item["url"] in _used_urls:
            continue

        _used_urls.add(item["url"])

        return item["url"]

    return None


def _download(url, path):

    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()

    with open(path, "wb") as f:
        for chunk in r.iter_content(1024 * 1024):
            if chunk:
                f.write(chunk)


def fetch_visuals_for_script(script, config, workdir):

    os.makedirs(workdir, exist_ok=True)

    paths = []

    clip_no = 1

    for scene in script["scene_plan"]:

        scene_paths = []

        for shot in scene.get("shots", []):

            url = _search(shot["search"])

            if not url:
                continue

            out = os.path.join(
                workdir,
                f"clip_{clip_no}.mp4",
            )

            _download(url, out)

            scene_paths.append(out)

            clip_no += 1

        if scene_paths:
            paths.append(scene_paths)
        else:
            paths.append(None)

    return paths
