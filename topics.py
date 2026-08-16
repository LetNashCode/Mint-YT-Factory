"""
topics.py
Mint-YT-Factory

Version 4.0

Research-first educational topic generator.

FLOW:

Previous video's next_short
        ↓
Pending topic queue
        ↓
Research
        ↓
Script
        ↓
Claim verification
        ↓
Video
        ↓
New next_short becomes next topic

If no pending topic exists:
        ↓
Gemini generates a new research-friendly topic

IMPORTANT:

- New Gemini topics: maximum 8 words.
- next_short topics: NO word-count limit.
- next_short is allowed to be a continuation/open-loop topic.
- Topics are only committed after the complete pipeline succeeds.
- Failed runs do not permanently consume the current topic.
"""

import json
import os
import re

from google import genai
from google.genai import types


# ==========================================================================
# FILES
# ==========================================================================

USED_TOPICS_PATH = "used_topics.json"

NEXT_TOPIC_PATH = "next_topic.json"


# ==========================================================================
# LIMITS
# ==========================================================================

# Only applies to NEW Gemini-generated topics.
NEW_TOPIC_MAX_WORDS = 8

# Safety limit for malformed/huge next_short text.
# This is intentionally character-based, NOT word-based.
MAX_TOPIC_CHARACTERS = 300


# ==========================================================================
# GEMINI PROMPT
# ==========================================================================

SYSTEM_PROMPT = """
You are the content strategist for a high-quality educational YouTube
Shorts channel.

Generate ONE educational topic that is highly likely to have strong,
credible, publicly verifiable research available.

Allowed categories:

1. Human Body
2. Psychology
3. Science
4. Space
5. Earth
6. Technology
7. History
8. Animals

============================================================
HARD RULES FOR NEW TOPICS
============================================================

- Return ONLY ONE topic.
- Maximum 8 words.
- Phrase it as a curiosity question.
- No clickbait.
- No listicles.
- No "Top 10".
- No "Top 5".
- No "Did you know".
- No emojis.
- No numbering.
- No quotation marks.
- No punctuation at the end.
- Do not make supernatural claims.
- Do not make conspiracy claims.
- Do not make medical diagnosis or treatment claims.
- Avoid controversial claims requiring political or ideological debate.
- Avoid topics where reliable evidence is unlikely to exist.
- Prefer topics that can be supported by multiple scholarly,
  government, university, or research-institution sources.
- The final topic must describe ONE specific phenomenon or question.
- Never repeat previous topics.
"""


# ==========================================================================
# FILE HELPERS
# ==========================================================================

