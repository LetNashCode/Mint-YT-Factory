"""
topics.py
Mint-YT-Factory

Version 5.0

VIRAL CURIOSITY TOPIC ENGINE

Core strategy:

Human curiosity
        ↓
High-interest question
        ↓
Curiosity / surprise / payoff scoring
        ↓
Researchability filter
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

Examples:

- Why can't you tickle yourself
- Why does your voice sound different recorded
- Why does ice float
- Why do songs get stuck in your head
- Why does metal feel colder than wood
- Why do fingers wrinkle in water
- Why can birds sit on power lines
- Why does the Moon look bigger near the horizon

The ideal topic creates:

"I've wondered about that."

followed by:

"Wait... that's why?"

The research gate remains strict.

The topic engine is optimized for:

- curiosity
- familiarity
- surprise
- satisfying payoff
- visual potential
- researchability
- originality
- monetization-friendly content

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

# Slightly increased from 8 because natural curiosity questions sometimes
# need a few extra words to sound human.
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

# Minimum total score required before a generated topic can enter the
# research pipeline.
MIN_VIRAL_SCORE = 24

# Individual dimensions are scored 1-5.
MAX_SCORE_PER_DIMENSION = 5


# ==========================================================================
# GEMINI SYSTEM PROMPT
# ==========================================================================

SYSTEM_PROMPT = """
You are the viral content strategist for Mint-YT-Factory.

Your job is NOT to generate generic educational topics.

Your job is to discover ONE highly compelling question that ordinary
people genuinely want answered.

The channel's content philosophy is:

"Questions you've probably wondered about but never looked up."

The final video will be a roughly 45-second research-backed YouTube
Short.

============================================================
PRIMARY GOAL
============================================================

Generate topics that have strong potential to make viewers stop
scrolling because they recognize the question and immediately want
the answer.

The ideal viewer reaction is:

"I've wondered about that."

followed by:

"Wait... really?"

and finally:

"Ohhh, that's why."

============================================================
HIGH-VALUE TOPIC TYPES
============================================================

Prefer questions involving:

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

Simple observations about the body with surprising explanations.

Examples:

- Why do we get goosebumps
- Why does scratching an itch feel good
- Why does yawning spread
- Why do eyes water when cutting onions

4. BRAIN AND PSYCHOLOGY

Common experiences with an unexpected mechanism.

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

Behavior people have noticed but don't understand.

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

Before returning a topic, evaluate it internally.

Score each dimension from 1 to 5.

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

Avoid topics that are merely technically interesting.

============================================================
PREFER QUESTIONS OVER SUBJECTS
============================================================

BAD:

"How honeybees regulate hive temperature"

BETTER:

"How do bees keep their hive cool?"

BEST:

"How do thousands of bees keep their hive from overheating?"

The viewer should immediately understand what mystery the video will
solve.

============================================================
HOOK POTENTIAL
============================================================

The topic should naturally allow a strong opening sentence.

GOOD:

"Your brain knows you're about to tickle yourself."

GOOD:

"That metal spoon isn't actually colder than the wooden one."

GOOD:

"Birds are sitting on a wire carrying electricity."

BAD:

"Today we will learn about thermal conductivity."

============================================================
SURPRISE AND COUNTERINTUITION
============================================================

Prefer topics where:

- the obvious answer is wrong
- something ordinary has a hidden mechanism
- a familiar experience has a strange explanation
- a common belief is incomplete
- the explanation is more interesting than the question

Do NOT manufacture controversy.

The surprise must come from the real answer.

============================================================
RESEARCH REQUIREMENT
============================================================

The topic must be realistically researchable.

Prefer phenomena that can be supported by at least two independent
credible sources.

Strong source types include:

- peer-reviewed research
- universities
- government agencies
- scientific institutions
- established research organizations
- authoritative scientific databases

Avoid topics that depend primarily on:

- rumors
- anecdotes
- social media claims
- conspiracy theories
- unverifiable stories
- vague internet folklore

============================================================
VISUAL REQUIREMENT
============================================================

The topic must be capable of producing compelling visual storytelling.

Prefer topics where we can show:

- a physical process
- a before/after
- hidden mechanisms
- microscopic processes
- internal body processes
- cause and effect
- surprising transformations
- scale comparisons
- movement
- environments
- experiments
- simulations

