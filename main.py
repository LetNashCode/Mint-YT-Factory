"""
main.py
Educational YouTube Shorts Pipeline
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
from sfx import download_sfx
from assemble import assemble_video
from upload_youtube import upload_video


def load_config():

    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_title_description(script):

    title = script["title"]

    description = "\n\n".join([
        script["hook"],
        script["question"],
        script["explanation"],
        script["example"],
        script["mindblowing_fact"],
        script["ending"],
    ])

    if script.get("tags"):

        description += "\n\n"

        description += " ".join(
            "#" + tag.replace(" ", "")
            for tag in script["tags"]
        )

    return (
        title[:100],
        description[:5000],
    )


def run(dry_run=False):

    config = load_config()

    print("=" * 80)
    print("🧠 GENERATING TOPIC")
    print("=" * 80)

    topic = get_next_topic()

    print(topic)

    print("=" * 80)
    print("✍️ GENERATING SCRIPT")
    print("=" * 80)

    script = generate_script(
        topic,
        config,
    )

    run_id = str(int(time.time()))

    workdir = os.path.join(
        "output",
        run_id,
    )

    os.makedirs(
        workdir,
        exist_ok=True,
    )

    print("=" * 80)
    print("🎙️ GENERATING NARRATION")
    print("=" * 80)

    audio = synthesize_script(
        script,
        config,
        os.path.join(
            workdir,
            "audio",
        ),
    )

    print("=" * 80)
    print("🖼️ GENERATING VISUALS")
    print("=" * 80)

    visuals = generate_images(
        script,
        os.path.join(
            workdir,
            "visuals",
        ),
        config,
    )

    print("=" * 80)
    print("🎵 DOWNLOADING MUSIC")
    print("=" * 80)

    music = download_music(
        script,
        os.path.join(
            workdir,
            "music",
        ),
    )

    print("=" * 80)
    print("💥 DOWNLOADING SOUND EFFECTS")
    print("=" * 80)

    sfx = download_sfx(
        script,
        os.path.join(
            workdir,
            "sfx",
        ),
    )

    final_video = os.path.join(
        workdir,
        "final.mp4",
    )

    print("=" * 80)
    print("🎬 RENDERING VIDEO")
    print("=" * 80)

    assemble_video(
        script,
        audio,
        visuals,
        music,
        sfx,
        config,
        final_video,
    )

    if dry_run:

        print("=" * 80)
        print("✅ DRY RUN COMPLETE")
        print(final_video)
        print("=" * 80)
        return

    if not config["upload"]["auto_upload"]:

        print("Auto upload disabled.")

        return

    title, description = build_title_description(
        script
    )

    print("=" * 80)
    print("🚀 UPLOADING TO YOUTUBE")
    print("=" * 80)

    upload_video(
        final_video,
        title,
        description,
        config,
    )

    print("=" * 80)
    print("🎉 PIPELINE COMPLETE")
    print("=" * 80)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    args = parser.parse_args()

    run(args.dry_run)
