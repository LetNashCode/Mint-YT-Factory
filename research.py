"""
research.py - Mint-YT-Factory v10.1

Dynamic research-first evidence layer.

v10.1 focuses on QUESTION CONCEPT COVERAGE.

Pipeline:

    topics.py
        ↓
    research.py
        ↓
    Question structure extraction
        ↓
    Concept-aware scholarly discovery
        ↓
    Concept coverage filtering
        ↓
    DOI identity verification
        ↓
    Abstract evidence verification
        ↓
    Final concept coverage verification
        ↓
    Verified research package

IMPORTANT:

This module does NOT use Gemini/LLM-generated evidence.

Research relevance is determined deterministically from the
actual question.

The system separates:

    SUBJECT
    PHENOMENON
    CONDITION
    CAUSAL INTENT

This prevents simple word overlap from being treated as proof
that a paper explains the question.

Example:

    "why do ceiling fans make ticking sounds as they slow down"

is represented approximately as:

    subject:
        ceiling fan

    phenomenon:
        ticking sound

    condition:
        slow down

    intent:
        cause

A paper about "ceiling" and "ticking" in an unrelated context
must not pass merely because individual words overlap.

DOI identity verification remains independent from relevance.

Abstract evidence verification remains independent from identity.

A source must pass all required gates before becoming part of
the verified research package.
"""

import hashlib
import json
import os
import re
import sys
import time
from urllib.parse import quote

import requests


# ============================================================================
# CONFIG
# ============================================================================

VERSION = "10.1"

CROSSREF_URL = "https://api.crossref.org/v1/works"

SEMANTIC_SEARCH_URL = (
    "https://api.semanticscholar.org/graph/v1/paper/search"
)

SEMANTIC_PAPER_URL = (
    "https://api.semanticscholar.org/graph/v1/paper"
)

OPENALEX_URL = (
    "https://api.openalex.org/works"
)

TIMEOUT = 30

MAX_CROSSREF_RESULTS = 15
MAX_SEMANTIC_RESULTS = 10
MAX_OPENALEX_RESULTS = 12

MAX_VERIFICATION_CANDIDATES = 20
MAX_EVIDENCE_SOURCES = 5

MIN_ACCEPTED_SOURCES = 2

MIN_ABSTRACT_CHARACTERS = 120

MAX_EVIDENCE_TEXT_CHARACTERS = 12000

TITLE_SIMILARITY_MINIMUM = 0.55

# ---------------------------------------------------------------------------
# Concept coverage thresholds
# ---------------------------------------------------------------------------

MIN_CONCEPT_SCORE = 8

# For questions containing a recognizable condition, require it.
REQUIRE_CONDITION_FOR_CAUSAL_QUESTIONS = True

# Require the phenomenon to be represented in title/evidence.
REQUIRE_PHENOMENON = True

# Require subject representation.
REQUIRE_SUBJECT = True

# ---------------------------------------------------------------------------
# Semantic Scholar circuit breaker
# ---------------------------------------------------------------------------

SEMANTIC_RETRIES = 0
SEMANTIC_BACKOFF_SECONDS = 4
SEMANTIC_RATE_LIMITED = False

USER_AGENT = (
    f"Mint-YT-Factory/{VERSION} "
    "(educational research verification)"
)

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
)


# ============================================================================
# HTTP
# ============================================================================

def _get(
    url,
    params=None,
    retries=2,
    backoff=2,
    provider=None,
):

    global SEMANTIC_RATE_LIMITED

    if (
        provider == "Semantic Scholar"
        and SEMANTIC_RATE_LIMITED
    ):

        raise RuntimeError(
            "Semantic Scholar skipped: "
            "rate limited earlier in this run."
        )

    last_error = None

    for attempt in range(
        retries + 1
    ):

        try:

            response = SESSION.get(
                url,
                params=params,
                timeout=TIMEOUT,
            )

            if response.status_code == 429:

                retry_after = (
                    response.headers.get(
                        "Retry-After"
                    )
                )

                try:

                    delay = float(
                        retry_after
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    delay = (
                        backoff
                        * (attempt + 1)
                    )

                if (
                    provider
                    == "Semantic Scholar"
                ):

                    SEMANTIC_RATE_LIMITED = True

                    raise RuntimeError(
                        "Semantic Scholar "
                        "HTTP 429 rate limit exceeded."
                    )

                if attempt < retries:

                    print(
                        "⚠️ HTTP 429. "
                        f"Retrying in {delay:.1f}s..."
                    )

                    time.sleep(
                        delay
                    )

                    continue

                raise RuntimeError(
                    "HTTP 429 rate limit exceeded."
                )

            if (
                response.status_code >= 500
                and attempt < retries
            ):

                delay = (
                    backoff
                    * (attempt + 1)
                )

                print(
                    f"⚠️ HTTP {response.status_code}. "
                    f"Retrying in {delay:.1f}s..."
                )

                time.sleep(
                    delay
                )

                continue

            response.raise_for_status()

            return response.json()

        except Exception as error:

            last_error = error

            if (
                provider == "Semantic Scholar"
                and "429" in str(error)
            ):

                SEMANTIC_RATE_LIMITED = True

                raise

            if attempt < retries:

                delay = (
                    backoff
                    * (attempt + 1)
                )

                print(
                    "⚠️ Request failed. "
                    f"Retrying in {delay:.1f}s..."
                )

                time.sleep(
                    delay
                )

                continue

            raise last_error

    raise RuntimeError(
        "HTTP request failed."
    )


# ============================================================================
# TEXT HELPERS
# ============================================================================

def _clean(text):

    if text is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(text),
    ).strip()


def _clean_abstract(text):

    text = _clean(
        text
    )

    if not text:
        return ""

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _normalize_doi(doi):

    doi = _clean(
        doi
    )

    if not doi:
        return ""

    doi = re.sub(
        r"^https?://doi\.org/",
        "",
        doi,
        flags=re.IGNORECASE,
    )

    doi = re.sub(
        r"^https?://dx\.doi\.org/",
        "",
        doi,
        flags=re.IGNORECASE,
    )

    doi = re.sub(
        r"^doi:\s*",
        "",
        doi,
        flags=re.IGNORECASE,
    )

    return doi.strip().rstrip(
        ".,;:)"
    ).lower()


def _generate_source_id(doi):

    doi = _normalize_doi(
        doi
    )

    if not doi:

        raise RuntimeError(
            "Cannot generate source_id "
            "without DOI."
        )

    digest = hashlib.sha256(
        doi.encode(
            "utf-8"
        )
    ).hexdigest()[:12]

    return (
        f"doi_{digest}"
    )


def _normalize_title(title):

    title = _clean(
        title
    ).lower()

    title = re.sub(
        r"[^a-z0-9\s]",
        " ",
        title,
    )

    return " ".join(
        title.split()
    )


def _title_tokens(title):

    return {
        token
        for token in re.findall(
            r"[a-z0-9]+",
            _normalize_title(
                title
            ),
        )
        if len(token) >= 3
    }


def _title_similarity(
    title_a,
    title_b,
):

    a = _title_tokens(
        title_a
    )

    b = _title_tokens(
        title_b
    )

    if not a or not b:
        return 0.0

    return len(
        a & b
    ) / len(
        a | b
    )


def _text_clean_for_matching(
    text
):

    text = _clean(
        text
    ).lower()

    return " ".join(
        re.sub(
            r"[^a-z0-9\s-]",
            " ",
            text,
        ).split()
    )


# ============================================================================
# STOPWORDS
# ============================================================================

STOPWORDS = {
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
    "should",
    "will",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
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
    "about",
    "into",
    "through",
    "during",
    "using",
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
    "one",
    "ones",
    "thing",
    "things",
    "make",
    "makes",
    "made",
    "cause",
    "causes",
    "causing",
}


# ============================================================================
# TOKENIZATION
# ============================================================================

def _tokenize(text):

    return [
        token
        for token in re.findall(
            r"[a-z0-9]+",
            _clean(text).lower(),
        )
        if (
            token not in STOPWORDS
            and len(token) >= 3
        )
    ]


def _topic_terms(topic):

    return set(
        _tokenize(
            topic
        )
    )


def _stem_variants(term):

    variants = {
        term
    }

    if (
        term.endswith("ies")
        and len(term) > 4
    ):

        variants.add(
            term[:-3] + "y"
        )

    if (
        term.endswith("ing")
        and len(term) > 5
    ):

        variants.add(
            term[:-3]
        )

    if (
        term.endswith("ed")
        and len(term) > 4
    ):

        variants.add(
            term[:-2]
        )

    if (
        term.endswith("es")
        and len(term) > 4
    ):

        variants.add(
            term[:-2]
        )

    if (
        term.endswith("s")
        and len(term) > 4
    ):

        variants.add(
            term[:-1]
        )

    return variants


def _expanded_topic_terms(
    topic
):

    base = _topic_terms(
        topic
    )

    expanded = set(
        base
    )

    for term in list(
        base
    ):

        expanded.update(
            _stem_variants(
                term
            )
        )

    return expanded


def _stem_like_match(
    term,
    text,
):

    if not term:
        return False

    term = term.lower().strip()

    text = text.lower()

    if " " in term:

        return term in text

    for candidate in _stem_variants(
        term
    ):

        if len(candidate) < 3:
            continue

        if re.search(
            rf"\b{re.escape(candidate)}\w*\b",
            text,
        ):

            return True

    return False


def _matched_terms(
    terms,
    text,
):

    clean_text = (
        _text_clean_for_matching(
            text
        )
    )

    return {
        term
        for term in terms
        if _stem_like_match(
            term,
            clean_text,
        )
    }


# ============================================================================
# QUESTION STRUCTURE
# ============================================================================

def _phrase_exists(
    phrase,
    text,
):

    phrase = _text_clean_for_matching(
        phrase
    )

    text = _text_clean_for_matching(
        text
    )

    if not phrase:
        return False

    return phrase in text


def _phrase_matches(
    phrases,
    text,
):

    return [
        phrase
        for phrase in phrases
        if _phrase_exists(
            phrase,
            text,
        )
    ]


def _build_adjacent_phrases(
    words,
    max_size=3,
):

    phrases = []

    for size in range(
        max_size,
        1,
        -1,
    ):

        for index in range(
            len(words) - size + 1
        ):

            phrase = " ".join(
                words[
                    index:index + size
                ]
            )

            if phrase not in phrases:

                phrases.append(
                    phrase
                )

    return phrases