Avoid topics that would require seven scenes of people simply talking.

============================================================
MONETIZATION SAFETY
============================================================

Prefer advertiser-friendly topics.

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

Educational explanations of the human body are allowed when handled
factually and non-graphically.

============================================================
CONTENT QUALITY
============================================================

One video = ONE question.

Do NOT generate:

- listicles
- countdowns
- "Top 5"
- "Top 10"
- compilations
- collections of unrelated facts
- generic "10 amazing facts"
- generic "5 things you didn't know"
- broad academic subjects

The question should be narrow enough to answer meaningfully in
approximately 45 seconds.

============================================================
ORIGINALITY
============================================================

Do not repeat previous topics.

Do not generate a topic that is merely a slight wording variation
of a previous topic.

For example, if we already covered:

"Why does metal feel colder than wood?"

Do not generate:

"Why does steel feel colder than plastic?"

unless it represents a genuinely different phenomenon.

============================================================
TOPIC FORMAT
============================================================

Return ONLY ONE topic.

Maximum 12 words.

Natural conversational English.

A curiosity question is preferred.

Do not use:

- "Did you know"
- "Let's explore"
- "Today we're going to"
- "In this video"
- "The science of"
- "Amazing facts about"
- "Top 5"
- "Top 10"

No emojis.

No numbering.

No quotation marks.

No clickbait.

No terminal punctuation.

============================================================
IMPORTANT
============================================================

Do NOT optimize for academic sophistication.

Optimize for:

HUMAN CURIOSITY
+
SURPRISE
+
SATISFYING ANSWER
+
VISUAL STORY
+
STRONG RESEARCH
+
ADVERTISER SAFETY

The best topic is something a huge number of people could recognize
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

    Normally this is only used when the pending topic is still
    the current topic being committed.
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

    # ----------------------------------------------------------------------
    # Remove Markdown/code formatting.
    # ----------------------------------------------------------------------

    topic = topic.replace(
        "```json",
        "",
    )

    topic = topic.replace(
        "```",
        "",
    )

    # ----------------------------------------------------------------------
    # Remove quotation marks.
    # ----------------------------------------------------------------------

    topic = topic.replace(
        '"',
        "",
    )

    topic = topic.replace(
        "'",
        "",
    )

    # ----------------------------------------------------------------------
    # Remove accidental labels.
    # ----------------------------------------------------------------------

    topic = re.sub(
        r"^(topic|next topic|next_short|next short)\s*:\s*",
        "",
        topic,
        flags=re.IGNORECASE,
    )

    # ----------------------------------------------------------------------
    # Remove accidental numbering.
    # ----------------------------------------------------------------------

    topic = re.sub(
        r"^\s*\d+[\.\)\-:]\s*",
        "",
        topic,
    )

    # ----------------------------------------------------------------------
    # Normalize whitespace.
    # ----------------------------------------------------------------------

    topic = " ".join(
        topic.split()
    )

    # ----------------------------------------------------------------------
    # Remove terminal punctuation.
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # Character safety.
    # ----------------------------------------------------------------------

    if len(
        topic
    ) > MAX_TOPIC_CHARACTERS:

        return False

    # ----------------------------------------------------------------------
    # Optional word limit.
    # ----------------------------------------------------------------------

    if max_words is not None:

        if len(
            topic.split()
        ) > max_words:

            return False

    # ----------------------------------------------------------------------
    # Forbidden patterns.
    # ----------------------------------------------------------------------

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
    ]

    lowered = topic.lower()

    for phrase in forbidden:

        if phrase in lowered:

            return False

    # ----------------------------------------------------------------------
    # Obvious list formatting.
    # ----------------------------------------------------------------------

    if re.match(
        r"^(top|best)\s+\d+",
        lowered,
    ):

        return False

    # ----------------------------------------------------------------------
    # Reject obvious generic educational subjects.
    # ----------------------------------------------------------------------

    generic_starts = [
        "the history of",
        "introduction to",
        "understanding",
        "an introduction",
        "what is science",
        "what is biology",
        "what is physics",
    ]

    for phrase in generic_starts:

        if lowered.startswith(
            phrase
        ):

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
# TOPIC SIMILARITY
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

        # Very high overlap means this is probably just a reworded
        # version of an old topic.
        if similarity >= 0.72:

            return True

    return False


