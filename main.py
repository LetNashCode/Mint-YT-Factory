"""
main.py
Mint-YT-Factory

Version 10.1

Research-first production pipeline.

FLOW:

Previous video's next_short
→ Topic
→ Verified research
→ Research-backed script
→ Claim verification
→ HARD VERIFICATION GATE
→ Save verified artifacts
→ TTS
→ Images
→ Music
→ Video
→ Verified citations
→ YouTube upload
→ Save NEW next_short
→ Commit current topic

IMPORTANT:

The current topic is NOT committed until the complete pipeline
successfully uploads the video.

If anything fails before upload:
- Current topic remains pending.
- The next_short remains available.
- The current topic can be retried safely.

SCIENTIFIC SAFETY:

Research verification and claim verification are independent gates.

Research must be VERIFIED before script generation.

The generated script must PASS claim verification before
any production asset is generated.

A failed claim verification ALWAYS stops the pipeline.

No TTS.
No images.
No music.
No video.
No upload.

until claim verification passes.
"""

import argparse
import json
import os
import time

import yaml

from topics import (
    get_next_topic,
    save_next_short,
    commit_topic,
)

from research import research_topic

from generate_script import generate_script

from verify_claims import (
    verify_script_claims,
    claims_are_verified,
)

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
# SAVE JSON
# ==========================================================================

def save_json(
    data,
    path,
):

    directory = os.path.dirname(
        path
    )

    if directory:

        os.makedirs(
            directory,
            exist_ok=True,
        )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )


# ==========================================================================
# RESEARCH DESCRIPTION
# ==========================================================================

def build_research_section(
    script
):

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
    # CLAIM VERIFICATION
    # ----------------------------------------------------------------------

    verification = script.get(
        "claim_verification",
        {},
    )

    if not isinstance(
        verification,
        dict,
    ):

        raise RuntimeError(
            "Cannot publish: "
            "claim verification record is missing."
        )

    if verification.get(
        "verified"
    ) is not True:

        raise RuntimeError(
            "Cannot publish: "
            "claim verification failed."
        )

    if verification.get(
        "overall_status"
    ) != "PASS":

        raise RuntimeError(
            "Cannot publish: "
            "claim verification status is not PASS."
        )

    description_parts.append(
        "🔬 Scientific claim verification: PASSED"
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
# NEXT SHORT EXTRACTION
# ==========================================================================

def get_next_short_topic(
    script
):

    next_short = script.get(
        "next_short",
        {},
    )

    if not isinstance(
        next_short,
        dict,
    ):

        return ""

    topic = str(
        next_short.get(
            "topic",
            "",
        )
    ).strip()

    return topic


# ==========================================================================
# HARD RESEARCH GATE
# ==========================================================================

def enforce_research_gate(
    research,
):

    if not isinstance(
        research,
        dict,
    ):

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "research package is invalid."
        )

    if research.get(
        "verified"
    ) is not True:

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "research package is not VERIFIED."
        )

    if research.get(
        "status"
    ) != "VERIFIED":

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "research status is not VERIFIED."
        )

    sources = research.get(
        "sources",
        [],
    )

    if not isinstance(
        sources,
        list,
    ):

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "research sources are invalid."
        )

    if len(sources) < 2:

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "fewer than 2 verified research sources."
        )

    for index, source in enumerate(
        sources,
        start=1,
    ):

        if not isinstance(
            source,
            dict,
        ):

            raise RuntimeError(
                f"PIPELINE STOPPED: "
                f"research source {index} is invalid."
            )

        if source.get(
            "verified"
        ) is not True:

            raise RuntimeError(
                f"PIPELINE STOPPED: "
                f"research source {index} is not verified."
            )

        if source.get(
            "evidence_verified"
        ) is not True:

            raise RuntimeError(
                f"PIPELINE STOPPED: "
                f"research source {index} is not evidence verified."
            )

        abstract = str(
            source.get(
                "abstract",
                "",
            )
        ).strip()

        if not abstract:

            raise RuntimeError(
                f"PIPELINE STOPPED: "
                f"research source {index} has no evidence abstract."
            )

    print(
        "✅ RESEARCH HARD GATE PASSED"
    )

    return True