def _question_structure(
    topic
):
    """
    Deterministically identify the important semantic pieces
    of the question.

    This is intentionally conservative.

    It does not pretend to understand arbitrary language like
    an LLM. Instead, it extracts useful phrase relationships
    from the actual wording.

    The output is then used as a hard relevance signal.
    """

    topic = _clean(
        topic
    )

    lowered = topic.lower()

    words = [
        word
        for word in re.findall(
            r"[a-z0-9]+",
            lowered,
        )
        if word not in STOPWORDS
        and len(word) >= 3
    ]

    subject = []
    phenomenon = []
    condition = []

    # ----------------------------------------------------------------------
    # CAUSAL QUESTION DETECTION
    # ----------------------------------------------------------------------

    causal_patterns = [
        r"\bwhy\b",
        r"\bhow\b.*\bcaus",
        r"\bwhat causes\b",
        r"\bwhat makes\b",
        r"\bwhat is causing\b",
        r"\bwhat makes\b",
    ]

    causal_intent = any(
        re.search(
            pattern,
            lowered,
        )
        for pattern in causal_patterns
    )

    # ----------------------------------------------------------------------
    # CONDITION PHRASES
    # ----------------------------------------------------------------------

    condition_patterns = [
        r"\bas\s+(.+?)\s+slow(?:s|ing)?\b",
        r"\bwhile\s+(.+?)\s+slow(?:s|ing)?\b",
        r"\bwhen\s+(.+?)\s+slow(?:s|ing)?\b",
        r"\bduring\s+(.+?)\s+slow(?:s|ing)?\b",
        r"\bas\s+(.+?)\s+stop(?:s|ping)?\b",
        r"\bwhile\s+(.+?)\s+stop(?:s|ping)?\b",
        r"\bwhen\s+(.+?)\s+stop(?:s|ping)?\b",
    ]

    for pattern in condition_patterns:

        match = re.search(
            pattern,
            lowered,
        )

        if not match:
            continue

        captured = _clean(
            match.group(0)
        )

        if captured:

            condition.append(
                captured
            )

    # Generic transition conditions.
    transition_patterns = [
        r"\bslow down\b",
        r"\bslowing down\b",
        r"\bslows down\b",
        r"\bspeeding up\b",
        r"\bspeeds up\b",
        r"\baccelerating\b",
        r"\bdecelerating\b",
        r"\bstarting\b",
        r"\bturning on\b",
        r"\bturning off\b",
        r"\bstopping\b",
        r"\bstopped\b",
        r"\bstarting up\b",
    ]

    for pattern in transition_patterns:

        match = re.search(
            pattern,
            lowered,
        )

        if match:

            phrase = _clean(
                match.group(0)
            )

            if phrase not in condition:

                condition.append(
                    phrase
                )

    # ----------------------------------------------------------------------
    # PHENOMENON PHRASES
    # ----------------------------------------------------------------------

    phenomenon_patterns = [
        r"\b(.+?)\s+(ticking\s+sounds?)\b",
        r"\b(.+?)\s+(ticking\s+noises?)\b",
        r"\b(.+?)\s+(clicking\s+sounds?)\b",
        r"\b(.+?)\s+(clicking\s+noises?)\b",
        r"\b(.+?)\s+(buzzing\s+sounds?)\b",
        r"\b(.+?)\s+(buzzing\s+noises?)\b",
        r"\b(.+?)\s+(humming\s+sounds?)\b",
        r"\b(.+?)\s+(humming\s+noises?)\b",
        r"\b(.+?)\s+(rattling\s+sounds?)\b",
        r"\b(.+?)\s+(rattling\s+noises?)\b",
        r"\b(.+?)\s+(vibrations?)\b",
        r"\b(.+?)\s+(noise)\b",
        r"\b(.+?)\s+(sound)\b",
        r"\b(.+?)\s+(sounds)\b",
        r"\b(.+?)\s+(noise)\b",
        r"\b(.+?)\s+(noises)\b",
    ]

    for pattern in phenomenon_patterns:

        match = re.search(
            pattern,
            lowered,
        )

        if not match:
            continue

        phenomenon_phrase = _clean(
            match.group(
                match.lastindex
            )
        )

        if phenomenon_phrase:

            phenomenon.append(
                phenomenon_phrase
            )

    # ----------------------------------------------------------------------
    # FALLBACK PHENOMENON VOCABULARY
    #
    # This is generic phenomenon vocabulary, not subject-specific.
    # ----------------------------------------------------------------------

    phenomenon_words = {
        "sound",
        "sounds",
        "noise",
        "noises",
        "click",
        "clicking",
        "tick",
        "ticking",
        "buzz",
        "buzzing",
        "hum",
        "humming",
        "rattle",
        "rattling",
        "vibration",
        "vibrations",
        "heat",
        "heating",
        "cooling",
        "smell",
        "odor",
        "odour",
        "color",
        "colour",
        "light",
        "glow",
        "flicker",
        "flickering",
        "spark",
        "sparking",
        "pressure",
        "motion",
        "movement",
        "rust",
        "rusting",
        "corrosion",
        "crack",
        "cracking",
        "leak",
        "leaking",
        "shake",
        "shaking",
        "squeak",
        "squeaking",
        "whistle",
        "whistling",
    }

    for word in words:

        if word in phenomenon_words:

            if word not in phenomenon:

                phenomenon.append(
                    word
                )

    # ----------------------------------------------------------------------
    # SUBJECT
    #
    # Remove obvious phenomenon/condition/question words from the
    # question and preserve the remaining meaningful terms.
    # ----------------------------------------------------------------------

    excluded_subject_terms = set(
        STOPWORDS
    )

    excluded_subject_terms.update(
        phenomenon_words
    )

    excluded_subject_terms.update(
        {
            "slow",
            "slows",
            "slowing",
            "speeding",
            "accelerating",
            "decelerating",
            "starting",
            "stopping",
            "stopped",
            "turning",
            "down",
            "up",
        }
    )

    subject_words = [
        word
        for word in words
        if word not in excluded_subject_terms
    ]

    # Preserve the most likely noun phrase(s).
    subject_phrases = _build_adjacent_phrases(
        subject_words,
        max_size=3,
    )

    if subject_phrases:

        # Prefer longer phrases.
        subject.extend(
            subject_phrases[:3]
        )

    subject.extend(
        subject_words[:8]
    )

    # ----------------------------------------------------------------------
    # Special handling for "X makes Y"
    # ----------------------------------------------------------------------

    makes_match = re.search(
        r"\b(.+?)\s+makes?\s+(.+)$",
        lowered,
    )

    if makes_match:

        left = _clean(
            makes_match.group(1)
        )

        right = _clean(
            makes_match.group(2)
        )

        left_words = [
            word
            for word in re.findall(
                r"[a-z0-9]+",
                left,
            )
            if word not in STOPWORDS
        ]

        right_words = [
            word
            for word in re.findall(
                r"[a-z0-9]+",
                right,
            )
            if word not in STOPWORDS
        ]

        if left_words:

            subject.insert(
                0,
                " ".join(
                    left_words
                ),
            )

        if right_words:

            phenomenon.insert(
                0,
                " ".join(
                    right_words
                ),
            )

    # ----------------------------------------------------------------------
    # Deduplicate and clean
    # ----------------------------------------------------------------------

    def unique_clean(values):

        result = []

        seen = set()

        for value in values:

            value = _clean(
                value
            )

            if not value:
                continue

            key = value.lower()

            if key in seen:
                continue

            seen.add(
                key
            )

            result.append(
                value
            )

        return result

    subject = unique_clean(
        subject
    )

    phenomenon = unique_clean(
        phenomenon
    )

    condition = unique_clean(
        condition
    )

    # ----------------------------------------------------------------------
    # If subject extraction accidentally captured phenomenon words,
    # remove them when possible.
    # ----------------------------------------------------------------------

    cleaned_subject = []

    phenomenon_tokens = set()

    for phrase in phenomenon:

        phenomenon_tokens.update(
            re.findall(
                r"[a-z0-9]+",
                phrase.lower(),
            )
        )

    for phrase in subject:

        tokens = set(
            re.findall(
                r"[a-z0-9]+",
                phrase.lower(),
            )
        )

        if (
            tokens
            and tokens.issubset(
                phenomenon_tokens
            )
        ):
            continue

        cleaned_subject.append(
            phrase
        )

    subject = cleaned_subject

    # ----------------------------------------------------------------------
    # Query phrases
    # ----------------------------------------------------------------------

    query_phrases = []

    query_phrases.append(
        topic
    )

    if subject:

        query_phrases.extend(
            subject[:3]
        )

    if phenomenon:

        query_phrases.extend(
            phenomenon[:3]
        )

    if subject and phenomenon:

        for s in subject[:2]:

            for p in phenomenon[:2]:

                query_phrases.append(
                    f"{s} {p}"
                )

    if subject and phenomenon and condition:

        for s in subject[:2]:

            for p in phenomenon[:2]:

                for c in condition[:2]:

                    query_phrases.append(
                        f"{s} {p} {c}"
                    )

    query_phrases = unique_clean(
        query_phrases
    )

    # ----------------------------------------------------------------------
    # All useful terms
    # ----------------------------------------------------------------------

    topic_terms = sorted(
        _topic_terms(
            topic
        )
    )

    expanded_terms = sorted(
        _expanded_topic_terms(
            topic
        )
    )

    return {
        "topic_terms": topic_terms,
        "expanded_terms": expanded_terms,
        "subject": subject,
        "phenomenon": phenomenon,
        "condition": condition,
        "causal_intent": bool(
            causal_intent
        ),
        "query_phrases": query_phrases,
        "concept_terms": sorted(
            set(
                topic_terms
                + expanded_terms
                + subject
                + phenomenon
                + condition
            )
        ),
    }


# ============================================================================
# QUESTION CONCEPTS
# ============================================================================

def _question_concepts(
    topic
):

    structure = _question_structure(
        topic
    )

    # Backwards-compatible field names.
    return {
        "topic_terms": structure[
            "topic_terms"
        ],
        "expanded_terms": structure[
            "expanded_terms"
        ],
        "question_phrases": structure[
            "query_phrases"
        ],
        "concept_terms": structure[
            "concept_terms"
        ],
        "subject": structure[
            "subject"
        ],
        "phenomenon": structure[
            "phenomenon"
        ],
        "condition": structure[
            "condition"
        ],
        "causal_intent": structure[
            "causal_intent"
        ],
    }


# ============================================================================
# QUERY GENERATION
# ============================================================================

def build_scholarly_queries(
    topic
):
    """
    Generate several research queries from the actual question.

    Query families:

        1. exact natural-language question
        2. subject
        3. subject + phenomenon
        4. subject + phenomenon + condition
        5. subject + phenomenon + cause
        6. original concept terms

    No subject-specific vocabulary is hardcoded.
    """

    topic = _clean(
        topic
    )

    if not topic:
        return []

    concepts = _question_concepts(
        topic
    )

    subject = concepts[
        "subject"
    ]

    phenomenon = concepts[
        "phenomenon"
    ]

    condition = concepts[
        "condition"
    ]

    topic_terms = concepts[
        "topic_terms"
    ]

    queries = []

    # ----------------------------------------------------------------------
    # 1. Exact question
    # ----------------------------------------------------------------------

    queries.append(
        topic
    )

    # ----------------------------------------------------------------------
    # 2. Subject
    # ----------------------------------------------------------------------

    for value in subject[:2]:

        queries.append(
            value
        )

    # ----------------------------------------------------------------------
    # 3. Subject + phenomenon
    # ----------------------------------------------------------------------

    for s in subject[:3]:

        for p in phenomenon[:3]:

            queries.append(
                f"{s} {p}"
            )

    # ----------------------------------------------------------------------
    # 4. Subject + phenomenon + condition
    # ----------------------------------------------------------------------

    if condition:

        for s in subject[:2]:

            for p in phenomenon[:2]:

                for c in condition[:2]:

                    queries.append(
                        f"{s} {p} {c}"
                    )

    # ----------------------------------------------------------------------
    # 5. Causal research query
    # ----------------------------------------------------------------------

    if subject and phenomenon:

        queries.append(
            " ".join(
                [
                    subject[0],
                    phenomenon[0],
                    "mechanism",
                ]
            )
        )

        queries.append(
            " ".join(
                [
                    subject[0],
                    phenomenon[0],
                    "cause",
                ]
            )
        )

    # ----------------------------------------------------------------------
    # 6. Topic terms
    # ----------------------------------------------------------------------

    if topic_terms:

        queries.append(
            " ".join(
                topic_terms[:10]
            )
        )

    # ----------------------------------------------------------------------
    # Deduplicate
    # ----------------------------------------------------------------------

    final = []

    seen = set()

    for query in queries:

        query = _clean(
            query
        )

        if not query:
            continue

        key = query.lower()

        if key in seen:
            continue

        seen.add(
            key
        )

        final.append(
            query
        )

    return final[:12]


