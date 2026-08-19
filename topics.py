"""
topics.py
Mint-YT-Factory

Version 11.1

Science Curiosity Topic Engine

Purpose:

Generate high-potential curiosity questions for a
research-backed science/technology YouTube Shorts channel.

The channel promise:

    "Things you've noticed but never looked up."

Every topic must be:

- scientifically or technically researchable
- based on one observable phenomenon
- specific enough for scholarly research
- visually explainable
- curiosity-driven
- suitable for a 35–45 second Short
- meaningfully different from previous topics

Research.py remains the authoritative evidence gate.

This file selects QUESTIONS.

Research.py determines whether credible evidence actually
supports those questions.

IMPORTANT PERSISTENCE RULE
--------------------------

The current topic is only committed after:

1. YouTube upload succeeds
2. next_short is successfully written
3. next_short is successfully read back and verified

Historical duplicate protection is used when GENERATING a
brand-new topic.

It is intentionally NOT used when persisting a next_short
already produced by the verified script.
"""


import json
import os
import re
import tempfile

from google import genai
from google.genai import types


# ==========================================================================
# VERSION
# ==========================================================================

VERSION = "11.1"


# ==========================================================================
# FILES
# ==========================================================================

USED_TOPICS_PATH = "used_topics.json"
NEXT_TOPIC_PATH = "next_topic.json"


# ==========================================================================
# LIMITS
# ==========================================================================

NEW_TOPIC_MAX_WORDS = 12
MAX_TOPIC_CHARACTERS = 300

MAX_PREVIOUS_TOPICS = 300
MAX_TOPIC_GENERATION_ATTEMPTS = 12

MIN_CONTENT_WORDS = 3


# ==========================================================================
# GEMINI
# ==========================================================================

MODEL_NAME = "gemini-flash-lite-latest"


# ==========================================================================
# SYSTEM PROMPT
# ==========================================================================

