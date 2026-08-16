"""
topics.py
Mint-YT-Factory

Version 4.1

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
- Pending topics survive failed pipeline runs.
- The current topic never overwrites the newly generated next_short.
"""

import json
import os
import re
import tempfile

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

# ONLY applies to brand-new Gemini-generated topics.
NEW_TOPIC_MAX_WORDS = 8

# Safety limit for malformed/huge topic strings.
# This is NOT a word limit.
MAX_TOPIC_CHARACTERS = 300

# Number of previous topics supplied to Gemini.
MAX_PREVIOUS_TOPICS = 300

# Gemini generation attempts.
MAX_TOPIC_GENERATION_ATTEMPTS = 7


# ==========================================================================
# GEMINI CONFIG
# ==========================================================================

MODEL_NAME = "gemini-flash-lite-latest"


# ==========================================================================
# GEMINI SYSTEM PROMPT
# ==========================================================================

SYSTEM_PROMPT = """
You are the content strategist for a high-quality educational
YouTube Shorts channel.

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
- Prefer topics with a clear scientific mechanism.
- Prefer topics that can be visually explained.
"""


# ==========================================================================
# FILE HELPERS
# ==========================================================================

def _atomic_write_json(
    path,
    data,
):
    """
    Safely write JSON using a temporary file and atomic replacement.

    This reduces the chance of leaving a partially written JSON file
    if the process is interrupted during a write.
    """

    directory = os.path.dirname(
        os.path.abspath(path)
    )

    os.makedirs(
        directory,
        exist_ok=True,
    )

    fd = None
    temp_path = None

    try:

        fd, temp_path = tempfile.mkstemp(
            prefix=".mint_topic_",
            suffix=".tmp",
            dir=directory,
            text=True,
        )

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as f:

            fd = None

            json.dump(
                data,
                f,
                indent=2,
                ensure_ascii=False,
            )

            f.write(
                "\n"
            )

            f.flush()

            os.fsync(
                f.fileno()
            )

        os.replace(
            temp_path,
            path,
        )

        temp_path = None

    finally:

        if fd is not None:

            try:
                os.close(fd)
            except Exception:
                pass

        if temp_path and os.path.exists(
            temp_path
        ):

            try:
                os.remove(
                    temp_path
                )
            except Exception:
                pass


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

            data = json.load(
                f
            )

        if isinstance(
            data,
            list,
        ):

            return [
                _clean_topic(x)
                for x in data
                if _clean_topic(x)
            ]

    except Exception as error:

        print(
            f"⚠️ Could not read "
            f"{USED_TOPICS_PATH}: {error}"
        )

    return []