# ============================================================================
# CONCEPT COVERAGE
# ============================================================================

def _concept_phrase_variants(
    phrase
):

    phrase = _clean(
        phrase
    ).lower()

    if not phrase:
        return []

    variants = [
        phrase
    ]

    tokens = phrase.split()

    # Simple singular/plural variants.
    if len(tokens) > 1:

        last = tokens[-1]

        if last.endswith("s"):

            variants.append(
                " ".join(
                    tokens[:-1]
                    + [last[:-1]]
                )
            )

        else:

            variants.append(
                " ".join(
                    tokens[:-1]
                    + [last + "s"]
                )
            )

    return list(
        dict.fromkeys(
            variants
        )
    )


def _concept_phrase_match(
    phrase,
    title,
    evidence,
):

    title_clean = (
        _text_clean_for_matching(
            title
        )
    )

    evidence_clean = (
        _text_clean_for_matching(
            evidence
        )
    )

    variants = _concept_phrase_variants(
        phrase
    )

    title_match = False
    evidence_match = False

    for variant in variants:

        if _phrase_exists(
            variant,
            title_clean,
        ):

            title_match = True

        if _phrase_exists(
            variant,
            evidence_clean,
        ):

            evidence_match = True

    # ----------------------------------------------------------------------
    # If the phrase does not occur literally, allow token-level
    # matching, but require every meaningful token.
    # ----------------------------------------------------------------------

    if not title_match:

        tokens = [
            token
            for token in re.findall(
                r"[a-z0-9]+",
                phrase.lower(),
            )
            if len(token) >= 3
        ]

        if len(tokens) >= 2:

            title_match = all(
                _stem_like_match(
                    token,
                    title_clean,
                )
                for token in tokens
            )

    if not evidence_match:

        tokens = [
            token
            for token in re.findall(
                r"[a-z0-9]+",
                phrase.lower(),
            )
            if len(token) >= 3
        ]

        if len(tokens) >= 2:

            evidence_match = all(
                _stem_like_match(
                    token,
                    evidence_clean,
                )
                for token in tokens
            )

    return (
        title_match,
        evidence_match,
    )


def _concept_coverage(
    topic,
    source,
):

    title = _clean(
        source.get(
            "title",
            "",
        )
    )

    evidence = _clean(
        source.get(
            "evidence_text",
            "",
        )
        or source.get(
            "abstract",
            "",
        )
    )

    concepts = _question_concepts(
        topic
    )

    subject = concepts[
        "subject"
    ]

    phenomenon = concepts[
        "phenomenon"
    ]

    condition = concepts[
        "condition"
    ]

    causal_intent = concepts[
        "causal_intent"
    ]

    # ----------------------------------------------------------------------
    # SUBJECT COVERAGE
    # ----------------------------------------------------------------------

    subject_title = []
    subject_evidence = []

    for phrase in subject:

        title_match, evidence_match = (
            _concept_phrase_match(
                phrase,
                title,
                evidence,
            )
        )

        if title_match:
            subject_title.append(
                phrase
            )

        if evidence_match:
            subject_evidence.append(
                phrase
            )

    # ----------------------------------------------------------------------
    # PHENOMENON COVERAGE
    # ----------------------------------------------------------------------

    phenomenon_title = []
    phenomenon_evidence = []

    for phrase in phenomenon:

        title_match, evidence_match = (
            _concept_phrase_match(
                phrase,
                title,
                evidence,
            )
        )

        if title_match:
            phenomenon_title.append(
                phrase
            )

        if evidence_match:
            phenomenon_evidence.append(
                phrase
            )

    # ----------------------------------------------------------------------
    # CONDITION COVERAGE
    # ----------------------------------------------------------------------

    condition_title = []
    condition_evidence = []

    for phrase in condition:

        title_match, evidence_match = (
            _concept_phrase_match(
                phrase,
                title,
                evidence,
            )
        )

        if title_match:
            condition_title.append(
                phrase
            )

        if evidence_match:
            condition_evidence.append(
                phrase
            )

    # ----------------------------------------------------------------------
    # Generic topic-term coverage
    # ----------------------------------------------------------------------

    topic_terms = set(
        concepts[
            "topic_terms"
        ]
    )

    title_term_matches = _matched_terms(
        topic_terms,
        _text_clean_for_matching(
            title
        ),
    )

    evidence_term_matches = _matched_terms(
        topic_terms,
        _text_clean_for_matching(
            evidence
        ),
    )

    # ----------------------------------------------------------------------
    # Causal relevance
    #
    # We don't require literal words such as "cause".
    #
    # Instead, if the question is causal, the source must contain
    # enough subject + phenomenon evidence to plausibly address
    # the causal relationship.
    # ----------------------------------------------------------------------

    causal_relevance = False

    if causal_intent:

        if (
            subject_evidence
            and phenomenon_evidence
        ):

            causal_relevance = True

        elif (
            subject_title
            and phenomenon_evidence
        ):

            causal_relevance = True

        elif (
            phenomenon_title
            and subject_evidence
        ):

            causal_relevance = True

    else:

        causal_relevance = True

    # ----------------------------------------------------------------------
    # SUBJECT PASS
    # ----------------------------------------------------------------------

    if subject:

        subject_pass = bool(
            subject_evidence
            or (
                subject_title
                and len(
                    subject_title
                ) >= 1
            )
        )

    else:

        subject_pass = (
            len(
                title_term_matches
                | evidence_term_matches
            )
            >= 1
        )

    # ----------------------------------------------------------------------
    # PHENOMENON PASS
    # ----------------------------------------------------------------------

    if phenomenon:

        phenomenon_pass = bool(
            phenomenon_evidence
            or (
                phenomenon_title
                and len(
                    phenomenon_title
                ) >= 1
            )
        )

    else:

        phenomenon_pass = True

    # ----------------------------------------------------------------------
    # CONDITION PASS
    # ----------------------------------------------------------------------

    if condition:

        condition_pass = bool(
            condition_evidence
            or condition_title
        )

    else:

        condition_pass = True

    # ----------------------------------------------------------------------
    # Condition strictness
    #
    # A causal question containing a specific transition such as
    # "as they slow down" should not be satisfied by a paper that
    # only discusses the object and sound in a completely different
    # operating state.
    # ----------------------------------------------------------------------

    condition_required = (
        bool(condition)
        and causal_intent
        and REQUIRE_CONDITION_FOR_CAUSAL_QUESTIONS
    )

    # ----------------------------------------------------------------------
    # Score
    # ----------------------------------------------------------------------

    score = 0

    if subject_evidence:
        score += 5

    elif subject_title:
        score += 3

    if phenomenon_evidence:
        score += 5

    elif phenomenon_title:
        score += 3

    if condition_evidence:
        score += 4

    elif condition_title:
        score += 2

    if causal_relevance:
        score += 3

    score += min(
        len(title_term_matches),
        3,
    )

    score += min(
        len(evidence_term_matches),
        4,
    )

    # ----------------------------------------------------------------------
    # Hard requirements
    # ----------------------------------------------------------------------

    overall = True

    rejection_reasons = []

    if (
        REQUIRE_SUBJECT
        and not subject_pass
    ):

        overall = False

        rejection_reasons.append(
            "subject_not_covered"
        )

    if (
        REQUIRE_PHENOMENON
        and not phenomenon_pass
    ):

        overall = False

        rejection_reasons.append(
            "phenomenon_not_covered"
        )

    if (
        condition_required
        and not condition_pass
    ):

        overall = False

        rejection_reasons.append(
            "required_condition_not_covered"
        )

    if (
        causal_intent
        and not causal_relevance
    ):

        overall = False

        rejection_reasons.append(
            "causal_relationship_not_supported"
        )

    if score < MIN_CONCEPT_SCORE:

        overall = False

        rejection_reasons.append(
            "concept_score_below_threshold"
        )

    # ----------------------------------------------------------------------
    # Class
    # ----------------------------------------------------------------------

    if overall:

        if score >= 18:

            relevance_class = "strong"

        elif score >= MIN_CONCEPT_SCORE:

            relevance_class = "moderate"

        else:

            relevance_class = "weak"

    else:

        relevance_class = "weak"

    result = {
        "subject_required": bool(
            subject
        ),

        "subject_pass": bool(
            subject_pass
        ),

        "subject_title_matches": sorted(
            subject_title
        ),

        "subject_evidence_matches": sorted(
            subject_evidence
        ),

        "phenomenon_required": bool(
            phenomenon
        ),

        "phenomenon_pass": bool(
            phenomenon_pass
        ),

        "phenomenon_title_matches": sorted(
            phenomenon_title
        ),

        "phenomenon_evidence_matches": sorted(
            phenomenon_evidence
        ),

        "condition_required": bool(
            condition_required
        ),

        "condition_pass": bool(
            condition_pass
        ),

        "condition_title_matches": sorted(
            condition_title
        ),

        "condition_evidence_matches": sorted(
            condition_evidence
        ),

        "causal_intent": bool(
            causal_intent
        ),

        "causal_relevance": bool(
            causal_relevance
        ),

        "topic_title_matches": sorted(
            title_term_matches
        ),

        "topic_evidence_matches": sorted(
            evidence_term_matches
        ),

        "concept_score": score,

        "relevance_score": score,

        "relevance_class": relevance_class,

        "concept_coverage_pass": overall,

        "intent_pass": overall,

        "intent_class": (
            "causal_concept"
            if causal_intent
            else "concept"
        ),

        "rejection_reasons": rejection_reasons,
    }

    source[
        "concept_coverage"
    ] = result

    # ----------------------------------------------------------------------
    # Backwards-compatible fields expected elsewhere in the project.
    # ----------------------------------------------------------------------

    source[
        "matched_terms"
    ] = sorted(
        set(
            title_term_matches
            | evidence_term_matches
        )
    )

    source[
        "topic_terms"
    ] = sorted(
        topic_terms
    )

    source[
        "expanded_topic_terms"
    ] = concepts[
        "expanded_terms"
    ]

    source[
        "question_phrases"
    ] = concepts[
        "question_phrases"
    ]

    source[
        "title_match_count"
    ] = len(
        title_term_matches
    )

    source[
        "abstract_match_count"
    ] = len(
        evidence_term_matches
    )

    source[
        "expanded_title_match_count"
    ] = 0

    source[
        "expanded_abstract_match_count"
    ] = 0

    source[
        "phrase_title_match_count"
    ] = 0

    source[
        "phrase_evidence_match_count"
    ] = 0

    source[
        "relevance_class"
    ] = relevance_class

    source[
        "relevance_score"
    ] = score

    source[
        "intent_pass"
    ] = overall

    source[
        "intent_class"
    ] = result[
        "intent_class"
    ]

    source[
        "question_intents"
    ] = (
        ["cause"]
        if causal_intent
        else []
    )

    source[
        "intent_score"
    ] = score

    source[
        "intent_mechanism_matches"
    ] = sorted(
        set(
            phenomenon_evidence
            + subject_evidence
        )
    )

    source[
        "intent_event_matches"
    ] = sorted(
        condition_evidence
    )

    source[
        "intent_target_matches"
    ] = sorted(
        subject_evidence
    )

    source[
        "intent_negative_matches"
    ] = []

    return result


