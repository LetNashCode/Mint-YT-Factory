"""
topics.py
Mint-YT-Factory

Version 6.0

VIRAL CURIOSITY QUESTION ENGINE

v6.0 improvements:
- Generates specific WHY/HOW curiosity questions
- Strong observable-phenomenon requirement
- Mechanism-oriented question generation
- Prevents broad academic subjects
- Prevents generic "how X works" questions
- Prevents listicles/countdowns
- Stronger 35–45 second scope control
- Better researchability requirements
- Better visual-story requirements
- Stronger duplicate/concept protection
- Existing pending topics retain priority
- Existing queue/commit architecture preserved
- Atomic topic writes preserved
- Current topic is only committed after successful upload
- next_short remains protected
- Gemini remains responsible for ideation
- research.py remains authoritative for scientific evidence
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

VERSION = "6.0"


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
# VIRAL SCORING
# ==========================================================================

MIN_VIRAL_SCORE = 20
MAX_VIRAL_SCORE = 30


# ==========================================================================
# QUESTION QUALITY
# ==========================================================================

"""
The topic engine is deliberately stricter than the research engine.

topics.py asks:

    Is this a good QUESTION?

research.py asks:

    Can credible evidence actually answer this QUESTION?

The two systems therefore have different responsibilities.
"""


# Words that usually indicate an overly broad academic subject.
BROAD_SUBJECT_TERMS = {
    "science",
    "biology",
    "physics",
    "chemistry",
    "technology",
    "engineering",
    "psychology",
    "astronomy",
    "medicine",
    "nature",
    "evolution",
    "ecosystem",
    "electricity",
    "quantum",
    "thermodynamics",
    "neuroscience",
}


# Generic questions that usually require too much explanation.
BROAD_QUESTION_PATTERNS = [
    r"^how does the internet work",
    r"^how does electricity work",
    r"^how does the brain work",
    r"^how does the human body work",
    r"^how does space work",
    r"^how does gravity work",
    r"^how does evolution work",
    r"^how does technology work",
    r"^how do airplanes work",
    r"^how do computers work",
    r"^how do phones work",
    r"^what is gravity",
    r"^what is quantum",
    r"^what is consciousness",
    r"^what is dark matter",
    r"^what is artificial intelligence",
]


# Topics that tend to produce poor Shorts even if technically
# researchable.
LOW_VALUE_PATTERNS = [
    "history of",
    "importance of",
    "benefits of",
    "types of",
    "uses of",
    "advantages of",
    "disadvantages of",
    "everything about",
    "all about",
    "complete guide",
    "ultimate guide",
    "introduction to",
    "overview of",
    "what are the different",
    "what are some",
]


# ==========================================================================
# GEMINI SYSTEM PROMPT
# ==========================================================================

SYSTEM_PROMPT = """
You are the viral curiosity strategist for Mint-YT-Factory.

Your job is NOT to generate generic educational subjects.

Your job is to discover ONE highly compelling, specific QUESTION
that ordinary people genuinely want answered.

The final question will become a roughly 35–45 second
research-backed YouTube Short.

============================================================
CHANNEL PHILOSOPHY
============================================================

"Questions you've probably wondered about but never looked up."

The ideal viewer reaction is:

"I've wondered about that."

then:

"Wait... that's why?"

then:

"Ohhh."

============================================================
THE MOST IMPORTANT RULE
============================================================

Generate a QUESTION about ONE SPECIFIC OBSERVABLE PHENOMENON.

The question should describe something a person can:

- see
- hear
- feel
- experience
- notice
- encounter
- observe

and ask WHY or HOW it happens.

The answer should explain a mechanism, cause, process,
or counterintuitive reason.

============================================================
QUESTION STRUCTURE
============================================================

Strong questions usually follow structures such as:

Why does [familiar thing] [unexpected behavior]?

Why do [people/animals/things] [observable behavior]?

How does [familiar phenomenon] happen?

Why can [familiar thing] [unexpected ability]?

Why does [ordinary experience] feel/look/sound different?

Examples:

