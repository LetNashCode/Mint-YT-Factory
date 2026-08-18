"""
topics.py
Mint-YT-Factory

Version 8.0

Evidence-Friendly Curiosity Topic Engine
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

VERSION = "8.0"


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
# SYSTEM PROMPT
# ==========================================================================

SYSTEM_PROMPT = """
You are the curiosity strategist for Mint-YT-Factory.

Generate ONE highly specific question for a 35–45 second
research-backed YouTube Short.

The channel asks:

"Questions you've probably wondered about but never looked up."

The ideal reaction is:

"I've noticed that."

"Wait... why?"

"Ohhh, that's why."

============================================================
CORE REQUIREMENT
============================================================

Choose ONE observable phenomenon.

The question must contain:

1. A familiar observation
2. A specific object, behavior, or event
3. ONE causal mechanism
4. A researchable explanation
5. Strong visual potential
6. A satisfying reveal

The answer must be possible without broad historical,
philosophical, cultural, or academic background.

============================================================
EVIDENCE-FIRST REQUIREMENT
============================================================

This is extremely important.

Choose topics where credible sources are likely to discuss
the ACTUAL MECHANISM behind the observation.

GOOD:

Why does your voice sound different in recordings

Why does a cold glass become covered in water

Why does metal feel colder than wood

Why do shadows become longer near sunset

Why does popcorn suddenly pop

BAD:

Why are old photographs fascinating

Why do photographs preserve memories

Why is time mysterious

Why is space strange

Why does history matter

Why do humans remember the past

The topic must describe a physical, biological, behavioral,
perceptual, environmental, or technological phenomenon that
can be directly investigated.

============================================================
IMPORTANT
============================================================

Do NOT choose a topic merely because it sounds interesting.

Do NOT rely on metaphorical claims.

Do NOT create questions whose likely answer is subjective.

Do NOT create questions requiring philosophical interpretation.

Do NOT create questions where the explanation depends mainly
on cultural interpretation.

Do NOT create questions where evidence would likely be vague.

============================================================
ONE PHENOMENON
============================================================

Exactly ONE mystery.

GOOD:

Why does your voice sound different in recordings

GOOD:

Why does a cold glass become covered in water

GOOD:

Why does popcorn suddenly pop

BAD:

Why do old photos fade and memories change

BAD:

Why do phones heat up and lose battery

BAD:

Why does the brain remember some things and forget others

============================================================
MECHANISM
============================================================

Prefer questions involving:

- cause and effect
- physical processes
- chemical processes
- biological processes
- sensory perception
- observable behavior
- material changes
- environmental effects
- mechanical effects
- light
- sound
- temperature
- pressure
- motion
- electricity
- everyday technology

The mechanism should be explainable visually.

============================================================
RESEARCHABILITY
============================================================

Prefer topics likely to have evidence from:

- peer-reviewed research
- universities
- government agencies
- scientific institutions
- established research organizations
- authoritative technical sources

Avoid topics where evidence is likely to be only opinion,
metaphor, general discussion, or an unrelated paper containing
the same keywords.

============================================================
ORIGINALITY
============================================================

Do not repeat previous topics.

Do not merely reword an existing topic.

The underlying phenomenon must be different.

============================================================
FORBIDDEN
============================================================

No:

- Top 5
- Top 10
- countdowns
- lists
- compilations
- generic facts
- "facts about"
- "interesting facts"
- "the science of"
- "history of"
- "benefits of"
- "everything about"
- "complete guide"
- "ultimate guide"
- broad academic subjects
- philosophical questions
- conspiracy theories
- fearbait
- political outrage
- medical diagnosis
- medical treatment
- unsupported claims

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

def _atomic_write_json(path, data):

    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    fd = None
    temp_path = None

    try:
        fd, temp_path = tempfile.mkstemp(
            prefix=".mint_topic_",
            suffix=".tmp",
            dir=directory,
            text=True,
        )

        with os.fdopen(fd, "w", encoding="utf-8") as f:
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

        os.replace(temp_path, path)
        temp_path = None

    finally:

        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass

        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def _load_used():

    if not os.path.exists(USED_TOPICS_PATH):
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

        return [
            topic
            for topic in (
                _clean_topic(item)
                for item in data
            )
            if topic
        ]

    except Exception as error:

        print(
            f"⚠️ Could not read {USED_TOPICS_PATH}: {error}"
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

    if not os.path.exists(NEXT_TOPIC_PATH):
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
            f"⚠️ Could not read {NEXT_TOPIC_PATH}: {error}"
        )

    return ""


