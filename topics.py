"""
topics.py
Mint-YT-Factory

Version 5.1

VIRAL CURIOSITY TOPIC ENGINE

Core strategy:

Human curiosity
        ↓
High-interest question
        ↓
Curiosity / familiarity / surprise / payoff scoring
        ↓
Researchability filter
        ↓
Visual potential filter
        ↓
Originality filter
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
Upload
        ↓
Save NEW next_short
        ↓
Commit CURRENT topic

CONTENT PHILOSOPHY:

Mint-YT-Factory is NOT a generic educational-facts channel.

The goal is to create research-backed Shorts about things people
genuinely wonder about.

The ideal viewer reaction is:

"I've wondered about that."

followed by:

"Wait... that's why?"

and finally:

"Ohhh."

CONTENT PRIORITIES:

1. Human curiosity
2. Familiarity
3. Surprise
4. Satisfying payoff
5. Visual storytelling
6. Strong researchability
7. Originality
8. Advertiser safety
9. Broad audience appeal
10. Monetization potential

IMPORTANT:

- Pending topics survive failed runs.
- Current topics are only committed after upload succeeds.
- next_topic.json is NEVER blindly deleted during commit.
- A newly generated next_short is preserved.
- Topic files are written atomically.
- A topic is never automatically marked used merely because it
  was selected.
- New Gemini topics have a maximum 12 words.
- next_short topics have NO word-count limit.
- Existing pending next_short topics always take priority.
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

NEW_TOPIC_MAX_WORDS = 12

MAX_TOPIC_CHARACTERS = 300

MAX_PREVIOUS_TOPICS = 300

MAX_TOPIC_GENERATION_ATTEMPTS = 10


# ==========================================================================
# GEMINI CONFIG
# ==========================================================================

MODEL_NAME = "gemini-flash-lite-latest"


# ==========================================================================
# VIRAL TOPIC REQUIREMENTS
# ==========================================================================

# The local heuristic can now reach 30 points.
#
# 30 = maximum possible:
#
# Curiosity      5
# Familiarity    5
# Surprise       5
# Payoff         5
# Visual         5
# Researchable   5
#
# The heuristic is intentionally only a PRE-FILTER.
# The real research gate remains in research.py.
#
MIN_VIRAL_SCORE = 20

MAX_VIRAL_SCORE = 30


# ==========================================================================
# GEMINI SYSTEM PROMPT
# ==========================================================================

SYSTEM_PROMPT = """
You are the viral content strategist for Mint-YT-Factory.

Your job is NOT to generate generic educational topics.

Your job is to discover ONE highly compelling question that ordinary
people genuinely want answered.

The channel's philosophy is:

"Questions you've probably wondered about but never looked up."

The final video will be a roughly 35–45 second research-backed
YouTube Short.

============================================================
PRIMARY GOAL
============================================================

Generate topics that make viewers stop scrolling because they
recognize the question and immediately want the answer.

The ideal reaction is:

"I've wondered about that."

then:

"Wait... really?"

then:

"Ohhh, that's why."

============================================================
HIGH-VALUE TOPIC TYPES
============================================================

Prefer:

1. SHOWER THOUGHTS

Things people randomly wonder about.

Examples:

- Why can't you tickle yourself
- Why does time feel faster as you age
- Why do we forget why we entered a room
- Why can you hear your own thoughts

2. EVERYDAY MYSTERIES

Things people experience constantly but rarely understand.

Examples:

- Why does metal feel colder than wood
- Why do fingers wrinkle in water
- Why does rain smell
- Why does your voice sound different recorded

3. HUMAN BODY QUESTIONS

Simple observations with surprising explanations.

Examples:

- Why do we get goosebumps
- Why does scratching an itch feel good
- Why does yawning spread
- Why do eyes water when cutting onions

4. BRAIN AND PSYCHOLOGY

Common experiences with unexpected mechanisms.

Examples:

- Why do songs get stuck in your head
- Why do embarrassing memories return years later
- Why do dreams feel real
- Why does déjà vu happen