Why do your eyes water when cutting onions

Why does metal feel colder than wood

Why do fingers wrinkle in water

Why does your voice sound different recorded

Why can't you tickle yourself

Why does ice float

Why does rain smell

Why do dogs tilt their heads

Why can birds sit on power lines

Why does the Moon look bigger near the horizon

Do NOT copy these examples.

============================================================
ONE PHENOMENON ONLY
============================================================

Every video must answer ONE central question.

GOOD:

Why do your eyes water when cutting onions

The phenomenon:
Eyes water while cutting onions.

The mechanism:
A chemical released by damaged onion tissue irritates
the eye and triggers tearing.

BAD:

Why do onions make you cry and smell so strong?

Too many phenomena.

BAD:

Why do onions make people cry, how are they grown,
and why are they healthy?

Multiple subjects.

BAD:

The science of onions

Not a question.

============================================================
MECHANISM REQUIREMENT
============================================================

The question must have an identifiable underlying mechanism.

Good:

Why does metal feel colder than wood?

Possible mechanism:
Different thermal conductivity / heat transfer.

Good:

Why do fingers wrinkle in water?

Possible mechanism:
Nervous-system-mediated vascular response.

Good:

Why does your voice sound different recorded?

Possible mechanism:
Bone conduction versus air conduction.

Bad:

Why is the universe amazing?

No specific mechanism.

Bad:

Why is nature so interesting?

No specific mechanism.

============================================================
OBSERVABLE PHENOMENON REQUIREMENT
============================================================

Prefer things ordinary people have personally experienced.

High-value categories:

EVERYDAY MYSTERIES

- metal and wood feeling different
- rain smell
- echoes
- static electricity
- reflections
- shadows
- ice floating
- glass appearing invisible

HUMAN BODY

- eyes watering
- goosebumps
- yawning
- sneezing
- hiccups
- fingers wrinkling
- voice sounding different
- feeling dizzy
- getting brain freeze

BRAIN / PSYCHOLOGY

- forgetting why you entered a room
- songs getting stuck in your head
- déjà vu
- embarrassing memories returning
- dreams feeling real
- time feeling faster

ANIMALS

- dogs tilting their heads
- cats purring
- birds flying in formation
- bees behaving collectively
- animals responding to sounds

EVERYDAY PHYSICS

- lightning before thunder
- objects floating
- heat transfer
- sound traveling
- shadows
- reflections
- pressure

SPACE

- Moon appearing larger near horizon
- stars appearing to move
- space appearing black
- eclipses
- planetary motion

TECHNOLOGY

Only when the question concerns ONE familiar observable feature.

GOOD:

Why does airplane turbulence happen?

Why does noise cancellation work?

Why does your phone get hot while charging?

BAD:

How do smartphones work?

How does the internet work?

How do computers work?

These are too broad.

============================================================
35–45 SECOND TEST
============================================================

Imagine the finished Short.

Can the question be answered with:

0–3 sec:
HOOK

3–20 sec:
MECHANISM

20–35 sec:
SURPRISING DETAIL / TWIST

35–45 sec:
PAYOFF + OPEN LOOP

If answering the question requires a long history lesson,
multiple unrelated mechanisms, or extensive background,
REJECT IT.

============================================================
RESEARCH TEST
============================================================

The question must realistically be answerable using at least
two independent credible sources.

Prefer:

- peer-reviewed research
- universities
- government agencies
- scientific institutions
- established research organizations
- authoritative scientific databases

The answer should be supported by actual evidence.

Avoid:

- rumors
- myths
- social media claims
- conspiracy theories
- unverifiable stories
- vague folklore
- speculation presented as fact

============================================================
VISUAL TEST
============================================================

The phenomenon should naturally produce useful visuals.

Prefer:

- physical processes
- microscopic processes
- internal mechanisms
- cause and effect
- before/after
- transformations
- movement
- experiments
- simulations
- scale comparisons
- environments
- anatomical visualization

Avoid questions where the video would mostly show
people talking.

============================================================
SURPRISE TEST
============================================================

