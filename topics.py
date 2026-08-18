"""
topics.py
Mint-YT-Factory

Version 6.1

VIRAL CURIOSITY QUESTION ENGINE

v6.1 improvements:
- Generates specific WHY/HOW curiosity questions
- Strong observable-phenomenon requirement
- Mechanism-oriented question generation
- Semantic-style specificity gate instead of hardcoded topic vocabulary
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

VERSION = "6.1"


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
# BROAD SUBJECT PROTECTION
# ==========================================================================

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
    "technology",
    "computer",
    "computers",
    "internet",
    "smartphones",
    "smartphone",
    "artificial",
    "intelligence",
}


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
    r"^how do smartphones work",
    r"^how does a smartphone work",
    r"^how does the internet",
    r"^what is gravity",
    r"^what is quantum",
    r"^what is consciousness",
    r"^what is dark matter",
    r"^what is artificial intelligence",
    r"^what is biology",
    r"^what is physics",
    r"^what is chemistry",
    r"^what is psychology",
    r"^what is astronomy",
    r"^what is evolution",
    r"^what is electricity",
]


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
    "facts about",
    "interesting facts",
    "the science of",
    "the biology of",
    "the physics of",
    "the psychology of",
    "the history of",
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
MOST IMPORTANT RULE
============================================================

Generate ONE question about ONE SPECIFIC OBSERVABLE PHENOMENON.

The viewer should be able to understand what is happening
without already knowing the science.

The phenomenon should be something a person can:

- see
- hear
- feel
- experience
- notice
- encounter
- observe

The question should ask WHY or HOW it happens.

The answer should reveal:

- a cause
- a mechanism
- a process
- an unexpected explanation
- or a counterintuitive reason

============================================================
STRONG QUESTION STRUCTURES
============================================================

Prefer:

Why does [familiar thing] [unexpected behavior]?

Why do [people/animals/things] [observable behavior]?

How does [specific phenomenon] happen?

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

These are FORMAT examples only.

Do NOT copy them.

============================================================
ONE PHENOMENON ONLY
============================================================

GOOD:

Why does static electricity make your hair stand up

One phenomenon:
Hair standing up because of static electricity.

GOOD:

Why does a mirror reverse left and right

One phenomenon:
The apparent left-right reversal.

BAD:

Why does static electricity make your hair stand up
and make clothes cling?

Two phenomena.

BAD:

How does electricity work?

Too broad.

BAD:

The science of static electricity

Not a question.

============================================================
MECHANISM REQUIREMENT
============================================================

There must be a realistic mechanism behind the phenomenon.

The question does NOT need to contain technical terminology.

The mechanism will be discovered during research.

GOOD:

Why does your shadow change length during the day

GOOD:

Why does static electricity make your hair stand up

GOOD:

Why does your phone get hot while charging

GOOD:

Why do echoes repeat your voice

BAD:

Why is the universe so strange

BAD:

Why is nature amazing

BAD:

Why are humans special

============================================================
FAMILIARITY
============================================================

Prefer things millions of ordinary people can recognize.

The viewer should be able to think:

"I've experienced that."

The subject does NOT need to come from a fixed category.

Possible areas include:

- everyday experiences
- human behavior
- body observations
- brain experiences
- animals
- physics
- weather
- sound
- light
- food
- household objects
- transportation
- technology
- nature
- space
- materials
- common social experiences

Do not restrict yourself to a predefined vocabulary.

============================================================
35–45 SECOND TEST
============================================================

Imagine the finished Short.

0–3 sec:
HOOK

3–20 sec:
MECHANISM

20–35 sec:
SURPRISING DETAIL

35–45 sec:
PAYOFF + OPEN LOOP

If the question requires a long history lesson,
multiple unrelated mechanisms, or extensive background,
reject it.

============================================================
RESEARCH TEST
============================================================

The question must realistically be answerable using
at least two independent credible sources.

Prefer:

- peer-reviewed research
- universities
- government agencies
- scientific institutions
- established research organizations
- authoritative databases

Avoid:

- rumors
- myths
- social media claims
- conspiracy theories
- folklore
- unverifiable stories
- speculation presented as fact

============================================================
VISUAL TEST
============================================================

The phenomenon should naturally produce useful visuals.

Prefer:

- physical processes
- microscopic mechanisms
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

============================================================
SURPRISE TEST
============================================================

The real answer should be more interesting than the obvious answer.

The surprise must come from the actual mechanism.

Do not manufacture controversy or clickbait.

============================================================
ORIGINALITY
============================================================

Do not repeat previous topics.

Do not create superficial wording variations.

The underlying phenomenon must be genuinely different.

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

Normal educational explanations are allowed.

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
- extremely broad "what is..." questions

============================================================
TOPIC LENGTH
============================================================

Maximum 12 words.

Prefer 5–10 words.

============================================================
OUTPUT
============================================================

Return ONLY ONE topic.

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
+
BROAD AUDIENCE APPEAL
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

        if isinstance(data, list):

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

    if not topic:
        return False

    topic = _clean_topic(topic)

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
        "the psychology of",
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

        if lowered.startswith(phrase):
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
# QUESTION STRUCTURE
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

    return lowered.startswith(starters)


# ==========================================================================
# SEMANTIC-STYLE SPECIFICITY GATE
# ==========================================================================

def _extract_content_words(topic):

    """
    Extract meaningful words without relying on a fixed subject list.

    This intentionally avoids saying:

        "a valid topic must contain 'brain' or 'water'"

    because that artificially limits topic diversity.
    """

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

    words = re.findall(
        r"[a-z0-9]+",
        topic.lower(),
    )

    return [
        word
        for word in words
        if (
            len(word) >= 3
            and word not in stop_words
        )
    ]


def _has_concrete_subject(topic):

    """
    Determine whether the question contains enough concrete language
    to describe an actual phenomenon.

    This is deliberately vocabulary-independent.

    It looks for:
    - multiple meaningful content words
    - nouns/materials/objects implied by sentence structure
    - possessive or relational constructions
    - specific observable targets
    """

    words = _extract_content_words(topic)

    if len(words) < 2:
        return False

    lowered = topic.lower()

    # A question with a concrete noun-like object followed by
    # an action/condition is generally sufficiently specific.
    #
    # Examples:
    #
    # static electricity -> hair stand
    # spoon -> bend
    # clouds -> pink
    # windshield -> fog
    # bread -> become stale
    #

    concrete_patterns = [

        r"\bwhy does .+ (feel|look|sound|smell|taste|change|move|"
        r"turn|become|appear|seem|happen|form|break|stick|float|"
        r"fall|rise|glow|bend|freeze|melt|fog|fade|grow|shrink)",

        r"\bwhy do .+ (feel|look|sound|smell|taste|change|move|"
        r"turn|become|appear|seem|happen|form|break|stick|float|"
        r"fall|rise|glow|bend|freeze|melt|fog|fade|grow|shrink)",

        r"\bwhy can .+ (sit|stand|fly|float|bend|break|stick|"
        r"move|change|survive|see|hear|smell|sense|produce)",

        r"\bhow does .+ (happen|form|change|work|move|produce|"
        r"create|cause|become|occur)",

        r"\bhow do .+ (happen|form|change|work|move|produce|"
        r"create|cause|become|occur)",
    ]

    for pattern in concrete_patterns:

        if re.search(
            pattern,
            lowered,
        ):

            return True

    # Possessive constructions often indicate a specific experience:
    #
    # your hair
    # your phone
    # a car's brakes
    # birds' feathers
    #

    if re.search(
        r"\b(your|our|their|its|a|an|the)\s+\w+\s+\w+",
        lowered,
    ):

        if len(words) >= 3:
            return True

    # A sufficiently short question with several concrete content
    # words can also pass without matching a predefined vocabulary.
    if 3 <= len(words) <= 7:

        return True

    return False


def _has_observable_action(topic):

    """
    Detect observable/experiential wording without maintaining
    a hardcoded list of acceptable subjects.
    """

    lowered = topic.lower()

    observable_patterns = [

        # Sensory experiences
        r"\b(feel|feels|feeling)\b",
        r"\b(look|looks|looking)\b",
        r"\b(sound|sounds|sounding)\b",
        r"\b(hear|hears|hearing)\b",
        r"\b(see|sees|seeing)\b",
        r"\b(smell|smells|smelling)\b",
        r"\b(taste|tastes|tasting)\b",

        # Physical changes
        r"\b(change|changes|changing)\b",
        r"\b(move|moves|moving)\b",
        r"\b(turn|turns|turning)\b",
        r"\b(become|becomes|becoming)\b",
        r"\b(form|forms|forming)\b",
        r"\b(break|breaks|breaking)\b",
        r"\b(bend|bends|bending)\b",
        r"\b(stick|sticks|sticking)\b",
        r"\b(float|floats|floating)\b",
        r"\b(fall|falls|falling)\b",
        r"\b(rise|rises|rising)\b",
        r"\b(freeze|freezes|freezing)\b",
        r"\b(melt|melts|melting)\b",
        r"\b(fade|fades|fading)\b",
        r"\b(glow|glows|glowing)\b",
        r"\b(fog|fogs|fogging)\b",
        r"\b(shrink|shrinks|shrinking)\b",
        r"\b(grow|grows|growing)\b",

        # Human experiences
        r"\b(remember|remembers|remembering)\b",
        r"\b(forget|forgets|forgetting)\b",
        r"\b(dream|dreams|dreaming)\b",
        r"\b(yawn|yawns|yawning)\b",
        r"\b(sneeze|sneezes|sneezing)\b",
        r"\b(tickle|tickles|tickling)\b",
        r"\b(wrinkle|wrinkles|wrinkling)\b",
        r"\b(cry|cries|crying)\b",
        r"\b(blink|blinks|blinking)\b",
        r"\b(breathe|breathes|breathing)\b",

        # Environmental / natural phenomena
        r"\b(rain|rains|raining)\b",
        r"\b(snow|snows|snowing)\b",
        r"\b(thunder|thunders)\b",
        r"\b(lightning)\b",
        r"\b(eclipse|eclipses)\b",
        r"\b(shadow|shadows)\b",
        r"\b(reflection|reflections)\b",
        r"\b(echo|echoes)\b",

        # Generic causal observation
        r"\bhappen(s)?\b",
        r"\bwork(s)?\b",
        r"\bappear(s)?\b",
        r"\bseem(s)?\b",
        r"\bcause(s)?\b",
        r"\bproduce(s)?\b",
    ]

    return any(
        re.search(
            pattern,
            lowered,
        )
        for pattern in observable_patterns
    )


def _has_mechanism_question(topic):

    lowered = topic.lower()

    mechanism_patterns = [

        r"\bwhy\b",
        r"\bhow\b",
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
        r"\bfloat(s)?\b",
        r"\bfreeze(s)?\b",
        r"\bmelt(s)?\b",
        r"\bremember(s)?\b",
        r"\bforget(s)?\b",
        r"\bdream(s)?\b",
        r"\btickle(s)?\b",
        r"\bwrinkle(s)?\b",
        r"\byawn(s)?\b",
    ]

    return any(
        re.search(
            pattern,
            lowered,
        )
        for pattern in mechanism_patterns
    )


def _is_broad_subject(topic):

    lowered = topic.lower().strip()

    for pattern in BROAD_QUESTION_PATTERNS:

        if re.search(
            pattern,
            lowered,
        ):
            return True

    for phrase in LOW_VALUE_PATTERNS:

        if phrase in lowered:
            return True

    words = set(
        re.findall(
            r"[a-z]+",
            lowered,
        )
    )

    broad_hits = words & BROAD_SUBJECT_TERMS

    if broad_hits:

        # A broad term can still be acceptable if the question
        # clearly narrows it to one observable phenomenon.
        #
        # Example:
        # "Why does electricity make your hair stand up?"
        #
        # "electricity" is broad, but the phenomenon is specific.
        #

        if not _has_observable_action(topic):
            return True

        content_words = _extract_content_words(topic)

        if len(content_words) < 4:
            return True

    return False


def _question_quality_score(topic):

    score = 0

    if _is_question(topic):
        score += 2

    if _has_concrete_subject(topic):
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

    if not _has_concrete_subject(topic):

        print(
            "⚠️ Rejected: question lacks a sufficiently concrete phenomenon."
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

    for existing in used:

        if (
            _topic_key(existing)
            ==
            key
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
        _topic_key(topic),
    )

    return {
        word
        for word in words
        if (
            len(word) >= 3
            and word not in stop_words
        )
    }


# ==========================================================================
# TOPIC SIMILARITY
# ==========================================================================

def _too_similar_to_used(
    topic,
    used,
):

    current_words = _topic_words(topic)

    if not current_words:
        return False

    for existing in used:

        existing_words = _topic_words(existing)

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

    # Familiarity is now based partly on linguistic structure rather
    # than a fixed list of allowed subjects.

    content_words = _extract_content_words(
        topic
    )

    if len(content_words) >= 4:
        scores["familiarity"] = 4

    elif len(content_words) >= 3:
        scores["familiarity"] = 3

    elif len(content_words) >= 2:
        scores["familiarity"] = 2

    # Personal/experiential phrasing increases familiarity.

    personal_patterns = [
        r"\byour\b",
        r"\byou\b",
        r"\bpeople\b",
        r"\bwe\b",
        r"\bhumans\b",
        r"\beveryone\b",
        r"\bwhen\b",
    ]

    personal_hits = sum(
        1
        for pattern in personal_patterns
        if re.search(
            pattern,
            lowered,
        )
    )

    scores["familiarity"] = min(
        5,
        scores["familiarity"] + min(
            2,
            personal_hits,
        ),
    )

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
        or "feel" in lowered
        or "look" in lowered
        or "sound" in lowered
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
        "stand",
        "stick",
        "bend",
        "glow",
        "melt",
        "fall",
        "rise",
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

    # Visual scoring remains intentionally broad but no longer controls
    # whether a subject is valid.

    visual_action_patterns = [

        r"\bfeel",
        r"\blook",
        r"\bsound",
        r"\bmove",
        r"\bchange",
        r"\bturn",
        r"\bform",
        r"\bfall",
        r"\brise",
        r"\bfloat",
        r"\bfreeze",
        r"\bmelt",
        r"\bbend",
        r"\bstick",
        r"\bglow",
        r"\bgrow",
        r"\bshrink",
        r"\breflect",
        r"\bshadow",
        r"\becho",
        r"\bappear",
        r"\bdisappear",
        r"\bfly",
        r"\brun",
        r"\bspin",
        r"\brotate",
    ]

    visual_hits = sum(
        1
        for pattern in visual_action_patterns
        if re.search(
            pattern,
            lowered,
        )
    )

    if visual_hits >= 3:
        scores["visual"] = 5

    elif visual_hits == 2:
        scores["visual"] = 4

    elif visual_hits == 1:
        scores["visual"] = 3

    # Specific questions are inherently more visually adaptable.

    if _has_concrete_subject(topic):

        scores["visual"] = min(
            5,
            scores["visual"] + 1,
        )

    # ----------------------------------------------------------------------
    # RESEARCHABILITY
    # ----------------------------------------------------------------------

    # Do not use a hardcoded subject whitelist here.
    #
    # The purpose of this score is only a pre-filter.
    # research.py performs the real evidence validation.

    research_action_patterns = [

        r"\bhappen",
        r"\bwork",
        r"\bcause",
        r"\bproduce",
        r"\bcreate",
        r"\bchange",
        r"\bform",
        r"\bmove",
        r"\bfeel",
        r"\bsound",
        r"\blook",
        r"\bsmell",
        r"\bfloat",
        r"\bfreeze",
        r"\bmelt",
        r"\bremember",
        r"\bforget",
        r"\bdream",
        r"\bstand",
        r"\bstick",
        r"\bbend",
        r"\breflect",
        r"\becho",
    ]

    research_hits = sum(
        1
        for pattern in research_action_patterns
        if re.search(
            pattern,
            lowered,
        )
    )

    if research_hits >= 3:
        scores["researchable"] = 5

    elif research_hits >= 2:
        scores["researchable"] = 4

    elif research_hits >= 1:
        scores["researchable"] = 3

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

    score = _score_topic(topic)

    print(
        f"📊 Curiosity pre-score: "
        f"{score}/{MAX_VIRAL_SCORE}"
    )

    return score >= MIN_VIRAL_SCORE


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

Generate ONE completely new curiosity question for
Mint-YT-Factory.

============================================================
QUESTION-FIRST REQUIREMENT
============================================================

The output MUST be a specific question about ONE observable
phenomenon.

Think:

"What exactly is the viewer noticing?"

Then:

"What mechanism could explain it?"

The question must be narrow enough to explain properly
in approximately 35–45 seconds.

============================================================
IMPORTANT
============================================================

Do NOT restrict yourself to a fixed list of subjects.

The phenomenon can come from any ordinary experience,
including:

- household objects
- food
- weather
- materials
- sound
- light
- transportation
- animals
- human behavior
- body experiences
- brain experiences
- technology
- nature
- space
- everyday physics
- everyday chemistry

But it MUST be something ordinary people can recognize.

============================================================
PREFERRED STRUCTURE
============================================================

Why does [thing] [observable behavior]?

Why do [people/animals/things] [observable behavior]?

How does [specific phenomenon] happen?

Why can [familiar thing] [unexpected behavior]?

Why does [ordinary experience] feel/look/sound different?

============================================================
GOOD EXAMPLES
============================================================

Why does static electricity make your hair stand up

Why does your shadow change length during the day

Why does a cold drink make a glass sweat

Why do echoes repeat your voice

Why does bread become stale

Why does your phone get hot while charging

These are examples of FORMAT only.

Do NOT copy them.

============================================================
REJECT BROAD QUESTIONS
============================================================

How does the internet work

How does electricity work

How does the brain work

How do airplanes work

How do computers work

What is gravity

What is quantum physics

How does artificial intelligence work

The science of sleep

The biology of humans

============================================================
REJECT GENERIC QUESTIONS
============================================================

The science of static electricity

Benefits of sleep

History of airplanes

Interesting facts about birds

How animals communicate

Why nature is amazing

How the human body works

============================================================
ONE PHENOMENON
============================================================

Do not combine two mysteries.

BAD:

Why do phones get hot and batteries drain quickly?

GOOD:

Why does your phone get hot while charging?

============================================================
RESEARCH
============================================================

The question must have enough credible evidence to support
the answer with at least two independent sources.

Prefer:

scientific papers
universities
government agencies
scientific institutions
established research organizations

Avoid myths, rumors, conspiracy theories and unverifiable claims.

============================================================
VISUALS
============================================================

The phenomenon should be easy to visualize through:

physical processes
cause and effect
movement
transformations
experiments
simulations
internal mechanisms
microscopic processes
before/after
scale comparisons

============================================================
MONETIZATION
============================================================

Avoid graphic violence, gore, sexual content, extremist content,
dangerous instructions, drugs, political outrage, conspiracy
theories, fearbait, medical diagnosis and treatment instructions.

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
                _topic_key(pending)
                ==
                _topic_key(topic)
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
    Priority:

    1. Existing pending next_short
    2. Gemini-generated high-quality question

    Selected topic is NOT committed here.
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