"""
main.py
Mint-YT-Factory

Version 10.2

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
→ Final scientific safety check
→ YouTube upload
→ Save NEW next_short
→ Commit current topic

IMPORTANT:

The current topic is NOT committed until the complete pipeline
successfully uploads the video.

SCIENTIFIC SAFETY:

Research verification and claim verification are independent gates.

Research must be VERIFIED before script generation.

The generated script must PASS claim verification before
production assets are generated.

A failed claim verification ALWAYS stops the pipeline.

No TTS.
No images.
No music.
No video.
No upload.

until claim verification passes.

Version 10.2 fixes:

- Research gate now uses evidence_text.
- Research gate validates evidence_available/evidence_verified.
- Research gate validates minimum evidence length.
- --dry-run stops before TTS/images/music/video.
- Final pre-upload scientific gates remain active.
- Post-upload next_short handling is explicit.
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

MIN_EVIDENCE_CHARACTERS = 120


# ==========================================================================
# CONFIG LOADER
# ==========================================================================

def load_config():

    with open(
        "config.yaml",
        "r",
        encoding="utf-8",
    ) as f:

        config = yaml.safe_load(f)

    if not isinstance(
        config,
        dict,
    ):

        raise RuntimeError(
            "config.yaml did not return a valid configuration."
        )

    return config


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

        if not isinstance(
            scene,
            dict,
        ):

            continue

        scene_number = scene.get(
            "scene",
        )

        source_ids = scene.get(
            "source_ids",
            [],
        )

        if not isinstance(
            source_ids,
            list,
        ):

            continue

        for source_id in source_ids:

            source_id = str(
                source_id
            ).strip()

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

        if not isinstance(
            source,
            dict,
        ):

            raise RuntimeError(
                f"Research source {index} is invalid."
            )

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
                f"Research source {index} is incomplete."
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

    if len(
        sources
    ) < 2:

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "fewer than 2 verified research sources."
        )

    usable_sources = 0

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

        if source.get(
            "evidence_available"
        ) is not True:

            raise RuntimeError(
                f"PIPELINE STOPPED: "
                f"research source {index} does not have "
                f"evidence_available=True."
            )

        evidence_text = str(
            source.get(
                "evidence_text",
                "",
            )
        ).strip()

        if not evidence_text:

            raise RuntimeError(
                f"PIPELINE STOPPED: "
                f"research source {index} has no evidence_text."
            )

        if len(
            evidence_text
        ) < MIN_EVIDENCE_CHARACTERS:

            raise RuntimeError(
                f"PIPELINE STOPPED: "
                f"research source {index} evidence_text is too short. "
                f"Minimum: {MIN_EVIDENCE_CHARACTERS} characters."
            )

        usable_sources += 1

    if usable_sources < 2:

        raise RuntimeError(
            "PIPELINE STOPPED: "
            "fewer than 2 usable evidence-verified sources."
        )

    print(
        "✅ RESEARCH HARD GATE PASSED"
    )

    print(
        f"   Usable evidence sources: {usable_sources}"
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

        source_ids = claim.get(
            "source_ids",
            [],
        )

        if not isinstance(
            source_ids,
            list,
        ) or not source_ids:

            raise RuntimeError(
                "PIPELINE STOPPED: "
                "supported claim has no source IDs."
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
# SAVE VERIFIED ARTIFACTS
# ==========================================================================

def save_verified_artifacts(
    workdir,
    research,
    script,
):

    os.makedirs(
        workdir,
        exist_ok=True,
    )

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

    # ----------------------------------------------------------------------
    # SAVE VERIFIED ARTIFACTS
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("💾 SAVING VERIFIED PIPELINE ARTIFACTS")
    print("=" * 80)

    save_verified_artifacts(
        workdir,
        research,
        script,
    )

    # ----------------------------------------------------------------------
    # DRY RUN
    #
    # IMPORTANT:
    #
    # A dry run stops here.
    #
    # It does NOT generate:
    #
    # - TTS
    # - images
    # - music
    # - video
    # - YouTube upload
    # - topic commit
    #
    # ----------------------------------------------------------------------

    if dry_run:

        print("=" * 80)
        print("✅ DRY RUN COMPLETE")
        print("=" * 80)

        print(
            "Research: VERIFIED"
        )

        print(
            "Claims: VERIFIED"
        )

        print(
            f"Verified artifacts: {workdir}"
        )

        print(
            f"Current topic remains pending: "
            f"{topic}"
        )

        print(
            f"Next Short remains pending: "
            f"{next_short_topic}"
        )

        print(
            "No TTS generated."
        )

        print(
            "No images generated."
        )

        print(
            "No music downloaded."
        )

        print(
            "No video rendered."
        )

        print(
            "No YouTube upload performed."
        )

        print(
            "Current topic NOT committed."
        )

        print("=" * 80)

        return

    # ----------------------------------------------------------------------
    # PRODUCTION START
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
    # AUTO UPLOAD CHECK
    # ----------------------------------------------------------------------

    if not config.get(
        "upload",
        {}
    ).get(
        "auto_upload",
        False,
    ):

        print("=" * 80)
        print("⚠️ AUTO UPLOAD DISABLED")
        print("=" * 80)

        print(
            "Current topic will NOT be committed."
        )

        print(
            f"Next Short remains: "
            f"{next_short_topic}"
        )

        print(
            f"Video available at: "
            f"{final_video}"
        )

        print("=" * 80)

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

    upload_result = upload_video(
        final_video,
        title,
        description,
        config,
    )

    print(
        "✅ YouTube upload completed."
    )

    if upload_result:

        print(
            f"Upload result: {upload_result}"
        )

    # ----------------------------------------------------------------------
    # SAVE NEXT SHORT
    #
    # IMPORTANT:
    #
    # The video is already published at this point.
    #
    # If this fails, DO NOT commit the current topic because the next
    # topic state has not been safely persisted.
    #
    # topics.py will be the next file we harden for crash-safe state.
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🔗 SAVING NEXT SHORT")
    print("=" * 80)

    try:

        saved_next = save_next_short(
            next_short_topic
        )

    except Exception as error:

        print(
            "❌ NEXT SHORT SAVE FAILED"
        )

        print(
            f"{type(error).__name__}: {error}"
        )

        print(
            "Current topic was NOT committed."
        )

        raise RuntimeError(
            "YouTube upload succeeded, but next_short "
            "could not be persisted safely."
        ) from error

    if not saved_next:

        raise RuntimeError(
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

    try:

        committed = commit_topic(
            topic
        )

    except Exception as error:

        print(
            "❌ CURRENT TOPIC COMMIT FAILED"
        )

        print(
            f"{type(error).__name__}: {error}"
        )

        raise RuntimeError(
            "YouTube upload and next_short save succeeded, "
            "but current topic commit failed."
        ) from error

    if committed is False:

        raise RuntimeError(
            "YouTube upload and next_short save succeeded, "
            "but current topic was not committed."
        )

    print(
        f"✅ Current topic committed: {topic}"
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

    print(
        f"Artifacts: {workdir}"
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
        help=(
            "Run research, script generation and claim verification "
            "only. No TTS, images, music, video or upload."
        ),
    )

    args = parser.parse_args()

    run(
        dry_run=args.dry_run
    )