# ============================================================================
# RELEVANCE FILTER
# ============================================================================

def _relevance_score(
    topic,
    source,
):

    result = _concept_coverage(
        topic,
        source,
    )

    return result[
        "concept_score"
    ]


def relevance_filter(
    topic,
    sources,
    label="STRICT QUESTION RELEVANCE FILTER",
):

    print("=" * 80)

    print(
        label
    )

    print("=" * 80)

    print(
        "Question: "
        + topic
    )

    concepts = _question_concepts(
        topic
    )

    print(
        "Subject concepts: "
        + (
            ", ".join(
                concepts[
                    "subject"
                ]
            )
            or "none"
        )
    )

    print(
        "Phenomenon concepts: "
        + (
            ", ".join(
                concepts[
                    "phenomenon"
                ]
            )
            or "none"
        )
    )

    print(
        "Condition concepts: "
        + (
            ", ".join(
                concepts[
                    "condition"
                ]
            )
            or "none"
        )
    )

    print(
        "Causal question: "
        + str(
            concepts[
                "causal_intent"
            ]
        )
    )

    accepted = []

    for source in sources:

        result = _concept_coverage(
            topic,
            source,
        )

        score = result[
            "concept_score"
        ]

        title = source.get(
            "title",
            "",
        )

        classification = result[
            "relevance_class"
        ]

        if (
            result[
                "concept_coverage_pass"
            ]
            and classification in {
                "strong",
                "moderate",
            }
        ):

            accepted.append(
                source
            )

            print(
                f"✅ RELEVANT: {title}"
            )

            print(
                f"   Score: {score}"
            )

            print(
                f"   Class: {classification}"
            )

            print(
                "   Subject: "
                f"{result['subject_pass']}"
            )

            print(
                "   Phenomenon: "
                f"{result['phenomenon_pass']}"
            )

            print(
                "   Condition: "
                f"{result['condition_pass']}"
            )

            print(
                "   Causal relevance: "
                f"{result['causal_relevance']}"
            )

        else:

            print(
                f"❌ REJECTED: {title}"
            )

            print(
                f"   Score: {score}"
            )

            print(
                "   Reasons: "
                + (
                    ", ".join(
                        result[
                            "rejection_reasons"
                        ]
                    )
                    or "insufficient concept coverage"
                )
            )

    print(
        f"Relevant candidates: "
        f"{len(accepted)}"
    )

    return accepted


# ============================================================================
# METADATA HELPERS
# ============================================================================

def _authors_crossref(item):

    authors = []

    for author in item.get(
        "author",
        [],
    ):

        given = _clean(
            author.get(
                "given",
                "",
            )
        )

        family = _clean(
            author.get(
                "family",
                "",
            )
        )

        name = " ".join(
            part
            for part in (
                given,
                family,
            )
            if part
        )

        if name:
            authors.append(
                name
            )

    return ", ".join(
        authors
    )


def _authors_semantic(item):

    authors = []

    for author in item.get(
        "authors",
        [],
    ):

        name = _clean(
            author.get(
                "name",
                "",
            )
        )

        if name:
            authors.append(
                name
            )

    return ", ".join(
        authors
    )


def _extract_year(item):

    for key in (
        "published-print",
        "published-online",
        "published",
        "issued",
        "created",
    ):

        date_info = item.get(
            key,
            {},
        )

        if not isinstance(
            date_info,
            dict,
        ):
            continue

        parts = date_info.get(
            "date-parts",
            [],
        )

        if parts and parts[0]:

            try:

                return int(
                    parts[0][0]
                )

            except Exception:
                pass

    return None


def _openalex_abstract_text(
    inverted_index
):

    if not isinstance(
        inverted_index,
        dict,
    ):
        return ""

    words = []

    for word, positions in (
        inverted_index.items()
    ):

        if not isinstance(
            positions,
            list,
        ):
            continue

        for position in positions:

            try:

                words.append(
                    (
                        int(position),
                        word,
                    )
                )

            except Exception:
                continue

    words.sort(
        key=lambda item: item[0]
    )

    return _clean_abstract(
        " ".join(
            word
            for _, word in words
        )
    )


# ============================================================================
# EVIDENCE
# ============================================================================

def _record_evidence_provider(
    source,
    provider,
    abstract,
):

    abstract = _clean_abstract(
        abstract
    )

    if not abstract:
        return

    providers = set(
        source.get(
            "evidence_providers",
            [],
        )
    )

    providers.add(
        provider
    )

    source[
        "evidence_providers"
    ] = sorted(
        providers
    )

    records = source.get(
        "evidence_records",
        [],
    )

    if not isinstance(
        records,
        list,
    ):

        records = []

    if not any(
        isinstance(
            record,
            dict,
        )
        and record.get(
            "provider"
        ) == provider
        for record in records
    ):

        records.append(
            {
                "provider": provider,
                "characters": len(
                    abstract
                ),
            }
        )

    source[
        "evidence_records"
    ] = records


def _build_evidence_package(
    source
):

    abstract = _clean_abstract(
        source.get(
            "abstract",
            "",
        )
    )

    if abstract:

        evidence = abstract[
            :MAX_EVIDENCE_TEXT_CHARACTERS
        ]

        source[
            "evidence_available"
        ] = True

        source[
            "evidence_type"
        ] = "abstract"

        source[
            "evidence_quality"
        ] = "moderate"

        source[
            "evidence_text"
        ] = evidence

        source[
            "evidence_notes"
        ] = (
            "Retrieved scholarly abstract. "
            "It is not the full paper."
        )

        source[
            "abstract"
        ] = evidence

    else:

        source[
            "evidence_available"
        ] = False

        source[
            "evidence_type"
        ] = "metadata_only"

        source[
            "evidence_quality"
        ] = "none"

        source[
            "evidence_text"
        ] = ""

        source[
            "evidence_notes"
        ] = (
            "No abstract/evidence text was retrieved. "
            "Metadata alone is not evidence."
        )

        source[
            "abstract"
        ] = ""

    return source


# ============================================================================
# DISCOVERY
# ============================================================================

def _crossref_search_once(
    query
):

    params = {
        "query.bibliographic": query,
        "rows": MAX_CROSSREF_RESULTS,
        "select": (
            "DOI,title,author,container-title,publisher,type,"
            "published,published-print,published-online,URL,abstract"
        ),
    }

    data = _get(
        CROSSREF_URL,
        params,
        retries=2,
        backoff=2,
        provider="Crossref",
    )

    return (
        data.get(
            "message",
            {},
        ).get(
            "items",
            [],
        )
    )


def search_crossref(
    topic
):

    print("=" * 80)
    print(
        "🔎 CROSSREF SEARCH"
    )
    print("=" * 80)

    results = []
    seen = set()

    for query in build_scholarly_queries(
        topic
    ):

        print(
            f"   • {query}"
        )

        try:

            items = _crossref_search_once(
                query
            )

        except Exception as error:

            print(
                "⚠️ Crossref query failed: "
                f"{error}"
            )

            continue

        for item in items:

            title = _clean(
                (
                    item.get(
                        "title",
                        [],
                    )
                    or [""]
                )[0]
            )

            doi = _normalize_doi(
                item.get(
                    "DOI",
                    "",
                )
            )

            if (
                not title
                or not doi
                or doi in seen
            ):
                continue

            seen.add(
                doi
            )

            abstract = _clean_abstract(
                item.get(
                    "abstract",
                    "",
                )
            )

            source = {
                "source_database": "Crossref",
                "source_databases": [
                    "Crossref"
                ],
                "discovery_provider": "Crossref",
                "discovery_providers": [
                    "Crossref"
                ],
                "title": title,
                "authors": _authors_crossref(
                    item
                ),
                "journal": _clean(
                    (
                        item.get(
                            "container-title",
                            [],
                        )
                        or [""]
                    )[0]
                ),
                "publisher": _clean(
                    item.get(
                        "publisher",
                        "",
                    )
                ),
                "year": _extract_year(
                    item
                ),
                "doi": doi,
                "url": (
                    _clean(
                        item.get(
                            "URL",
                            "",
                        )
                    )
                    or
                    f"https://doi.org/{doi}"
                ),
                "type": _clean(
                    item.get(
                        "type",
                        "",
                    )
                ),
                "publication_type": _clean(
                    item.get(
                        "type",
                        "",
                    )
                ),
                "abstract": abstract,
                "evidence_source": (
                    "Crossref abstract"
                    if abstract
                    else ""
                ),
                "evidence_providers": (
                    ["Crossref"]
                    if abstract
                    else []
                ),
                "metadata_verified": False,
                "evidence_verified": False,
                "verified": False,
            }

            if abstract:

                _record_evidence_provider(
                    source,
                    "Crossref",
                    abstract,
                )

            results.append(
                _build_evidence_package(
                    source
                )
            )

    print(
        f"Crossref results: "
        f"{len(results)}"
    )

    return results