def _save_next_topic(topic):

    topic = _clean_topic(topic)

    if not topic:
        return False

    if len(topic) > MAX_TOPIC_CHARACTERS:
        return False

    try:

        _atomic_write_json(
            NEXT_TOPIC_PATH,
            {"topic": topic},
        )

        return True

    except Exception as error:

        print(
            f"❌ Could not save {NEXT_TOPIC_PATH}: {error}"
        )

        return False


def clear_next_topic():

    if not os.path.exists(NEXT_TOPIC_PATH):
        return True

    try:
        os.remove(NEXT_TOPIC_PATH)
        print("✅ Pending topic removed.")
        return True

    except Exception as error:

        print(
            f"⚠️ Could not remove {NEXT_TOPIC_PATH}: {error}"
        )

        return False


# ==========================================================================
# CLEANING
# ==========================================================================

def _clean_topic(topic):

    topic = str(topic or "").strip()

    if not topic:
        return ""

    topic = re.sub(
        r"```(?:text|json)?",
        "",
        topic,
        flags=re.IGNORECASE,
    )

    topic = topic.replace('"', "")
    topic = topic.replace("'", "")

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

    topic = " ".join(topic.split())

    return topic.rstrip(".!? ").strip()


# ==========================================================================
# BASIC VALIDATION
# ==========================================================================

def _valid_topic(topic, max_words=None):

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
        "why is the universe",
        "why is space strange",
        "why is time strange",
        "why is history",
        "why are memories",
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