5. EVERYDAY PHYSICS

Simple things with surprising scientific explanations.

Examples:

- Why does ice float
- Why can birds sit on power lines
- Why does glass look invisible
- Why can you see lightning before hearing thunder

6. SPACE QUESTIONS

Popular questions about things people see or wonder about.

Examples:

- Why is space black
- Why does the Moon look bigger near the horizon
- Why does the Moon show one side
- Why don't planets fall into the Sun

7. ANIMALS

Behavior people notice but don't understand.

Examples:

- Why do cats purr
- Why do dogs tilt their heads
- Why do birds fly in formation
- Why do bees fan their wings

8. TECHNOLOGY AND ENGINEERING

Everyday technology that seems mysterious.

Examples:

- Why does airplane mode exist
- Why don't phones overheat instantly
- How does noise cancellation work

============================================================
VIRALITY TEST
============================================================

Evaluate every candidate internally.

Score these dimensions mentally from 1 to 5:

CURIOUS:
Would a normal person genuinely wonder about this?

FAMILIAR:
Has the viewer personally experienced, seen, or encountered it?

SURPRISING:
Is the real answer likely to differ from the obvious assumption?

PAYOFF:
Does the answer create a satisfying "that's why" moment?

VISUAL:
Can the answer be shown through compelling visuals?

RESEARCHABLE:
Can credible independent scientific, academic, government,
university, or institutional sources explain it?

Each dimension should ideally score 4 or 5.

Do not optimize for academic sophistication.

Optimize for viewer curiosity.

============================================================
THE MOST IMPORTANT RULE
============================================================

A technically interesting subject is NOT automatically a good Short.

For example:

BAD:
"Hive temperature regulation in honeybees"

BETTER:
"How do bees keep their hive cool?"

STRONGER:
"How do thousands of bees stop their hive overheating?"

The viewer should immediately understand the mystery.

============================================================
HOOK POTENTIAL
============================================================

The topic should naturally allow a strong opening.

GOOD:

"That metal spoon isn't actually colder than the wooden one."

"Birds are sitting on a wire carrying electricity."

"Your brain knows you're about to tickle yourself."

BAD:

"Today we will learn about thermal conductivity."

============================================================
SURPRISE
============================================================

Prefer questions where:

- the obvious answer is incomplete
- something ordinary has a hidden mechanism
- a familiar experience has a strange explanation
- the explanation is more interesting than the question
- the viewer learns something counterintuitive

Do NOT manufacture controversy.

The surprise must come from the real answer.

============================================================
RESEARCH REQUIREMENT
============================================================

The topic must realistically be researchable.

Prefer phenomena that can be supported by at least two independent
credible sources.

Strong sources include:

- peer-reviewed research
- universities
- government agencies
- scientific institutions
- established research organizations
- authoritative scientific databases

Avoid:

- rumors
- anecdotes
- social media claims
- conspiracy theories
- unverifiable stories
- vague internet folklore

============================================================
VISUAL REQUIREMENT
============================================================

Prefer topics where we can show:

- physical processes
- before and after
- hidden mechanisms
- microscopic processes
- internal body processes
- cause and effect
- transformations
- scale comparisons
- movement
- environments
- experiments
- simulations

Avoid topics that would require several scenes of people simply
talking.

============================================================
MONETIZATION SAFETY
============================================================

Prefer advertiser-friendly subjects.

Avoid:

- graphic violence
- gore
- sexual content
- extremist content
- dangerous instructions
- drug use
- conspiracy theories
- political outrage
- medical diagnosis
- medical treatment instructions
- fearmongering
- fabricated discoveries

Educational human-body explanations are allowed when factual
and non-graphic.

============================================================
CONTENT FORMAT
============================================================

One video = ONE question.

Never generate:

- listicles
- countdowns
- Top 5
- Top 10
- compilations
- unrelated facts
- generic fact collections
- broad academic subjects

The question must be narrow enough to answer meaningfully in
approximately 35–45 seconds.