SYSTEM_PROMPT = """
You are the topic strategist for a research-backed
science curiosity YouTube Shorts channel.

The channel promise is:

"Things you've noticed but never looked up."

Your job is NOT to generate generic science facts.

Your job is to discover ONE highly clickable question
about ONE real-world phenomenon that people can observe,
experience, hear, see, use, or encounter.

The question will later be independently researched using
scholarly and authoritative sources.

============================================================
PRIMARY OBJECTIVE
============================================================

Optimize for:

1. HIGH CURIOSITY
2. STRONG HUMAN RECOGNITION
3. SCIENTIFIC RESEARCHABILITY
4. VISUAL STORY POTENTIAL
5. SIMPLE EXPLANATION
6. SURPRISING BUT REAL REVEAL

The ideal viewer reaction is:

"I've noticed that."

"Wait, why does that happen?"

"I never knew that."

============================================================
SCIENCE / TECHNOLOGY REQUIREMENT
============================================================

The underlying explanation must plausibly involve a
real scientific or technical mechanism.

Acceptable areas include:

- physics
- chemistry
- biology
- neuroscience
- psychology
- perception
- human behavior when experimentally studied
- animals
- nature
- astronomy
- Earth science
- weather
- materials
- sound
- light
- optics
- electricity
- mechanics
- computing
- engineering
- everyday technology
- environmental science

Do NOT generate a question simply because it contains
a scientific-sounding word.

The phenomenon itself must be observable and researchable.

============================================================
ONE PHENOMENON
============================================================

Every question must contain exactly ONE central mystery.

GOOD:

Why does metal feel colder than wood

GOOD:

Why does a cold glass get covered in water

GOOD:

Why does your voice sound different in recordings

GOOD:

Why does popcorn suddenly pop

GOOD:

Why do shadows get longer near sunset

BAD:

Why do phones heat up and lose battery

BAD:

Why do humans forget things and remember others

BAD:

Why does sleep affect memory and mood

BAD:

Why does the ocean look blue and move with waves

============================================================
OBSERVABLE-FIRST
============================================================

Prefer questions based on something a normal person can
actually notice.

Strong sources of curiosity:

- something feels different
- something sounds different
- something suddenly changes
- something behaves unexpectedly
- something appears or disappears
- something changes color
- something moves strangely
- something gets hotter or colder
- something sticks, bends, cracks, floats, sinks, pops,
  vibrates, echoes, glows, freezes, melts, expands,
  shrinks, reflects, refracts, or changes appearance
- something familiar behaves differently under a
  particular condition

Avoid questions that require abstract knowledge before
the curiosity exists.

============================================================
HIGH-VIRALITY QUESTION PATTERN
============================================================

Prefer:

FAMILIAR EXPERIENCE
+
SPECIFIC UNEXPECTED BEHAVIOR
+
"WHY/HOW?"

Examples:

Why does metal feel colder than wood

Why does your voice sound different in recordings

Why does a mirror reverse left and right

Why does ice sometimes crack loudly

Why does popcorn suddenly explode

Why does the Moon look bigger near the horizon

Why does hot water sometimes freeze faster

Why does wet skin feel colder in moving air

These work because the viewer can recognize the
phenomenon immediately.

============================================================
RESEARCHABILITY
============================================================

Prefer questions where credible evidence is likely to exist
from:

- peer-reviewed papers
- universities
- government agencies
- scientific institutions
- established research organizations
- authoritative technical organizations

The phenomenon should be describable using more than one
scientific phrase.

Avoid phenomena where research would likely return only
opinions, anecdotes, entertainment articles, or unrelated
papers.

============================================================
DO NOT OPTIMIZE FOR ACADEMIC SOUNDING TITLES
============================================================

BAD:

The thermodynamics of everyday refrigeration

The neuroscience of human memory

The physics of acoustic resonance

The biology of animal communication

GOOD:

Why does your fridge feel warm on the sides

Why can you remember a song but forget its name

Why does your voice echo in an empty room

Why do some birds suddenly copy human sounds

The question should sound like something a person would
actually ask, not like a university course title.

============================================================
VISUAL POTENTIAL
============================================================

Prefer phenomena that can be demonstrated visually.

Excellent:

- ice
- water
- glass
- mirrors
- shadows
- sound
- fire
- smoke
- light
- animals
- plants
- weather
- everyday objects
- phones
- cars
- machines
- food
- materials
- space
- human perception

Avoid topics that are scientifically valid but difficult
to visualize in a 35–45 second Short.

============================================================
ORIGINALITY
============================================================

Do NOT repeat previous topics.

Do NOT merely change wording around an existing topic.

The underlying phenomenon must be substantially different.

For example:

Previous:
Why does metal feel colder than wood

Do NOT generate:

Why does steel feel colder than plastic

because the underlying phenomenon is essentially the same.

============================================================
FORBIDDEN
============================================================

Never generate:

- Top 5
- Top 10
- countdowns
- lists
- compilations
- generic facts
- "facts about"
- "interesting facts"
- "did you know"
- "the science of..."
- "history of..."
- "benefits of..."
- "importance of..."
- "everything about..."
- "complete guide"
- "ultimate guide"
- broad academic subjects
- philosophical questions
- existential questions
- conspiracy theories
- political outrage
- fearbait
- supernatural claims presented as fact
- medical diagnosis
- medical treatment
- medical advice
- unsupported health claims
- subjective opinion questions

============================================================
MEDICAL TOPICS
============================================================

Avoid medical diagnosis, treatment, disease advice, symptoms,
supplements, medications, or health recommendations.

General non-clinical human biology/perception is allowed when
the phenomenon is safe, observable, and researchable.

============================================================
QUESTION FORM
============================================================

Prefer:

Why does...

Why do...

Why is...

Why are...

How does...

How do...

How can...

The question must describe an observable phenomenon rather
than ask for a broad explanation of a subject.

============================================================
LENGTH
============================================================

Maximum 12 words.

Prefer 6–10 words.

============================================================
OUTPUT
============================================================

Return ONLY ONE question.

No explanation.
No quotation marks.
No numbering.
No emoji.
No terminal punctuation.
"""


# ==========================================================================
# FILE HELPERS
# ==========================================================================