The real answer should be more interesting than the obvious answer.

GOOD:

Why does metal feel colder than wood?

The viewer may assume the metal is actually colder.

GOOD:

Why does your voice sound different recorded?

The viewer may not realize they normally hear their voice
through both air conduction and bone conduction.

GOOD:

Why do eyes water when cutting onions?

The viewer may think the onion somehow "makes you cry,"
but the mechanism is chemical irritation and a protective
tear response.

============================================================
FAMILIARITY TEST
============================================================

Prefer questions that millions of people could recognize.

The viewer should be able to think:

"I've experienced that."

Avoid questions that require the viewer to already care about
a specialized field.

============================================================
ORIGINALITY
============================================================

Do not repeat previous topics.

Do not produce a superficial wording variation.

Example:

Previous:
Why does metal feel colder than wood

Reject:

Why does steel feel colder than plastic

unless the underlying phenomenon is genuinely different.

============================================================
MONETIZATION SAFETY
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
- fearmongering
- medical diagnosis
- medical treatment instructions

Normal educational explanations of human biology are allowed.

============================================================
FORBIDDEN FORMATS
============================================================

Never generate:

- Top 5
- Top 10
- lists
- countdowns
- compilations
- generic facts
- broad academic subjects
- "the science of..."
- "history of..."
- "benefits of..."
- "everything about..."
- "what is..."
  when the subject is extremely broad

============================================================
TOPIC LENGTH
============================================================

Maximum 12 words.

Prefer 5–10 words.

The question must remain natural conversational English.

============================================================
OUTPUT
============================================================

Return ONLY ONE topic.

No explanation.

No quotation marks.

No numbering.

No emojis.

No "Did you know".

No "Let's explore".

No "Today we're going to".

No terminal punctuation.

============================================================
FINAL OBJECTIVE
============================================================

Generate:

ONE FAMILIAR PHENOMENON
+
ONE CLEAR QUESTION
+
ONE EXPLANATABLE MECHANISM
+
ONE SURPRISING PAYOFF
+
STRONG VISUAL POTENTIAL
+
STRONG RESEARCHABILITY

The best topic is something millions of people could recognize
and immediately want explained.
"""


# ==========================================================================
# FILE HELPERS
# ==========================================================================

def _atomic_write_json(path, data):
    """
    Safely write JSON using a temporary file followed by atomic replace.
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

        if isinstance(
            data,
            list,
        ):

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


def _save_used(used):

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


def _save_next_topic(topic):

    topic = _clean_topic(
        topic
    )

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

    topic = str(
        topic or ""
    ).strip()

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
# TOPIC BASIC VALIDATION
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

    if len(topic) > MAX_TOPIC_CHARACTERS:
        return False

    if max_words is not None:

        if len(topic.split()) > max_words:
            return False

    lowered = topic.lower()

    forbidden = [

        "top 10",
        "top 5",
        "did you know",
        "conspiracy",
        "miracle",
        "amazing facts",
        "interesting facts",
        "things you didn't know",
        "things you never knew",
        "10 facts",
        "5 facts",
        "facts about",
        "ultimate guide",
        "complete guide",
        "shocking truth",
        "secret they don't want",
        "the science of",
        "the biology of",
        "the physics of",
        "the history of",
    ]

    for phrase in forbidden:

        if phrase in lowered:
            return False

    if re.match(
        r"^(top|best)\s+\d+",
        lowered,
    ):

        return False

    generic_starts = [
        "the history of",
        "introduction to",
        "understanding",
        "an introduction",
        "what is science",
        "what is biology",
        "what is physics",
        "the science of",
        "the biology of",
        "the physics of",
    ]

    for phrase in generic_starts:

        if lowered.startswith(
            phrase
        ):

            return False

    academic_terms = [
        "phenophysiological",
        "thermodynamic",
        "methodological",
        "characterization",
        "classification",
        "quantification",
    ]

    for term in academic_terms:

        if term in lowered:
            return False

    return True


# ==========================================================================
# QUESTION STRUCTURE VALIDATION
# ==========================================================================