# ==========================================================================
# VIRAL TOPIC SCORING
# ==========================================================================

def _score_topic(
    topic,
):
    """
    Heuristic pre-filter.

    Gemini performs the real semantic evaluation in the prompt,
    but these checks prevent obviously weak topics from entering
    the research pipeline.
    """

    lowered = topic.lower()

    words = topic.split()

    score = 0

    # ----------------------------------------------------------------------
    # Curiosity question.
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

        score += 4

    # ----------------------------------------------------------------------
    # Everyday language / recognizable concepts.
    # ----------------------------------------------------------------------

    familiar_terms = [
        "brain",
        "body",
        "voice",
        "hand",
        "hands",
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
    ]

    familiarity_hits = sum(
        1
        for term in familiar_terms
        if term in lowered
    )

    score += min(
        6,
        familiarity_hits * 2
    )

    # ----------------------------------------------------------------------
    # Mechanism / surprise indicators.
    # ----------------------------------------------------------------------

    mechanism_terms = [
        "really",
        "actually",
        "feel",
        "seem",
        "look",
        "sound",
        "happen",
        "work",
        "change",
        "move",
        "float",
        "freeze",
        "boil",
        "shock",
        "hear",
        "see",
        "remember",
        "forget",
        "dream",
        "tickle",
        "wrinkle",
        "yawn",
        "smell",
    ]

    mechanism_hits = sum(
        1
        for term in mechanism_terms
        if term in lowered
    )

    score += min(
        8,
        mechanism_hits * 2
    )

    # ----------------------------------------------------------------------
    # Concise questions tend to be easier to hook.
    # ----------------------------------------------------------------------

    if 4 <= len(words) <= 9:

        score += 4

    elif 10 <= len(words) <= 12:

        score += 2

    # ----------------------------------------------------------------------
    # Penalize generic academic language.
    # ----------------------------------------------------------------------

    generic_terms = [
        "phenomenon",
        "mechanism",
        "process",
        "regulation",
        "variation",
        "physiology",
        "thermodynamics",
        "characteristics",
        "classification",
    ]

    generic_hits = sum(
        1
        for term in generic_terms
        if term in lowered
    )

    score -= generic_hits * 3

    return score


def _passes_viral_score(
    topic,
):

    score = _score_topic(
        topic
    )

    print(
        f"📊 Curiosity pre-score: {score}"
    )

    return score >= MIN_VIRAL_SCORE


# ==========================================================================
# PENDING TOPIC
# ==========================================================================

def get_pending_topic():

    """
    Return the currently queued topic.

    Pending topics have NO word-count restriction.
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

The topic should preferably be something that:

- ordinary people recognize
- people have personally experienced
- makes viewers curious immediately
- has a surprising or counterintuitive answer
- has a satisfying explanation
- can be visually demonstrated
- can become a compelling 45-second story
- can be researched using at least two credible independent sources
- is advertiser-friendly
- is scientifically or historically defensible

Prefer questions such as:

Why can't you tickle yourself?

Why does metal feel colder than wood?

Why do fingers wrinkle in water?

Why does your voice sound different recorded?

Why do songs get stuck in your head?

Why can birds sit on power lines?

Why does ice float?

Why does the Moon look bigger near the horizon?

Do NOT copy these examples.

Find a different question.

Avoid:

- generic school topics
- academic paper titles
- obscure terminology
- generic "facts"
- listicles
- countdowns
- controversial claims
- conspiracy theories
- medical diagnosis
- medical treatment
- political topics
- fearbait
- clickbait
- fabricated phenomena
- unverifiable internet myths

The question should be narrow enough to answer properly in about
45 seconds.

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
            # Never repeat a committed topic.
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
            # Reject semantically similar topics.
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
            # Never duplicate pending topic.
            # --------------------------------------------------------------

            pending = _load_next_topic()

            if (
                pending
                and
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

            # --------------------------------------------------------------
            # Viral curiosity pre-score.
            # --------------------------------------------------------------

            if not _passes_viral_score(
                topic
            ):

                print(
                    "⚠️ Topic failed curiosity/viral pre-score."
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
                f"Pre-score: {_score_topic(topic)}"
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

    IMPORTANT:

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

    # ----------------------------------------------------------------------
    # Validate basic structure.
    # ----------------------------------------------------------------------

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