def search_semantic_scholar(
    topic
):

    global SEMANTIC_RATE_LIMITED

    print("=" * 80)
    print(
        "🔎 SEMANTIC SCHOLAR SEARCH"
    )
    print("=" * 80)

    if SEMANTIC_RATE_LIMITED:

        print(
            "⚠️ Semantic Scholar rate limited; skipping."
        )

        return []

    results = []
    seen = set()

    for query in build_scholarly_queries(
        topic
    ):

        if SEMANTIC_RATE_LIMITED:
            break

        params = {
            "query": query,
            "limit": MAX_SEMANTIC_RESULTS,
            "fields": (
                "title,authors,year,abstract,url,externalIds,"
                "publicationTypes,venue,citationCount"
            ),
        }

        print(
            f"   • {query}"
        )

        try:

            data = _get(
                SEMANTIC_SEARCH_URL,
                params,
                retries=SEMANTIC_RETRIES,
                backoff=SEMANTIC_BACKOFF_SECONDS,
                provider="Semantic Scholar",
            )

        except Exception as error:

            print(
                "⚠️ Semantic Scholar unavailable: "
                f"{error}"
            )

            continue

        for paper in data.get(
            "data",
            [],
        ):

            title = _clean(
                paper.get(
                    "title",
                    "",
                )
            )

            ids = (
                paper.get(
                    "externalIds",
                    {},
                )
                or {}
            )

            doi = _normalize_doi(
                ids.get(
                    "DOI",
                    "",
                )
            )

            if (
                not title
                or not doi
                or doi in seen
            ):
                continue

            seen.add(
                doi
            )

            abstract = _clean_abstract(
                paper.get(
                    "abstract",
                    "",
                )
            )

            publication_types = (
                paper.get(
                    "publicationTypes",
                    [],
                )
                or []
            )

            source = {
                "source_database": "Semantic Scholar",
                "source_databases": [
                    "Semantic Scholar"
                ],
                "discovery_provider": "Semantic Scholar",
                "discovery_providers": [
                    "Semantic Scholar"
                ],
                "title": title,
                "authors": _authors_semantic(
                    paper
                ),
                "journal": _clean(
                    paper.get(
                        "venue",
                        "",
                    )
                ),
                "publisher": "",
                "year": paper.get(
                    "year"
                ),
                "doi": doi,
                "url": (
                    f"https://doi.org/{doi}"
                ),
                "semantic_scholar_url": _clean(
                    paper.get(
                        "url",
                        "",
                    )
                ),
                "abstract": abstract,
                "publication_types": publication_types,
                "publication_type": (
                    publication_types[0]
                    if publication_types
                    else ""
                ),
                "citation_count": (
                    paper.get(
                        "citationCount",
                        0,
                    )
                    or 0
                ),
                "evidence_source": (
                    "Semantic Scholar abstract"
                    if abstract
                    else ""
                ),
                "evidence_providers": (
                    ["Semantic Scholar"]
                    if abstract
                    else []
                ),
                "metadata_verified": False,
                "evidence_verified": False,
                "verified": False,
            }

            if abstract:

                _record_evidence_provider(
                    source,
                    "Semantic Scholar",
                    abstract,
                )

            results.append(
                _build_evidence_package(
                    source
                )
            )

    print(
        "Semantic Scholar results: "
        f"{len(results)}"
    )

    return results


def search_openalex(
    topic
):

    print("=" * 80)
    print(
        "🔎 OPENALEX SEARCH"
    )
    print("=" * 80)

    results = []
    seen = set()

    for query in build_scholarly_queries(
        topic
    ):

        print(
            f"   • {query}"
        )

        params = {
            "search": query,
            "per-page": MAX_OPENALEX_RESULTS,
        }

        try:

            data = _get(
                OPENALEX_URL,
                params,
                retries=2,
                backoff=2,
                provider="OpenAlex",
            )

        except Exception as error:

            print(
                "⚠️ OpenAlex search failed: "
                f"{error}"
            )

            continue

        for item in data.get(
            "results",
            [],
        ):

            title = _clean(
                item.get(
                    "display_name",
                    "",
                )
            )

            ids = (
                item.get(
                    "ids",
                    {},
                )
                or {}
            )

            doi = _normalize_doi(
                ids.get(
                    "doi",
                    "",
                )
            )

            if (
                not title
                or not doi
                or doi in seen
            ):
                continue

            seen.add(
                doi
            )

            authors = []

            for authorship in item.get(
                "authorships",
                [],
            ):

                author = (
                    authorship.get(
                        "author",
                        {},
                    )
                    or {}
                )

                name = _clean(
                    author.get(
                        "display_name",
                        "",
                    )
                )

                if name:
                    authors.append(
                        name
                    )

            location = (
                item.get(
                    "primary_location",
                    {},
                )
                or {}
            )

            source_info = (
                location.get(
                    "source",
                    {},
                )
                or {}
            )

            abstract = _openalex_abstract_text(
                item.get(
                    "abstract_inverted_index"
                )
            )

            open_access = (
                item.get(
                    "open_access",
                    {},
                )
                or {}
            )

            source = {
                "source_database": "OpenAlex",
                "source_databases": [
                    "OpenAlex"
                ],
                "discovery_provider": "OpenAlex",
                "discovery_providers": [
                    "OpenAlex"
                ],
                "title": title,
                "authors": ", ".join(
                    authors
                ),
                "journal": _clean(
                    source_info.get(
                        "display_name",
                        "",
                    )
                ),
                "publisher": "",
                "year": item.get(
                    "publication_year"
                ),
                "doi": doi,
                "url": (
                    f"https://doi.org/{doi}"
                ),
                "openalex_url": _clean(
                    ids.get(
                        "openalex",
                        "",
                    )
                ),
                "abstract": abstract,
                "publication_type": _clean(
                    item.get(
                        "type",
                        "",
                    )
                ),
                "citation_count": (
                    item.get(
                        "cited_by_count",
                        0,
                    )
                    or 0
                ),
                "open_access": bool(
                    open_access.get(
                        "is_oa",
                        False,
                    )
                ),
                "evidence_source": (
                    "OpenAlex abstract"
                    if abstract
                    else ""
                ),
                "evidence_providers": (
                    ["OpenAlex"]
                    if abstract
                    else []
                ),
                "metadata_verified": False,
                "evidence_verified": False,
                "verified": False,
            }

            if abstract:

                _record_evidence_provider(
                    source,
                    "OpenAlex",
                    abstract,
                )

            results.append(
                _build_evidence_package(
                    source
                )
            )

    print(
        f"OpenAlex results: "
        f"{len(results)}"
    )

    return results


# ============================================================================
# DEDUPLICATION
# ============================================================================

def _merge_sources(
    primary,
    secondary,
):

    databases = set(
        primary.get(
            "source_databases",
            [],
        )
    )

    databases.update(
        secondary.get(
            "source_databases",
            [],
        )
    )

    primary[
        "source_databases"
    ] = sorted(
        databases
    )

    providers = set(
        primary.get(
            "discovery_providers",
            [],
        )
    )

    providers.update(
        secondary.get(
            "discovery_providers",
            [],
        )
    )

    primary[
        "discovery_providers"
    ] = sorted(
        providers
    )

    for field in (
        "authors",
        "journal",
        "publisher",
        "year",
        "url",
        "type",
        "publication_type",
        "semantic_scholar_url",
        "openalex_url",
    ):

        if (
            not primary.get(
                field
            )
            and secondary.get(
                field
            )
        ):

            primary[
                field
            ] = secondary[
                field
            ]

    primary_abstract = (
        _clean_abstract(
            primary.get(
                "abstract",
                "",
            )
        )
    )

    secondary_abstract = (
        _clean_abstract(
            secondary.get(
                "abstract",
                "",
            )
        )
    )

    if secondary_abstract:

        _record_evidence_provider(
            primary,
            secondary.get(
                "source_database",
                "unknown",
            ),
            secondary_abstract,
        )

    if len(
        secondary_abstract
    ) > len(
        primary_abstract
    ):

        primary[
            "abstract"
        ] = secondary_abstract

        primary[
            "evidence_source"
        ] = secondary.get(
            "evidence_source",
            "",
        )

    primary[
        "citation_count"
    ] = max(
        primary.get(
            "citation_count",
            0,
        )
        or 0,
        secondary.get(
            "citation_count",
            0,
        )
        or 0,
    )

    primary[
        "openalex_citation_count"
    ] = max(
        primary.get(
            "openalex_citation_count",
            0,
        )
        or 0,
        secondary.get(
            "openalex_citation_count",
            0,
        )
        or 0,
    )

    return _build_evidence_package(
        primary
    )


def deduplicate_sources(
    sources
):

    by_doi = {}
    by_title = {}
    unique = []

    for source in sources:

        doi = _normalize_doi(
            source.get(
                "doi",
                "",
            )
        )

        title = _normalize_title(
            source.get(
                "title",
                "",
            )
        )

        existing = None

        if (
            doi
            and doi in by_doi
        ):

            existing = by_doi[
                doi
            ]

        elif (
            not doi
            and title
            and title in by_title
        ):

            existing = by_title[
                title
            ]

        if existing is not None:

            _merge_sources(
                existing,
                source,
            )

            continue

        source[
            "doi"
        ] = doi

        source.setdefault(
            "source_databases",
            [],
        )

        if source.get(
            "source_database"
        ):

            source[
                "source_databases"
            ].append(
                source[
                    "source_database"
                ]
            )

        source[
            "source_databases"
        ] = sorted(
            set(
                source[
                    "source_databases"
                ]
            )
        )

        source.setdefault(
            "discovery_providers",
            [],
        )

        if source.get(
            "discovery_provider"
        ):

            source[
                "discovery_providers"
            ].append(
                source[
                    "discovery_provider"
                ]
            )

        source[
            "discovery_providers"
        ] = sorted(
            set(
                source[
                    "discovery_providers"
                ]
            )
        )

        unique.append(
            source
        )

        if doi:

            by_doi[
                doi
            ] = source

        if title:

            by_title[
                title
            ] = source

    return unique


# ============================================================================
# IDENTITY VERIFICATION
# ============================================================================

def _identity_matches(
    source,
    returned_title,
    returned_doi,
    provider,
):

    expected_doi = _normalize_doi(
        source.get(
            "doi",
            "",
        )
    )

    returned_doi = _normalize_doi(
        returned_doi
    )

    if not expected_doi:

        source[
            "identity_error"
        ] = (
            f"{provider}: source has no DOI."
        )

        return False

    if not returned_doi:

        source[
            "identity_error"
        ] = (
            f"{provider}: response did not contain DOI."
        )

        return False

    if expected_doi != returned_doi:

        source[
            "identity_error"
        ] = (
            f"{provider}: DOI mismatch."
        )

        return False

    returned_title = _clean(
        returned_title
    )

    if not returned_title:

        source[
            "identity_error"
        ] = (
            f"{provider}: response did not contain title."
        )

        return False

    similarity = _title_similarity(
        source.get(
            "title",
            "",
        ),
        returned_title,
    )

    source[
        "verified_title_similarity"
    ] = round(
        similarity,
        3,
    )

    if (
        similarity
        < TITLE_SIMILARITY_MINIMUM
    ):

        source[
            "identity_error"
        ] = (
            f"{provider}: title mismatch."
        )

        return False

    return True


def verify_crossref_source(
    source
):

    doi = _normalize_doi(
        source.get(
            "doi",
            "",
        )
    )

    if not doi:
        return False

    try:

        data = _get(
            CROSSREF_URL
            + "/"
            + quote(
                doi,
                safe="",
            ),
            retries=1,
            provider="Crossref",
        )

        item = data.get(
            "message",
            {},
        )

        returned_doi = _normalize_doi(
            item.get(
                "DOI",
                "",
            )
        )

        returned_title = _clean(
            (
                item.get(
                    "title",
                    [],
                )
                or [""]
            )[0]
        )

        if not _identity_matches(
            source,
            returned_title,
            returned_doi,
            "Crossref",
        ):
            return False

        source[
            "metadata_verified"
        ] = True

        source[
            "metadata_verification_provider"
        ] = "Crossref"

        source[
            "verified_title"
        ] = returned_title

        source[
            "doi"
        ] = returned_doi

        authors = _authors_crossref(
            item
        )

        if authors:
            source[
                "authors"
            ] = authors

        journal = _clean(
            (
                item.get(
                    "container-title",
                    [],
                )
                or [""]
            )[0]
        )

        if journal:
            source[
                "journal"
            ] = journal

        publisher = _clean(
            item.get(
                "publisher",
                "",
            )
        )

        if publisher:
            source[
                "publisher"
            ] = publisher

        year = _extract_year(
            item
        )

        if year:
            source[
                "year"
            ] = year

        abstract = _clean_abstract(
            item.get(
                "abstract",
                "",
            )
        )

        if abstract:

            source[
                "abstract"
            ] = abstract

            source[
                "evidence_source"
            ] = "Crossref abstract"

            _record_evidence_provider(
                source,
                "Crossref",
                abstract,
            )

        source[
            "verification"
        ] = (
            "DOI and publication identity "
            "verified through Crossref."
        )

        return _build_evidence_package(
            source
        )

    except Exception as error:

        source[
            "crossref_verification_error"
        ] = str(
            error
        )

        return False


