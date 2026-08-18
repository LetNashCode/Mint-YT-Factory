"""
topics.py
Mint-YT-Factory

Version 7.0

CURIOSITY-FIRST TOPIC ENGINE

Purpose
-------
Generate highly compelling, specific questions for 35–45 second
research-backed YouTube Shorts.

Architecture
------------
topics.py
    -> discovers and validates interesting questions

research.py
    -> authoritative evidence validation

script generation
    -> turns the verified question into a story

visual generation
    -> creates visual storytelling

upload
    -> publishes the Short

The topic engine deliberately does NOT try to become a scientific
fact checker. research.py remains authoritative for evidence.

Core philosophy
---------------
"Questions you've probably wondered about but never looked up."

The ideal viewer reaction:

    "I've wondered about that."

    "Wait... why does that happen?"

    "Ohhh, that's why."

Important
---------
Do not use fixed subject vocabulary to decide whether a topic is good.

A good question can come from anywhere.

The engine evaluates the SHAPE and STORY POTENTIAL of the question,
not whether it contains words such as "brain", "water", "physics", etc.
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

VERSION = "7.0"


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

MAX_TOPIC_GENERATION_ATTEMPTS = 10


# ==========================================================================
# GEMINI
# ==========================================================================

MODEL_NAME = "gemini-flash-lite-latest"


# ==========================================================================
# QUESTION PHILOSOPHY
# ==========================================================================

SYSTEM_PROMPT = """
You are the curiosity strategist for Mint-YT-Factory.

Your job is to discover ONE question that could become a highly
engaging 35–45 second YouTube Short.

This is NOT a generic educational channel.

The channel philosophy is:

    "Questions you've probably wondered about but never looked up."

The viewer reaction we want is:

    "I've wondered about that."

followed by:

    "Wait... why?"

and finally:

    "Ohhh, that's why."

============================================================
PRIMARY OBJECTIVE
============================================================

Generate ONE genuinely compelling question.

The question must describe ONE specific phenomenon, behavior,
experience, or observation.

It must be something an ordinary person can recognize.

The viewer should be able to imagine the phenomenon immediately.

The answer should reveal a mechanism, cause, process, or
counterintuitive explanation.

============================================================
THE GOLDEN TEST
============================================================

Before generating the question, mentally ask:

1. What exactly is the viewer noticing?
2. Have ordinary people likely experienced this?
3. Is the obvious explanation incomplete or wrong?
4. Is there a satisfying mechanism behind it?
5. Can that mechanism be explained in roughly 35–45 seconds?
6. Can the mechanism be shown visually?
7. Can credible sources explain it?

If the answer to these is weak, choose another idea.

============================================================
WHAT MAKES A GREAT QUESTION
============================================================

A strong question usually has:

FAMILIARITY
Something people have seen, heard, felt, experienced, or noticed.

CURIOSITY
The observation naturally creates a "why?" or "how?" reaction.

SPECIFICITY
One phenomenon rather than an entire subject.

MECHANISM
There is an actual explanation behind the observation.

SURPRISE
The real explanation is more interesting than the obvious one.

VISUAL POTENTIAL
The mechanism can be represented through animation,
experiments, diagrams, environments, transformations,
microscopic views, internal views, or cause-and-effect scenes.

RESEARCHABILITY
Credible independent sources should realistically exist.

============================================================
IDEAL QUESTION PATTERNS
============================================================

Prefer natural questions such as:

Why does [familiar thing] [unexpected behavior]?

Why do [people/animals/things] [observable behavior]?

Why can [familiar thing] [unexpected ability]?

Why does [ordinary experience] feel/look/sound different?

How does [specific phenomenon] happen?

How can [specific thing] cause [specific observable result]?

These are structures, not templates to copy mechanically.

============================================================
ONE PHENOMENON ONLY
============================================================

Every Short should have ONE central mystery.

GOOD:

Why does a cold drink make a glass wet?

One central phenomenon.

