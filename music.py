"""
music.py
Random local background music selector
"""

import glob
import os
import random

MUSIC_FOLDER = os.path.join(
    "assets",
    "music",
)

LAST_TRACK_FILE = os.path.join(
    MUSIC_FOLDER,
    ".last_track",
)


def download_music(script, workdir):

    if not os.path.isdir(MUSIC_FOLDER):

        print("=" * 80)
        print("⚠️ Music folder not found.")
        print(MUSIC_FOLDER)
        print("=" * 80)

        return None

    tracks = glob.glob(
        os.path.join(
            MUSIC_FOLDER,
            "*.mp3",
        )
    )

    if not tracks:

        print("=" * 80)
        print("⚠️ No music files found.")
        print("=" * 80)

        return None

    last_track = None

    if os.path.exists(LAST_TRACK_FILE):

        try:

            with open(
                LAST_TRACK_FILE,
                "r",
                encoding="utf-8",
            ) as f:

                last_track = f.read().strip()

        except Exception:

            last_track = None

    available_tracks = [
        track
        for track in tracks
        if track != last_track
    ]

    if not available_tracks:

        available_tracks = tracks

    music = random.choice(
        available_tracks
    )

    try:

        with open(
            LAST_TRACK_FILE,
            "w",
            encoding="utf-8",
        ) as f:

            f.write(music)

    except Exception:

        pass

    print("=" * 80)
    print("🎵 SELECTED BACKGROUND MUSIC")
    print(os.path.basename(music))
    print("=" * 80)

    return music