def verify_semantic_source(
    source
):

    global SEMANTIC_RATE_LIMITED

    if SEMANTIC_RATE_LIMITED:
        return False

    doi = _normalize_doi(
        source.get(
            "doi",
            "",
        )
    )

    if not doi:
        return False

    try:

        data = _get(
            SEMANTIC_PAPER_URL
            + "/DOI:"
            + quote(
                doi,
                safe="",
            ),
            params={
                "fields": (
                    "title,authors,year,abstract,"
                    "externalIds,venue,publicationTypes,"
                    "citationCount"
                )
            },
            retries=SEMANTIC_RETRIES,
            backoff=SEMANTIC_BACKOFF_SECONDS,
            provider="Semantic Scholar",
        )

        returned_title = _clean(
            data.get(
                "title",
                "",
            )
        )

        ids = (
            data.get(
                "externalIds",
                {},
            )
            or {}
        )

        returned_doi = _normalize_doi(
            ids.get(
                "DOI",
                "",
            )
        )

        if not _identity_matches(
            source,
            returned_title,
            returned_doi,
            "Semantic Scholar",
        ):
            return False

        source[
            "metadata_verified"
        ] = True

        source[
            "metadata_verification_provider"
        ] = "Semantic Scholar"

        source[
            "verified_title"
        ] = returned_title

        source[
            "doi"
        ] = returned_doi

        authors = _authors_semantic(
            data
        )

        if authors:
            source[
                "authors"
            ] = authors

        venue = _clean(
            data.get(
                "venue",
                "",
            )
        )

        if venue:
            source[
                "journal"
            ] = venue

        if data.get(
            "year"
        ):

            source[
                "year"
            ] = data[
                "year"
            ]

        abstract = _clean_abstract(
            data.get(
                "abstract",
                "",
            )
        )

        if abstract:

            source[
                "abstract"
            ] = abstract

            source[
                "evidence_source"
            ] = "Semantic Scholar abstract"

            _record_evidence_provider(
                source,
                "Semantic Scholar",
                abstract,
            )

        source[
            "citation_count"
        ] = (
            data.get(
                "citationCount",
                source.get(
                    "citation_count",
                    0,
                ),
            )
            or 0
        )

        source[
            "verification"
        ] = (
            "DOI and publication identity "
            "verified through Semantic Scholar."
        )

        return _build_evidence_package(
            source
        )

    except Exception as error:

        if "429" in str(
            error
        ):

            SEMANTIC_RATE_LIMITED = True

        source[
            "semantic_verification_error"
        ] = str(
            error
        )

        return False


def verify_openalex_source(
    source
):

    doi = _normalize_doi(
        source.get(
            "doi",
            "",
        )
    )

    if not doi:
        return False

    try:

        data = _get(
            OPENALEX_URL
            + "/https://doi.org/"
            + quote(
                doi,
                safe="",
            ),
            retries=1,
            provider="OpenAlex",
        )

        ids = (
            data.get(
                "ids",
                {},
            )
            or {}
        )

        returned_doi = _normalize_doi(
            ids.get(
                "doi",
                "",
            )
        )

        returned_title = _clean(
            data.get(
                "display_name",
                "",
            )
        )

        if not _identity_matches(
            source,
            returned_title,
            returned_doi,
            "OpenAlex",
        ):
            return False

        source[
            "metadata_verified"
        ] = True

        source[
            "metadata_verification_provider"
        ] = "OpenAlex"

        source[
            "verified_title"
        ] = returned_title

        source[
            "doi"
        ] = returned_doi

        if data.get(
            "publication_year"
        ):

            source[
                "year"
            ] = data[
                "publication_year"
            ]

        abstract = _openalex_abstract_text(
            data.get(
                "abstract_inverted_index"
            )
        )

        if abstract:

            source[
                "abstract"
            ] = abstract

            source[
                "evidence_source"
            ] = "OpenAlex abstract"

            _record_evidence_provider(
                source,
                "OpenAlex",
                abstract,
            )

        source[
            "openalex_citation_count"
        ] = (
            data.get(
                "cited_by_count",
                0,
            )
            or 0
        )

        source[
            "openalex_id"
        ] = _clean(
            data.get(
                "id",
                "",
            )
        )

        source[
            "verification"
        ] = (
            "DOI and publication identity "
            "verified through OpenAlex."
        )

        return _build_evidence_package(
            source
        )

    except Exception as error:

        source[
            "openalex_verification_error"
        ] = str(
            error
        )

        return False


def verify_source_identity(
    source
):

    discovery = source.get(
        "discovery_provider",
        "",
    )

    providers = []

    if discovery:
        providers.append(
            discovery
        )

    for provider in (
        "Crossref",
        "OpenAlex",
        "Semantic Scholar",
    ):

        if provider not in providers:

            providers.append(
                provider
            )

    errors = []

    for provider in providers:

        print(
            f"   ↪ Trying {provider}..."
        )

        if provider == "Crossref":

            verified = (
                verify_crossref_source(
                    source
                )
            )

        elif provider == "OpenAlex":

            verified = (
                verify_openalex_source(
                    source
                )
            )

        elif provider == "Semantic Scholar":

            verified = (
                verify_semantic_source(
                    source
                )
            )

        else:

            verified = False

        if verified:

            source[
                "verification_attempts"
            ] = providers

            return source

        if source.get(
            "identity_error"
        ):

            errors.append(
                source[
                    "identity_error"
                ]
            )

    source[
        "verification_attempts"
    ] = providers

    source[
        "verification_errors"
    ] = list(
        dict.fromkeys(
            errors
        )
    )

    return False


# ============================================================================
# EVIDENCE ENRICHMENT
# ============================================================================

def enrich_from_crossref(
    source
):

    doi = _normalize_doi(
        source.get(
            "doi",
            "",
        )
    )

    if not doi:
        return source

    try:

        data = _get(
            CROSSREF_URL
            + "/"
            + quote(
                doi,
                safe="",
            ),
            retries=1,
            provider="Crossref",
        )

        abstract = _clean_abstract(
            data.get(
                "message",
                {},
            ).get(
                "abstract",
                "",
            )
        )

        if abstract:

            _record_evidence_provider(
                source,
                "Crossref",
                abstract,
            )

            current = _clean_abstract(
                source.get(
                    "abstract",
                    "",
                )
            )

            if len(
                abstract
            ) > len(
                current
            ):

                source[
                    "abstract"
                ] = abstract

                source[
                    "evidence_source"
                ] = "Crossref abstract"

    except Exception as error:

        source[
            "crossref_enrichment_error"
        ] = str(
            error
        )

    return source


def enrich_from_openalex(
    source
):

    doi = _normalize_doi(
        source.get(
            "doi",
            "",
        )
    )

    if not doi:
        return source

    try:

        data = _get(
            OPENALEX_URL
            + "/https://doi.org/"
            + quote(
                doi,
                safe="",
            ),
            retries=1,
            provider="OpenAlex",
        )

        abstract = _openalex_abstract_text(
            data.get(
                "abstract_inverted_index"
            )
        )

        if abstract:

            _record_evidence_provider(
                source,
                "OpenAlex",
                abstract,
            )

            current = _clean_abstract(
                source.get(
                    "abstract",
                    "",
                )
            )

            if len(
                abstract
            ) > len(
                current
            ):

                source[
                    "abstract"
                ] = abstract

                source[
                    "evidence_source"
                ] = "OpenAlex abstract"

        source[
            "openalex_citation_count"
        ] = (
            data.get(
                "cited_by_count",
                0,
            )
            or 0
        )

        source[
            "openalex_id"
        ] = _clean(
            data.get(
                "id",
                "",
            )
        )

    except Exception as error:

        source[
            "openalex_enrichment_error"
        ] = str(
            error
        )

    return source


def enrich_from_semantic(
    source
):

    global SEMANTIC_RATE_LIMITED

    if SEMANTIC_RATE_LIMITED:
        return source

    doi = _normalize_doi(
        source.get(
            "doi",
            "",
        )
    )

    if not doi:
        return source

    try:

        data = _get(
            SEMANTIC_PAPER_URL
            + "/DOI:"
            + quote(
                doi,
                safe="",
            ),
            params={
                "fields": (
                    "title,abstract,year,externalIds,"
                    "publicationTypes,citationCount"
                )
            },
            retries=SEMANTIC_RETRIES,
            backoff=SEMANTIC_BACKOFF_SECONDS,
            provider="Semantic Scholar",
        )

        abstract = _clean_abstract(
            data.get(
                "abstract",
                "",
            )
        )

        if abstract:

            _record_evidence_provider(
                source,
                "Semantic Scholar",
                abstract,
            )

            current = _clean_abstract(
                source.get(
                    "abstract",
                    "",
                )
            )

            if len(
                abstract
            ) > len(
                current
            ):

                source[
                    "abstract"
                ] = abstract

                source[
                    "evidence_source"
                ] = "Semantic Scholar abstract"

        source[
            "citation_count"
        ] = (
            data.get(
                "citationCount",
                source.get(
                    "citation_count",
                    0,
                ),
            )
            or 0
        )

    except Exception as error:

        if "429" in str(
            error
        ):

            SEMANTIC_RATE_LIMITED = True

        source[
            "semantic_enrichment_error"
        ] = str(
            error
        )

    return source


def enrich_source(
    source
):

    if _clean_abstract(
        source.get(
            "abstract",
            "",
        )
    ):

        return _build_evidence_package(
            source
        )

    source = enrich_from_openalex(
        source
    )

    if _clean_abstract(
        source.get(
            "abstract",
            "",
        )
    ):

        return _build_evidence_package(
            source
        )

    source = enrich_from_crossref(
        source
    )

    if _clean_abstract(
        source.get(
            "abstract",
            "",
        )
    ):

        return _build_evidence_package(
            source
        )

    source = enrich_from_semantic(
        source
    )

    return _build_evidence_package(
        source
    )


def enrich_sources(
    sources
):

    print("=" * 80)
    print(
        "📚 ENRICHING RESEARCH EVIDENCE"
    )
    print("=" * 80)

    enriched = []

    for index, source in enumerate(
        sources,
        start=1,
    ):

        print(
            f"Evidence {index}/"
            f"{len(sources)}: "
            f"{source.get('title', '')}"
        )

        source = enrich_source(
            source
        )

        if source.get(
            "evidence_available"
        ):

            print(
                "✅ Evidence available "
                f"({len(source.get('evidence_text', ''))} chars)"
            )

            enriched.append(
                source
            )

        else:

            print(
                "❌ No evidence available"
            )

    return enriched


# ============================================================================
# EVIDENCE VALIDATION
# ============================================================================