GOOD:

Why does your voice sound different in recordings?

One central phenomenon.

GOOD:

Why does a shadow change length during the day?

One central phenomenon.

BAD:

Why do phones get hot and batteries drain quickly?

Two related but separate phenomena.

BAD:

How does the human body work?

Entire subject.

BAD:

Why is space so strange?

Too broad.

============================================================
FAMILIARITY
============================================================

Prefer observations from ordinary life.

Examples of possible domains include:

- household objects
- food
- materials
- weather
- light
- sound
- transportation
- animals
- human behavior
- body experiences
- perception
- memory
- everyday technology
- nature
- space
- ordinary physics
- ordinary chemistry
- social experiences

These are examples of domains only.

Do NOT restrict generation to these categories.

Unexpected but understandable domains are encouraged.

============================================================
SURPRISE
============================================================

The surprise must come from the real mechanism.

Do NOT manufacture:

- fake mystery
- conspiracy
- sensationalism
- fear
- "shocking truth"
- unsupported claims

The best surprise is:

"You thought it happened because of X,
but the important reason is actually Y."

============================================================
35–45 SECOND STORY TEST
============================================================

Imagine the finished Short:

0–3 seconds:
The observation creates immediate curiosity.

3–20 seconds:
The mechanism begins to unfold.

20–35 seconds:
The surprising part is revealed.

35–45 seconds:
The explanation lands with a satisfying payoff.

Reject questions requiring:

- long historical background
- many unrelated mechanisms
- multiple case studies
- extensive terminology
- a long list of facts
- several separate questions

============================================================
VISUAL STORY TEST
============================================================

The question should naturally support visual storytelling.

Strong visual mechanisms include:

- movement
- transformation
- cause and effect
- microscopic processes
- internal processes
- before/after
- experiments
- simulations
- scale changes
- environmental changes
- anatomical visualization
- physical interactions
- light and sound behavior

The visual potential must come from the phenomenon itself.

============================================================
RESEARCH TEST
============================================================

The topic must realistically be researchable.

Prefer phenomena that can be supported by:

- peer-reviewed research
- universities
- government agencies
- scientific institutions
- established research organizations
- authoritative databases

Do not invent facts.

Do not choose a topic merely because it sounds mysterious.

research.py will perform the actual evidence validation.

============================================================
ORIGINALITY
============================================================

Do not repeat a previous topic.

More importantly:

Do not repeat the same underlying phenomenon using different wording.

For example, these should be treated as conceptually related:

"Why does your voice sound different recorded?"

"Why does your recorded voice sound strange?"

"Why does your voice change on recordings?"

Changing wording does not make a new topic.

The underlying mystery must be meaningfully different.

============================================================
FORBIDDEN CONTENT
============================================================

Avoid:

- graphic violence
- gore
- sexual content
- extremist content
- dangerous instructions
- drug use
- political outrage
- conspiracy theories
- fearbait
- medical diagnosis
- medical treatment instructions
- misinformation

Normal educational science is fine.

============================================================
FORBIDDEN FORMATS
============================================================

Never generate:

- Top 5
- Top 10
- countdowns
- lists
- compilations
- generic facts
- "facts about..."
- "interesting facts..."
- "the science of..."
- "history of..."
- "benefits of..."
- "everything about..."
- "complete guide..."
- "ultimate guide..."
- broad academic subjects
- generic "how X works" questions
- broad "what is X" questions

============================================================
TOPIC LENGTH
============================================================

Maximum 12 words.

Prefer 6–10 words.

The question should sound natural when spoken aloud.

============================================================
OUTPUT
============================================================

Return ONLY ONE question.

No explanation.

No quotation marks.

No numbering.

No emojis.

No terminal punctuation.

No "Did you know".

No "Let's explore".

No "Today we're going to".

============================================================
FINAL OBJECTIVE
============================================================