def _atomic_write_json(
    path,
    data,
):
    """
    Atomically write JSON to disk.

    The file is first written to a temporary file in the same
    directory and then replaced into place.

    This prevents partially written JSON from becoming the
    active topic file.
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

            f.write("\n")

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

                os.close(
                    fd
                )

            except Exception:
                pass

        if (
            temp_path
            and os.path.exists(
                temp_path
            )
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

        if not isinstance(
            data,
            list,
        ):

            return []

        cleaned = []

        for item in data:

            topic = _clean_topic(
                item
            )

            if topic:

                cleaned.append(
                    topic
                )

        return cleaned

    except Exception as error:

        print(
            f"⚠️ Could not read "
            f"{USED_TOPICS_PATH}: {error}"
        )

        return []


def _save_used(
    used
):

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

        if isinstance(
            data,
            dict,
        ):

            return _clean_topic(
                data.get(
                    "topic",
                    "",
                )
            )

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
    """
    Save a pending topic atomically.

    Returns True only when the atomic write itself succeeds.

    The caller that needs strong persistence guarantees should
    subsequently read the file back and verify it.
    """

    topic = _clean_topic(
        topic
    )

    if not topic:

        print(
            "❌ Cannot save empty topic."
        )

        return False

    if len(
        topic
    ) > MAX_TOPIC_CHARACTERS:

        print(
            "❌ Cannot save topic: "
            f"{len(topic)} characters exceeds "
            f"{MAX_TOPIC_CHARACTERS}."
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
            "❌ Could not save "
            f"{NEXT_TOPIC_PATH}: {error}"
        )

        print(
            f"Exception type: "
            f"{type(error).__name__}"
        )

        return False


def clear_next_topic():

    if not os.path.exists(
        NEXT_TOPIC_PATH
    ):

        return True

    try:

        os.remove(
            NEXT_TOPIC_PATH
        )

        print(
            "✅ Pending topic removed."
        )

        return True

    except Exception as error:

        print(
            f"⚠️ Could not remove "
            f"{NEXT_TOPIC_PATH}: {error}"
        )

        return False


def reject_topic(
    topic=None,
    reason="research failed",
):

    pending = _load_next_topic()

    if not pending:

        return True

    if topic:

        topic = _clean_topic(
            topic
        )

        if (
            _topic_key(
                topic
            )
            !=
            _topic_key(
                pending
            )
        ):

            print(
                "⚠️ Pending topic does not match "
                "the topic being rejected."
            )

            return False

    print(
        f"🗑️ Rejecting pending topic: {pending}"
    )

    print(
        f"Reason: {reason}"
    )

    return clear_next_topic()


# ==========================================================================
# CLEANING
# ==========================================================================

def _clean_topic(
    topic
):

    topic = str(
        topic or ""
    ).strip()

    if not topic:

        return ""

    topic = re.sub(
        r"```(?:text|json)?",
        "",
        topic,
        flags=re.IGNORECASE,
    )

    topic = topic.replace(
        '"',
        "",
    )

    topic = topic.replace(
        "'",
        "",
    )

    topic = re.sub(
        r"^(topic|next topic|next_short|next short)\s*:\s*",
        "",
        topic,
        flags=re.IGNORECASE,
    )

    topic = re.sub(
        r"^\s*\d+[\.\)\-:]\s*",
        "",
        topic,
    )

    topic = " ".join(
        topic.split()
    )

    return topic.rstrip(
        ".!? "
    ).strip()


# ==========================================================================
# BASIC VALIDATION
# ==========================================================================

def _valid_topic(
    topic,
    max_words=None,
):

    topic = _clean_topic(
        topic
    )

    if not topic:

        return False

    if len(
        topic
    ) > MAX_TOPIC_CHARACTERS:

        return False

    if max_words is not None:

        if len(
            topic.split()
        ) > max_words:

            return False

    lowered = topic.lower()

    forbidden = [
        "top 5",
        "top 10",
        "top five",
        "top ten",
        "did you know",
        "amazing facts",
        "interesting facts",
        "facts about",
        "things you didn't know",
        "things you never knew",
        "ultimate guide",
        "complete guide",
        "shocking truth",
        "the science of",
        "the biology of",
        "the physics of",
        "the history of",
        "the psychology of",
        "benefits of",
        "importance of",
        "everything about",
        "all about",
        "introduction to",
        "overview of",
        "conspiracy",
        "miracle",
        "fearbait",
        "medical treatment",
        "medical diagnosis",
        "how to treat",
        "how to cure",
        "should i take",
        "should you take",
    ]

    for phrase in forbidden:

        if phrase in lowered:

            return False

    if re.match(
        r"^(top|best)\s+\d+",
        lowered,
    ):

        return False

    if re.match(
        r"^(top|best)\s+(five|ten)\b",
        lowered,
    ):

        return False

    return True


# ==========================================================================
# QUESTION VALIDATION
# ==========================================================================

def _question_words(
    topic
):

    return re.findall(
        r"[a-z0-9]+",
        topic.lower(),
    )


def _content_words(
    topic
):

    stop_words = {
        "why",
        "what",
        "how",
        "when",
        "where",
        "who",
        "does",
        "do",
        "did",
        "can",
        "could",
        "would",
        "will",
        "should",
        "is",
        "are",
        "was",
        "were",
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "from",
        "your",
        "you",
        "we",
        "our",
        "they",
        "their",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "very",
        "really",
        "actually",
        "often",
        "usually",
        "sometimes",
        "people",
        "thing",
        "things",
    }

    return [
        word
        for word in _question_words(
            topic
        )
        if (
            len(word) >= 3
            and word not in stop_words
        )
    ]


def _is_question(
    topic
):

    return topic.lower().strip().startswith(
        (
            "why ",
            "how ",
            "can ",
            "does ",
            "do ",
            "is ",
            "are ",
        )
    )


def _has_observation_structure(
    topic
):

    lowered = topic.lower()

    patterns = [
        r"^why does .+ .+",
        r"^why do .+ .+",
        r"^why can .+ .+",
        r"^why is .+ .+",
        r"^why are .+ .+",
        r"^how does .+ .+",
        r"^how do .+ .+",
        r"^how can .+ .+",
        r"^how is .+ .+",
        r"^how are .+ .+",
    ]

    return any(
        re.search(
            pattern,
            lowered,
        )
        for pattern in patterns
    )


def _has_single_phenomenon_shape(
    topic
):

    lowered = topic.lower()

    multiple_patterns = [
        " and why ",
        " and how ",
        " or why ",
        " or how ",
        " while ",
        " but also ",
        " as well as ",
        " and then ",
        " plus ",
    ]

    for pattern in multiple_patterns:

        if pattern in lowered:

            return False

    if topic.count(
        "?"
    ) > 1:

        return False

    return True


def _has_subject_specificity(
    topic
):

    content = _content_words(
        topic
    )

    if len(
        content
    ) < MIN_CONTENT_WORDS:

        return False

    generic_patterns = [
        r"^why do people behave",
        r"^why do humans behave",
        r"^why do people act",
        r"^why is life",
        r"^why is everything",
        r"^why does life",
        r"^how does life",
        r"^why do humans",
        r"^why are humans",
        r"^why does nature",
        r"^how does nature",
        r"^why is science",
        r"^why is technology",
        r"^how does technology",
        r"^why is the universe",
        r"^how does the universe",
    ]

    lowered = topic.lower()

    for pattern in generic_patterns:

        if re.search(
            pattern,
            lowered,
        ):

            return False

    return True


def _has_researchable_shape(
    topic
):

    """
    Structural test only.

    We intentionally do NOT hardcode a list of scientific
    mechanism words here.

    research.py is responsible for determining whether
    credible evidence actually exists.
    """

    lowered = topic.lower()

    question_starts = (
        "why ",
        "how ",
    )

    if not lowered.startswith(
        question_starts
    ):

        return False

    content = _content_words(
        topic
    )

    if len(
        content
    ) < 3:

        return False

    abstract_only = {
        "life",
        "existence",
        "meaning",
        "reality",
        "universe",
        "time",
        "space",
        "consciousness",
        "success",
        "failure",
        "happiness",
        "love",
        "memory",
        "history",
        "future",
        "truth",
        "knowledge",
        "science",
        "technology",
    }

    concrete_hits = [
        word
        for word in content
        if word not in abstract_only
    ]

    return len(
        concrete_hits
    ) >= 2


def _passes_question_quality(
    topic
):

    if not _is_question(
        topic
    ):

        print(
            "⚠️ Rejected: not a question."
        )

        return False

    content = _content_words(
        topic
    )

    if len(
        content
    ) < MIN_CONTENT_WORDS:

        print(
            "⚠️ Rejected: insufficient specificity."
        )

        return False

    if not _has_observation_structure(
        topic
    ):

        print(
            "⚠️ Rejected: weak observable phenomenon."
        )

        return False

    if not _has_researchable_shape(
        topic
    ):

        print(
            "⚠️ Rejected: weak science/research structure."
        )

        return False

    if not _has_single_phenomenon_shape(
        topic
    ):

        print(
            "⚠️ Rejected: multiple phenomena detected."
        )

        return False

    if not _has_subject_specificity(
        topic
    ):

        print(
            "⚠️ Rejected: topic is too generic."
        )

        return False

    if len(
        topic.split()
    ) > NEW_TOPIC_MAX_WORDS:

        print(
            "⚠️ Rejected: topic too long."
        )

        return False

    print(
        "🧩 Question structure: PASS"
    )

    return True


# ==========================================================================
# DUPLICATE PROTECTION
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
    used,
):

    key = _topic_key(
        topic
    )

    if not key:

        return False

    return any(
        _topic_key(
            existing
        ) == key
        for existing in used
    )


def _topic_words(
    topic
):

    stop_words = {
        "why",
        "what",
        "how",
        "when",
        "where",
        "does",
        "do",
        "did",
        "can",
        "could",
        "would",
        "will",
        "should",
        "is",
        "are",
        "was",
        "were",
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "from",
        "your",
        "you",
        "we",
        "our",
        "they",
        "their",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
    }

    return {
        word
        for word in re.findall(
            r"[a-z0-9]+",
            _topic_key(
                topic
            ),
        )
        if (
            len(word) >= 3
            and word not in stop_words
        )
    }


def _too_similar_to_used(
    topic,
    used,
):

    current = _topic_words(
        topic
    )

    if len(
        current
    ) < 2:

        return False

    for existing in used:

        previous = _topic_words(
            existing
        )

        if len(
            previous
        ) < 2:

            continue

        intersection = (
            current & previous
        )

        union = (
            current | previous
        )

        if not union:

            continue

        jaccard = (
            len(intersection)
            / len(union)
        )

        if jaccard >= 0.72:

            return True

        current_coverage = (
            len(intersection)
            / len(current)
        )

        previous_coverage = (
            len(intersection)
            / len(previous)
        )

        if (
            current_coverage >= 0.80
            and previous_coverage >= 0.60
            and len(intersection) >= 3
        ):

            return True

    return False


# ==========================================================================
# VIRAL POTENTIAL SCORE
# ==========================================================================

def _curiosity_score(
    topic
):

    """
    Score the question for YouTube curiosity potential.

    This is deliberately a lightweight heuristic.

    It does NOT decide whether the topic is scientifically true.

    research.py remains the evidence authority.
    """

    lowered = topic.lower()

    words = topic.split()

    score = 0

    # Familiarity / direct human experience.
    if any(
        word in lowered
        for word in (
            "your",
            "you",
            "we",
            "people",
            "human",
            "everyday",
            "phone",
            "car",
            "glass",
            "water",
            "ice",
            "food",
            "voice",
            "mirror",
            "shadow",
        )
    ):

        score += 3

    # Strong curiosity structures.
    if lowered.startswith(
        (
            "why does ",
            "why do ",
            "why is ",
            "why are ",
        )
    ):

        score += 3

    elif lowered.startswith(
        (
            "how does ",
            "how do ",
            "how can ",
        )
    ):

        score += 2

    # A condition/change usually creates a visual reveal.
    if any(
        word in lowered
        for word in (
            "feel",
            "sound",
            "look",
            "appear",
            "disappear",
            "change",
            "suddenly",
            "cold",
            "hot",
            "warm",
            "freeze",
            "melt",
            "move",
            "pop",
            "float",
            "sink",
            "stick",
            "bend",
            "crack",
            "glow",
            "echo",
            "reflect",
            "shadow",
            "color",
        )
    ):

        score += 3

    # Moderate length is better for a spoken hook.
    if 6 <= len(words) <= 10:

        score += 2

    elif 5 <= len(words) <= 12:

        score += 1

    # Specificity.
    content = _content_words(
        topic
    )

    if len(
        content
    ) >= 5:

        score += 2

    elif len(
        content
    ) >= 4:

        score += 1

    return min(
        13,
        score,
    )


# ==========================================================================
# TOPIC QUALITY SCORE
# ==========================================================================

def _topic_quality_score(
    topic
):

    score = 0

    words = topic.split()

    content = _content_words(
        topic
    )

    if _is_question(
        topic
    ):

        score += 3

    if _has_observation_structure(
        topic
    ):

        score += 3

    if _has_researchable_shape(
        topic
    ):

        score += 3

    if _has_subject_specificity(
        topic
    ):

        score += 2

    if _has_single_phenomenon_shape(
        topic
    ):

        score += 2

    if 6 <= len(words) <= 10:

        score += 2

    elif 5 <= len(words) <= 12:

        score += 1

    if len(
        content
    ) >= 5:

        score += 2

    elif len(
        content
    ) >= 4:

        score += 1

    score += min(
        3,
        _curiosity_score(
            topic
        ) // 4,
    )

    return min(
        20,
        score,
    )


def _passes_topic_score(
    topic
):

    score = _topic_quality_score(
        topic
    )

    curiosity = _curiosity_score(
        topic
    )

    print(
        f"📊 Topic structure score: "
        f"{score}/20"
    )

    print(
        f"🔥 Curiosity score: "
        f"{curiosity}/13"
    )

    return (
        score >= 14
        and curiosity >= 7
    )


# ==========================================================================
# PIPELINE VALIDATION
# ==========================================================================

def validate_topic_for_pipeline(
    topic,
    used=None,
    check_duplicate=True,
):

    topic = _clean_topic(
        topic
    )

    if not _valid_topic(
        topic,
        max_words=NEW_TOPIC_MAX_WORDS,
    ):

        return False

    if not _passes_question_quality(
        topic
    ):

        return False

    if not _passes_topic_score(
        topic
    ):

        return False

    if used is None:

        used = _load_used()

    if check_duplicate:

        if _already_used(
            topic,
            used,
        ):

            print(
                "⚠️ Topic already used."
            )

            return False

        if _too_similar_to_used(
            topic,
            used,
        ):

            print(
                "⚠️ Topic is too similar "
                "to a previous topic."
            )

            return False

    return True


# ==========================================================================
# PENDING TOPIC
# ==========================================================================

def get_pending_topic():

    topic = _load_next_topic()

    if not topic:

        return ""

    if not validate_topic_for_pipeline(
        topic,
        check_duplicate=False,
    ):

        print(
            "⚠️ Pending topic is invalid."
        )

        clear_next_topic()

        return ""

    print("=" * 80)

    print(
        "🔗 CONTINUING FROM PREVIOUS SHORT"
    )

    print("=" * 80)

    print(
        f"Next topic: {topic}"
    )

    print("=" * 80)

    return topic


# ==========================================================================
# GEMINI GENERATION
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
        used[
            -MAX_PREVIOUS_TOPICS:
        ]
    )

    prompt = f"""
