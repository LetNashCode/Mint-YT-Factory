"""
research.py
Mint-YT-Factory

Version 11.0

RESEARCH-FIRST SCIENTIFIC EVIDENCE ENGINE

Pipeline:

    topics.py
        ↓
    Scientific research discovery
        ↓
    Multi-source scholarly search
        ↓
    DOI verification
        ↓
    Evidence retrieval
        ↓
    Scientific relevance scoring
        ↓
    Independent-source verification
        ↓
    VERIFIED research package

Core rule:

A topic is usable only when credible scientific/technical
literature can actually support the explanation.

This module does NOT use Gemini or any LLM to decide whether
evidence exists.

LLMs may generate the topic elsewhere, but this module acts as
the deterministic scientific gatekeeper.

The system prefers:

    - peer-reviewed research
    - scientific journals
    - university research
    - government/scientific institutions
    - established technical literature

The system rejects:

    - generic fact pages
    - opinion pieces
    - philosophical topics
    - vague claims
    - weak keyword matches
    - sources that only mention the subject
    - sources without retrievable evidence
    - sources whose DOI identity cannot be verified

IMPORTANT:

An abstract is evidence that a paper discusses a subject.
It is NOT treated as proof that every claim in the final video
is established.

The downstream script-generation layer must stay within the
verified evidence package.
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
# VERSION
# ============================================================================

VERSION = "11.0"


# ============================================================================
# PROVIDERS
# ============================================================================

CROSSREF_URL = "https://api.crossref.org/v1/works"

OPENALEX_URL = "https://api.openalex.org/works"

SEMANTIC_SEARCH_URL = (
    "https://api.semanticscholar.org/graph/v1/paper/search"
)

SEMANTIC_PAPER_URL = (
    "https://api.semanticscholar.org/graph/v1/paper"
)


# ============================================================================
# CONFIGURATION
# ============================================================================

TIMEOUT = 30

MAX_CROSSREF_RESULTS = 12
MAX_OPENALEX_RESULTS = 12
MAX_SEMANTIC_RESULTS = 8

MAX_VERIFICATION_CANDIDATES = 24
MAX_EVIDENCE_SOURCES = 5

MIN_ACCEPTED_SOURCES = 2

MIN_ABSTRACT_CHARACTERS = 180

MAX_EVIDENCE_TEXT_CHARACTERS = 14000

TITLE_SIMILARITY_MINIMUM = 0.55

MIN_SCIENTIFIC_SCORE = 12

REQUIRE_SUBJECT = True
REQUIRE_PHENOMENON = True
REQUIRE_CAUSAL_SUPPORT = True

SEMANTIC_RETRIES = 0

USER_AGENT = (
    f"Mint-YT-Factory/{VERSION} "
    "(research verification)"
)


# ============================================================================
# HTTP SESSION
# ============================================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
)

SEMANTIC_RATE_LIMITED = False


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
            "Semantic Scholar skipped because "
            "it was rate limited earlier."
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

                if provider == "Semantic Scholar":

                    SEMANTIC_RATE_LIMITED = True

                    raise RuntimeError(
                        "Semantic Scholar HTTP 429."
                    )

                retry_after = response.headers.get(
                    "Retry-After"
                )

                try:
                    delay = float(
                        retry_after
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    delay = backoff * (
                        attempt + 1
                    )

                if attempt < retries:

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

                time.sleep(
                    backoff * (
                        attempt + 1
                    )
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

                time.sleep(
                    backoff * (
                        attempt + 1
                    )
                )

                continue

            raise last_error

    raise RuntimeError(
        "HTTP request failed."
    )


# ============================================================================
# TEXT
# ============================================================================

def _clean(value):

    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def _clean_abstract(value):

    value = _clean(
        value
    )

    if not value:
        return ""

    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    return _clean(
        value
    )


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
    first,
    second,
):

    a = _title_tokens(
        first
    )

    b = _title_tokens(
        second
    )

    if not a or not b:
        return 0.0

    return len(
        a & b
    ) / len(
        a | b
    )


def _source_id(doi):

    doi = _normalize_doi(
        doi
    )

    if not doi:
        raise RuntimeError(
            "Cannot create source ID without DOI."
        )

    return (
        "doi_"
        + hashlib.sha256(
            doi.encode("utf-8")
        ).hexdigest()[:12]
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
    "as",
    "at",
    "by",
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
    "human",
    "humans",
    "thing",
    "things",
    "cause",
    "causes",
    "causing",
}


# ============================================================================
# TOKENIZATION
# ============================================================================

def _tokens(text):

    return [
        token
        for token in re.findall(
            r"[a-z0-9]+",
            _clean(text).lower(),
        )
        if (
            len(token) >= 3
            and token not in STOPWORDS
        )
    ]


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


def _term_match(
    term,
    text,
):

    term = _clean(
        term
    ).lower()

    text = _clean(
        text
    ).lower()

    if not term:
        return False

    if " " in term:
        return term in text

    for variant in _stem_variants(
        term
    ):

        if re.search(
            rf"\b{re.escape(variant)}\w*\b",
            text,
        ):
            return True

    return False


def _matched_terms(
    terms,
    text,
):

    return {
        term
        for term in terms
        if _term_match(
            term,
            text,
        )
    }


# ============================================================================
# QUESTION ANALYSIS
# ============================================================================

def _extract_question_terms(
    topic
):

    words = _tokens(
        topic
    )

    return list(
        dict.fromkeys(
            words
        )
    )


def _extract_subject(
    topic
):

    lowered = _clean(
        topic
    ).lower()

    words = _extract_question_terms(
        topic
    )

    # Remove common causal/condition vocabulary.
    excluded = {
        "slow",
        "slows",
        "slowing",
        "speed",
        "speeding",
        "faster",
        "faster",
        "starting",
        "stopping",
        "stopped",
        "turning",
        "during",
        "while",
        "after",
        "before",
        "cold",
        "hot",
    }

    words = [
        word
        for word in words
        if word not in excluded
    ]

    # Try to isolate the object before the main phenomenon.
    for separator in (
        " make ",
        " makes ",
        " cause ",
        " causes ",
        " sound ",
        " sounds ",
        " become ",
        " becomes ",
        " feel ",
        " feels ",
        " look ",
        " looks ",
    ):

        if separator in lowered:

            left = lowered.split(
                separator,
                1,
            )[0]

            left_tokens = [
                token
                for token in _tokens(
                    left
                )
                if token not in excluded
            ]

            if left_tokens:

                return [
                    " ".join(
                        left_tokens
                    ),
                    *left_tokens,
                ]

    if len(words) >= 2:

        return [
            " ".join(
                words[:2]
            ),
            *words,
        ]

    return words


def _extract_phenomenon(
    topic
):

    lowered = _clean(
        topic
    ).lower()

    candidates = [
        "ticking sound",
        "ticking sounds",
        "clicking sound",
        "clicking sounds",
        "buzzing sound",
        "buzzing sounds",
        "humming sound",
        "humming sounds",
        "rattling sound",
        "rattling sounds",
        "sound",
        "sounds",
        "noise",
        "noises",
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
        "pop",
        "popping",
        "fade",
        "fading",
        "freeze",
        "freezing",
        "melt",
        "melting",
        "expand",
        "expanding",
        "shrink",
        "shrinking",
        "float",
        "floating",
        "sink",
        "sinking",
        "stick",
        "sticking",
        "echo",
        "echoes",
        "shadow",
        "shadows",
    ]

    found = []

    for candidate in candidates:

        if candidate in lowered:

            found.append(
                candidate
            )

    if found:
        return list(
            dict.fromkeys(
                found
            )
        )

    # Fallback: use the latter part of the question as
    # the observable event.
    words = _extract_question_terms(
        topic
    )

    if len(words) >= 2:

        return [
            " ".join(
                words[-2:]
            )
        ]

    return words


def _extract_conditions(
    topic
):

    lowered = _clean(
        topic
    ).lower()

    patterns = [
        r"\bas (.+?) slows? down\b",
        r"\bwhile (.+?) slows? down\b",
        r"\bwhen (.+?) slows? down\b",
        r"\bduring (.+?) slowing down\b",
        r"\bwhile (.+?) speeding up\b",
        r"\bwhen (.+?) speeds up\b",
        r"\bwhen (.+?) stops?\b",
        r"\bwhile (.+?) stops?\b",
        r"\bwhen (.+?) starts?\b",
        r"\bwhile (.+?) starts?\b",
        r"\bafter (.+?) stops?\b",
        r"\bbefore (.+?) stops?\b",
        r"\bwhen (.+?) turns on\b",
        r"\bwhen (.+?) turns off\b",
        r"\bas (.+?) heats up\b",
        r"\bas (.+?) cools down\b",
        r"\bwhen (.+?) freezes\b",
        r"\bwhen (.+?) melts\b",
    ]

    conditions = []

    for pattern in patterns:

        match = re.search(
            pattern,
            lowered,
        )

        if match:

            phrase = _clean(
                match.group(0)
            )

            if phrase:
                conditions.append(
                    phrase
                )

    transition_terms = [
        "slow down",
        "slowing down",
        "speeds up",
        "speeding up",
        "accelerating",
        "decelerating",
        "starting",
        "stopping",
        "stopped",
        "turning on",
        "turning off",
        "heating up",
        "cooling down",
        "freezing",
        "melting",
    ]

    for term in transition_terms:

        if term in lowered:
            conditions.append(
                term
            )

    return list(
        dict.fromkeys(
            conditions
        )
    )


def _question_structure(
    topic
):

    topic = _clean(
        topic
    )

    lowered = topic.lower()

    causal = (
        lowered.startswith("why ")
        or lowered.startswith("how ")
        or "what causes" in lowered
        or "what makes" in lowered
        or "why does" in lowered
        or "why do" in lowered
    )

    subject = _extract_subject(
        topic
    )

    phenomenon = _extract_phenomenon(
        topic
    )

    condition = _extract_conditions(
        topic
    )

    terms = _extract_question_terms(
        topic
    )

    queries = [
        topic
    ]

    queries.extend(
        subject[:3]
    )

    queries.extend(
        phenomenon[:3]
    )

    for s in subject[:2]:

        for p in phenomenon[:2]:

            queries.append(
                f"{s} {p}"
            )

            queries.append(
                f"{s} {p} mechanism"
            )

            queries.append(
                f"{s} {p} cause"
            )

    for c in condition[:2]:

        for s in subject[:2]:

            for p in phenomenon[:2]:

                queries.append(
                    f"{s} {p} {c}"
                )

    final_queries = []

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

        final_queries.append(
            query
        )

    return {
        "subject": list(
            dict.fromkeys(
                subject
            )
        ),
        "phenomenon": list(
            dict.fromkeys(
                phenomenon
            )
        ),
        "condition": list(
            dict.fromkeys(
                condition
            )
        ),
        "topic_terms": terms,
        "causal_intent": causal,
        "queries": final_queries[:15],
    }


def _question_concepts(
    topic
):

    structure = _question_structure(
        topic
    )

    return {
        "subject": structure[
            "subject"
        ],
        "phenomenon": structure[
            "phenomenon"
        ],
        "condition": structure[
            "condition"
        ],
        "topic_terms": structure[
            "topic_terms"
        ],
        "causal_intent": structure[
            "causal_intent"
        ],
        "question_phrases": structure[
            "queries"
        ],
        "concept_terms": list(
            dict.fromkeys(
                structure[
                    "topic_terms"
                ]
                + structure[
                    "subject"
                ]
                + structure[
                    "phenomenon"
                ]
                + structure[
                    "condition"
                ]
            )
        ),
    }


# ============================================================================
# SCHOLARLY QUERIES
# ============================================================================

def build_scholarly_queries(
    topic
):

    return _question_concepts(
        topic
    )[
        "question_phrases"
    ]


# ============================================================================
# EVIDENCE HELPERS
# ============================================================================

def _record_evidence(
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
        record.get(
            "provider"
        ) == provider
        for record in records
        if isinstance(
            record,
            dict,
        )
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


def _package_evidence(
    source
):

    abstract = _clean_abstract(
        source.get(
            "abstract",
            "",
        )
    )

    if len(
        abstract
    ) >= MIN_ABSTRACT_CHARACTERS:

        source[
            "evidence_available"
        ] = True

        source[
            "evidence_type"
        ] = "abstract"

        source[
            "evidence_text"
        ] = abstract[
            :MAX_EVIDENCE_TEXT_CHARACTERS
        ]

        source[
            "evidence_quality"
        ] = "moderate"

        source[
            "evidence_notes"
        ] = (
            "Scholarly abstract retrieved. "
            "The abstract is evidence of what the "
            "paper discusses, not a substitute for "
            "the full paper."
        )

    else:

        source[
            "evidence_available"
        ] = False

        source[
            "evidence_type"
        ] = "metadata_only"

        source[
            "evidence_text"
        ] = ""

        source[
            "evidence_quality"
        ] = "none"

    return source


# ============================================================================
# CROSSREF
# ============================================================================

def _crossref_authors(
    item
):

    names = []

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
            names.append(
                name
            )

    return ", ".join(
        names
    )


def _crossref_year(
    item
):

    for field in (
        "published-print",
        "published-online",
        "published",
        "issued",
        "created",
    ):

        value = item.get(
            field,
            {},
        )

        parts = (
            value.get(
                "date-parts",
                [],
            )
            if isinstance(
                value,
                dict,
            )
            else []
        )

        if parts and parts[0]:

            try:
                return int(
                    parts[0][0]
                )
            except Exception:
                pass

    return None


def search_crossref(
    topic
):

    print("=" * 80)
    print("🔎 CROSSREF")
    print("=" * 80)

    results = []
    seen = set()

    for query in build_scholarly_queries(
        topic
    ):

        try:

            data = _get(
                CROSSREF_URL,
                {
                    "query.bibliographic": query,
                    "rows": MAX_CROSSREF_RESULTS,
                    "select": (
                        "DOI,title,author,container-title,"
                        "publisher,type,published,published-print,"
                        "published-online,URL,abstract"
                    ),
                },
                provider="Crossref",
            )

        except Exception as error:

            print(
                f"⚠️ Crossref failed: {error}"
            )

            continue

        for item in data.get(
            "message",
            {}
        ).get(
            "items",
            [],
        ):

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
                "discovery_provider": "Crossref",
                "discovery_providers": [
                    "Crossref"
                ],
                "source_databases": [
                    "Crossref"
                ],
                "title": title,
                "authors": _crossref_authors(
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
                "year": _crossref_year(
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
                    or f"https://doi.org/{doi}"
                ),
                "publication_type": _clean(
                    item.get(
                        "type",
                        "",
                    )
                ),
                "abstract": abstract,
                "citation_count": 0,
                "metadata_verified": False,
                "evidence_verified": False,
                "verified": False,
                "evidence_providers": [],
            }

            if abstract:

                _record_evidence(
                    source,
                    "Crossref",
                    abstract,
                )

            results.append(
                _package_evidence(
                    source
                )
            )

    print(
        f"Crossref candidates: {len(results)}"
    )

    return results


# ============================================================================
# OPENALEX
# ============================================================================

def _openalex_abstract(
    inverted
):

    if not isinstance(
        inverted,
        dict,
    ):
        return ""

    words = []

    for word, positions in inverted.items():

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
                pass

    words.sort(
        key=lambda item: item[0]
    )

    return _clean_abstract(
        " ".join(
            word
            for _, word in words
        )
    )


def search_openalex(
    topic
):

    print("=" * 80)
    print("🔎 OPENALEX")
    print("=" * 80)

    results = []
    seen = set()

    for query in build_scholarly_queries(
        topic
    ):

        try:

            data = _get(
                OPENALEX_URL,
                {
                    "search": query,
                    "per-page": MAX_OPENALEX_RESULTS,
                },
                provider="OpenAlex",
            )

        except Exception as error:

            print(
                f"⚠️ OpenAlex failed: {error}"
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

            abstract = _openalex_abstract(
                item.get(
                    "abstract_inverted_index"
                )
            )

            source = {
                "source_database": "OpenAlex",
                "discovery_provider": "OpenAlex",
                "discovery_providers": [
                    "OpenAlex"
                ],
                "source_databases": [
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
                "metadata_verified": False,
                "evidence_verified": False,
                "verified": False,
                "evidence_providers": [],
            }

            if abstract:

                _record_evidence(
                    source,
                    "OpenAlex",
                    abstract,
                )

            results.append(
                _package_evidence(
                    source
                )
            )

    print(
        f"OpenAlex candidates: {len(results)}"
    )

    return results


# ============================================================================
# SEMANTIC SCHOLAR
# ============================================================================

def _semantic_authors(
    item
):

    names = []

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
            names.append(
                name
            )

    return ", ".join(
        names
    )


def search_semantic_scholar(
    topic
):

    global SEMANTIC_RATE_LIMITED

    print("=" * 80)
    print("🔎 SEMANTIC SCHOLAR")
    print("=" * 80)

    if SEMANTIC_RATE_LIMITED:

        print(
            "⚠️ Semantic Scholar unavailable; skipping."
        )

        return []

    results = []
    seen = set()

    for query in build_scholarly_queries(
        topic
    ):

        if SEMANTIC_RATE_LIMITED:
            break

        try:

            data = _get(
                SEMANTIC_SEARCH_URL,
                {
                    "query": query,
                    "limit": MAX_SEMANTIC_RESULTS,
                    "fields": (
                        "title,authors,year,abstract,"
                        "url,externalIds,publicationTypes,"
                        "venue,citationCount"
                    ),
                },
                retries=SEMANTIC_RETRIES,
                provider="Semantic Scholar",
            )

        except Exception as error:

            print(
                f"⚠️ Semantic Scholar failed: {error}"
            )

            continue

        for item in data.get(
            "data",
            [],
        ):

            title = _clean(
                item.get(
                    "title",
                    "",
                )
            )

            ids = (
                item.get(
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
                item.get(
                    "abstract",
                    "",
                )
            )

            publication_types = (
                item.get(
                    "publicationTypes",
                    [],
                )
                or []
            )

            source = {
                "source_database": "Semantic Scholar",
                "discovery_provider": "Semantic Scholar",
                "discovery_providers": [
                    "Semantic Scholar"
                ],
                "source_databases": [
                    "Semantic Scholar"
                ],
                "title": title,
                "authors": _semantic_authors(
                    item
                ),
                "journal": _clean(
                    item.get(
                        "venue",
                        "",
                    )
                ),
                "publisher": "",
                "year": item.get(
                    "year"
                ),
                "doi": doi,
                "url": (
                    f"https://doi.org/{doi}"
                ),
                "semantic_scholar_url": _clean(
                    item.get(
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
                    item.get(
                        "citationCount",
                        0,
                    )
                    or 0
                ),
                "metadata_verified": False,
                "evidence_verified": False,
                "verified": False,
                "evidence_providers": [],
            }

            if abstract:

                _record_evidence(
                    source,
                    "Semantic Scholar",
                    abstract,
                )

            results.append(
                _package_evidence(
                    source
                )
            )

    print(
        f"Semantic Scholar candidates: "
        f"{len(results)}"
    )

    return results


# ============================================================================
# DEDUPLICATION
# ============================================================================

def deduplicate_sources(
    sources
):

    by_doi = {}

    for source in sources:

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

        if doi not in by_doi:

            by_doi[
                doi
            ] = source

            continue

        existing = by_doi[
            doi
        ]

        existing[
            "source_databases"
        ] = sorted(
            set(
                existing.get(
                    "source_databases",
                    [],
                )
                + source.get(
                    "source_databases",
                    [],
                )
            )
        )

        existing[
            "discovery_providers"
        ] = sorted(
            set(
                existing.get(
                    "discovery_providers",
                    [],
                )
                + source.get(
                    "discovery_providers",
                    [],
                )
            )
        )

        providers = set(
            existing.get(
                "evidence_providers",
                [],
            )
        )

        providers.update(
            source.get(
                "evidence_providers",
                [],
            )
        )

        existing[
            "evidence_providers"
        ] = sorted(
            providers
        )

        current_abstract = _clean_abstract(
            existing.get(
                "abstract",
                "",
            )
        )

        new_abstract = _clean_abstract(
            source.get(
                "abstract",
                "",
            )
        )

        if len(
            new_abstract
        ) > len(
            current_abstract
        ):

            existing[
                "abstract"
            ] = new_abstract

    return list(
        by_doi.values()
    )


# ============================================================================
# CONCEPT MATCHING
# ============================================================================

def _phrase_match(
    phrase,
    text,
):

    phrase = _clean(
        phrase
    ).lower()

    text = _clean(
        text
    ).lower()

    if not phrase:
        return False

    if phrase in text:
        return True

    words = _tokens(
        phrase
    )

    if len(words) < 2:
        return _term_match(
            phrase,
            text,
        )

    return all(
        _term_match(
            word,
            text,
        )
        for word in words
    )


def _any_phrase_match(
    phrases,
    text,
):

    return [
        phrase
        for phrase in phrases
        if _phrase_match(
            phrase,
            text,
        )
    ]


# ============================================================================
# SCIENTIFIC RELEVANCE
# ============================================================================

def _score_source(
    topic,
    source,
):

    concepts = _question_concepts(
        topic
    )

    title = _clean(
        source.get(
            "title",
            "",
        )
    )

    abstract = _clean_abstract(
        source.get(
            "evidence_text",
            "",
        )
        or source.get(
            "abstract",
            "",
        )
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

    causal = concepts[
        "causal_intent"
    ]

    subject_title = _any_phrase_match(
        subject,
        title,
    )

    subject_evidence = _any_phrase_match(
        subject,
        abstract,
    )

    phenomenon_title = _any_phrase_match(
        phenomenon,
        title,
    )

    phenomenon_evidence = _any_phrase_match(
        phenomenon,
        abstract,
    )

    condition_title = _any_phrase_match(
        condition,
        title,
    )

    condition_evidence = _any_phrase_match(
        condition,
        abstract,
    )

    topic_matches_title = _matched_terms(
        set(
            concepts[
                "topic_terms"
            ]
        ),
        title,
    )

    topic_matches_evidence = _matched_terms(
        set(
            concepts[
                "topic_terms"
            ]
        ),
        abstract,
    )

    score = 0

    # Subject.
    if subject_evidence:
        score += 6
    elif subject_title:
        score += 3

    # Phenomenon.
    if phenomenon_evidence:
        score += 6
    elif phenomenon_title:
        score += 3

    # Condition.
    if condition_evidence:
        score += 4
    elif condition_title:
        score += 2

    # General conceptual overlap.
    score += min(
        3,
        len(
            topic_matches_title
        ),
    )

    score += min(
        5,
        len(
            topic_matches_evidence
        ),
    )

    # Causal support.
    causal_support = False

    if causal:

        if (
            subject_evidence
            and phenomenon_evidence
        ):
            causal_support = True
            score += 4

        elif (
            subject_title
            and phenomenon_evidence
        ):
            causal_support = True
            score += 2

    else:

        causal_support = True

    # Scientific mechanism language.
    mechanism_terms = {
        "mechanism",
        "mechanisms",
        "effect",
        "effects",
        "process",
        "processes",
        "interaction",
        "interactions",
        "physical",
        "physiological",
        "biological",
        "chemical",
        "mechanical",
        "thermal",
        "acoustic",
        "optical",
        "experimental",
        "experiment",
        "observed",
        "observation",
        "results",
        "measured",
        "measurement",
        "cause",
        "caused",
        "influence",
        "response",
    }

    mechanism_matches = _matched_terms(
        mechanism_terms,
        abstract,
    )

    if mechanism_matches:
        score += min(
            4,
            len(
                mechanism_matches
            ),
        )

    # Evidence quality.
    if len(abstract) >= 500:
        score += 2

    if len(
        source.get(
            "evidence_providers",
            [],
        )
        or []
    ) >= 2:
        score += 2

    # Hard gates.
    subject_pass = (
        bool(
            subject_evidence
            or subject_title
        )
        if subject
        else True
    )

    phenomenon_pass = (
        bool(
            phenomenon_evidence
            or phenomenon_title
        )
        if phenomenon
        else True
    )

    # For causal questions, require the actual evidence to
    # contain both the subject and phenomenon whenever possible.
    causal_pass = (
        causal_support
        if causal
        else True
    )

    condition_required = bool(
        condition
        and causal
    )

    # Condition is deliberately softer than the subject/phenomenon.
    # A paper can explain the same mechanism without repeating the
    # exact everyday wording used by the question.
    condition_pass = (
        bool(
            condition_evidence
            or condition_title
        )
        if condition_required
        else True
    )

    hard_pass = (
        subject_pass
        and phenomenon_pass
        and causal_pass
        and (
            condition_pass
            or not condition_required
        )
        and score >= MIN_SCIENTIFIC_SCORE
    )

    if hard_pass:

        if score >= 24:
            relevance_class = "strong"
        elif score >= 17:
            relevance_class = "moderate"
        else:
            relevance_class = "acceptable"

    else:

        relevance_class = "weak"

    reasons = []

    if not subject_pass:
        reasons.append(
            "subject_not_supported"
        )

    if not phenomenon_pass:
        reasons.append(
            "phenomenon_not_supported"
        )

    if causal and not causal_pass:
        reasons.append(
            "causal_support_missing"
        )

    if (
        condition_required
        and not condition_pass
    ):
        reasons.append(
            "condition_not_supported"
        )

    if score < MIN_SCIENTIFIC_SCORE:
        reasons.append(
            "scientific_score_below_threshold"
        )

    return {
        "scientific_score": score,
        "relevance_score": score,
        "relevance_class": relevance_class,
        "subject_pass": subject_pass,
        "phenomenon_pass": phenomenon_pass,
        "condition_pass": condition_pass,
        "causal_support": causal_support,
        "causal_pass": causal_pass,
        "subject_title_matches": subject_title,
        "subject_evidence_matches": subject_evidence,
        "phenomenon_title_matches": phenomenon_title,
        "phenomenon_evidence_matches": phenomenon_evidence,
        "condition_title_matches": condition_title,
        "condition_evidence_matches": condition_evidence,
        "topic_title_matches": sorted(
            topic_matches_title
        ),
        "topic_evidence_matches": sorted(
            topic_matches_evidence
        ),
        "mechanism_matches": sorted(
            mechanism_matches
        ),
        "condition_required": condition_required,
        "scientific_relevance_pass": hard_pass,
        "concept_coverage_pass": hard_pass,
        "intent_pass": hard_pass,
        "rejection_reasons": reasons,
    }


def apply_relevance(
    topic,
    sources,
):

    accepted = []

    print("=" * 80)
    print("🧪 SCIENTIFIC RELEVANCE FILTER")
    print("=" * 80)

    concepts = _question_concepts(
        topic
    )

    print(
        "Subject: "
        + ", ".join(
            concepts[
                "subject"
            ]
        )
    )

    print(
        "Phenomenon: "
        + ", ".join(
            concepts[
                "phenomenon"
            ]
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

    for source in sources:

        result = _score_source(
            topic,
            source,
        )

        source[
            "concept_coverage"
        ] = result

        source[
            "scientific_score"
        ] = result[
            "scientific_score"
        ]

        source[
            "relevance_score"
        ] = result[
            "relevance_score"
        ]

        source[
            "relevance_class"
        ] = result[
            "relevance_class"
        ]

        source[
            "intent_pass"
        ] = result[
            "intent_pass"
        ]

        source[
            "intent_class"
        ] = (
            "causal_scientific"
            if concepts[
                "causal_intent"
            ]
            else "scientific"
        )

        if result[
            "scientific_relevance_pass"
        ]:

            accepted.append(
                source
            )

            print(
                f"✅ {source.get('title', '')}"
            )

            print(
                f"   Scientific score: "
                f"{result['scientific_score']}"
            )

        else:

            print(
                f"❌ {source.get('title', '')}"
            )

            print(
                f"   Score: "
                f"{result['scientific_score']}"
            )

            print(
                "   Reasons: "
                + ", ".join(
                    result[
                        "rejection_reasons"
                    ]
                )
            )

    print(
        f"Scientifically relevant: "
        f"{len(accepted)}"
    )

    return accepted


# ============================================================================
# IDENTITY VERIFICATION
# ============================================================================

def _identity_matches(
    source,
    returned_title,
    returned_doi,
    provider,
):

    expected = _normalize_doi(
        source.get(
            "doi",
            "",
        )
    )

    actual = _normalize_doi(
        returned_doi
    )

    if not expected or not actual:

        source[
            "identity_error"
        ] = (
            f"{provider}: DOI unavailable."
        )

        return False

    if expected != actual:

        source[
            "identity_error"
        ] = (
            f"{provider}: DOI mismatch."
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

    if similarity < TITLE_SIMILARITY_MINIMUM:

        source[
            "identity_error"
        ] = (
            f"{provider}: title mismatch."
        )

        return False

    return True


def verify_crossref(
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

        title = _clean(
            (
                item.get(
                    "title",
                    [],
                )
                or [""]
            )[0]
        )

        returned_doi = _normalize_doi(
            item.get(
                "DOI",
                "",
            )
        )

        if not _identity_matches(
            source,
            title,
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
        ] = title

        source[
            "doi"
        ] = returned_doi

        authors = _crossref_authors(
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

        year = _crossref_year(
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

            _record_evidence(
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

        return _package_evidence(
            source
        )

    except Exception as error:

        source[
            "crossref_verification_error"
        ] = str(
            error
        )

        return False


def verify_openalex(
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

        title = _clean(
            data.get(
                "display_name",
                "",
            )
        )

        if not _identity_matches(
            source,
            title,
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
        ] = title

        source[
            "doi"
        ] = returned_doi

        abstract = _openalex_abstract(
            data.get(
                "abstract_inverted_index"
            )
        )

        if abstract:

            source[
                "abstract"
            ] = abstract

            _record_evidence(
                source,
                "OpenAlex",
                abstract,
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
            "openalex_citation_count"
        ] = (
            data.get(
                "cited_by_count",
                0,
            )
            or 0
        )

        source[
            "verification"
        ] = (
            "DOI and publication identity "
            "verified through OpenAlex."
        )

        return _package_evidence(
            source
        )

    except Exception as error:

        source[
            "openalex_verification_error"
        ] = str(
            error
        )

        return False


def verify_semantic(
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
            {
                "fields": (
                    "title,authors,year,abstract,"
                    "externalIds,venue,citationCount"
                )
            },
            retries=SEMANTIC_RETRIES,
            provider="Semantic Scholar",
        )

        title = _clean(
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
            title,
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
        ] = title

        source[
            "doi"
        ] = returned_doi

        authors = _semantic_authors(
            data
        )

        if authors:
            source[
                "authors"
            ] = authors

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

            _record_evidence(
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

        return _package_evidence(
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


def verify_identity(
    source
):

    discovery = source.get(
        "discovery_provider",
        "",
    )

    order = []

    if discovery:
        order.append(
            discovery
        )

    for provider in (
        "Crossref",
        "OpenAlex",
        "Semantic Scholar",
    ):

        if provider not in order:
            order.append(
                provider
            )

    for provider in order:

        if provider == "Crossref":

            verified = verify_crossref(
                source
            )

        elif provider == "OpenAlex":

            verified = verify_openalex(
                source
            )

        elif provider == "Semantic Scholar":

            verified = verify_semantic(
                source
            )

        else:

            verified = False

        if verified:
            return source

    return False


# ============================================================================
# EVIDENCE VALIDATION
# ============================================================================

def validate_evidence(
    source
):

    if source.get(
        "metadata_verified"
    ) is not True:
        return False

    evidence = _clean_abstract(
        source.get(
            "evidence_text",
            "",
        )
    )

    if len(
        evidence
    ) < MIN_ABSTRACT_CHARACTERS:
        return False

    if not _clean(
        source.get(
            "authors",
            "",
        )
    ):
        return False

    if not source.get(
        "year"
    ):
        return False

    doi = _normalize_doi(
        source.get(
            "doi",
            "",
        )
    )

    if not doi:
        return False

    source[
        "source_id"
    ] = _source_id(
        doi
    )

    source[
        "doi"
    ] = doi

    source[
        "evidence_verified"
    ] = True

    source[
        "verified"
    ] = True

    source[
        "evidence_type"
    ] = "abstract"

    source[
        "evidence_available"
    ] = True

    source[
        "verification_level"
    ] = "DOI_METADATA_PLUS_ABSTRACT"

    source[
        "evidence_verification"
    ] = (
        "Publication identity verified through "
        "an authoritative scholarly metadata provider "
        "and abstract evidence retrieved."
    )

    return True


# ============================================================================
# SOURCE SELECTION
# ============================================================================

def select_sources(
    sources
):

    def key(source):

        coverage = source.get(
            "concept_coverage",
            {},
        )

        return (
            source.get(
                "scientific_score",
                0,
            ),
            len(
                source.get(
                    "evidence_providers",
                    [],
                )
                or []
            ),
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
            coverage.get(
                "causal_support",
                False,
            ),
        )

    return sorted(
        sources,
        key=key,
        reverse=True,
    )[
        :MAX_EVIDENCE_SOURCES
    ]


def validate_source_independence(
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
    }

    if len(
        dois
    ) < MIN_ACCEPTED_SOURCES:

        raise RuntimeError(
            "RESEARCH FAILED: fewer than "
            "two distinct DOI-backed sources."
        )

    return {
        "distinct_doi_count": len(
            dois
        ),
        "independence_basis": (
            "distinct normalized DOI identities"
        ),
    }


# ============================================================================
# FINAL VALIDATION
# ============================================================================

def validate_research_package(
    package
):

    if package.get(
        "status"
    ) != "VERIFIED":

        raise RuntimeError(
            "RESEARCH FAILED: package not verified."
        )

    sources = package.get(
        "sources",
        [],
    )

    if len(
        sources
    ) < MIN_ACCEPTED_SOURCES:

        raise RuntimeError(
            "RESEARCH FAILED: insufficient sources."
        )

    for source in sources:

        if source.get(
            "metadata_verified"
        ) is not True:

            raise RuntimeError(
                "RESEARCH FAILED: metadata not verified."
            )

        if source.get(
            "evidence_verified"
        ) is not True:

            raise RuntimeError(
                "RESEARCH FAILED: evidence not verified."
            )

        if source.get(
            "verified"
        ) is not True:

            raise RuntimeError(
                "RESEARCH FAILED: source not verified."
            )

        if source.get(
            "relevance_class"
        ) not in {
            "strong",
            "moderate",
            "acceptable",
        }:

            raise RuntimeError(
                "RESEARCH FAILED: weak source survived."
            )

        if source.get(
            "concept_coverage",
            {},
        ).get(
            "scientific_relevance_pass"
        ) is not True:

            raise RuntimeError(
                "RESEARCH FAILED: scientific relevance "
                "check failed."
            )

        if source.get(
            "concept_coverage",
            {},
        ).get(
            "causal_pass"
        ) is not True:

            raise RuntimeError(
                "RESEARCH FAILED: causal support "
                "check failed."
            )

    validate_source_independence(
        sources
    )

    return True


# ============================================================================
# MAIN PIPELINE
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
        f"🔬 MINT-YT-FACTORY SCIENTIFIC RESEARCH v{VERSION}"
    )
    print("=" * 80)

    print(
        f"Topic: {topic}"
    )

    concepts = _question_concepts(
        topic
    )

    print("=" * 80)
    print("🧠 QUESTION STRUCTURE")
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

    # ----------------------------------------------------------------------
    # DISCOVERY
    # ----------------------------------------------------------------------

    all_sources = []

    for search_function in (
        search_crossref,
        search_openalex,
        search_semantic_scholar,
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
        f"Unique DOI candidates: "
        f"{len(candidates)}"
    )

    if not candidates:

        raise RuntimeError(
            "RESEARCH FAILED: no DOI-backed "
            "scientific literature discovered."
        )

    # ----------------------------------------------------------------------
    # INITIAL RELEVANCE
    # ----------------------------------------------------------------------

    relevant = apply_relevance(
        topic,
        candidates,
    )

    if not relevant:

        raise RuntimeError(
            "RESEARCH FAILED: scientific literature "
            "does not adequately match the question."
        )

    relevant = sorted(
        relevant,
        key=lambda source: (
            source.get(
                "scientific_score",
                0,
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
    # DOI VERIFICATION
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🔐 DOI / PUBLICATION IDENTITY VERIFICATION")
    print("=" * 80)

    verified_metadata = []

    for index, source in enumerate(
        relevant,
        start=1,
    ):

        print(
            f"{index}/{len(relevant)} "
            f"{source.get('title', '')}"
        )

        verified = verify_identity(
            source
        )

        if verified:

            print(
                "   ✅ VERIFIED"
            )

            verified_metadata.append(
                source
            )

        else:

            print(
                "   ❌ REJECTED"
            )

    if not verified_metadata:

        raise RuntimeError(
            "RESEARCH FAILED: no publication "
            "identity could be verified."
        )

    # ----------------------------------------------------------------------
    # EVIDENCE
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("📚 ABSTRACT EVIDENCE VALIDATION")
    print("=" * 80)

    evidence_sources = []

    for source in verified_metadata:

        source = _package_evidence(
            source
        )

        if validate_evidence(
            source
        ):

            evidence_sources.append(
                source
            )

            print(
                f"✅ Evidence: "
                f"{source.get('title', '')}"
            )

        else:

            print(
                f"❌ No sufficient evidence: "
                f"{source.get('title', '')}"
            )

    if not evidence_sources:

        raise RuntimeError(
            "RESEARCH FAILED: no verified scholarly "
            "abstract evidence remained."
        )

    # ----------------------------------------------------------------------
    # FINAL SCIENTIFIC RELEVANCE
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🧪 FINAL SCIENTIFIC EVIDENCE CHECK")
    print("=" * 80)

    final_sources = apply_relevance(
        topic,
        evidence_sources,
    )

    final_sources = [
        source
        for source in final_sources
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
                "scientific_relevance_pass"
            ) is True
        )
    ]

    final_sources = select_sources(
        final_sources
    )

    if len(
        final_sources
    ) < MIN_ACCEPTED_SOURCES:

        raise RuntimeError(
            "RESEARCH FAILED: fewer than two "
            "independent scientific sources "
            "survived final verification."
        )

    # ----------------------------------------------------------------------
    # SOURCE IDS
    # ----------------------------------------------------------------------

    seen_dois = set()
    seen_ids = set()

    for source in final_sources:

        doi = _normalize_doi(
            source.get(
                "doi",
                "",
            )
        )

        source_id = _source_id(
            doi
        )

        if doi in seen_dois:
            raise RuntimeError(
                "RESEARCH FAILED: duplicate DOI."
            )

        if source_id in seen_ids:
            raise RuntimeError(
                "RESEARCH FAILED: duplicate source ID."
            )

        seen_dois.add(
            doi
        )

        seen_ids.add(
            source_id
        )

        source[
            "source_id"
        ] = source_id

    # ----------------------------------------------------------------------
    # INDEPENDENCE
    # ----------------------------------------------------------------------

    independence = (
        validate_source_independence(
            final_sources
        )
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
            "subject": concepts[
                "subject"
            ],
            "phenomenon": concepts[
                "phenomenon"
            ],
            "condition": concepts[
                "condition"
            ],
            "topic_terms": concepts[
                "topic_terms"
            ],
            "concept_terms": concepts[
                "concept_terms"
            ],
            "question_phrases": concepts[
                "question_phrases"
            ],
            "causal_intent": concepts[
                "causal_intent"
            ],
            "scholarly_queries": build_scholarly_queries(
                topic
            ),
        },

        "verification_policy": {
            "scientific_research_required": True,
            "minimum_sources": MIN_ACCEPTED_SOURCES,
            "doi_required": True,
            "metadata_verification_required": True,
            "abstract_evidence_required": True,
            "minimum_abstract_characters": (
                MIN_ABSTRACT_CHARACTERS
            ),
            "minimum_scientific_score": (
                MIN_SCIENTIFIC_SCORE
            ),
            "subject_required": REQUIRE_SUBJECT,
            "phenomenon_required": REQUIRE_PHENOMENON,
            "causal_support_required": REQUIRE_CAUSAL_SUPPORT,
            "independent_doi_sources_required": True,
            "metadata_is_not_evidence": True,
            "gemini_used_for_evidence": False,
            "llm_used_for_evidence_decision": False,
            "final_evidence_relevance_check": True,
            "doi_identity_verification": True,
            "source_id_from_normalized_doi": True,
        },

        "source_count": len(
            final_sources
        ),

        "evidence_source_count": len(
            final_sources
        ),

        "source_diversity": independence,

        "sources": final_sources,
    }

    # ----------------------------------------------------------------------
    # FINAL HARD VALIDATION
    # ----------------------------------------------------------------------

    validate_research_package(
        package
    )

    print("=" * 80)
    print("✅ SCIENTIFIC RESEARCH VERIFIED")
    print("=" * 80)

    for index, source in enumerate(
        final_sources,
        start=1,
    ):

        coverage = source.get(
            "concept_coverage",
            {},
        )

        print(
            f"{index}. {source.get('title', '')}"
        )

        print(
            f"   DOI: {source.get('doi', '')}"
        )

        print(
            f"   Score: "
            f"{source.get('scientific_score', 0)}"
        )

        print(
            f"   Class: "
            f"{source.get('relevance_class', '')}"
        )

        print(
            "   Causal support: "
            f"{coverage.get('causal_support', False)}"
        )

        print(
            "   Evidence: "
            f"{len(source.get('evidence_text', ''))} chars"
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
        print("📄 RESEARCH SAVED")
        print("=" * 80)
        print(output)

    except Exception as error:

        print("=" * 80)
        print("❌ RESEARCH FAILED")
        print("=" * 80)
        print(error)

        sys.exit(1)