def _is_question(topic):

    lowered = topic.lower().strip()

    starters = (
        "why ",
        "how ",
        "can ",
        "do ",
        "does ",
        "is ",
        "are ",
    )

    return lowered.startswith(
        starters
    )


def _has_specificity(topic):

    lowered = topic.lower()

    # A question containing one of these concrete experience
    # indicators is more likely to represent an observable phenomenon.
    concrete_terms = [

        "eye",
        "eyes",
        "ear",
        "ears",
        "voice",
        "sound",
        "skin",
        "hair",
        "hand",
        "hands",
        "finger",
        "fingers",
        "brain",
        "body",
        "sleep",
        "dream",
        "memory",
        "song",
        "music",
        "water",
        "ice",
        "rain",
        "snow",
        "metal",
        "wood",
        "glass",
        "light",
        "shadow",
        "heat",
        "cold",
        "fire",
        "smell",
        "onion",
        "bird",
        "birds",
        "dog",
        "dogs",
        "cat",
        "cats",
        "bee",
        "bees",
        "moon",
        "sun",
        "stars",
        "phone",
        "plane",
        "airplane",
        "car",
        "road",
        "electricity",
    ]

    return any(
        re.search(
            rf"\b{re.escape(term)}\b",
            lowered,
        )
        for term in concrete_terms
    )


def _has_observable_action(topic):

    lowered = topic.lower()

    action_terms = [

        "feel",
        "feels",
        "feeling",
        "look",
        "looks",
        "looking",
        "sound",
        "sounds",
        "hear",
        "hearing",
        "see",
        "seeing",
        "water",
        "watering",
        "tear",
        "tears",
        "cry",
        "crying",
        "wrinkle",
        "wrinkles",
        "float",
        "floats",
        "freeze",
        "freezes",
        "melt",
        "melts",
        "move",
        "moves",
        "fly",
        "flies",
        "tilt",
        "tilts",
        "smell",
        "smells",
        "stick",
        "sticks",
        "burn",
        "burns",
        "glow",
        "glows",
        "ring",
        "rings",
        "echo",
        "echoes",
        "yawn",
        "yawns",
        "tickle",
        "tickles",
        "sneeze",
        "sneezes",
        "hiccup",
        "hiccups",
        "change",
        "changes",
        "happen",
        "happens",
        "work",
        "works",
    ]

    return any(
        re.search(
            rf"\b{re.escape(term)}\b",
            lowered,
        )
        for term in action_terms
    )


def _has_mechanism_question(topic):

    lowered = topic.lower()

    mechanism_indicators = [

        "why",
        "how",
        "happen",
        "happens",
        "work",
        "works",
        "cause",
        "causes",
        "feel",
        "feels",
        "change",
        "changes",
        "move",
        "moves",
        "sound",
        "sounds",
        "look",
        "looks",
        "smell",
        "smells",
        "float",
        "floats",
        "freeze",
        "freezes",
        "remember",
        "forget",
        "dream",
        "tickle",
        "wrinkle",
        "yawn",
    ]

    return any(
        re.search(
            rf"\b{re.escape(term)}\b",
            lowered,
        )
        for term in mechanism_indicators
    )


def _is_broad_subject(topic):

    lowered = topic.lower().strip()

    for pattern in BROAD_QUESTION_PATTERNS:

        if re.search(
            pattern,
            lowered,
        ):

            return True

    words = set(
        re.findall(
            r"[a-z]+",
            lowered,
        )
    )

    # Broad academic nouns without a concrete phenomenon.
    broad_hits = words & BROAD_SUBJECT_TERMS

    if broad_hits and not _has_observable_action(
        topic
    ):

        return True

    for phrase in LOW_VALUE_PATTERNS:

        if phrase in lowered:
            return True

    return False


def _question_quality_score(topic):

    score = 0

    if _is_question(topic):
        score += 2

    if _has_specificity(topic):
        score += 2

    if _has_observable_action(topic):
        score += 2

    if _has_mechanism_question(topic):
        score += 2

    if not _is_broad_subject(topic):
        score += 2

    return score


