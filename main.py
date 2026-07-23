"""
main.py
"""

import argparse
import os
import time
import yaml

from topics import get_next_topic
from generate_script import generate_script
from tts import synthesize_script
from generate_images import generate_images
from music import download_music
from assemble import assemble_video
from upload_youtube import upload_video


def load_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def build_title_description(script):
    title = script["title"]
    description = (
        script["hook"] + "\n\n"
        + script["story"] + "\n\n"
        + script["twist"] + "\n\n"
        + script["ending"]
    )
    return title[:100], description[:5000]


def run(dry_run=False):
    config = load_config()

    topic = get_next_topic()
    print("Topic:", topic)

    script = generate_script(topic, config)

    run_id = str(int(time.time()))
    workdir = os.path.join("output", run_id)

    os.makedirs(workdir, exist_ok=True)

    audio = synthesize_script(script, config, os.path.join(workdir, "audio"))
    print("Generating Whisper timestamps...")
    
    print("=" * 80)
    print("🎨 Generating AI Images...")
    print("=" * 80)

    visuals = generate_images(
        script,
        os.path.join(workdir, "visuals"),
    )

    print("=" * 80)
    print("🎵 Downloading Background Music...")
    print("=" * 80)

    music = download_music(
        script,
        os.path.join(workdir, "music"),
    )

    final_video = os.path.join(workdir, "final.mp4")

    assemble_video(
        script,
        audio,
        visuals,
        music,
        config,
        final_video,
    )

    if dry_run or not config["upload"]["auto_upload"]:
        print("Dry run.")
        return

    title, description = build_title_description(script)

    upload_video(
        final_video,
        title,
        description,
        config,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run(args.dry_run)