ONE FAMILIAR OBSERVATION
+
ONE SPECIFIC MYSTERY
+
ONE REAL MECHANISM
+
ONE SURPRISING EXPLANATION
+
STRONG VISUAL STORY
+
RESEARCHABILITY
+
BROAD HUMAN APPEAL

Generate curiosity, not curriculum.
"""


# ==========================================================================
# FILE HELPERS
# ==========================================================================

def _atomic_write_json(path, data):

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
            os.fsync(f.fileno())

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

        if (
            temp_path
            and
            os.path.exists(temp_path)
        ):

            try:
                os.remove(temp_path)
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

            data = json.load(f)

        if not isinstance(data, list):
            return []

        cleaned = []

        for item in data:

            topic = _clean_topic(item)

            if topic:
                cleaned.append(topic)

        return cleaned

    except Exception as error:

        print(
            f"⚠️ Could not read "
            f"{USED_TOPICS_PATH}: {error}"
        )

        return []


def _save_used(used):

    cleaned = []
    seen = set()

    for topic in used:

        topic = _clean_topic(topic)

        if not topic:
            continue

        key = _topic_key(topic)

        if key in seen:
            continue

        seen.add(key)
        cleaned.append(topic)

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

            data = json.load(f)

        if isinstance(data, dict):

            return _clean_topic(
                data.get("topic", "")
            )

        if isinstance(data, str):

            return _clean_topic(data)

    except Exception as error:

        print(
            f"⚠️ Could not read "
            f"{NEXT_TOPIC_PATH}: {error}"
        )

    return ""


def _save_next_topic(topic):

    topic = _clean_topic(topic)

    if not topic:
        return False

    if len(topic) > MAX_TOPIC_CHARACTERS:

        print(
            "⚠️ Topic exceeds character safety limit."
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


# ==========================================================================
# TOPIC CLEANING
# ==========================================================================

def _clean_topic(topic):

    topic = str(topic or "").strip()

    if not topic:
        return ""

    topic = topic.replace(
        "```json",
        "",
    )

    topic = topic.replace(
        "```",
        "",
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

    topic = topic.rstrip(
        ".!? "
    )

    return topic.strip()


# ==========================================================================
# BASIC VALIDATION
# ==========================================================================

def _valid_topic(
    topic,
    max_words=None,
):

    topic = _clean_topic(topic)

    if not topic:
        return False

    if len(topic) > MAX_TOPIC_CHARACTERS:
        return False

    if max_words is not None:

        if len(topic.split()) > max_words:
            return False

    lowered = topic.lower()

    forbidden_phrases = [

        "top 5",
        "top 10",
        "top five",
        "top ten",
        "did you know",
        "amazing facts",
        "interesting facts",
        "things you didn't know",
        "things you never knew",
        "facts about",
        "ultimate guide",
        "complete guide",
        "shocking truth",
        "secret they don't want",
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
    ]

    for phrase in forbidden_phrases:

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
# QUESTION STRUCTURE
# ==========================================================================

def _is_question(topic):

    lowered = topic.lower().strip()

    return lowered.startswith(
        (
            "why ",
            "how ",
            "can ",
            "do ",
            "does ",
            "is ",
            "are ",
        )
    )


def _question_words(topic):

    return re.findall(
        r"[a-z0-9]+",
        topic.lower(),
    )


# ==========================================================================
# CONTENT WORDS
# ==========================================================================

def _content_words(topic):

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
        for word in _question_words(topic)
        if (
            len(word) >= 3
            and word not in stop_words
        )
    ]


# ==========================================================================
# OBSERVATION / MECHANISM VALIDATION
# ==========================================================================

def _has_observation_structure(topic):

    """
    Detect whether the question describes an observable event.

    This intentionally does NOT maintain a list of allowed subjects.

    It looks for sentence structure suggesting:

        object/person/thing
        +
        behavior/change/experience

    The generator remains responsible for choosing the actual
    phenomenon.
    """

    lowered = topic.lower()

    words = _content_words(topic)

    if len(words) < 3:
        return False

    # Questions containing an explicit experiential relationship
    # are generally strong candidates.

    relationship_patterns = [

        r"\bwhy does .+ .+",

        r"\bwhy do .+ .+",

        r"\bwhy can .+ .+",

        r"\bhow does .+ .+",

        r"\bhow do .+ .+",

        r"\bwhy is .+ .+",

        r"\bwhy are .+ .+",
    ]

    for pattern in relationship_patterns:

        if re.search(
            pattern,
            lowered,
        ):

            return True

    return False


def _has_mechanism_structure(topic):

    """
    The question must ask about causation, behavior or process.

    We deliberately avoid hardcoded scientific vocabulary.
    """

    lowered = topic.lower()

    mechanism_patterns = [

        r"^why\b",
        r"^how\b",
        r"\bhappen(s)?\b",
        r"\bwork(s)?\b",
        r"\bcause(s)?\b",
        r"\bmake(s)?\b",
        r"\bchange(s)?\b",
        r"\bmove(s)?\b",
        r"\bproduce(s)?\b",
        r"\bcreate(s)?\b",
        r"\bbecome(s)?\b",
        r"\bform(s)?\b",
        r"\bfeel(s)?\b",
        r"\bsound(s)?\b",
        r"\blook(s)?\b",
        r"\bsmell(s)?\b",
        r"\bappear(s)?\b",
        r"\bseem(s)?\b",
        r"\bfloat(s)?\b",
        r"\bfreeze(s)?\b",
        r"\bmelt(s)?\b",
        r"\bstand(s)?\b",
        r"\bstick(s)?\b",
        r"\bbend(s)?\b",
        r"\breflect(s)?\b",
        r"\becho(es)?\b",
        r"\bremember(s)?\b",
        r"\bforget(s)?\b",
        r"\bdream(s)?\b",
        r"\btickle(s)?\b",
        r"\byawn(s)?\b",
    ]

    return any(
        re.search(
            pattern,
            lowered,
        )
        for pattern in mechanism_patterns
    )


def _has_single_phenomenon_shape(topic):

    """
    Reject obvious multi-part questions.

    This is intentionally conservative.

    We don't want to reject a perfectly valid phenomenon merely
    because it contains a conjunction, so only obvious combinations
    are blocked.
    """

    lowered = topic.lower()

    # Explicit multiple-question constructions.

    if " and why " in lowered:
        return False

    if " and how " in lowered:
        return False

    if " or why " in lowered:
        return False

    if " or how " in lowered:
        return False

    # Multiple question marks should never survive cleaning,
    # but keep this protection here.

    if topic.count("?") > 1:
        return False

    return True


def _passes_question_quality(topic):

    if not _is_question(topic):

        print(
            "⚠️ Rejected: not a natural curiosity question."
        )

        return False

    content = _content_words(topic)

    if len(content) < 3:

        print(
            "⚠️ Rejected: insufficient concrete information."
        )

        return False

    if not _has_observation_structure(topic):

        print(
            "⚠️ Rejected: not clearly describing an observation."
        )

        return False

    if not _has_mechanism_structure(topic):

        print(
            "⚠️ Rejected: mechanism/question structure is weak."
        )

        return False

    if not _has_single_phenomenon_shape(topic):

        print(
            "⚠️ Rejected: multiple phenomena detected."
        )

        return False

    # Extremely short questions tend to become broad.

    if len(content) < 3:

        print(
            "⚠️ Rejected: question is too vague."
        )

        return False

    # Extremely long questions are difficult to turn into
    # a 35–45 second Short.

    if len(topic.split()) > NEW_TOPIC_MAX_WORDS:

        print(
            "⚠️ Rejected: question is too long."
        )

        return False

    print(
        "🧩 Question structure: PASS"
    )

    return True


# ==========================================================================
# TOPIC NORMALIZATION
# ==========================================================================

def _topic_key(topic):

    topic = _clean_topic(topic).lower()

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

    key = _topic_key(topic)

    if not key:
        return False

    return any(
        _topic_key(existing) == key
        for existing in used
    )


# ==========================================================================
# SEMANTIC-LITE DUPLICATE PROTECTION
# ==========================================================================

def _topic_words(topic):

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
            _topic_key(topic),
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

    current_words = _topic_words(topic)

    if len(current_words) < 2:
        return False

    for existing in used:

        existing_words = _topic_words(existing)

        if len(existing_words) < 2:
            continue

        intersection = (
            current_words
            &
            existing_words
        )

        union = (
            current_words
            |
            existing_words
        )

        if not union:
            continue

        jaccard = (
            len(intersection)
            /
            len(union)
        )

        # Strong overall overlap.

        if jaccard >= 0.72:
            return True

        # Catch rewritten versions where most of the meaningful
        # words are shared even if a few words have changed.

        current_coverage = (
            len(intersection)
            /
            len(current_words)
        )

        existing_coverage = (
            len(intersection)
            /
            len(existing_words)
        )

        if (
            current_coverage >= 0.80
            and
            existing_coverage >= 0.60
            and
            len(intersection) >= 3
        ):
            return True

    return False


# ==========================================================================
# TOPIC QUALITY HEURISTIC
# ==========================================================================

def _topic_quality_score(topic):

    """
    Lightweight structural score.

    This is NOT a "viral prediction model".

    It exists only as a sanity check.

    Gemini is responsible for creative judgment.
    research.py is responsible for evidence.

    Maximum: 20
    """

    score = 0

    words = topic.split()
    content = _content_words(topic)
    lowered = topic.lower()

    # --------------------------------------------------------------
    # Question
    # --------------------------------------------------------------

    if _is_question(topic):
        score += 3

    # --------------------------------------------------------------
    # Specificity
    # --------------------------------------------------------------

    if len(content) >= 4:
        score += 3

    elif len(content) >= 3:
        score += 2

    # --------------------------------------------------------------
    # Observation
    # --------------------------------------------------------------

    if _has_observation_structure(topic):
        score += 3

    # --------------------------------------------------------------
    # Mechanism
    # --------------------------------------------------------------

    if _has_mechanism_structure(topic):
        score += 3

    # --------------------------------------------------------------
    # Natural length
    # --------------------------------------------------------------

    if 6 <= len(words) <= 10:
        score += 2

    elif 5 <= len(words) <= 12:
        score += 1

    # --------------------------------------------------------------
    # Personal familiarity
    # --------------------------------------------------------------

    familiarity_patterns = [
        r"\byour\b",
        r"\byou\b",
        r"\bpeople\b",
        r"\bwe\b",
        r"\beveryone\b",
    ]

    if any(
        re.search(
            pattern,
            lowered,
        )
        for pattern in familiarity_patterns
    ):
        score += 2

    # --------------------------------------------------------------
    # Single phenomenon
    # --------------------------------------------------------------

    if _has_single_phenomenon_shape(topic):
        score += 2

    return min(
        20,
        score,
    )


def _passes_topic_score(topic):

    score = _topic_quality_score(topic)

    print(
        f"📊 Topic structure score: "
        f"{score}/20"
    )

    # This is deliberately lower than a "viral score".
    #
    # We are not pretending Python can predict virality from keywords.

    return score >= 14


# ==========================================================================
# PENDING TOPIC
# ==========================================================================

def get_pending_topic():

    topic = _load_next_topic()

    if not topic:
        return ""

    if not _valid_topic(
        topic,
        max_words=None,
    ):

        print(
            "⚠️ Pending topic is invalid:"
        )

        print(topic)

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

Generate ONE completely new question for Mint-YT-Factory.

============================================================
THINK BEFORE ANSWERING
============================================================

Find an observation that makes an ordinary person think:

"I've noticed that."

Then ask:

"Why does that happen?"

or:

"How does that happen?"

The final question must be specific enough that a 35–45 second
Short can answer it with one coherent mechanism.

============================================================
IMPORTANT
============================================================

Do NOT choose a topic because it belongs to a popular category.

Do NOT use a fixed subject list.

Explore broadly.

The phenomenon can come from ANY domain if it satisfies the
curiosity test.

============================================================
THE BEST IDEA HAS THIS SHAPE
============================================================

FAMILIAR OBSERVATION
        ↓
NATURAL QUESTION
        ↓
UNEXPECTED MECHANISM
        ↓
SURPRISING EXPLANATION
        ↓
VISUAL STORY
        ↓
SATISFYING PAYOFF

============================================================
QUESTIONS TO ASK YOURSELF
============================================================

Would millions of people understand the observation?

Would someone plausibly have wondered about it?

Is the phenomenon visually understandable?

Is there one main mechanism?

Can the explanation fit naturally into 35–45 seconds?

Would the answer contain a satisfying "Ohhh" moment?

Could credible sources realistically support the explanation?

If not, reject the idea.

============================================================
ONE PHENOMENON
============================================================

Do NOT combine separate mysteries.

BAD:

Why does my phone get hot and lose battery?

GOOD:

Why does your phone get hot while charging?

BAD:

Why do mirrors reverse things and create reflections?

GOOD:

Why does a mirror appear to reverse left and right?

============================================================
DO NOT GENERATE
============================================================

Broad subjects.

Generic educational questions.

Listicles.

Countdowns.

Definitions.

History lessons.

Benefits.

"Interesting facts".

"Things you didn't know".

"The science of..."

"How X works" when X is an entire system.

"Why is X amazing?"

"Why is the universe strange?"

Conspiracy theories.

Fearbait.

Political outrage.

Medical diagnosis or treatment.

============================================================
ORIGINALITY
============================================================

The following are previous topics.

Do NOT repeat them.

Do NOT create a reworded version of them.

The new question must involve a genuinely different underlying
phenomenon.

PREVIOUS TOPICS:

{previous}

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

No quotes.

No numbering.

No emoji.

No terminal punctuation.

No "Did you know".

No "Let's explore".

No "Today we're going to".
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

                    system_instruction=
                        SYSTEM_PROMPT,

                    temperature=0.90,
                ),
            )

            response_text = getattr(
                response,
                "text",
                "",
            )

            topic = _clean_topic(
                response_text
            )

            print(
                f"Generated candidate: "
                f"{topic}"
            )

            # --------------------------------------------------------------
            # BASIC VALIDATION
            # --------------------------------------------------------------

            if not _valid_topic(
                topic,
                max_words=NEW_TOPIC_MAX_WORDS,
            ):

                print(
                    "⚠️ Failed basic validation."
                )

                continue

            # --------------------------------------------------------------
            # QUESTION QUALITY
            # --------------------------------------------------------------

            if not _passes_question_quality(
                topic
            ):

                print(
                    "⚠️ Failed curiosity structure."
                )

                continue

            # --------------------------------------------------------------
            # EXACT DUPLICATE
            # --------------------------------------------------------------

            if _already_used(
                topic,
                used,
            ):

                print(
                    "⚠️ Exact topic already used."
                )

                continue

            # --------------------------------------------------------------
            # CONCEPT DUPLICATE
            # --------------------------------------------------------------

            if _too_similar_to_used(
                topic,
                used,
            ):

                print(
                    "⚠️ Underlying concept is too similar to previous topic."
                )

                continue

            # --------------------------------------------------------------
            # PENDING DUPLICATE
            # --------------------------------------------------------------

            pending = _load_next_topic()

            if (
                pending
                and
                _topic_key(pending)
                ==
                _topic_key(topic)
            ):

                print(
                    "⚠️ Topic is already pending."
                )

                continue

            # --------------------------------------------------------------
            # STRUCTURAL QUALITY
            # --------------------------------------------------------------

            if not _passes_topic_score(
                topic
            ):

                print(
                    "⚠️ Topic structure score too low."
                )

                continue

            # --------------------------------------------------------------
            # SUCCESS
            # --------------------------------------------------------------

            print("=" * 80)
            print("🔥 GENERATED CURIOSITY QUESTION")
            print("=" * 80)

            print(topic)

            print(
                f"Words: "
                f"{len(topic.split())}"
            )

            print(
                f"Characters: "
                f"{len(topic)}"
            )

            print(
                f"Structure score: "
                f"{_topic_quality_score(topic)}/20"
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
    Topic priority:

    1. Existing pending next_short
    2. Gemini-generated new curiosity question

    The selected topic is NOT committed here.

    It is committed only after the video has successfully uploaded.
    """

    pending = get_pending_topic()

    if pending:
        return pending

    topic = _generate_new_topic()

    if topic:

        if not _save_next_topic(topic):

            raise RuntimeError(
                "Could not save newly generated "
                "topic to pending queue."
            )

        print("=" * 80)
        print("📌 NEW CURIOSITY QUESTION QUEUED")
        print("=" * 80)

        print(topic)

        print("=" * 80)

        return topic

    raise RuntimeError(
        "Could not generate a strong curiosity question "
        "and no pending topic is available."
    )