def _passes_question_quality(topic):

    if not _is_question(topic):

        print(
            "⚠️ Rejected: not a natural WHY/HOW-style question."
        )

        return False

    if not _has_specificity(topic):

        print(
            "⚠️ Rejected: question is not specific enough."
        )

        return False

    if not _has_observable_action(topic):

        print(
            "⚠️ Rejected: no clear observable phenomenon/action."
        )

        return False

    if not _has_mechanism_question(topic):

        print(
            "⚠️ Rejected: no clear mechanism-oriented question."
        )

        return False

    if _is_broad_subject(topic):

        print(
            "⚠️ Rejected: question is too broad."
        )

        return False

    score = _question_quality_score(
        topic
    )

    print(
        f"🧩 Question quality score: "
        f"{score}/10"
    )

    return score >= 8


# ==========================================================================
# NORMALIZED TOPIC COMPARISON
# ==========================================================================

def _topic_key(topic):

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

    for existing in used:

        if (
            _topic_key(
                existing
            )
            == key
        ):

            return True

    return False


# ==========================================================================
# TOPIC WORDS
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

    words = re.findall(
        r"[a-z0-9]+",
        _topic_key(
            topic
        ),
    )

    return {
        word
        for word in words
        if (
            len(word) >= 3
            and
            word not in stop_words
        )
    }


# ==========================================================================
# TOPIC SIMILARITY
# ==========================================================================

def _too_similar_to_used(
    topic,
    used,
):

    current_words = _topic_words(
        topic
    )

    if not current_words:
        return False

    for existing in used:

        existing_words = _topic_words(
            existing
        )

        if not existing_words:
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

        similarity = (
            len(intersection)
            /
            len(union)
        )

        if similarity >= 0.72:
            return True

    return False


# ==========================================================================
# VIRAL TOPIC SCORING
# ==========================================================================

def _contains_term(
    text,
    term,
):

    return bool(
        re.search(
            rf"\b{re.escape(term)}\b",
            text,
        )
    )