def _save_used(
    used
):

    # Remove duplicates while preserving order.
    cleaned = []

    seen = set()

    for topic in used:

        topic = _clean_topic(
            topic
        )

        if not topic:
            continue

        key = _topic_key(
            topic
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        cleaned.append(
            topic
        )

    _atomic_write_json(
        USED_TOPICS_PATH,
        cleaned,
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

            data = json.load(
                f
            )

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

    try:

        _atomic_write_json(
            NEXT_TOPIC_PATH,
            {
                "topic": topic
            },
        )

        return True

    except Exception as error:

        print(
            f"❌ Could not save "
            f"{NEXT_TOPIC_PATH}: {error}"
        )

        return False


def clear_next_topic():

    """
    Remove the pending topic.

    This should only be called when the pending topic is known to
    have been successfully consumed.
    """

    if not os.path.exists(
        NEXT_TOPIC_PATH
    ):

        return True

    try:

        os.remove(
            NEXT_TOPIC_PATH
        )

        print(
            "✅ Pending next topic consumed."
        )

        return True

    except Exception as error:

        print(
            f"⚠️ Could not remove "
            f"{NEXT_TOPIC_PATH}: {error}"
        )

        return False


# ==========================================================================
# TOPIC CLEANING
# ==========================================================================

def _clean_topic(
    topic
):

    topic = str(
        topic or ""
    ).strip()

    if not topic:
        return ""

    # --------------------------------------------------------------
    # Remove Markdown/code formatting.
    # --------------------------------------------------------------

    topic = topic.replace(
        "```json",
        "",
    )

    topic = topic.replace(
        "```",
        "",
    )

    # --------------------------------------------------------------
    # Remove quotation marks.
    # --------------------------------------------------------------

    topic = topic.replace(
        '"',
        "",
    ).replace(
        "'",
        "",
    )

    # --------------------------------------------------------------
    # Remove accidental leading labels.
    # --------------------------------------------------------------

    topic = re.sub(
        r"^(topic|next topic|next_short|next short)\s*:\s*",
        "",
        topic,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------------------
    # Remove accidental numbering.
    # --------------------------------------------------------------

    topic = re.sub(
        r"^\s*\d+[\.\)\-:]\s*",
        "",
        topic,
    )

    # --------------------------------------------------------------
    # Normalize whitespace.
    # --------------------------------------------------------------

    topic = " ".join(
        topic.split()
    )

    # --------------------------------------------------------------
    # Remove trailing punctuation.
    #
    # The source next_short can technically be a phrase, so we only
    # remove terminal punctuation for consistency.
    # --------------------------------------------------------------

    topic = topic.rstrip(
        ".!? "
    )

    return topic.strip()


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
    # Character safety limit.
    #
    # This applies to ALL topics.
    #
    # It does NOT impose a word limit.
    # --------------------------------------------------------------

    if len(topic) > MAX_TOPIC_CHARACTERS:

        return False

    # --------------------------------------------------------------
    # Optional word limit.
    #
    # New Gemini topics:
    # max_words=8
    #
    # next_short:
    # max_words=None
    # --------------------------------------------------------------

    if max_words is not None:

        words = topic.split()

        if len(words) > max_words:

            return False

    # --------------------------------------------------------------
    # Forbidden phrases.
    # --------------------------------------------------------------

    forbidden = [

        "top 10",
        "top 5",
        "did you know",
        "conspiracy",
        "miracle",
    ]

    lowered = topic.lower()

    for phrase in forbidden:

        if phrase in lowered:

            return False

    # --------------------------------------------------------------
    # Reject obvious list formatting.
    # --------------------------------------------------------------

    if re.match(
        r"^(top|best)\s+\d+",
        lowered,
    ):

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

    if not key:
        return False

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

    """
    Return the currently queued topic.

    IMPORTANT:

    There is NO 8-word restriction here.

    The previous video's next_short may be a long,
    research-ready continuation topic.
    """

    topic = _load_next_topic()

    if not topic:

        return ""

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

    print(
        f"Characters: {len(topic)}"
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
        used[-MAX_PREVIOUS_TOPICS:]
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

Prefer topics that can be explained visually in approximately
45 seconds.

Do not invent obscure claims.

Return ONLY the topic.
"""

    for attempt in range(
        1,
        MAX_TOPIC_GENERATION_ATTEMPTS + 1,
    ):

        print(
            f"🧠 Gemini topic attempt "
            f"{attempt}/"
            f"{MAX_TOPIC_GENERATION_ATTEMPTS}"
        )

        try:

            response = client.models.generate_content(

                model=MODEL_NAME,

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

            # ----------------------------------------------------------
            # New Gemini topics HAVE the 8-word limit.
            # ----------------------------------------------------------

            if not _valid_topic(
                topic,
                max_words=NEW_TOPIC_MAX_WORDS,
            ):

                print(
                    "⚠️ Invalid new topic. Retrying."
                )

                continue

            # ----------------------------------------------------------
            # Never repeat a committed topic.
            # ----------------------------------------------------------

            if _already_used(
                topic,
                used,
            ):

                print(
                    "⚠️ Topic already used. Retrying."
                )

                continue

            # ----------------------------------------------------------
            # Never duplicate the currently pending topic.
            # ----------------------------------------------------------

            pending = _load_next_topic()

            if pending and (
                _topic_key(
                    pending
                )
                == _topic_key(
                    topic
                )
            ):

                print(
                    "⚠️ Topic already pending. Retrying."
                )

                continue

            print("=" * 80)
            print("✅ GENERATED RESEARCH-FRIENDLY TOPIC")
            print("=" * 80)

            print(
                topic
            )

            print(
                f"Words: {len(topic.split())}"
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

    1. Existing pending next_short
    2. Gemini-generated topic

    IMPORTANT:

    This function does NOT immediately mark a topic as used.

    A topic becomes used only after main.py successfully completes
    the entire production and upload process.
    """

    # ----------------------------------------------------------------------
    # PRIORITY 1:
    #
    # Continue from previous video's next_short.
    # ----------------------------------------------------------------------

    pending = get_pending_topic()

    if pending:

        return pending

    # ----------------------------------------------------------------------
    # PRIORITY 2:
    #
    # Generate a brand-new topic.
    # ----------------------------------------------------------------------

    topic = _generate_new_topic()

    if topic:

        # --------------------------------------------------------------
        # Keep the topic pending until the complete pipeline succeeds.
        # --------------------------------------------------------------

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
    # FINAL FAILURE
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

    main.py MUST call this only after the video has successfully
    uploaded.

    IMPORTANT:

    If next_topic.json contains the NEW next_short, it is preserved.

    The pending file is deleted only if it still contains the
    CURRENT topic.
    """

    topic = _clean_topic(
        topic
    )

    if not topic:

        raise RuntimeError(
            "Cannot commit an empty topic."
        )

    used = _load_used()

    # ----------------------------------------------------------------------
    # Add current topic to used topics.
    # ----------------------------------------------------------------------

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
    # Never blindly delete next_topic.json.
    #
    # It may contain the NEW next_short.
    #
    # Only remove it if it still contains the CURRENT topic.
    # ----------------------------------------------------------------------

    pending = _load_next_topic()

    if not pending:

        return

    if _topic_key(
        pending
    ) == _topic_key(
        topic
    ):

        clear_next_topic()

    else:

        print(
            "🔗 Preserving newly queued next_short:"
        )

        print(
            f"   {pending}"
        )


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
        How do deep sea fish survive immense pressure

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

    # ----------------------------------------------------------------------
    # Validate WITHOUT word limit.
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # Do not queue a topic that has already been committed.
    #
    # This protects against Gemini accidentally generating a continuation
    # that is identical to an older published topic.
    # ----------------------------------------------------------------------

    used = _load_used()

    if _already_used(
        next_short,
        used,
    ):

        print(
            "⚠️ next_short is already a committed topic:"
        )

        print(
            next_short
        )

        return False

    # ----------------------------------------------------------------------
    # Save the next topic.
    # ----------------------------------------------------------------------

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
        f"Characters: "
        f"{len(next_short)}"
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