# ==========================================================================
# TOPIC COMMIT
# ==========================================================================

def commit_topic(topic):

    """
    Commit the CURRENT topic only after successful upload.

    Important:

    If next_topic.json contains a NEW next_short, preserve it.

    Only remove next_topic.json when it still contains the
    exact topic that has just been committed.
    """

    topic = _clean_topic(topic)

    if not topic:

        raise RuntimeError(
            "Cannot commit an empty topic."
        )

    used = _load_used()

    if not _already_used(
        topic,
        used,
    ):

        used.append(topic)

        _save_used(used)

        print("=" * 80)
        print("✅ CURRENT TOPIC COMMITTED")
        print("=" * 80)

        print(topic)

        print("=" * 80)

    else:

        print(
            "ℹ️ Current topic is already committed:"
        )

        print(topic)

    pending = _load_next_topic()

    if not pending:
        return True

    if (
        _topic_key(pending)
        ==
        _topic_key(topic)
    ):

        if not clear_next_topic():

            raise RuntimeError(
                "Current topic committed, but its pending queue "
                "entry could not be removed."
            )

        return True

    print(
        "🔗 Preserving NEW next_short:"
    )

    print(
        f"   {pending}"
    )

    return True


# ==========================================================================
# SAVE NEXT SHORT
# ==========================================================================