# ==========================================================================
# HARD CLAIM VERIFICATION GATE
# ==========================================================================

def enforce_claim_verification_gate(
    script,
):

    verification = script.get(
        "claim_verification",
        {},
    )

    if not isinstance(
        verification,
        dict,
    ):

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "claim verification result is missing."
        )

    status = verification.get(
        "overall_status"
    )

    verified = (
        verification.get(
            "verified"
        )
        is True
    )

    if status != "PASS":

        print("=" * 80)
        print("❌ CLAIM VERIFICATION HARD GATE FAILED")
        print("=" * 80)

        print(
            f"Verification status: {status}"
        )

        unsupported = verification.get(
            "unsupported_claims",
            [],
        )

        warnings = verification.get(
            "warnings",
            [],
        )

        if unsupported:

            print(
                "\n❌ Unsupported / invalid claims:"
            )

            for item in unsupported:

                print(
                    f"  ❌ {item}"
                )

        if warnings:

            print(
                "\n⚠️ Uncertain claims:"
            )

            for item in warnings:

                print(
                    f"  ⚠️ {item}"
                )

        print("=" * 80)

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "scientific claim verification did not PASS."
        )

    if not verified:

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "claim verification status is PASS but "
            "verified flag is not True."
        )

    claims = verification.get(
        "claims",
        [],
    )

    if not isinstance(
        claims,
        list,
    ):

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "claim verification claims are invalid."
        )

    # Every returned claim must be supported.
    for claim in claims:

        if not isinstance(
            claim,
            dict,
        ):

            raise RuntimeError(
                "PIPELINE STOPPED: "
                "claim verification contains an invalid claim."
            )

        claim_status = str(
            claim.get(
                "status",
                "",
            )
        ).strip().lower()

        if claim_status != "supported":

            raise RuntimeError(
                "PIPELINE STOPPED: "
                "claim verification contains a non-supported claim."
            )

    print("=" * 80)
    print("✅ CLAIM VERIFICATION HARD GATE PASSED")
    print("=" * 80)

    print(
        f"Verified claims: {len(claims)}"
    )

    return True


# ==========================================================================
# FINAL PUBLISHING SAFETY GATE
# ==========================================================================