Generate ONE completely new question for a
research-backed science curiosity YouTube Short.

The question must satisfy ALL of these:

1. It describes ONE observable real-world phenomenon.
2. A normal person could notice or experience it.
3. It creates an immediate "why does that happen?" reaction.
4. The answer should involve a real scientific or technical
   mechanism.
5. The phenomenon should be explainable using credible
   scholarly or authoritative sources.
6. It should have strong visual potential.
7. The explanation should fit naturally into 35–45 seconds.
8. It must be meaningfully different from every previous topic.

Think:

FAMILIAR EXPERIENCE
→ UNEXPECTED BEHAVIOR
→ SCIENTIFIC MYSTERY
→ SURPRISING REVEAL

GOOD EXAMPLES:

Why does metal feel colder than wood

Why does your voice sound different in recordings

Why does a cold glass get covered in water

Why does popcorn suddenly pop

Why does ice sometimes crack loudly

Why does a mirror seem to reverse left and right

Why does wet skin feel colder in moving air

Why does the Moon look bigger near the horizon

BAD EXAMPLES:

Why is space mysterious

Why is time strange

Why is life complicated

Why are humans interesting

Why is science important

The history of electricity

The science of memory

Benefits of cold showers

How to improve your memory

Why do phones heat up and lose battery

Do not generate:

- lists
- countdowns
- generic facts
- broad academic subjects
- philosophy
- conspiracy theories
- fearbait
- politics
- medical diagnosis
- medical treatment
- health advice
- unsupported claims
- subjective questions

Maximum 12 words.
Prefer 6–10 words.

PREVIOUS TOPICS:
{previous}

Return ONLY the question.
No explanation.
No quotes.
No numbering.
No emoji.
No terminal punctuation.
"""

    for attempt in range(
        1,
        MAX_TOPIC_GENERATION_ATTEMPTS + 1,
    ):

        print(
            f"🧠 Curiosity generation attempt "
            f"{attempt}/"
            f"{MAX_TOPIC_GENERATION_ATTEMPTS}"
        )

        try:

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.90,
                ),
            )

            topic = _clean_topic(
                getattr(
                    response,
                    "text",
                    "",
                )
            )

            print(
                f"Generated candidate: {topic}"
            )

            if not validate_topic_for_pipeline(
                topic,
                used=used,
            ):

                continue

            pending = _load_next_topic()

            if (
                pending
                and
                _topic_key(
                    pending
                )
                ==
                _topic_key(
                    topic
                )
            ):

                print(
                    "⚠️ Candidate equals pending topic."
                )

                continue

            print("=" * 80)

            print(
                "🔥 GENERATED SCIENCE CURIOSITY QUESTION"
            )

            print("=" * 80)

            print(
                topic
            )

            print(
                f"Words: "
                f"{len(topic.split())}"
            )

            print(
                "Structure score: "
                f"{_topic_quality_score(topic)}/20"
            )

            print(
                "Curiosity score: "
                f"{_curiosity_score(topic)}/13"
            )

            print("=" * 80)

            return topic

        except Exception as error:

            print(
                "⚠️ Gemini topic generation "
                f"failed: {error}"
            )

    return ""


# ==========================================================================
# MAIN TOPIC FUNCTION
# ==========================================================================

def get_next_topic():

    pending = get_pending_topic()

    if pending:

        return pending

    topic = _generate_new_topic()

    if topic:

        # ------------------------------------------------------------------
        # Save newly generated topic.
        # ------------------------------------------------------------------

        if not _save_next_topic(
            topic
        ):

            raise RuntimeError(
                "Could not save generated topic."
            )

        # ------------------------------------------------------------------
        # HARD PERSISTENCE VERIFICATION
        # ------------------------------------------------------------------

        persisted_topic = _load_next_topic()

        if (
            not persisted_topic
            or
            _topic_key(
                persisted_topic
            )
            !=
            _topic_key(
                topic
            )
        ):

            raise RuntimeError(
                "Generated topic was written, "
                "but could not be verified after persistence."
            )

        print("=" * 80)

        print(
            "📌 NEW SCIENCE CURIOSITY QUESTION QUEUED"
        )

        print("=" * 80)

        print(
            persisted_topic
        )

        print("=" * 80)

        return persisted_topic

    raise RuntimeError(
        "Could not generate a strong "
        "science curiosity question."
    )


# ==========================================================================
# COMMIT
# ==========================================================================

def commit_topic(
    topic
):

    topic = _clean_topic(
        topic
    )

    if not topic:

        raise RuntimeError(
            "Cannot commit an empty topic."
        )

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

        print(
            "✅ CURRENT TOPIC COMMITTED"
        )

        print("=" * 80)

        print(
            topic
        )

        print("=" * 80)

    pending = _load_next_topic()

    if not pending:

        return True

    if (
        _topic_key(
            pending
        )
        ==
        _topic_key(
            topic
        )
    ):

        if not clear_next_topic():

            raise RuntimeError(
                "Could not remove committed "
                "pending topic."
            )

    else:

        print(
            "🔗 Preserving NEW next_short:"
        )

        print(
            pending
        )

    return True


# ==========================================================================
# SAVE NEXT SHORT
# ==========================================================================

def save_next_short(
    next_short
):
    """
    Save the next Short topic after the current Short has successfully
    uploaded.

    IMPORTANT:

    We intentionally use:

        check_duplicate=False

    here.

    The next_short has already been selected by the verified script.
    Historical duplicate/similarity protection is necessary when
    GENERATING a brand-new topic, but applying it here can incorrectly
    reject a valid next topic after the current video has already been
    uploaded.

    Persistence is then independently verified by reading
    NEXT_TOPIC_PATH back from disk.
    """

    next_short = _clean_topic(
        next_short
    )

    print("=" * 80)

    print(
        "🔗 VALIDATING NEXT SHORT FOR PERSISTENCE"
    )

    print("=" * 80)

    print(
        f"Candidate: "
        f"{next_short or '[EMPTY]'}"
    )

    # ----------------------------------------------------------------------
    # Empty check
    # ----------------------------------------------------------------------

    if not next_short:

        print(
            "❌ NEXT SHORT SAVE FAILED: "
            "empty topic."
        )

        return False

    # ----------------------------------------------------------------------
    # Basic validation
    # ----------------------------------------------------------------------

    if not _valid_topic(
        next_short,
        max_words=NEW_TOPIC_MAX_WORDS,
    ):

        print(
            "❌ NEXT SHORT SAVE FAILED: "
            "basic topic validation failed."
        )

        print(
            f"Topic: {next_short}"
        )

        return False

    # ----------------------------------------------------------------------
    # Question / quality validation
    #
    # IMPORTANT:
    #
    # No historical duplicate check.
    # ----------------------------------------------------------------------

    if not _passes_question_quality(
        next_short
    ):

        print(
            "❌ NEXT SHORT SAVE FAILED: "
            "question structure validation failed."
        )

        return False

    if not _passes_topic_score(
        next_short
    ):

        print(
            "❌ NEXT SHORT SAVE FAILED: "
            "topic quality score failed."
        )

        return False

    print(
        "✅ Next Short topic validation passed."
    )

    # ----------------------------------------------------------------------
    # Persist
    # ----------------------------------------------------------------------

    print()

    print(
        f"💾 Writing to: {NEXT_TOPIC_PATH}"
    )

    if not _save_next_topic(
        next_short
    ):

        print(
            "❌ NEXT SHORT SAVE FAILED: "
            "atomic write failed."
        )

        return False

    # ----------------------------------------------------------------------
    # HARD READ-BACK VERIFICATION
    # ----------------------------------------------------------------------

    print(
        "🔍 Verifying persisted next_short..."
    )

    persisted_topic = _load_next_topic()

    if not persisted_topic:

        print(
            "❌ NEXT SHORT SAVE FAILED: "
            f"{NEXT_TOPIC_PATH} is empty after write."
        )

        return False

    if (
        _topic_key(
            persisted_topic
        )
        !=
        _topic_key(
            next_short
        )
    ):

        print(
            "❌ NEXT SHORT SAVE FAILED: "
            "persisted topic does not match requested topic."
        )

        print(
            f"Requested: {next_short}"
        )

        print(
            f"Persisted: {persisted_topic}"
        )

        return False

    # ----------------------------------------------------------------------
    # SUCCESS
    # ----------------------------------------------------------------------

    print("=" * 80)

    print(
        "✅ NEXT SCIENCE SHORT SAVED AND VERIFIED"
    )

    print("=" * 80)

    print(
        f"Next topic: {persisted_topic}"
    )

    print(
        f"File: {NEXT_TOPIC_PATH}"
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

        print(
            "🎯 NEXT MINT-YT-FACTORY SCIENCE QUESTION"
        )

        print("=" * 80)

        print(
            topic
        )

        print("=" * 80)

    except Exception as error:

        print("=" * 80)

        print(
            "❌ TOPIC GENERATION FAILED"
        )

        print("=" * 80)

        print(
            f"{type(error).__name__}: {error}"
        )

        print(
            f"Error: {error}"
        )

        print("=" * 80)

        raise