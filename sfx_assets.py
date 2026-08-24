"""Automatic real-SFX asset bootstrap for Mint-YT-Factory.

Downloads a small curated set of Mixkit SFX on demand into assets/sfx.
Mixkit's Sound Effects Free License permits commercial and YouTube use.
The downloader intentionally discovers the official download links from the
Mixkit category pages instead of hard-coding fragile CDN URLs.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

SFX_ROOT = Path(__file__).resolve().parent / "assets" / "sfx"
USER_AGENT = "Mint-YT-Factory-SFX-Bootstrap/1.0"
TIMEOUT = 20

# Category -> number of real effects to cache. Keep the pack deliberately small.
CATEGORIES = {
    "whoosh": ("https://mixkit.co/free-sound-effects/whoosh/", 4),
    "impact": ("https://mixkit.co/free-sound-effects/impact/", 3),
    "interface": ("https://mixkit.co/free-sound-effects/interface/", 3),
    "magic": ("https://mixkit.co/free-sound-effects/magic/", 2),
    "misc": ("https://mixkit.co/free-sound-effects/misc/", 3),
    "correct": ("https://mixkit.co/free-sound-effects/correct/", 2),
    "spin": ("https://mixkit.co/free-sound-effects/spin/", 2),
}


def _safe_name(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("._-")
    return value[:90] or "sfx"


def _discover_downloads(html: str, base_url: str):
    # Mixkit exposes the download targets in the rendered page markup.
    found = []
    for match in re.findall(r'(?:href|data-url|data-download-url)=["\']([^"\']+)["\']', html, re.I):
        url = urljoin(base_url, match)
        if re.search(r"\.(?:mp3|wav)(?:\?|$)", url, re.I):
            if url not in found:
                found.append(url)
    # Also catch JSON-escaped URLs when the page embeds the download object.
    for match in re.findall(r'https?:\\?/\\?/[^"\'\\ ]+?\.(?:mp3|wav)(?:\?[^"\'\\ ]*)?', html, re.I):
        url = match.replace("\\/", "/")
        if url not in found:
            found.append(url)
    return found


def _download(url: str, path: Path):
    tmp = path.with_suffix(path.suffix + ".part")
    with requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, stream=True) as response:
        response.raise_for_status()
        with open(tmp, "wb") as handle:
            for chunk in response.iter_content(64 * 1024):
                if chunk:
                    handle.write(chunk)
    tmp.replace(path)


def ensure_sfx_assets(force: bool = False) -> dict:
    """Ensure the real curated SFX pack exists. Returns category->paths."""
    SFX_ROOT.mkdir(parents=True, exist_ok=True)
    result = {}
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    for category, (page, wanted) in CATEGORIES.items():
        folder = SFX_ROOT / category
        folder.mkdir(parents=True, exist_ok=True)
        existing = sorted([*folder.glob("*.mp3"), *folder.glob("*.wav")])
        if not force and len(existing) >= wanted:
            result[category] = [str(p) for p in existing[:wanted]]
            continue

        try:
            response = session.get(page, timeout=TIMEOUT)
            response.raise_for_status()
            urls = _discover_downloads(response.text, page)
            downloaded = list(existing)
            for index, url in enumerate(urls):
                if len(downloaded) >= wanted:
                    break
                name = _safe_name(Path(url.split("?", 1)[0]).stem)
                if not name:
                    name = f"{category}_{index+1}"
                path = folder / f"{name}.mp3"
                if path.exists() and path.stat().st_size > 1024:
                    if path not in downloaded:
                        downloaded.append(path)
                    continue
                try:
                    _download(url, path)
                    if path.stat().st_size > 1024:
                        downloaded.append(path)
                except Exception as error:
                    print(f"⚠️ SFX download skipped: {category}/{name}: {error}")
            result[category] = [str(p) for p in downloaded[:wanted]]
            print(f"🔊 SFX assets: {category} {len(result[category])}/{wanted}")
        except Exception as error:
            print(f"⚠️ SFX category unavailable: {category}: {error}")
            result[category] = [str(p) for p in existing[:wanted]]
        time.sleep(0.25)

    total = sum(len(v) for v in result.values())
    print(f"🔊 Real SFX pack ready: {total} assets in {SFX_ROOT}")
    return result


if __name__ == "__main__":
    ensure_sfx_assets()