def _load_used():

    if not os.path.exists(
        USED_TOPICS_PATH
    ):

        return []

    try:

        with open(
            USED_TOPICS_PATH,
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        if isinstance(
            data,
            list,
        ):

            return data

    except Exception as error:

        print(
            f"⚠️ Could not read "
            f"{USED_TOPICS_PATH}: {error}"
        )

    return []


def _save_used(
    used
):

    with open(
        USED_TOPICS_PATH,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            used,
            f,
            indent=2,
            ensure_ascii=False,
        )


def _load_next_topic():

    if not os.path.exists(
        NEXT_TOPIC_PATH
    ):

        return ""

    try:

        with open(
            NEXT_TOPIC_PATH,
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        # --------------------------------------------------------------
        # Supported format:
        #
        # {
        #   "topic": "discover how deep ocean trenches..."
        # }
        # --------------------------------------------------------------

        if isinstance(
            data,
            dict,
        ):

            topic = data.get(
                "topic",
                "",
            )

            return _clean_topic(
                topic
            )

        # --------------------------------------------------------------
        # Also support plain string.
        # --------------------------------------------------------------

        if isinstance(
            data,
            str,
        ):

            return _clean_topic(
                data
            )

    except Exception as error:

        print(
            f"⚠️ Could not read "
            f"{NEXT_TOPIC_PATH}: {error}"
        )

    return ""


def _save_next_topic(
    topic
):

    topic = _clean_topic(
        topic
    )

    if not topic:

        return False

    if len(topic) > MAX_TOPIC_CHARACTERS:

        print(
            "⚠️ Topic is too long."
        )

        print(
            f"Characters: {len(topic)}"
        )

        print(
            f"Maximum: {MAX_TOPIC_CHARACTERS}"
        )

        return False

    with open(
        NEXT_TOPIC_PATH,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            {
                "topic": topic
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    return True


def clear_next_topic():

    """
    Remove the pending topic after the pipeline has successfully
    completed the video based on that topic.
    """

    if not os.path.exists(
        NEXT_TOPIC_PATH
    ):

        return

    try:

        os.remove(
            NEXT_TOPIC_PATH
        )

        print(
            "✅ Pending next topic consumed."
        )

    except Exception as error:

        print(
            f"⚠️ Could not remove "
            f"{NEXT_TOPIC_PATH}: {error}"
        )


# ==========================================================================
# TOPIC CLEANING
# ==========================================================================

def _clean_topic(
    topic
):

    topic = str(
        topic or ""
    ).strip()

    # Remove markdown/code formatting.
    topic = topic.replace(
        "```",
        "",
    )

    topic = topic.replace(
        '"',
        "",
    ).replace(
        "'",
        "",
    )

    # Remove accidental leading labels.
    topic = re.sub(
        r"^(topic|next topic)\s*:\s*",
        "",
        topic,
        flags=re.IGNORECASE,
    )

    topic = topic.rstrip(
        ".!? "
    )

    topic = " ".join(
        topic.split()
    )

    return topic


# ==========================================================================
# TOPIC VALIDATION
# ==========================================================================

def _valid_topic(
    topic,
    max_words=None,
):

    if not topic:

        return False

    topic = _clean_topic(
        topic
    )

    if not topic:

        return False

    # --------------------------------------------------------------
    # Safety character limit.
    #
    # This applies to all topics but does NOT impose a word limit.
    # --------------------------------------------------------------

    if len(topic) > MAX_TOPIC_CHARACTERS:

        return False

    # --------------------------------------------------------------
    # Word limit is OPTIONAL.
    #
    # New Gemini topics use max_words=8.
    #
    # next_short uses max_words=None.
    # --------------------------------------------------------------

    if max_words is not None:

        words = topic.split()

        if len(words) > max_words:

            return False

    forbidden = [

        "top 10",

        "top 5",

        "did you know",

        "conspiracy",

        "aliens",

        "miracle",

    ]

    lowered = topic.lower()

    for phrase in forbidden:

        if phrase in lowered:

            return False

    return True


# ==========================================================================
# NORMALIZED COMPARISON
# ==========================================================================

def _topic_key(
    topic
):

    topic = _clean_topic(
        topic
    ).lower()

    topic = re.sub(
        r"[^a-z0-9\s]",
        "",
        topic,
    )

    return " ".join(
        topic.split()
    )


def _already_used(
    topic,
    used
):

    key = _topic_key(
        topic
    )

    for existing in used:

        if _topic_key(
            existing
        ) == key:

            return True

    return False


# ==========================================================================
# PENDING TOPIC
# ==========================================================================

def get_pending_topic():

    topic = _load_next_topic()

    if not topic:

        return ""

    # IMPORTANT:
    #
    # There is NO 8-word restriction here.
    #
    # The previous video's next_short can be:
    #
    # "discover how deep ocean trenches drive massive cyclonic
    # water circulation"
    #
    # or longer.

    if not _valid_topic(
        topic,
        max_words=None,
    ):

        print(
            "⚠️ Pending next topic is invalid:"
        )

        print(
            topic
        )

        return ""

    print("=" * 80)
    print("🔗 CONTINUING FROM PREVIOUS SHORT")
    print("=" * 80)

    print(
        f"Next topic: {topic}"
    )

    print(
        f"Word count: {len(topic.split())}"
    )

    print("=" * 80)

    return topic


# ==========================================================================
# GEMINI TOPIC GENERATION
# ==========================================================================

def _generate_new_topic():

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "GEMINI_API_KEY environment "
            "variable is missing."
        )

    client = genai.Client(
        api_key=api_key
    )

    used = _load_used()

    previous = "\n".join(
        used[-300:]
    )

    prompt = f"""
Previously used topics:

{previous}

Generate ONE completely different educational topic.

The topic must be specific enough for a research system to find
at least two credible independent sources.

Prefer questions about established scientific, historical,
technological, astronomical, biological, psychological,
geological, or engineering phenomena.

Do not invent obscure claims.

Return ONLY the topic.
"""

    for attempt in range(
        1,
        8,
    ):

        print(
            f"🧠 Gemini topic attempt "
            f"{attempt}/7"
        )

        try:

            response = client.models.generate_content(

                model="gemini-flash-lite-latest",

                contents=prompt,

                config=types.GenerateContentConfig(

                    system_instruction=
                        SYSTEM_PROMPT,

                    temperature=0.7,
                ),
            )

            topic = _clean_topic(
                response.text
            )

            print(
                f"Generated candidate: "
                f"{topic}"
            )

            # IMPORTANT:
            #
            # New Gemini topics ARE restricted to 8 words.

            if not _valid_topic(
                topic,
                max_words=NEW_TOPIC_MAX_WORDS,
            ):

                print(
                    "⚠️ Invalid new topic. Retrying."
                )

                continue

            if _already_used(
                topic,
                used,
            ):

                print(
                    "⚠️ Topic already used. Retrying."
                )

                continue

            print("=" * 80)
            print("✅ GENERATED RESEARCH-FRIENDLY TOPIC")
            print("=" * 80)

            print(
                topic
            )

            print("=" * 80)

            return topic

        except Exception as error:

            print(
                f"⚠️ Gemini topic generation "
                f"failed: {error}"
            )

    return ""


# ==========================================================================
# MAIN TOPIC FUNCTION
# ==========================================================================

def get_next_topic():

    """
    Return the topic that should be researched next.

    Priority:

    1. Previous video's next_short
    2. Existing pending topic
    3. Gemini-generated topic

    IMPORTANT:

    This function does NOT immediately mark the topic as used.

    The topic is only committed after the entire video succeeds.
    """

    # ----------------------------------------------------------------------
    # PRIORITY 1:
    #
    # Continue from previous video's open loop.
    # ----------------------------------------------------------------------

    pending = get_pending_topic()

    if pending:

        return pending

    # ----------------------------------------------------------------------
    # PRIORITY 2:
    #
    # Generate a completely new topic.
    # ----------------------------------------------------------------------

    topic = _generate_new_topic()

    if topic:

        # Keep it pending until the video succeeds.
        if not _save_next_topic(
            topic
        ):

            raise RuntimeError(
                "Could not save newly generated "
                "topic to pending queue."
            )

        print("=" * 80)
        print("📌 NEW TOPIC QUEUED")
        print("=" * 80)

        print(
            topic
        )

        print("=" * 80)

        return topic

    # ----------------------------------------------------------------------
    # FINAL FALLBACK
    # ----------------------------------------------------------------------

    raise RuntimeError(
        "Could not generate a new research-friendly topic "
        "and no pending next topic is available."
    )


# ==========================================================================
# TOPIC COMMIT
# ==========================================================================

def commit_topic(
    topic
):

    """
    Mark a successfully processed topic as used.

    main.py must call this ONLY after the complete pipeline succeeds.

    IMPORTANT:

    If a new next_short has already been saved, it remains in
    next_topic.json.

    The current topic is added to used_topics.json, while the
    newly generated next_short becomes the pending topic for the
    next GitHub Actions run.
    """

    topic = _clean_topic(
        topic
    )

    if not topic:

        return

    used = _load_used()

    if not _already_used(
        topic,
        used,
    ):

        used.append(
            topic
        )

        _save_used(
            used
        )

        print("=" * 80)
        print("✅ TOPIC COMMITTED")
        print("=" * 80)

        print(
            topic
        )

        print("=" * 80)

    else:

        print(
            f"ℹ️ Topic already exists in "
            f"{USED_TOPICS_PATH}: {topic}"
        )

    # ----------------------------------------------------------------------
    # IMPORTANT:
    #
    # Do NOT blindly delete next_topic.json here.
    #
    # It may already contain the NEW next_short generated by the
    # current video.
    #
    # Only remove it if it still contains the current topic.
    # ----------------------------------------------------------------------

    pending = _load_next_topic()

    if (
        pending
        and _topic_key(
            pending
        )
        == _topic_key(
            topic
        )
    ):

        clear_next_topic()


# ==========================================================================
# SAVE NEXT SHORT
# ==========================================================================

def save_next_short(
    next_short
):

    """
    Save the next topic generated by the current video's open loop.

    Example:

        Current video:
        How do deep sea fish survive immense pressure?

        next_short:
        discover how deep ocean trenches drive massive cyclonic
        water circulation

    The next_short becomes the next video's research topic.

    IMPORTANT:

    There is NO 8-word restriction here.
    """

    next_short = _clean_topic(
        next_short
    )

    if not next_short:

        print(
            "⚠️ No next_short was provided."
        )

        return False

    # --------------------------------------------------------------
    # Validate WITHOUT a word limit.
    # --------------------------------------------------------------

    if not _valid_topic(
        next_short,
        max_words=None,
    ):

        print(
            "⚠️ Generated next_short failed "
            "basic topic validation:"
        )

        print(
            next_short
        )

        return False

    if not _save_next_topic(
        next_short
    ):

        print(
            "❌ Could not save next_short "
            "to pending topic queue."
        )

        return False

    print("=" * 80)
    print("🔗 NEXT SHORT SAVED")
    print("=" * 80)

    print(
        next_short
    )

    print(
        f"Word count: "
        f"{len(next_short.split())}"
    )

    print(
        f"Queue file: "
        f"{NEXT_TOPIC_PATH}"
    )

    print("=" * 80)

    return True


# ==========================================================================
# CLI TEST
# ==========================================================================

if __name__ == "__main__":

    try:

        topic = get_next_topic()

        print("=" * 80)
        print("🎯 NEXT TOPIC")
        print("=" * 80)

        print(
            topic
        )

        print("=" * 80)

    except Exception as error:

        print("=" * 80)
        print("❌ TOPIC GENERATION FAILED")
        print("=" * 80)

        print(
            error
        )

        raise