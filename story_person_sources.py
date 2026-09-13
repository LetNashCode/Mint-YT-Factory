"""Multi-source real-person media retrieval for Story Shorts.

Identity is the primary ranking signal. Rights metadata is retained for audit
only because the production pipeline is authorized to use its selected media.
Story Shorts only; Publish Shorts is untouched.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

import requests

TIMEOUT = 25
PER_SOURCE_LIMIT = 50
USER_AGENT = "Mint-YT-Factory/StoryPersonSources/1.1"
_PERSON_POOL_CACHE: dict[str, list[dict]] = {}


def _clean(value: Any, maximum: int = 300) -> str:
    return " ".join(str(value or "").replace("\n", " ").split()).strip()[:maximum]


def _get(url: str, params: dict) -> dict:
    try:
        response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        suffix = f" HTTP {status}" if status else ""
        print(f"      ⚠️ Person source request failed: {type(exc).__name__}{suffix}: {_clean(exc, 220)}")
        return {}


def _commons(person: str, query: str) -> list[dict]:
    data = _get("https://commons.wikimedia.org/w/api.php", {
        "action": "query", "generator": "search", "gsrsearch": f"File:{person} {query}",
        "gsrnamespace": 6, "gsrlimit": PER_SOURCE_LIMIT, "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata", "iiurlwidth": 800, "format": "json", "origin": "*"
    })
    result = []
    for page in ((data.get("query") or {}).get("pages") or {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        mime = _clean(info.get("mime"), 80).lower()
        if not mime.startswith(("image/", "video/")):
            continue
        title = _clean(page.get("title"), 300)
        ext = info.get("extmetadata") or {}
        def meta(name: str) -> str:
            value = ext.get(name, "")
            return _clean(value.get("value") if isinstance(value, dict) else value, 300)
        result.append({"source": "Wikimedia Commons", "title": title, "url": info.get("url", ""),
                       "thumburl": info.get("thumburl") or info.get("url", ""), "mime": mime,
                       "creator": meta("Artist"), "license": meta("LicenseShortName") or meta("UsageTerms") or "Unknown / not supplied",
                       "source_url": f"https://commons.wikimedia.org/wiki/{quote(title.replace(' ', '_'))}", "query": query})
    return result


def _archive(person: str, query: str) -> list[dict]:
    q = f'"{person}" {query}'.strip()
    data = _get("https://archive.org/advancedsearch.php", {
        "q": q, "fl[]": ["identifier", "title", "description", "creator", "mediatype"],
        "rows": PER_SOURCE_LIMIT, "page": 1, "output": "json"
    })
    result = []
    for doc in ((data.get("response") or {}).get("docs") or []):
        media = str(doc.get("mediatype") or "")
        if media not in {"movies", "image", "texts"}:
            continue
        identifier = _clean(doc.get("identifier"), 180)
        if not identifier:
            continue
        result.append({"source": "Internet Archive", "title": _clean(doc.get("title"), 300),
                       "url": f"https://archive.org/download/{identifier}",
                       "thumburl": f"https://archive.org/services/img/{identifier}", "mime": "image/unknown",
                       "creator": _clean(doc.get("creator"), 250), "license": "Unknown / not supplied",
                       "source_url": f"https://archive.org/details/{identifier}", "query": query,
                       "archive_identifier": identifier, "mediatype": media})
    return result


def _europeana(person: str, query: str) -> list[dict]:
    import os
    key = os.getenv("EUROPEANA_API_KEY", "").strip()
    if not key:
        return []
    data = _get("https://api.europeana.eu/record/v2/search.json", {
        "wskey": key, "query": f'"{person}" {query}', "rows": PER_SOURCE_LIMIT,
        "profile": "rich", "media": "true", "thumbnail": "true"
    })
    result = []
    for item in data.get("items") or []:
        media = item.get("edmIsShownBy") or item.get("edmPreview")
        if not media:
            continue
        title = item.get("title") or item.get("dcTitle") or ["Europeana item"]
        title = title[0] if isinstance(title, list) else title
        result.append({"source": "Europeana", "title": _clean(title, 300), "url": media,
                       "thumburl": item.get("edmPreview") or media, "mime": "image/unknown",
                       "creator": _clean((item.get("dcCreator") or [""])[0] if isinstance(item.get("dcCreator"), list) else item.get("dcCreator"), 250),
                       "license": _clean((item.get("rights") or [""])[0] if isinstance(item.get("rights"), list) else item.get("rights"), 250) or "Unknown / not supplied",
                       "source_url": f"https://www.europeana.eu/en/item/{item.get('id', '').lstrip('/')}", "query": query})
    return result


def _flickr(person: str, query: str) -> list[dict]:
    import os
    key = os.getenv("FLICKR_API_KEY", "").strip()
    if not key:
        return []
    data = _get("https://www.flickr.com/services/rest/", {
        "method": "flickr.photos.search", "api_key": key, "text": f"{person} {query}",
        "content_type": 1, "media": "photos", "per_page": PER_SOURCE_LIMIT,
        "extras": "url_o,url_l,owner_name,date_taken,license", "format": "json", "nojsoncallback": 1
    })
    result = []
    for photo in ((data.get("photos") or {}).get("photo") or []):
        url = photo.get("url_o") or photo.get("url_l")
        if not url:
            continue
        pid = photo.get("id")
        result.append({"source": "Flickr", "title": _clean(photo.get("title"), 300), "url": url,
                       "thumburl": url, "mime": "image/unknown", "creator": _clean(photo.get("ownername"), 250),
                       "license": str(photo.get("license") or "Unknown / not supplied"),
                       "source_url": f"https://www.flickr.com/photos/{photo.get('owner')}/{pid}", "query": query})
    return result


def build_person_queries(person: str, scene_narration: str = "") -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z'-]{3,}", scene_narration)
    stop = {"this", "that", "with", "from", "they", "their", "were", "when", "what", "then", "into", "about", "because", "after", "before", "would", "could", "there", "have", "been", "while", "story", "person", "people", "life"}
    useful = []
    for word in words:
        if word.lower() not in stop and word.lower() not in person.lower().split() and word.lower() not in useful:
            useful.append(word.lower())
    queries = ["photograph", "portrait", "interview", "event", "historical photo", "footage"]
    if useful:
        queries.insert(0, " ".join(useful[:3]))
    return queries


def search_person_media(person: str, scene_narration: str = "") -> list[dict]:
    """Return a cached, deduplicated candidate pool across configured sources.

    The old implementation repeated up to 7 searches per source for every
    scene, which quickly triggered Wikimedia 429s and made the person layer
    slower without materially improving identity coverage. One pool per person
    is enough because Gemini performs the scene-specific selection.
    """
    person = _clean(person, 180)
    cache_key = person.lower()
    if cache_key in _PERSON_POOL_CACHE:
        candidates = _PERSON_POOL_CACHE[cache_key]
        print(f"      🔎 Person media pool: {len(candidates)} cached candidates")
        return list(candidates)

    candidates = []
    seen = set()
    for query in build_person_queries(person, scene_narration):
        for source_fn in (_commons, _archive, _europeana, _flickr):
            for item in source_fn(person, query):
                key = item.get("source_url") or item.get("url") or item.get("title")
                if key and key not in seen:
                    seen.add(key)
                    candidates.append(item)
    _PERSON_POOL_CACHE[cache_key] = list(candidates)
    print(f"      🔎 Person media pool: {len(candidates)} candidates across available sources")
    return list(candidates)