============================================================
ORIGINALITY
============================================================

Do not repeat previous topics.

Do not generate a slight wording variation of a previous topic.

Example:

Previous:
"Why does metal feel colder than wood?"

Do NOT generate:
"Why does steel feel colder than plastic?"

unless the underlying phenomenon is genuinely different.

============================================================
TOPIC FORMAT
============================================================

Return ONLY ONE topic.

Maximum 12 words.

Natural conversational English.

A curiosity question is strongly preferred.

Do not use:

- Did you know
- Let's explore
- Today we're going to
- In this video
- The science of
- Amazing facts about
- Top 5
- Top 10

No emojis.

No numbering.

No quotation marks.

No clickbait.

No terminal punctuation.

============================================================
FINAL OBJECTIVE
============================================================

Optimize for:

HUMAN CURIOSITY
+
FAMILIARITY
+
SURPRISE
+
SATISFYING PAYOFF
+
VISUAL STORY
+
STRONG RESEARCH
+
ADVERTISER SAFETY
+
BROAD AUDIENCE APPEAL

The best topic is something millions of people could recognize
and wonder about.
"""


# ==========================================================================
# FILE HELPERS
# ==========================================================================

def _atomic_write_json(
    path,
    data,
):
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
            os.path.exists(
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

    topic = _clean_topic(
        topic
    )

    if not topic:

        return False

    if len(
        topic
    ) > MAX_TOPIC_CHARACTERS:

        print(
            "⚠️ Topic exceeds character safety limit."
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
    Delete the pending topic.

    Normally only used when the pending topic is still the
    current topic being committed.
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

def _clean_topic(
    topic
):

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

    # ----------------------------------------------------------------------
    # Reject obviously long academic-style phrases.
    # ----------------------------------------------------------------------

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
# NORMALIZED TOPIC COMPARISON
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

        if (
            _topic_key(
                existing
            )
            == key
        ):

            return True

    return False


# ==========================================================================
# TOPIC WORD EXTRACTION
# ==========================================================================

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

    """
    Whole-word matching prevents false positives such as:

    "cat" matching "education"
    "car" matching "scare"
    """

    return bool(
        re.search(
            rf"\b{re.escape(term)}\b",
            text,
        )
    )


def _score_topic(
    topic,
):
    """
    Local curiosity pre-score.

    Maximum: 30

    Dimensions:

    Curiosity      0-5
    Familiarity    0-5
    Surprise       0-5
    Payoff         0-5
    Visual         0-5
    Researchable   0-5

    This is NOT the scientific verification gate.

    research.py remains responsible for actual research validation.
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
        curiosity_hits
    )

    scores["curiosity"] = min(
        5,
        scores["curiosity"]
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
        2 + surprise_hits
    )

    # Questions involving common experiences naturally receive
    # additional surprise potential.
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
            scores["surprise"] + 1
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

        # We do not automatically reject it here because research.py
        # is the authoritative research gate.
        scores["researchable"] = 2

    # ----------------------------------------------------------------------
    # QUESTION LENGTH
    # ----------------------------------------------------------------------

    if 4 <= len(words) <= 9:

        length_bonus = 2

    elif 10 <= len(words) <= 12:

        length_bonus = 1

    else:

        length_bonus = 0

    # ----------------------------------------------------------------------
    # FINAL SCORE
    # ----------------------------------------------------------------------

    total = sum(
        scores.values()
    )

    total = min(
        MAX_VIRAL_SCORE,
        total + length_bonus
    )

    return total


def _passes_viral_score(
    topic,
):

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
    Return the currently queued topic.

    Pending next_short topics have NO word-count restriction and
    are trusted as the continuation of the previous verified story.
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

Generate ONE completely new high-curiosity question for
Mint-YT-Factory.

The channel is built around:

"Questions you've probably wondered about but never looked up."

Think like a viral YouTube Shorts strategist.

The topic should:

- be recognizable to ordinary people
- feel personally relevant or familiar
- trigger immediate curiosity
- contain a real mystery
- have a surprising or counterintuitive explanation
- have a satisfying payoff
- be visually demonstrable
- work as a 35–45 second story
- have strong credible research available
- be advertiser-friendly
- be scientifically or historically defensible

Prefer topics involving:

- shower thoughts
- everyday mysteries
- human behavior
- brain and psychology
- body observations
- everyday physics
- animals
- space
- technology people use every day

Examples of the STYLE we want:

Why can't you tickle yourself

Why does metal feel colder than wood

Why do fingers wrinkle in water

Why does your voice sound different recorded

Why do songs get stuck in your head

Why can birds sit on power lines

Why does ice float

Why does the Moon look bigger near the horizon

Do NOT copy those examples.

Find a different question.

Avoid:

- generic school subjects
- academic paper titles
- obscure terminology
- generic facts
- listicles
- countdowns
- broad historical summaries
- controversial claims
- conspiracy theories
- medical diagnosis
- medical treatment
- political topics
- fearbait
- fabricated phenomena
- unverifiable internet myths

The topic must be narrow enough to answer properly in about
35–45 seconds.

Return ONLY the topic.
"""

    for attempt in range(
        1,
        MAX_TOPIC_GENERATION_ATTEMPTS + 1,
    ):

        print(
            f"🧠 Viral topic attempt "
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
            # Basic validation.
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
            # Exact duplicate.
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
            # Semantic duplicate.
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
            # Pending duplicate.
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
            # Viral curiosity pre-score.
            # --------------------------------------------------------------

            if not _passes_viral_score(
                topic
            ):

                print(
                    "⚠️ Topic failed curiosity pre-score. Retrying."
                )

                continue

            print("=" * 80)
            print("🔥 GENERATED HIGH-CURIOSITY TOPIC")
            print("=" * 80)

            print(
                topic
            )

            print(
                f"Words: {len(topic.split())}"
            )

            print(
                f"Characters: {len(topic)}"
            )

            print(
                f"Pre-score: "
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
    2. Gemini-generated high-curiosity topic

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
        print("📌 NEW VIRAL-CURIOSITY TOPIC QUEUED")
        print("=" * 80)

        print(
            topic
        )

        print("=" * 80)

        return topic

    raise RuntimeError(
        "Could not generate a strong high-curiosity topic "
        "and no pending topic is available."
    )


# ==========================================================================
# TOPIC COMMIT
# ==========================================================================

def commit_topic(
    topic
):

    """
    Commit the CURRENT topic after successful YouTube upload.

    next_topic.json may already contain the NEW next_short.

    Therefore this function NEVER blindly deletes next_topic.json.

    It deletes the file only if it still contains the CURRENT topic.
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
    # Add topic to used list.
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

        print(
            topic
        )

        print("=" * 80)

    else:

        print(
            "ℹ️ Current topic is already committed:"
        )

        print(
            topic
        )

    # ----------------------------------------------------------------------
    # Check pending file.
    # ----------------------------------------------------------------------

    pending = _load_next_topic()

    if not pending:

        return True

    # ----------------------------------------------------------------------
    # If pending file STILL contains current topic, remove it.
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
    # Otherwise it is the NEW next_short.
    #
    # Preserve it.
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

def save_next_short(
    next_short
):

    """
    Save the next topic generated by the current video's open loop.

    next_short has NO word-count restriction because it is generated
    from the story itself and can be more descriptive.
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

        print(
            next_short
        )

        return False

    # ----------------------------------------------------------------------
    # Do not queue an already committed topic.
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
    # Do not queue something extremely similar to an old topic.
    # ----------------------------------------------------------------------

    if _too_similar_to_used(
        next_short,
        used,
    ):

        print(
            "⚠️ next_short is too similar to a previously used topic:"
        )

        print(
            next_short
        )

        return False

    # ----------------------------------------------------------------------
    # Save atomically.
    # ----------------------------------------------------------------------

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
        print("🎯 NEXT VIRAL CURIOSITY TOPIC")
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