def _score_topic(topic):

    """
    Local curiosity pre-score.

    Maximum:

        Curiosity      5
        Familiarity    5
        Surprise       5
        Payoff         5
        Visual         5
        Researchable   5

    Total = 30

    This is only a pre-filter.

    research.py remains the authoritative research gate.
    """

    lowered = topic.lower()

    words = topic.split()

    scores = {
        "curiosity": 0,
        "familiarity": 0,
        "surprise": 0,
        "payoff": 0,
        "visual": 0,
        "researchable": 0,
    }

    # ----------------------------------------------------------------------
    # CURIOSITY
    # ----------------------------------------------------------------------

    question_starters = (
        "why ",
        "how ",
        "what ",
        "can ",
        "do ",
        "does ",
        "is ",
        "are ",
    )

    if lowered.startswith(
        question_starters
    ):

        scores["curiosity"] += 3

    curiosity_terms = [
        "why",
        "how",
        "really",
        "actually",
        "happen",
        "different",
        "feel",
        "look",
        "sound",
        "seem",
    ]

    curiosity_hits = sum(
        1
        for term in curiosity_terms
        if _contains_term(
            lowered,
            term,
        )
    )

    scores["curiosity"] += min(
        2,
        curiosity_hits,
    )

    scores["curiosity"] = min(
        5,
        scores["curiosity"],
    )

    # ----------------------------------------------------------------------
    # FAMILIARITY
    # ----------------------------------------------------------------------

    familiar_terms = [
        "brain",
        "body",
        "voice",
        "hand",
        "hands",
        "finger",
        "fingers",
        "eye",
        "eyes",
        "ear",
        "ears",
        "skin",
        "hair",
        "sleep",
        "dream",
        "memory",
        "time",
        "water",
        "ice",
        "rain",
        "snow",
        "metal",
        "wood",
        "phone",
        "car",
        "plane",
        "bird",
        "dog",
        "cat",
        "bee",
        "moon",
        "sun",
        "stars",
        "space",
        "sound",
        "light",
        "electricity",
        "fire",
        "food",
        "music",
        "song",
        "room",
        "road",
        "glass",
        "air",
        "cold",
        "hot",
        "heat",
        "onion",
    ]

    familiarity_hits = sum(
        1
        for term in familiar_terms
        if _contains_term(
            lowered,
            term,
        )
    )

    if familiarity_hits >= 3:
        scores["familiarity"] = 5

    elif familiarity_hits == 2:
        scores["familiarity"] = 4

    elif familiarity_hits == 1:
        scores["familiarity"] = 3

    # ----------------------------------------------------------------------
    # SURPRISE
    # ----------------------------------------------------------------------

    surprise_terms = [
        "actually",
        "really",
        "different",
        "feel",
        "seem",
        "look",
        "sound",
        "strange",
        "opposite",
        "before",
        "after",
        "without",
        "despite",
        "can't",
        "cannot",
        "never",
    ]

    surprise_hits = sum(
        1
        for term in surprise_terms
        if _contains_term(
            lowered,
            term,
        )
    )

    scores["surprise"] = min(
        5,
        2 + surprise_hits,
    )

    if (
        "different" in lowered
        or
        "feel" in lowered
        or
        "look" in lowered
        or
        "sound" in lowered
    ):

        scores["surprise"] = min(
            5,
            scores["surprise"] + 1,
        )

    # ----------------------------------------------------------------------
    # PAYOFF
    # ----------------------------------------------------------------------

    payoff_terms = [
        "why",
        "how",
        "happen",
        "work",
        "change",
        "move",
        "float",
        "freeze",
        "boil",
        "remember",
        "forget",
        "dream",
        "tickle",
        "wrinkle",
        "yawn",
        "smell",
        "hear",
        "see",
        "feel",
        "sound",
        "water",
        "tear",
        "cry",
    ]

    payoff_hits = sum(
        1
        for term in payoff_terms
        if _contains_term(
            lowered,
            term,
        )
    )

    if payoff_hits >= 3:
        scores["payoff"] = 5

    elif payoff_hits == 2:
        scores["payoff"] = 4

    elif payoff_hits == 1:
        scores["payoff"] = 3

    # ----------------------------------------------------------------------
    # VISUAL
    # ----------------------------------------------------------------------

    visual_terms = [
        "water",
        "ice",
        "rain",
        "snow",
        "metal",
        "wood",
        "fire",
        "light",
        "sound",
        "voice",
        "brain",
        "eye",
        "eyes",
        "hand",
        "hands",
        "finger",
        "fingers",
        "skin",
        "hair",
        "bird",
        "dog",
        "cat",
        "bee",
        "moon",
        "sun",
        "space",
        "plane",
        "phone",
        "electricity",
        "music",
        "song",
        "dream",
        "sleep",
        "glass",
        "heat",
        "cold",
        "onion",
    ]

    visual_hits = sum(
        1
        for term in visual_terms
        if _contains_term(
            lowered,
            term,
        )
    )

    if visual_hits >= 3:
        scores["visual"] = 5

    elif visual_hits == 2:
        scores["visual"] = 4

    elif visual_hits == 1:
        scores["visual"] = 3

    # ----------------------------------------------------------------------
    # RESEARCHABILITY
    # ----------------------------------------------------------------------

    research_terms = [
        "brain",
        "body",
        "psychology",
        "memory",
        "dream",
        "sleep",
        "sound",
        "light",
        "electricity",
        "water",
        "ice",
        "heat",
        "metal",
        "wood",
        "rain",
        "space",
        "moon",
        "sun",
        "planet",
        "bird",
        "bee",
        "dog",
        "cat",
        "voice",
        "eye",
        "eyes",
        "skin",
        "physics",
        "biology",
        "chemistry",
        "gravity",
        "weather",
        "air",
        "onion",
        "tears",
        "tearing",
        "irritation",
        "volatile",
    ]

    research_hits = sum(
        1
        for term in research_terms
        if _contains_term(
            lowered,
            term,
        )
    )

    if research_hits >= 2:
        scores["researchable"] = 5

    elif research_hits == 1:
        scores["researchable"] = 4

    else:
        scores["researchable"] = 2

    # ----------------------------------------------------------------------
    # LENGTH
    # ----------------------------------------------------------------------

    if 4 <= len(words) <= 9:
        length_bonus = 2

    elif 10 <= len(words) <= 12:
        length_bonus = 1

    else:
        length_bonus = 0

    # ----------------------------------------------------------------------
    # FINAL
    # ----------------------------------------------------------------------

    total = sum(
        scores.values()
    )

    total = min(
        MAX_VIRAL_SCORE,
        total + length_bonus,
    )

    return total


