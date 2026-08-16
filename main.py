"""
main.py
Mint-YT-Factory

Version 8.0

Research-first production pipeline.

FLOW:
Topic
→ Verified research
→ Research-backed script
→ TTS
→ Images
→ Music
→ Video
→ Verified citations in description
→ YouTube upload
"""

import argparse
import os
import time
import yaml

from topics import get_next_topic
from research import research_topic
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
# RESEARCH DESCRIPTION
# ==========================================================================

def build_research_section(script):

    sources = script.get(
        "research_sources",
        [],
    )

    if not isinstance(
        sources,
        list,
    ) or not sources:

        raise RuntimeError(
            "Cannot build description: "
            "no verified research sources found."
        )

    # --------------------------------------------------------------
    # Map each source to the scenes that cite it.
    # --------------------------------------------------------------

    source_scene_map = {}

    for index, source in enumerate(
        sources,
        start=1,
    ):

        source_id = source.get(
            "source_id",
            f"source_{index}",
        )

        source_scene_map[
            source_id
        ] = []

    for scene in script.get(
        "scene_plan",
        [],
    ):

        scene_number = scene.get(
            "scene",
        )

        for source_id in scene.get(
            "source_ids",
            [],
        ):

            if source_id in source_scene_map:

                source_scene_map[
                    source_id
                ].append(
                    scene_number
                )

    lines = [

        "📚 RESEARCH & FURTHER READING",

        "",

        "This Short is based on verified "
        "scientific research sources:"
    ]

    for index, source in enumerate(
        sources,
        start=1,
    ):

        if source.get(
            "verified"
        ) is not True:

            raise RuntimeError(
                f"Source {index} is not verified. "
                "Publishing stopped."
            )

        title = str(
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

        journal = str(
            source.get(
                "journal",
                "",
            )
        ).strip()

        year = source.get(
            "year",
            "",
        )

        doi = str(
            source.get(
                "doi",
                "",
            )
        ).strip()

        url = str(
            source.get(
                "url",
                "",
            )
        ).strip()

        verification = str(
            source.get(
                "verification",
                "",
            )
        ).strip()

        source_id = source.get(
            "source_id",
            f"source_{index}",
        )

        scenes = source_scene_map.get(
            source_id,
            [],
        )

        if not title or not authors or not url:

            raise RuntimeError(
                f"Research source {index} "
                "is incomplete."
            )

        line = (
            f"{index}. {title}"
        )

        if authors:

            line += (
                f" — {authors}"
            )

        if journal:

            line += (
                f" — {journal}"
            )

        if year:

            line += (
                f" ({year})"
            )

        line += (
            f"\n{url}"
        )

        if doi:

            line += (
                f"\nDOI: {doi}"
            )

        if scenes:

            line += (
                "\nUsed for scenes: "
                + ", ".join(
                    str(x)
                    for x in scenes
                )
            )

        if verification:

            line += (
                f"\nVerification: {verification}"
            )

        lines.append(
            line
        )

    return "\n\n".join(
        lines
    )


# ==========================================================================
# YOUTUBE METADATA
# ==========================================================================

def build_title_description(
    script,
):

    title = str(
        script.get(
            "title",
            "Educational Short",
        )
    ).strip()

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
    # VERIFIED RESEARCH
    # ----------------------------------------------------------------------

    description_parts.append(
        build_research_section(
            script
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
        title[:100],
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
    # VERIFIED RESEARCH
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🔬 RESEARCHING TOPIC")
    print("=" * 80)

    research = research_topic(
        topic
    )

    if research.get(
        "verified"
    ) is not True:

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "research was not verified."
        )

    if research.get(
        "status"
    ) != "VERIFIED":

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "research status is not VERIFIED."
        )

    verified_sources = research.get(
        "sources",
        [],
    )

    if len(
        verified_sources
    ) < 2:

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "fewer than 2 verified sources."
        )

    print(
        f"✅ VERIFIED SOURCES: "
        f"{len(verified_sources)}"
    )

    for index, source in enumerate(
        verified_sources,
        start=1,
    ):

        print(
            f"  {index}. "
            f"{source.get('title', '')}"
        )

    # ----------------------------------------------------------------------
    # SCRIPT
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("✍️ GENERATING VERIFIED SCRIPT")
    print("=" * 80)

    script = generate_script(
        topic,
        config,
        research,
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
        "Verified research sources: "
        f"{len(script.get('research_sources', []))}"
    )

    # ----------------------------------------------------------------------
    # FINAL RESEARCH SAFETY CHECK
    # ----------------------------------------------------------------------

    if script.get(
        "publishing",
        {}
    ).get(
        "research_verified"
    ) is not True:

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "script is not marked research verified."
        )

    if script.get(
        "publishing",
        {}
    ).get(
        "citations_ready"
    ) is not True:

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "citations are not ready."
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
    # SAVE RESEARCH
    # ----------------------------------------------------------------------

    research_path = os.path.join(
        workdir,
        "research.json",
    )

    import json

    with open(
        research_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            research,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(
        f"Research saved: "
        f"{research_path}"
    )

    # ----------------------------------------------------------------------
    # SAVE SCRIPT
    # ----------------------------------------------------------------------

    script_path = os.path.join(
        workdir,
        "script.json",
    )

    with open(
        script_path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            script,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(
        f"Script saved: "
        f"{script_path}"
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

        print(
            "No YouTube upload performed."
        )

        print("=" * 80)

        return

    # ----------------------------------------------------------------------
    # UPLOAD CHECK
    # ----------------------------------------------------------------------

    if not config[
        "upload"
    ][
        "auto_upload"
    ]:

        print(
            "Auto upload disabled."
        )

        return

    # ----------------------------------------------------------------------
    # BUILD YOUTUBE METADATA
    # ----------------------------------------------------------------------

    title, description = (
        build_title_description(
            script
        )
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

    print(
        "Research citations: VERIFIED"
    )

    print("=" * 80)

    # ----------------------------------------------------------------------
    # UPLOAD
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🚀 UPLOADING VERIFIED SHORT TO YOUTUBE")
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
    print("🎉 VERIFIED PIPELINE COMPLETE")
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