def save_next_short(next_short):

    """
    Save the next topic generated by the current video's open loop.

    next_short intentionally has no 12-word limit because it may be
    generated by the script/story system.

    It is still checked for basic safety and duplicate protection.
    """

    next_short = _clean_topic(
        next_short
    )

    if not next_short:

        print(
            "⚠️ No next_short was provided."
        )

        return False

    if not _valid_topic(
        next_short,
        max_words=None,
    ):

        print(
            "⚠️ next_short failed basic validation:"
        )

        print(next_short)

        return False

    used = _load_used()

    if _already_used(
        next_short,
        used,
    ):

        print(
            "⚠️ next_short is already committed:"
        )

        print(next_short)

        return False

    if _too_similar_to_used(
        next_short,
        used,
    ):

        print(
            "⚠️ next_short is too similar to a previous topic:"
        )

        print(next_short)

        return False

    if not _save_next_topic(
        next_short
    ):

        print(
            "❌ Could not save next_short."
        )

        return False

    print("=" * 80)
    print("🔗 NEXT SHORT SAVED")
    print("=" * 80)

    print(next_short)

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
        print("🎯 NEXT MINT-YT-FACTORY QUESTION")
        print("=" * 80)

        print(topic)

        print("=" * 80)

    except Exception as error:

        print("=" * 80)
        print("❌ TOPIC GENERATION FAILED")
        print("=" * 80)

        print(error)

        raise