def _is_question(topic):

    return topic.lower().strip().startswith(
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


def _content_words(topic):

    stop_words = {
        "why", "what", "how", "when", "where", "who",
        "does", "do", "did", "can", "could", "would",
        "will", "should", "is", "are", "was", "were",
        "the", "a", "an", "and", "or", "of", "to",
        "in", "on", "for", "with", "from", "your",
        "you", "we", "our", "they", "their", "it",
        "its", "this", "that", "these", "those",
        "very", "really", "actually", "often",
        "usually", "sometimes", "people", "thing",
        "things",
    }

    return [
        word
        for word in _question_words(topic)
        if len(word) >= 3 and word not in stop_words
    ]


def _has_observation_structure(topic):

    lowered = topic.lower()

    patterns = [
        r"^why does .+ .+",
        r"^why do .+ .+",
        r"^why can .+ .+",
        r"^how does .+ .+",
        r"^how do .+ .+",
        r"^why is .+ .+",
        r"^why are .+ .+",
        r"^how can .+ .+",
    ]

    return any(
        re.search(pattern, lowered)
        for pattern in patterns
    )


def _has_mechanism_structure(topic):

    lowered = topic.lower()

    mechanism_patterns = [
        r"^why\b",
        r"^how\b",
        r"\bhappen",
        r"\bchange",
        r"\bmove",
        r"\bmake",
        r"\bcause",
        r"\bproduce",
        r"\bcreate",
        r"\bform",
        r"\bbecome",
        r"\bfeel",
        r"\bsound",
        r"\blook",
        r"\bappear",
        r"\bfloat",
        r"\bfreeze",
        r"\bmelt",
        r"\bstick",
        r"\bbend",
        r"\breflect",
        r"\becho",
        r"\bremember",
        r"\bforget",
        r"\bdream",
        r"\btickle",
        r"\byawn",
        r"\bpop",
        r"\bfade",
        r"\bwarm",
        r"\bcool",
        r"\bheat",
        r"\bcold",
        r"\bexpand",
        r"\bshrink",
        r"\bevapor",
        r"\bcondens",
        r"\brefract",
        r"\babsorb",
        r"\bscatter",
    ]

    return any(
        re.search(pattern, lowered)
        for pattern in mechanism_patterns
    )


def _has_single_phenomenon_shape(topic):

    lowered = topic.lower()

    blocked = [
        " and why ",
        " and how ",
        " or why ",
        " or how ",
        " while ",
        " and ",
    ]

    # Only reject conjunctions when they clearly indicate
    # multiple phenomena.

    if " and why " in lowered:
        return False

    if " and how " in lowered:
        return False

    if " or why " in lowered:
        return False

    if " or how " in lowered:
        return False

    if topic.count("?") > 1:
        return False

    return True


def _passes_question_quality(topic):

    if not _is_question(topic):
        print("⚠️ Rejected: not a question.")
        return False

    content = _content_words(topic)

    if len(content) < 3:
        print("⚠️ Rejected: insufficient specificity.")
        return False

    if not _has_observation_structure(topic):
        print("⚠️ Rejected: weak observable phenomenon.")
        return False

    if not _has_mechanism_structure(topic):
        print("⚠️ Rejected: weak mechanism structure.")
        return False

    if not _has_single_phenomenon_shape(topic):
        print("⚠️ Rejected: multiple phenomena detected.")
        return False

    if len(topic.split()) > NEW_TOPIC_MAX_WORDS:
        print("⚠️ Rejected: topic too long.")
        return False

    print("🧩 Question structure: PASS")

    return True


# ==========================================================================
# DUPLICATE PROTECTION
# ==========================================================================

def _topic_key(topic):

    topic = _clean_topic(topic).lower()

    topic = re.sub(
        r"[^a-z0-9\s]",
        "",
        topic,
    )

    return " ".join(topic.split())


def _already_used(topic, used):

    key = _topic_key(topic)

    if not key:
        return False

    return any(
        _topic_key(existing) == key
        for existing in used
    )


def _topic_words(topic):

    stop_words = {
        "why", "what", "how", "when", "where",
        "does", "do", "did", "can", "could",
        "would", "will", "should", "is", "are",
        "was", "were", "the", "a", "an",
        "and", "or", "of", "to", "in", "on",
        "for", "with", "from", "your", "you",
        "we", "our", "they", "their", "it",
        "its", "this", "that", "these", "those",
    }

    return {
        word
        for word in re.findall(
            r"[a-z0-9]+",
            _topic_key(topic),
        )
        if len(word) >= 3 and word not in stop_words
    }


def _too_similar_to_used(topic, used):

    current = _topic_words(topic)

    if len(current) < 2:
        return False

    for existing in used:

        previous = _topic_words(existing)

        if len(previous) < 2:
            continue

        intersection = current & previous
        union = current | previous

        if not union:
            continue

        jaccard = len(intersection) / len(union)

        if jaccard >= 0.72:
            return True

        current_coverage = (
            len(intersection) / len(current)
        )

        previous_coverage = (
            len(intersection) / len(previous)
        )

        if (
            current_coverage >= 0.80
            and previous_coverage >= 0.60
            and len(intersection) >= 3
        ):
            return True

    return False


# ==========================================================================
# QUALITY SCORE
# ==========================================================================

def _topic_quality_score(topic):

    score = 0

    words = topic.split()
    content = _content_words(topic)

    if _is_question(topic):
        score += 3

    if len(content) >= 4:
        score += 3
    elif len(content) >= 3:
        score += 2

    if _has_observation_structure(topic):
        score += 3

    if _has_mechanism_structure(topic):
        score += 3

    if 6 <= len(words) <= 10:
        score += 2
    elif 5 <= len(words) <= 12:
        score += 1

    if any(
        word in topic.lower().split()
        for word in ["your", "you", "people", "everyone"]
    ):
        score += 2

    if _has_single_phenomenon_shape(topic):
        score += 2

    return min(20, score)


def _passes_topic_score(topic):

    score = _topic_quality_score(topic)

    print(
        f"📊 Topic structure score: {score}/20"
    )

    return score >= 14


# ==========================================================================
# PENDING TOPIC
# ==========================================================================

def get_pending_topic():

    topic = _load_next_topic()

    if not topic:
        return ""

    if not _valid_topic(topic):
        print("⚠️ Pending topic is invalid.")
        return ""

    print("=" * 80)
    print("🔗 CONTINUING FROM PREVIOUS SHORT")
    print("=" * 80)

    print(f"Next topic: {topic}")

    print("=" * 80)

    return topic


# ==========================================================================
# GEMINI GENERATION
# ==========================================================================

def _generate_new_topic():

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is missing."
        )

    client = genai.Client(api_key=api_key)

    used = _load_used()

    previous = "\n".join(
        used[-MAX_PREVIOUS_TOPICS:]
    )

    prompt = f"""
Generate ONE completely new curiosity question.

The question must describe ONE observable phenomenon
with ONE researchable causal mechanism.

Think:

FAMILIAR OBSERVATION
→ SPECIFIC MYSTERY
→ REAL MECHANISM
→ SURPRISING EXPLANATION

Prioritize topics where credible scientific or technical
sources are likely to discuss the exact mechanism.

GOOD EXAMPLES:

Why does your voice sound different in recordings

Why does a cold glass become covered in water

Why does metal feel colder than wood

Why does popcorn suddenly pop

Why does a shadow change length during the day

BAD EXAMPLES:

Why are old photographs fascinating

Why do photographs connect us to the past

Why is time mysterious

Why is space strange

Why are memories important

The topic must NOT depend on metaphor, philosophy,
cultural interpretation, or vague observations.

Do not generate:
- lists
- countdowns
- broad subjects
- generic facts
- history lessons
- benefits
- conspiracy
- fearbait
- medical diagnosis
- political topics

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
            f"{attempt}/{MAX_TOPIC_GENERATION_ATTEMPTS}"
        )

        try:

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.85,
                ),
            )

            topic = _clean_topic(
                getattr(response, "text", "")
            )

            print(
                f"Generated candidate: {topic}"
            )

            if not _valid_topic(
                topic,
                max_words=NEW_TOPIC_MAX_WORDS,
            ):
                continue

            if not _passes_question_quality(topic):
                continue

            if _already_used(topic, used):
                print("⚠️ Exact topic already used.")
                continue

            if _too_similar_to_used(topic, used):
                print(
                    "⚠️ Underlying concept too similar."
                )
                continue

            pending = _load_next_topic()

            if (
                pending
                and
                _topic_key(pending) == _topic_key(topic)
            ):
                continue

            if not _passes_topic_score(topic):
                continue

            print("=" * 80)
            print("🔥 GENERATED CURIOSITY QUESTION")
            print("=" * 80)

            print(topic)

            print(
                f"Words: {len(topic.split())}"
            )

            print(
                f"Structure score: "
                f"{_topic_quality_score(topic)}/20"
            )

            print("=" * 80)

            return topic

        except Exception as error:

            print(
                f"⚠️ Gemini topic generation failed: {error}"
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

        if not _save_next_topic(topic):
            raise RuntimeError(
                "Could not save generated topic."
            )

        print("=" * 80)
        print("📌 NEW CURIOSITY QUESTION QUEUED")
        print("=" * 80)

        print(topic)

        print("=" * 80)

        return topic

    raise RuntimeError(
        "Could not generate a strong curiosity question."
    )


# ==========================================================================
# COMMIT
# ==========================================================================

def commit_topic(topic):

    topic = _clean_topic(topic)

    if not topic:
        raise RuntimeError(
            "Cannot commit an empty topic."
        )

    used = _load_used()

    if not _already_used(topic, used):

        used.append(topic)
        _save_used(used)

        print("=" * 80)
        print("✅ CURRENT TOPIC COMMITTED")
        print("=" * 80)

        print(topic)

        print("=" * 80)

    pending = _load_next_topic()

    if not pending:
        return True

    if _topic_key(pending) == _topic_key(topic):

        if not clear_next_topic():
            raise RuntimeError(
                "Could not remove committed pending topic."
            )

    else:

        print("🔗 Preserving NEW next_short:")
        print(pending)

    return True


# ==========================================================================
# SAVE NEXT SHORT
# ==========================================================================

def save_next_short(next_short):

    next_short = _clean_topic(next_short)

    if not next_short:
        print("⚠️ No next_short was provided.")
        return False

    if not _valid_topic(next_short):
        print("⚠️ next_short failed validation.")
        return False

    used = _load_used()

    if _already_used(next_short, used):
        print("⚠️ next_short already committed.")
        return False

    if _too_similar_to_used(next_short, used):
        print(
            "⚠️ next_short is too similar to a previous topic."
        )
        return False

    if not _save_next_topic(next_short):
        return False

    print("=" * 80)
    print("🔗 NEXT SHORT SAVED")
    print("=" * 80)

    print(next_short)

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