def mark_evidence_verified(
    sources
):

    accepted = []

    for source in sources:

        title = _clean(
            source.get(
                "title",
                "",
            )
        )

        if source.get(
            "metadata_verified"
        ) is not True:

            print(
                f"❌ Rejected unverified source: "
                f"{title}"
            )

            continue

        evidence = _clean_abstract(
            source.get(
                "evidence_text",
                "",
            )
        )

        if len(
            evidence
        ) < MIN_ABSTRACT_CHARACTERS:

            print(
                f"❌ Rejected insufficient evidence: "
                f"{title}"
            )

            continue

        authors = _clean(
            source.get(
                "authors",
                "",
            )
        )

        year = source.get(
            "year"
        )

        doi = _normalize_doi(
            source.get(
                "doi",
                "",
            )
        )

        if (
            not authors
            or not year
            or not doi
        ):

            print(
                f"❌ Rejected incomplete source: "
                f"{title}"
            )

            continue

        source[
            "source_id"
        ] = _generate_source_id(
            doi
        )

        source[
            "doi"
        ] = doi

        source[
            "abstract"
        ] = evidence

        source[
            "evidence_text"
        ] = evidence

        source[
            "evidence_available"
        ] = True

        source[
            "evidence_type"
        ] = "abstract"

        source[
            "evidence_verified"
        ] = True

        source[
            "verified"
        ] = True

        source[
            "verification_level"
        ] = "DOI_METADATA_PLUS_ABSTRACT"

        source[
            "evidence_verification"
        ] = (
            "DOI/publication identity verified "
            "and scholarly abstract retrieved."
        )

        source[
            "evidence_quality"
        ] = "moderate"

        accepted.append(
            source
        )

    return accepted


# ============================================================================
# SOURCE SELECTION
# ============================================================================

def limit_sources(
    sources
):

    def sort_key(
        source
    ):

        citation_count = max(
            source.get(
                "citation_count",
                0,
            )
            or 0,
            source.get(
                "openalex_citation_count",
                0,
            )
            or 0,
        )

        relevance_rank = {
            "strong": 3,
            "moderate": 2,
            "weak": 1,
        }.get(
            source.get(
                "relevance_class",
                "weak",
            ),
            0,
        )

        evidence_provider_count = len(
            source.get(
                "evidence_providers",
                [],
            )
            or []
        )

        concept_score = (
            source.get(
                "concept_coverage",
                {},
            )
            or {}
        ).get(
            "concept_score",
            0,
        )

        return (
            relevance_rank,
            concept_score,
            source.get(
                "relevance_score",
                0,
            ),
            evidence_provider_count,
            citation_count,
        )

    return sorted(
        sources,
        key=sort_key,
        reverse=True,
    )[
        :MAX_EVIDENCE_SOURCES
    ]


# ============================================================================
# SOURCE INDEPENDENCE
# ============================================================================

def validate_independent_sources(
    sources
):

    dois = {
        _normalize_doi(
            source.get(
                "doi",
                "",
            )
        )
        for source in sources
        if _normalize_doi(
            source.get(
                "doi",
                "",
            )
        )
    }

    if len(
        dois
    ) < MIN_ACCEPTED_SOURCES:

        raise RuntimeError(
            "RESEARCH FAILED: fewer than "
            "two distinct DOI-backed sources remain."
        )

    provider_families = set()

    for source in sources:

        providers = tuple(
            sorted(
                set(
                    source.get(
                        "discovery_providers",
                        [],
                    )
                    or []
                )
            )
        )

        if providers:

            provider_families.add(
                providers
            )

    return {
        "distinct_doi_count": len(
            dois
        ),

        "independence_basis": (
            "distinct_normalized_dois"
        ),

        "independent_source_count": len(
            dois
        ),

        "discovery_provider_families": len(
            provider_families
        ),
    }


# ============================================================================
# SOURCE ID VALIDATION
# ============================================================================

def validate_source_ids(
    sources
):

    seen_ids = set()
    seen_dois = set()

    for source in sources:

        title = _clean(
            source.get(
                "title",
                "",
            )
        )

        source_id = _clean(
            source.get(
                "source_id",
                "",
            )
        )

        doi = _normalize_doi(
            source.get(
                "doi",
                "",
            )
        )

        if (
            not source_id
            or not doi
        ):

            raise RuntimeError(
                f"RESEARCH FAILED: source "
                f"'{title}' missing source_id or DOI."
            )

        expected_id = _generate_source_id(
            doi
        )

        if source_id != expected_id:

            raise RuntimeError(
                f"RESEARCH FAILED: source ID "
                f"mismatch for '{title}'."
            )

        if source_id in seen_ids:

            raise RuntimeError(
                "RESEARCH FAILED: duplicate source_id."
            )

        if doi in seen_dois:

            raise RuntimeError(
                "RESEARCH FAILED: duplicate DOI."
            )

        seen_ids.add(
            source_id
        )

        seen_dois.add(
            doi
        )

        for flag in (
            "metadata_verified",
            "evidence_verified",
            "evidence_available",
            "verified",
        ):

            if source.get(
                flag
            ) is not True:

                raise RuntimeError(
                    f"RESEARCH FAILED: source "
                    f"'{title}' does not have "
                    f"{flag}=True."
                )

        evidence = _clean(
            source.get(
                "evidence_text",
                "",
            )
        )

        if len(
            evidence
        ) < MIN_ABSTRACT_CHARACTERS:

            raise RuntimeError(
                f"RESEARCH FAILED: source "
                f"'{title}' has insufficient evidence."
            )

        if source.get(
            "evidence_type"
        ) != "abstract":

            raise RuntimeError(
                f"RESEARCH FAILED: source "
                f"'{title}' does not contain "
                "abstract evidence."
            )

        if not title:

            raise RuntimeError(
                "RESEARCH FAILED: source has no title."
            )

        if not _clean(
            source.get(
                "authors",
                "",
            )
        ):

            raise RuntimeError(
                f"RESEARCH FAILED: source "
                f"'{title}' has no authors."
            )

        if not source.get(
            "year"
        ):

            raise RuntimeError(
                f"RESEARCH FAILED: source "
                f"'{title}' has no publication year."
            )

        if not _clean(
            source.get(
                "url",
                "",
            )
        ):

            source[
                "url"
            ] = (
                f"https://doi.org/{doi}"
            )

        # ------------------------------------------------------------------
        # NEW v10.1 HARD CONCEPT CHECK
        # ------------------------------------------------------------------

        coverage = source.get(
            "concept_coverage",
            {},
        )

        if not isinstance(
            coverage,
            dict,
        ):

            raise RuntimeError(
                f"RESEARCH FAILED: source "
                f"'{title}' has no concept coverage."
            )

        if coverage.get(
            "concept_coverage_pass"
        ) is not True:

            raise RuntimeError(
                f"RESEARCH FAILED: source "
                f"'{title}' failed concept coverage."
            )

        if source.get(
            "intent_pass"
        ) is not True:

            raise RuntimeError(
                f"RESEARCH FAILED: source "
                f"'{title}' failed question relevance."
            )

    return True


# ============================================================================
# FINAL RESEARCH PACKAGE VALIDATION
# ============================================================================

def validate_research_package(
    package
):

    if not isinstance(
        package,
        dict,
    ):

        raise RuntimeError(
            "RESEARCH FAILED: invalid package."
        )

    if package.get(
        "status"
    ) != "VERIFIED":

        raise RuntimeError(
            "RESEARCH FAILED: package is not VERIFIED."
        )

    if package.get(
        "verified"
    ) is not True:

        raise RuntimeError(
            "RESEARCH FAILED: verified flag is false."
        )

    sources = package.get(
        "sources",
        [],
    )

    if not isinstance(
        sources,
        list,
    ):

        raise RuntimeError(
            "RESEARCH FAILED: invalid sources."
        )

    if len(
        sources
    ) < MIN_ACCEPTED_SOURCES:

        raise RuntimeError(
            "RESEARCH FAILED: fewer than two sources."
        )

    if package.get(
        "source_count"
    ) != len(
        sources
    ):

        raise RuntimeError(
            "RESEARCH FAILED: source_count mismatch."
        )

    if package.get(
        "evidence_source_count"
    ) != len(
        sources
    ):

        raise RuntimeError(
            "RESEARCH FAILED: evidence_source_count mismatch."
        )

    validate_source_ids(
        sources
    )

    validate_independent_sources(
        sources
    )

    for source in sources:

        if source.get(
            "relevance_class"
        ) not in {
            "strong",
            "moderate",
        }:

            raise RuntimeError(
                "RESEARCH FAILED: final source "
                f"is not relevant: "
                f"{source.get('title', '')}"
            )

        if source.get(
            "intent_pass"
        ) is not True:

            raise RuntimeError(
                "RESEARCH FAILED: source failed "
                "question relevance."
            )

        coverage = source.get(
            "concept_coverage",
            {},
        )

        if coverage.get(
            "concept_coverage_pass"
        ) is not True:

            raise RuntimeError(
                "RESEARCH FAILED: source failed "
                "final concept coverage."
            )

    return True


# ============================================================================
# RESEARCH FAILURE INFORMATION
# ============================================================================

def _research_failure(
    topic,
    stage,
    message,
    candidate_count=0,
    relevant_count=0,
    evidence_count=0,
):

    return {
        "status": "FAILED",
        "topic": topic,
        "stage": stage,
        "message": message,
        "candidate_count": candidate_count,
        "relevant_count": relevant_count,
        "evidence_count": evidence_count,
    }


# ============================================================================
# MAIN RESEARCH PIPELINE
# ============================================================================