def enforce_publishing_gate(
    script,
):

    publishing = script.get(
        "publishing",
        {},
    )

    if not isinstance(
        publishing,
        dict,
    ):

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "publishing metadata is missing."
        )

    if publishing.get(
        "research_verified"
    ) is not True:

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "script is not marked research verified."
        )

    if publishing.get(
        "citations_ready"
    ) is not True:

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "citations are not ready."
        )

    if not claims_are_verified(
        script
    ):

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "claims are not verified."
        )

    print(
        "✅ FINAL SCIENTIFIC PUBLISHING GATE PASSED"
    )

    return True


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
    print("🧠 SELECTING TOPIC")
    print("=" * 80)

    topic = get_next_topic()

    if not topic:

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "no topic available."
        )

    print(
        f"🎯 CURRENT TOPIC: {topic}"
    )

    # ----------------------------------------------------------------------
    # VERIFIED RESEARCH
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🔬 RESEARCHING TOPIC")
    print("=" * 80)

    research = research_topic(
        topic
    )

    enforce_research_gate(
        research
    )

    verified_sources = research.get(
        "sources",
        [],
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
            f"  source_{index}: "
            f"{source.get('title', '')}"
        )

    # ----------------------------------------------------------------------
    # SCRIPT
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("✍️ GENERATING RESEARCH-BACKED SCRIPT")
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
        "Verified research sources: "
        f"{len(script.get('research_sources', []))}"
    )

    next_short_topic = get_next_short_topic(
        script
    )

    print(
        "Next Short: "
        f"{next_short_topic or 'Not specified'}"
    )

    # ----------------------------------------------------------------------
    # REQUIRE NEXT SHORT
    # ----------------------------------------------------------------------

    if not next_short_topic:

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "script did not provide next_short.topic."
        )

    # ----------------------------------------------------------------------
    # CLAIM VERIFICATION
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🧪 VERIFYING IMPORTANT FACTUAL CLAIMS")
    print("=" * 80)

    script = verify_script_claims(
        script,
        research,
    )

    # ----------------------------------------------------------------------
    # HARD CLAIM GATE
    #
    # NOTHING BELOW THIS POINT MAY RUN IF CLAIM VERIFICATION FAILS.
    # ----------------------------------------------------------------------

    enforce_claim_verification_gate(
        script
    )

    # ----------------------------------------------------------------------
    # FINAL SCIENTIFIC SAFETY GATE
    # ----------------------------------------------------------------------

    enforce_publishing_gate(
        script
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

    print("=" * 80)
    print("💾 SAVING VERIFIED PIPELINE ARTIFACTS")
    print("=" * 80)

    # ----------------------------------------------------------------------
    # SAVE RESEARCH
    # ----------------------------------------------------------------------

    research_path = os.path.join(
        workdir,
        "research.json",
    )

    save_json(
        research,
        research_path,
    )

    print(
        f"Research saved: {research_path}"
    )

    # ----------------------------------------------------------------------
    # SAVE VERIFIED SCRIPT
    # ----------------------------------------------------------------------

    script_path = os.path.join(
        workdir,
        "script.json",
    )

    save_json(
        script,
        script_path,
    )

    print(
        f"Verified script saved: {script_path}"
    )

    # ----------------------------------------------------------------------
    # SAVE CLAIM VERIFICATION
    # ----------------------------------------------------------------------

    verification_path = os.path.join(
        workdir,
        "claim_verification.json",
    )

    save_json(
        script.get(
            "claim_verification",
            {},
        ),
        verification_path,
    )

    print(
        f"Claim verification saved: "
        f"{verification_path}"
    )

    # ----------------------------------------------------------------------
    # PRODUCTION START
    #
    # IMPORTANT:
    #
    # From this point onward the script has already passed:
    #
    # 1. Research verification
    # 2. Evidence verification
    # 3. Script generation validation
    # 4. Claim verification
    # 5. Citation validation
    #
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🎬 SCIENTIFIC VERIFICATION COMPLETE")
    print("=" * 80)

    print(
        "Research: VERIFIED"
    )

    print(
        "Claims: VERIFIED"
    )

    print(
        "Citations: READY"
    )

    print(
        "Production may proceed."
    )

    print("=" * 80)

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

    if not os.path.exists(
        final_video
    ):

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "final video was not created."
        )

    print(
        f"✅ Video created: "
        f"{final_video}"
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
            f"Next Short remains pending: "
            f"{next_short_topic}"
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
            "⚠️ Auto upload disabled."
        )

        print(
            "Current topic will NOT be committed."
        )

        print(
            f"Next Short remains: "
            f"{next_short_topic}"
        )

        return

    # ----------------------------------------------------------------------
    # FINAL PRE-UPLOAD GATE
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🔐 FINAL PRE-UPLOAD SCIENTIFIC SAFETY CHECK")
    print("=" * 80)

    enforce_research_gate(
        research
    )

    enforce_claim_verification_gate(
        script
    )

    enforce_publishing_gate(
        script
    )

    print(
        "✅ PRE-UPLOAD SAFETY CHECK PASSED"
    )

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

    print(
        "Scientific claims: VERIFIED"
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

    print(
        "✅ YouTube upload completed."
    )

    # ----------------------------------------------------------------------
    # SAVE NEXT SHORT
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🔗 SAVING NEXT SHORT")
    print("=" * 80)

    saved_next = save_next_short(
        next_short_topic
    )

    if not saved_next:

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "YouTube upload succeeded, but the "
            "next_short topic could not be saved."
        )

    print(
        f"✅ Next Short queued: "
        f"{next_short_topic}"
    )

    # ----------------------------------------------------------------------
    # COMMIT CURRENT TOPIC
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("📌 COMMITTING CURRENT TOPIC")
    print("=" * 80)

    commit_topic(
        topic
    )

    # ----------------------------------------------------------------------
    # COMPLETE
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🎉 VERIFIED PIPELINE COMPLETE")
    print("=" * 80)

    print(
        f"Published: {topic}"
    )

    print(
        f"Next run will start with: "
        f"{next_short_topic}"
    )

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