def _passes_viral_score(topic):

    score = _score_topic(
        topic
    )

    print(
        f"📊 Curiosity pre-score: "
        f"{score}/{MAX_VIRAL_SCORE}"
    )

    return score >= MIN_VIRAL_SCORE


# ==========================================================================
# PENDING TOPIC
# ==========================================================================

def get_pending_topic():

    """
    Pending next_short topics have no new-topic word restriction.
    """

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

Generate ONE completely new curiosity question for
Mint-YT-Factory.

============================================================
QUESTION-FIRST REQUIREMENT
============================================================

The output MUST be a specific question about ONE observable
phenomenon.

It should answer the following mental test:

"What exactly is happening that the viewer has noticed?"

Then:

"What mechanism explains it?"

The question must be narrow enough to explain properly
in approximately 35–45 seconds.

============================================================
PREFERRED STRUCTURE
============================================================

Prefer:

Why does [thing] [observable behavior]?

Why do [people/animals/things] [observable behavior]?

How does [specific phenomenon] happen?

Why can [familiar thing] [unexpected behavior]?

============================================================
GOOD EXAMPLES
============================================================

Why do your eyes water when cutting onions

Why does metal feel colder than wood

Why do fingers wrinkle in water

Why does your voice sound different recorded

Why can't you tickle yourself

Why does ice float

Why does rain smell

Why do dogs tilt their heads

Why can birds sit on power lines

Why does the Moon look bigger near the horizon

These are examples of FORMAT and specificity only.

Do NOT copy them.

============================================================
REJECT BROAD TOPICS
============================================================

Reject questions like:

How does the internet work

How do airplanes work

How does the brain work

How does electricity work

What is gravity

What is quantum physics

How does artificial intelligence work

The science of sleep

The biology of humans

These are too broad.

============================================================
REJECT GENERIC TOPICS
============================================================

Do not generate:

The science of onions

Benefits of sleep

History of airplanes

Interesting facts about birds

How animals communicate

Why nature is amazing

How the human body works

============================================================
PREFER
============================================================

Everyday mysteries.

Human body observations.

Brain and psychology experiences.

Animals people see regularly.

Simple physics people experience.

Technology features people personally encounter.

Space phenomena people recognize.

The viewer should be able to think:

"I've experienced that."

============================================================
RESEARCH
============================================================

The question must have enough credible evidence to support
the answer with at least two independent sources.

Prefer scientific papers, universities, government agencies,
scientific institutions, and established research organizations.

Do not rely on myths, rumors, social media claims,
conspiracy theories, or unverifiable stories.

============================================================
VISUALS
============================================================

The phenomenon should be visually demonstrable.

Prefer:

physical processes
microscopic mechanisms
internal processes
cause and effect
movement
transformations
experiments
simulations
before/after
scale comparisons

============================================================
MONETIZATION
============================================================

Avoid graphic violence, gore, sexual content, extremist content,
dangerous instructions, drugs, political outrage, conspiracy
theories, fearbait, medical diagnosis, and treatment instructions.

============================================================
OUTPUT
============================================================

Return ONLY ONE topic.

Maximum 12 words.