def research_topic(
    topic
):

    global SEMANTIC_RATE_LIMITED

    SEMANTIC_RATE_LIMITED = False

    topic = _clean(
        topic
    )

    if not topic:

        raise RuntimeError(
            "Research topic cannot be empty."
        )

    print("=" * 80)

    print(
        f"🔬 MINT-YT-FACTORY RESEARCH v{VERSION}"
    )

    print("=" * 80)

    print(
        f"Topic: {topic}"
    )

    concepts = _question_concepts(
        topic
    )

    scholarly_queries = build_scholarly_queries(
        topic
    )

    # ----------------------------------------------------------------------
    # QUESTION STRUCTURE
    # ----------------------------------------------------------------------

    print("=" * 80)
    print(
        "🧠 QUESTION CONCEPT STRUCTURE"
    )
    print("=" * 80)

    print(
        "Subject: "
        + (
            ", ".join(
                concepts[
                    "subject"
                ]
            )
            or "none"
        )
    )

    print(
        "Phenomenon: "
        + (
            ", ".join(
                concepts[
                    "phenomenon"
                ]
            )
            or "none"
        )
    )

    print(
        "Condition: "
        + (
            ", ".join(
                concepts[
                    "condition"
                ]
            )
            or "none"
        )
    )

    print(
        "Causal intent: "
        + str(
            concepts[
                "causal_intent"
            ]
        )
    )

    print("=" * 80)
    print(
        "🧠 SCHOLARLY RESEARCH QUERIES"
    )
    print("=" * 80)

    for query in scholarly_queries:

        print(
            f"   • {query}"
        )

    # ----------------------------------------------------------------------
    # DISCOVERY
    # ----------------------------------------------------------------------

    all_sources = []

    for search_function in (
        search_crossref,
        search_semantic_scholar,
        search_openalex,
    ):

        try:

            all_sources.extend(
                search_function(
                    topic
                )
            )

        except Exception as error:

            print(
                f"⚠️ {search_function.__name__} "
                f"failed: {error}"
            )

    candidates = deduplicate_sources(
        all_sources
    )

    print(
        f"Unique candidates: "
        f"{len(candidates)}"
    )

    if not candidates:

        raise RuntimeError(
            "RESEARCH FAILED: no research "
            "candidates found."
        )

    # ----------------------------------------------------------------------
    # DOI FILTER
    # ----------------------------------------------------------------------

    doi_candidates = []

    for source in candidates:

        doi = _normalize_doi(
            source.get(
                "doi",
                "",
            )
        )

        if not doi:
            continue

        source[
            "doi"
        ] = doi

        source[
            "source_id"
        ] = _generate_source_id(
            doi
        )

        doi_candidates.append(
            source
        )

    print(
        f"DOI-eligible candidates: "
        f"{len(doi_candidates)}"
    )

    if not doi_candidates:

        raise RuntimeError(
            "RESEARCH FAILED: no DOI candidates."
        )

    # ----------------------------------------------------------------------
    # FIRST CONCEPT RELEVANCE PASS
    # ----------------------------------------------------------------------

    relevant = relevance_filter(
        topic,
        doi_candidates,
        label=(
            "STRICT QUESTION CONCEPT COVERAGE FILTER"
        ),
    )

    if not relevant:

        raise RuntimeError(
            "RESEARCH FAILED: no sufficiently "
            "relevant concept-covered sources found."
        )

    relevant = sorted(
        relevant,
        key=lambda source: (
            source.get(
                "concept_coverage",
                {},
            ).get(
                "concept_score",
                0,
            ),

            source.get(
                "relevance_score",
                0,
            ),

            len(
                source.get(
                    "abstract",
                    "",
                )
            ),

            source.get(
                "citation_count",
                0,
            )
            or 0,
        ),
        reverse=True,
    )[
        :MAX_VERIFICATION_CANDIDATES
    ]

    # ----------------------------------------------------------------------
    # IDENTITY VERIFICATION
    # ----------------------------------------------------------------------

    print("=" * 80)

    print(
        "🧪 VERIFYING DOI + PUBLICATION IDENTITY"
    )

    print("=" * 80)

    verified_metadata = []

    for index, source in enumerate(
        relevant,
        start=1,
    ):

        print(
            f"Checking source {index}/"
            f"{len(relevant)}: "
            f"{source.get('title', '')}"
        )

        verified = verify_source_identity(
            source
        )

        if verified:

            print(
                "✅ DOI + IDENTITY VERIFIED"
            )

            verified_metadata.append(
                source
            )

        else:

            print(
                "❌ IDENTITY NOT VERIFIED"
            )

    print(
        "DOI/identity-verified sources: "
        f"{len(verified_metadata)}"
    )

    if not verified_metadata:

        raise RuntimeError(
            "RESEARCH FAILED: no DOI-verified "
            "sources remained."
        )

    # ----------------------------------------------------------------------
    # EVIDENCE
    # ----------------------------------------------------------------------

    verified_metadata = enrich_sources(
        verified_metadata
    )

    evidence_sources = mark_evidence_verified(
        verified_metadata
    )

    print(
        f"Evidence-backed sources: "
        f"{len(evidence_sources)}"
    )

    if not evidence_sources:

        raise RuntimeError(
            "RESEARCH FAILED: no evidence-backed "
            "sources remained."
        )

    # ----------------------------------------------------------------------
    # FINAL CONCEPT RELEVANCE PASS
    #
    # IMPORTANT:
    #
    # This pass happens AFTER the abstract is available.
    #
    # Therefore the system can determine whether the actual
    # evidence text covers the subject / phenomenon / condition.
    # ----------------------------------------------------------------------

    evidence_sources = relevance_filter(
        topic,
        evidence_sources,
        label=(
            "FINAL EVIDENCE CONCEPT COVERAGE CHECK"
        ),
    )

    evidence_sources = [
        source
        for source in evidence_sources
        if (
            source.get(
                "metadata_verified"
            ) is True

            and source.get(
                "evidence_verified"
            ) is True

            and source.get(
                "verified"
            ) is True

            and source.get(
                "concept_coverage",
                {},
            ).get(
                "concept_coverage_pass"
            ) is True
        )
    ]

    evidence_sources = limit_sources(
        evidence_sources
    )

    print(
        f"Final concept-covered sources: "
        f"{len(evidence_sources)}"
    )

    if (
        len(evidence_sources)
        < MIN_ACCEPTED_SOURCES
    ):

        raise RuntimeError(
            "RESEARCH FAILED: fewer than two "
            "evidence-backed concept-relevant "
            "sources remained."
        )

    # ----------------------------------------------------------------------
    # INDEPENDENCE
    # ----------------------------------------------------------------------

    diversity = (
        validate_independent_sources(
            evidence_sources
        )
    )

    validate_source_ids(
        evidence_sources
    )

    # ----------------------------------------------------------------------
    # PACKAGE
    # ----------------------------------------------------------------------

    package = {
        "research_version": VERSION,

        "topic": topic,

        "status": "VERIFIED",

        "verified": True,

        "verified_at": int(
            time.time()
        ),

        "research_vocabulary": {

            "topic_terms": sorted(
                concepts[
                    "topic_terms"
                ]
            ),

            "expanded_terms": sorted(
                concepts[
                    "expanded_terms"
                ]
            ),

            "concept_terms": sorted(
                concepts[
                    "concept_terms"
                ]
            ),

            "question_phrases": concepts[
                "question_phrases"
            ],

            "subject": concepts[
                "subject"
            ],

            "phenomenon": concepts[
                "phenomenon"
            ],

            "condition": concepts[
                "condition"
            ],

            "causal_intent": concepts[
                "causal_intent"
            ],

            "scholarly_queries": scholarly_queries,

            "question_intents": (
                ["cause"]
                if concepts[
                    "causal_intent"
                ]
                else []
            ),

            "mechanism_terms": [],

            "event_terms": concepts[
                "condition"
            ],

            "target_terms": concepts[
                "subject"
            ],

            "negative_topic_drift_terms": [],
        },

        "verification_policy": {

            "minimum_sources": (
                MIN_ACCEPTED_SOURCES
            ),

            "metadata_required": True,

            "doi_required": True,

            "abstract_required": True,

            "minimum_abstract_characters": (
                MIN_ABSTRACT_CHARACTERS
            ),

            "metadata_only_sources_allowed": False,

            "evidence_verification_required": True,

            "strict_topic_relevance": True,

            "question_intent_relevance": True,

            "mechanism_relevance_required": True,

            "final_relevance_recheck": True,

            "full_text_required": False,

            "abstract_is_full_text": False,

            "identity_verification_required": True,

            "identity_verification_providers": [
                "Crossref",
                "OpenAlex",
                "Semantic Scholar",
            ],

            "title_identity_similarity_minimum": (
                TITLE_SIMILARITY_MINIMUM
            ),

            "authoritative_source_id_required": True,

            "source_id_algorithm": (
                "sha256(normalized_doi)[:12]"
            ),

            "gemini_used_for_evidence": False,

            "evidence_must_be_retrieved": True,

            "distinct_doi_sources_required": True,

            "metadata_is_evidence": False,

            "semantic_scholar_rate_limit_circuit_breaker": True,

            "provider_aware_verification_order": True,

            "resilient_evidence_fallback": True,

            "returned_doi_required_for_identity": True,

            "dynamic_topic_vocabulary": True,

            "deterministic_query_expansion": True,

            "subject_only_matching_allowed": False,

            "topic_drift_protection": True,

            "question_mechanism_protection": True,

            "hardcoded_subject_rules": False,

            "concept_aware_query_generation": True,

            "surface_word_overlap_is_not_sole_signal": True,

            # --------------------------------------------------------------
            # v10.1
            # --------------------------------------------------------------

            "question_concept_structure": True,

            "subject_concept_required": (
                REQUIRE_SUBJECT
            ),

            "phenomenon_concept_required": (
                REQUIRE_PHENOMENON
            ),

            "condition_concept_required_for_causal_questions": (
                REQUIRE_CONDITION_FOR_CAUSAL_QUESTIONS
            ),

            "concept_coverage_required": True,

            "minimum_concept_score": (
                MIN_CONCEPT_SCORE
            ),

            "final_evidence_concept_recheck": True,

            "causal_concept_validation": True,

            "phrase_level_matching": True,

            "multiword_concepts_are_atomic": True,
        },

        "source_count": len(
            evidence_sources
        ),

        "evidence_source_count": len(
            evidence_sources
        ),

        "source_diversity": diversity,

        "sources": evidence_sources,
    }

    # ----------------------------------------------------------------------
    # FINAL PACKAGE VALIDATION
    # ----------------------------------------------------------------------

    validate_research_package(
        package
    )

    # ----------------------------------------------------------------------
    # LOG
    # ----------------------------------------------------------------------

    print("=" * 80)

    print(
        "✅ RESEARCH VERIFIED"
    )

    print("=" * 80)

    for index, source in enumerate(
        evidence_sources,
        start=1,
    ):

        coverage = source.get(
            "concept_coverage",
            {},
        )

        print(
            f"{index}. "
            f"{source['title']}"
        )

        print(
            f"   DOI: "
            f"{source['doi']}"
        )

        print(
            f"   Source ID: "
            f"{source['source_id']}"
        )

        print(
            "   Relevance: "
            f"{source.get('relevance_class', '')} "
            f"({source.get('relevance_score', 0)})"
        )

        print(
            "   Concept score: "
            f"{coverage.get('concept_score', 0)}"
        )

        print(
            "   Subject: "
            f"{coverage.get('subject_pass', False)}"
        )

        print(
            "   Phenomenon: "
            f"{coverage.get('phenomenon_pass', False)}"
        )

        print(
            "   Condition: "
            f"{coverage.get('condition_pass', False)}"
        )

        print(
            "   Causal relevance: "
            f"{coverage.get('causal_relevance', False)}"
        )

        print(
            "   Evidence: "
            f"{source.get('evidence_source', '')}"
        )

    print("=" * 80)

    return package


# ============================================================================
# SAVE
# ============================================================================

def save_research(
    research,
    output_path,
):

    directory = os.path.dirname(
        output_path
    )

    if directory:

        os.makedirs(
            directory,
            exist_ok=True,
        )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            research,
            file,
            indent=2,
            ensure_ascii=False,
        )

    return output_path


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":

    if len(
        sys.argv
    ) < 2:

        print(
            'Usage: python research.py '
            '"your topic"'
        )

        sys.exit(1)

    topic = " ".join(
        sys.argv[1:]
    )

    try:

        result = research_topic(
            topic
        )

        output = os.path.join(
            "output",
            "research_test.json",
        )

        save_research(
            result,
            output,
        )

        print("=" * 80)

        print(
            "📄 RESEARCH SAVED"
        )

        print("=" * 80)

        print(
            output
        )

    except Exception as error:

        print("=" * 80)

        print(
            "❌ RESEARCH FAILED"
        )

        print("=" * 80)

        print(
            error
        )

        sys.exit(1)