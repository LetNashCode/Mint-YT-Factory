"""
main.py
Educational YouTube Shorts Pipeline

Version 7.1

Production:
- 7 scenes
- 2 visuals per scene
- 14 images total
- 45 seconds
- Next-Short teaser
- Subscription/return strategy
- Research references in description
- Research sources clearly marked as unverified
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


# ==========================================================================
# CONFIG
# ==========================================================================

def load_config():

    with open(
        "config.yaml",
        "r",
        encoding="utf-8",
    ) as f:

        return yaml.safe_load(f)


# ==========================================================================
# YOUTUBE METADATA
# ==========================================================================

def build_title_description(script):

    title = script.get(
        "title",
        "Educational Short",
    )

    description_parts = []

    # ----------------------------------------------------------------------
    # MAIN DESCRIPTION
    # ----------------------------------------------------------------------

    description = str(
        script.get(
            "description",
            "",
        )
    ).strip()

    if description:

        description_parts.append(
            description
        )

    # ----------------------------------------------------------------------
    # NEXT SHORT
    # ----------------------------------------------------------------------

    next_short = script.get(
        "next_short",
        {},
    )

    if isinstance(
        next_short,
        dict,
    ):

        next_topic = str(
            next_short.get(
                "topic",
                "",
            )
        ).strip()

        teaser = str(
            next_short.get(
                "teaser",
                "",
            )
        ).strip()

        reason = str(
            next_short.get(
                "why_viewers_should_return",
                "",
            )
        ).strip()

        cta = str(
            next_short.get(
                "subscription_cta",
                "",
            )
        ).strip()

        if next_topic:

            next_section = (
                "🔮 NEXT SHORT\n\n"
                f"Coming next: {next_topic}"
            )

            if teaser:

                next_section += (
                    f"\n{teaser}"
                )

            if reason:

                next_section += (
                    f"\n\n{reason}"
                )

            if cta:

                next_section += (
                    f"\n\n{cta}"
                )

            description_parts.append(
                next_section
            )

    # ----------------------------------------------------------------------
    # RESEARCH REFERENCES
    # ----------------------------------------------------------------------

    research_sources = script.get(
        "research_sources",
        [],
    )

    if isinstance(
        research_sources,
        list,
    ) and research_sources:

        research_lines = [

            "📚 RESEARCH & FURTHER READING",

            "",

            "References related to the scientific topics "
            "discussed in this Short:"
        ]

        valid_source_count = 0

        for source in research_sources:

            if not isinstance(
                source,
                dict,
            ):
                continue

            source_title = str(
                source.get(
                    "title",
                    "",
                )
            ).strip()

            authors = str(
                source.get(
                    "authors",
                    "",
                )
            ).strip()

            organization = str(
                source.get(
                    "organization",
                    "",
                )
            ).strip()

            url = str(
                source.get(
                    "url",
                    "",
                )
            ).strip()

            claim = str(
                source.get(
                    "claim_supported",
                    "",
                )
            ).strip()

            verified = bool(
                source.get(
                    "verified",
                    False,
                )
            )

            if not source_title:

                continue

            valid_source_count += 1

            line = (
                f"{valid_source_count}. "
                f"{source_title}"
            )

            if authors:

                line += (
                    f" — {authors}"
                )

            if organization:

                line += (
                    f" — {organization}"
                )

            if url:

                line += (
                    f"\n{url}"
                )

            if claim:

                line += (
                    f"\nRelated claim: {claim}"
                )

            if not verified:

                line += (
                    "\nReference pending verification."
                )

            research_lines.append(
                line
            )

        if valid_source_count:

            description_parts.append(
                "\n".join(
                    research_lines
                )
            )

    # ----------------------------------------------------------------------
    # HASHTAGS
    # ----------------------------------------------------------------------

    tags = script.get(
        "tags",
        [],
    )

    if isinstance(
        tags,
        list,
    ):

        hashtags = " ".join(

            "#" + str(tag)
            .strip()
            .replace(" ", "")
            .replace("#", "")

            for tag in tags

            if str(tag).strip()
        )

        if hashtags:

            description_parts.append(
                hashtags
            )

    # ----------------------------------------------------------------------
    # FINAL DESCRIPTION
    # ----------------------------------------------------------------------

    final_description = "\n\n".join(
        description_parts
    ).strip()

    return (
        str(title)[:100],
        final_description[:5000],
    )


# ==========================================================================
# PIPELINE
# ==========================================================================

def run(
    dry_run=False,
):

    config = load_config()

    # ----------------------------------------------------------------------
    # TOPIC
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🧠 GENERATING TOPIC")
    print("=" * 80)

    topic = get_next_topic()

    print(topic)

    # ----------------------------------------------------------------------
    # SCRIPT
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("✍️ GENERATING SCRIPT")
    print("=" * 80)

    script = generate_script(
        topic,
        config,
    )

    print(
        f"Scenes: "
        f"{len(script.get('scene_plan', []))}"
    )

    print(
        "Images: "
        f"{script.get('image_generation', {}).get('total_images', 14)}"
    )

    print(
        "Next Short: "
        f"{script.get('next_short', {}).get('topic', 'Not specified')}"
    )

    print(
        "Research candidates: "
        f"{len(script.get('research_sources', []))}"
    )

    # ----------------------------------------------------------------------
    # WORK DIRECTORY
    # ----------------------------------------------------------------------

    run_id = str(
        int(
            time.time()
        )
    )

    workdir = os.path.join(
        "output",
        run_id,
    )

    os.makedirs(
        workdir,
        exist_ok=True,
    )

    # ----------------------------------------------------------------------
    # TTS
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # IMAGES
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # MUSIC
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # SFX
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("💥 SOUND EFFECTS DISABLED")
    print("=" * 80)

    sfx = []

    # ----------------------------------------------------------------------
    # FINAL VIDEO
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # DRY RUN
    # ----------------------------------------------------------------------

    if dry_run:

        print("=" * 80)
        print("✅ DRY RUN COMPLETE")
        print("=" * 80)

        print(
            f"Video: {final_video}"
        )

        print("=" * 80)

        return

    # ----------------------------------------------------------------------
    # UPLOAD CHECK
    # ----------------------------------------------------------------------

    if not config["upload"]["auto_upload"]:

        print(
            "Auto upload disabled."
        )

        return

    # ----------------------------------------------------------------------
    # BUILD YOUTUBE METADATA
    # ----------------------------------------------------------------------

    title, description = build_title_description(
        script
    )

    print("=" * 80)
    print("📝 YOUTUBE METADATA")
    print("=" * 80)

    print(
        f"Title: {title}"
    )

    print(
        f"Description length: "
        f"{len(description)} characters"
    )

    print("=" * 80)

    # ----------------------------------------------------------------------
    # UPLOAD
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🚀 UPLOADING TO YOUTUBE")
    print("=" * 80)

    upload_video(
        final_video,
        title,
        description,
        config,
    )

    # ----------------------------------------------------------------------
    # COMPLETE
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🎉 PIPELINE COMPLETE")
    print("=" * 80)


# ==========================================================================
# ENTRY POINT
# ==========================================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    args = parser.parse_args()

    run(
        args.dry_run
    )