Prefer 5–10 words.

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
            f"🧠 Viral question attempt "
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

                    temperature=0.85,
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
                    "⚠️ Invalid new topic. Retrying."
                )

                continue

            # --------------------------------------------------------------
            # QUESTION QUALITY
            # --------------------------------------------------------------

            if not _passes_question_quality(
                topic
            ):

                print(
                    "⚠️ Question quality gate failed. Retrying."
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
                    "⚠️ Topic already used. Retrying."
                )

                continue

            # --------------------------------------------------------------
            # SEMANTIC DUPLICATE
            # --------------------------------------------------------------

            if _too_similar_to_used(
                topic,
                used,
            ):

                print(
                    "⚠️ Topic is too similar to a previous topic. Retrying."
                )

                continue

            # --------------------------------------------------------------
            # PENDING DUPLICATE
            # --------------------------------------------------------------

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
                    "⚠️ Topic already pending. Retrying."
                )

                continue

            # --------------------------------------------------------------
            # VIRAL SCORE
            # --------------------------------------------------------------

            if not _passes_viral_score(
                topic
            ):

                print(
                    "⚠️ Topic failed curiosity pre-score. Retrying."
                )

                continue

            # --------------------------------------------------------------
            # SUCCESS
            # --------------------------------------------------------------

            print("=" * 80)
            print("🔥 GENERATED HIGH-CURIOSITY QUESTION")
            print("=" * 80)

            print(topic)

            print(
                f"Words: {len(topic.split())}"
            )

            print(
                f"Characters: {len(topic)}"
            )

            print(
                f"Question quality: "
                f"{_question_quality_score(topic)}/10"
            )

            print(
                f"Curiosity score: "
                f"{_score_topic(topic)}/"
                f"{MAX_VIRAL_SCORE}"
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
    2. Gemini-generated high-quality question

    The selected topic is NOT committed here.
    """

    # ----------------------------------------------------------------------
    # PRIORITY 1 — PENDING TOPIC
    # ----------------------------------------------------------------------

    pending = get_pending_topic()

    if pending:
        return pending

    # ----------------------------------------------------------------------
    # PRIORITY 2 — GENERATE NEW TOPIC
    # ----------------------------------------------------------------------

    topic = _generate_new_topic()

    if topic:

        if not _save_next_topic(
            topic
        ):

            raise RuntimeError(
                "Could not save newly generated "
                "topic to pending queue."
            )

        print("=" * 80)
        print("📌 NEW VIRAL-CURIOSITY QUESTION QUEUED")
        print("=" * 80)

        print(topic)

        print("=" * 80)

        return topic

    raise RuntimeError(
        "Could not generate a strong high-curiosity question "
        "and no pending topic is available."
    )


# ==========================================================================
# TOPIC COMMIT
# ==========================================================================

def commit_topic(topic):

    """
    Commit CURRENT topic only after successful upload.

    Never blindly deletes next_topic.json.

    If next_topic.json contains a new next_short,
    it is preserved.
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
    # Add current topic to used list.
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
        print("✅ CURRENT TOPIC COMMITTED")
        print("=" * 80)

        print(topic)

        print("=" * 80)

    else:

        print(
            "ℹ️ Current topic is already committed:"
        )

        print(topic)

    # ----------------------------------------------------------------------
    # Check pending queue.
    # ----------------------------------------------------------------------

    pending = _load_next_topic()

    if not pending:
        return True

    # ----------------------------------------------------------------------
    # If queue still contains current topic, remove it.
    # ----------------------------------------------------------------------

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
                "Current topic committed, but its pending queue "
                "entry could not be removed."
            )

        return True

    # ----------------------------------------------------------------------
    # Otherwise preserve NEW next_short.
    # ----------------------------------------------------------------------

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

    next_short has NO word-count restriction.
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
            "⚠️ next_short is already a committed topic:"
        )

        print(next_short)

        return False

    if _too_similar_to_used(
        next_short,
        used,
    ):

        print(
            "⚠️ next_short is too similar to a previously used topic:"
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
        print("🎯 NEXT VIRAL CURIOSITY QUESTION")
        print("=" * 80)

        print(topic)

        print("=" * 80)

    except Exception as error:

        print("=" * 80)
        print("❌ TOPIC GENERATION FAILED")
        print("=" * 80)

        print(error)

        raise