"""Background music cache/selector for Emotional Reels.

The repository owns the cache under assets/music/. New tracks can be supplied
through EMOTIONAL_REEL_MUSIC_URLS as comma/newline separated direct audio URLs.
Downloaded files are validated and left in the repo working tree so the
workflow can commit them for reuse on later runs.
"""

import hashlib
import json
import os
import random
import subprocess
from pathlib import Path

MUSIC_FOLDER = Path("assets/music")
CATALOG_FILE = MUSIC_FOLDER / "music_catalog.json"
HISTORY_FILE = MUSIC_FOLDER / "music_history.json"
MAX_HISTORY = 20
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}


def _read_json(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"⚠️ Could not read {path}: {exc}")
    return default


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


SEED_MUSIC_PAGES = [
    "https://pixabay.com/music/ambient-emotional-ambient-piece-with-slow-cinematic-textures-370142/",
    "https://pixabay.com/music/ambient-solitude-dark-ambient-music-354468/",
    "https://pixabay.com/music/ambient-dark-ambient-soundscape-dreamscape-462864/",
    "https://pixabay.com/music/ambient-dark-ambient-emotions-music-259996/",
    "https://pixabay.com/music/ambient-celestial-drift-space-ambient-meditation-403503/",
    "https://pixabay.com/music/ambient-somber-constellations-ambient-364828/",
    "https://pixabay.com/music/ambient-ambient-space-cinematic-music-370754/",
    "https://pixabay.com/music/ambient-wizards-road-calm-magical-ambient-music-371783/",
    "https://pixabay.com/music/ambient-calm-relaxing-ambient-peaceful-background-music-382554/",
    "https://pixabay.com/music/ambient-inspiring-ambient-music-348379/",
    "https://pixabay.com/music/beats-lofi-chill-relaxing-beat-444098/",
    "https://pixabay.com/music/beats-soulful-future-134912/",
    "https://pixabay.com/music/beats-so-strong-motivation-234816/",
    "https://pixabay.com/music/world-groove-culture-inspiration-chill-cool-native-music-93679/",
    "https://pixabay.com/music/modern-classical-calm-piano-music-sentimental-background-intro-theme-269137/",
    "https://pixabay.com/music/beats-upbeat-lo-fi-chill-instrumental-music-royalty-free-195449/",
    "https://pixabay.com/music/upbeat-upbeat-indie-folk-60s-13449/",
    "https://pixabay.com/music/beats-chill-lofi-music-interior-lounge-256260/",
    "https://pixabay.com/music/main-title-dark-cinematic-thriller-249485/",
    "https://pixabay.com/music/solo-piano-ambient-piano-cinematic-background-521853/",
    "https://pixabay.com/music/ambient-emotional-piano-527470/",
]

def _direct_urls():
    raw = os.getenv("EMOTIONAL_REEL_MUSIC_URLS", "")
    return [x.strip() for x in raw.replace(",", "\n").splitlines() if x.strip()]

def _resolve_music_page(url):
    if "cdn.pixabay.com" in url and url.lower().endswith(".mp3"):
        return url
    import html
    import re
    import requests
    try:
        response = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        page = html.unescape(response.text).replace("\\/", "/")
        patterns = [
            r'https?://cdn\.pixabay\.com/(?:download/)?audio/[^"<>\\s]+?\.mp3(?:\\?[^"<>\\s]+)?',
            r'https?://cdn\.pixabay\.com/[^"<>\\s]+?\.mp3(?:\\?[^"<>\\s]+)?',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, page)
            if matches:
                return matches[0]
        print(f"⚠️ No direct MP3 URL found on music page: {url}")
        return None
    except Exception as exc:
        print(f"⚠️ Could not resolve music page: {url} — {exc}")
        return None

def _safe_name(url, index):
    from urllib.parse import urlparse
    name = Path(urlparse(url).path).name or f"track_{index:03d}.mp3"
    stem, ext = os.path.splitext(name)
    ext = ext.lower() if ext.lower() in ALLOWED_EXTENSIONS else ".mp3"
    clean = "".join(c if c.isalnum() or c in "-_." else "_" for c in stem).strip("._")
    return f"{clean or f'track_{index:03d}'}{ext}"


def _validate_audio(path):
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,duration,sample_rate",
            "-of", "json", str(path),
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if probe.returncode:
        return False
    try:
        streams = json.loads(probe.stdout).get("streams") or []
        duration = float(streams[0].get("duration") or 0)
        return bool(streams and duration >= 5.0 and path.stat().st_size >= 4096)
    except Exception:
        return False


def _download_new_tracks():
    urls = _direct_urls()
    if not urls:
        urls = list(SEED_MUSIC_PAGES)
    resolved = []
    for url in urls:
        direct = _resolve_music_page(url)
        if direct:
            resolved.append(direct)
    urls = resolved
    if not urls:
        return []

    import requests

    MUSIC_FOLDER.mkdir(parents=True, exist_ok=True)
    catalog = _read_json(CATALOG_FILE, {"tracks": []})
    known = {str(x.get("sha256")) for x in catalog.get("tracks", []) if x.get("sha256")}
    downloaded = []

    for index, url in enumerate(urls, 1):
        try:
            response = requests.get(url, stream=True, timeout=(15, 60), headers={"User-Agent": "Mint-YT-Factory/1.0"})
            response.raise_for_status()
            temp = MUSIC_FOLDER / f".download_{index}.tmp"
            with temp.open("wb") as handle:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        handle.write(chunk)

            digest = hashlib.sha256(temp.read_bytes()).hexdigest()
            if digest in known:
                temp.unlink(missing_ok=True)
                print(f"🎵 Music already cached: {digest[:12]}")
                continue

            destination = MUSIC_FOLDER / _safe_name(url, index)
            if destination.exists():
                destination = MUSIC_FOLDER / f"{destination.stem}_{digest[:8]}{destination.suffix}"
            temp.replace(destination)

            if not _validate_audio(destination):
                destination.unlink(missing_ok=True)
                print(f"⚠️ Downloaded audio failed validation: {url}")
                continue

            catalog.setdefault("tracks", []).append({
                "id": digest[:16],
                "file": str(destination),
                "sha256": digest,
                "source_url": url,
            })
            known.add(digest)
            downloaded.append(destination)
            print(f"✅ Cached new music: {destination}")
        except Exception as exc:
            print(f"⚠️ Music download skipped: {url} — {exc}")

    _write_json(CATALOG_FILE, catalog)
    return downloaded


def _tracks():
    MUSIC_FOLDER.mkdir(parents=True, exist_ok=True)
    return [
        p for p in MUSIC_FOLDER.iterdir()
        if p.is_file()
        and p.suffix.lower() in ALLOWED_EXTENSIONS
        and not p.name.startswith(".")
        and _validate_audio(p)
    ]


def download_music(script, workdir):
    _download_new_tracks()
    tracks = _tracks()

    if not tracks:
        raise RuntimeError(
            "No usable background music exists in assets/music/. "
            "Add permitted audio files there or provide EMOTIONAL_REEL_MUSIC_URLS."
        )

    history = _read_json(HISTORY_FILE, [])
    recent = {str(x) for x in history[-MAX_HISTORY:]}
    available = [p for p in tracks if str(p) not in recent] or tracks
    music = random.choice(available)

    history.append(str(music))
    _write_json(HISTORY_FILE, history[-MAX_HISTORY:])

    print("=" * 80)
    print("🎵 SELECTED BACKGROUND MUSIC")
    print(music.name)
    print("=" * 80)
    return str(music)
