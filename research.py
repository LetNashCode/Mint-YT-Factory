"""
research.py
Mint-YT-Factory

Version 4.3

Research-first scientific evidence layer.

FLOW:

Topic
  ↓
Crossref + Semantic Scholar + OpenAlex
  ↓
Deduplicate / merge duplicate records
  ↓
Remove candidates without DOI
  ↓
STRICT TOPIC RELEVANCE FILTER
  ↓
Verify DOI / identity
  ↓
Enrich abstract/evidence
  ↓
Evidence-quality filter
  ↓
STRICT RELEVANCE RECHECK
  ↓
Minimum 2 evidence-backed sources
  ↓
Authoritative source_id assignment
  ↓
Final validation
  ↓
Verified research package

IMPORTANT:

- DOI verification is NOT evidence verification.
- Metadata-only sources are NEVER accepted as evidence.
- Abstracts are NEVER invented.
- Sources must actually exist.
- Minimum 2 evidence-backed sources are required.
- Semantic Scholar rate limits are handled gracefully.
- OpenAlex is used as a free evidence fallback.
- Long research topics are supported.
- Evidence text is explicitly separated from metadata.
- Gemini is NOT used to create or summarize evidence.
- Research sources are never fabricated.
- A DOI alone does not make a source evidence-backed.
- Relevance uses topic terms AND topic concepts.
- Irrelevant domain matches are rejected.
- Duplicate records are merged instead of blindly discarded.
- Every final source receives a stable authoritative source_id.
- source_id is derived from normalized DOI.
- Candidates without DOI are rejected before source_id generation.
"""


import hashlib
import json
import os
import re
import sys
import time

from urllib.parse import quote

import requests


# ==========================================================================
# CONFIG
# ==========================================================================

CROSSREF_URL = (
    "https://api.crossref.org/v1/works"
)

SEMANTIC_SCHOLAR_URL = (
    "https://api.semanticscholar.org/graph/v1/paper/search"
)

SEMANTIC_PAPER_URL = (
    "https://api.semanticscholar.org/graph/v1/paper"
)

OPENALEX_URL = (
    "https://api.openalex.org/works"
)

TIMEOUT = 30

MAX_CROSSREF_RESULTS = 12
MAX_SEMANTIC_RESULTS = 8
MAX_OPENALEX_RESULTS = 10

MIN_ACCEPTED_SOURCES = 2
MAX_EVIDENCE_SOURCES = 5

SEMANTIC_RETRIES = 2
SEMANTIC_BACKOFF_SECONDS = 4

MIN_ABSTRACT_CHARACTERS = 120
MAX_EVIDENCE_TEXT_CHARACTERS = 12000


# ==========================================================================
# EVIDENCE QUALITY
# ==========================================================================

EVIDENCE_QUALITY_HIGH = "high"
EVIDENCE_QUALITY_MODERATE = "moderate"
EVIDENCE_QUALITY_NONE = "none"


# ==========================================================================
# USER AGENT
# ==========================================================================

USER_AGENT = (
    "Mint-YT-Factory/4.3 "
    "(educational research verification)"
)


# ==========================================================================
# SESSION
# ==========================================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
)


# ==========================================================================
# HTTP
# ==========================================================================

def _get(
    url,
    params=None,
    retries=2,
    backoff=2,
):
    """
    GET JSON with retry support.

    Handles:
    - 429
    - 5xx
    - connection failures
    - timeout failures
    """

    last_error = None

    for attempt in range(retries + 1):

        try:

            response = SESSION.get(
                url,
                params=params,
                timeout=TIMEOUT,
            )

            # --------------------------------------------------------------
            # RATE LIMIT
            # --------------------------------------------------------------

            if response.status_code == 429:

                retry_after = response.headers.get(
                    "Retry-After"
                )

                if retry_after:

                    try:
                        delay = float(
                            retry_after
                        )
                    except Exception:
                        delay = backoff * (
                            attempt + 1
                        )

                else:

                    delay = backoff * (
                        attempt + 1
                    )

                if attempt < retries:

                    print(
                        f"⚠️ HTTP 429. "
                        f"Retrying in {delay:.1f}s..."
                    )

                    time.sleep(delay)

                    continue

                raise RuntimeError(
                    "HTTP 429 rate limit exceeded."
                )

            # --------------------------------------------------------------
            # SERVER ERRORS
            # --------------------------------------------------------------

            if (
                response.status_code >= 500
                and attempt < retries
            ):

                delay = backoff * (
                    attempt + 1
                )

                print(
                    f"⚠️ HTTP "
                    f"{response.status_code}. "
                    f"Retrying in {delay:.1f}s..."
                )

                time.sleep(delay)

                continue

            response.raise_for_status()

            return response.json()

        except Exception as error:

            last_error = error

            if attempt < retries:

                delay = backoff * (
                    attempt + 1
                )

                print(
                    f"⚠️ Request failed. "
                    f"Retrying in {delay:.1f}s..."
                )

                time.sleep(delay)

                continue

            raise last_error

    raise RuntimeError(
        "HTTP request failed."
    )


# ==========================================================================
# TEXT
# ==========================================================================

def _clean(text):

    if text is None:
        return ""

    text = str(text)

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def _clean_abstract(text):

    text = _clean(text)

    if not text:
        return ""

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def _normalize_doi(doi):

    doi = _clean(doi)

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

    doi = doi.strip()

    doi = doi.rstrip(
        ".,;:)"
    )

    return doi.lower()


def _generate_source_id(doi):

    doi = _normalize_doi(
        doi
    )

    if not doi:

        raise RuntimeError(
            "Cannot generate source_id without a DOI."
        )

    digest = hashlib.sha256(
        doi.encode("utf-8")
    ).hexdigest()[:12]

    return f"doi_{digest}"


def _normalize_title(title):

    title = _clean(title).lower()

    title = re.sub(
        r"[^a-z0-9\s]",
        "",
        title,
    )

    return " ".join(
        title.split()
    )


# ==========================================================================
# STOPWORDS
# ==========================================================================

STOPWORDS = {
    "how",
    "do",
    "does",
    "did",
    "can",
    "could",
    "would",
    "should",
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "from",
    "why",
    "what",
    "is",
    "are",
    "be",
    "their",
    "they",
    "them",
    "these",
    "those",
    "this",
    "that",
    "about",
    "into",
    "through",
    "will",
    "your",
    "our",
    "its",
    "it",
    "as",
    "by",
    "at",
    "over",
    "under",
    "than",
    "then",
    "when",
    "where",
    "which",
    "who",
    "during",
    "using",
    "long",
    "way",
    "ways",
}


# ==========================================================================
# CONCEPT GROUPS
# ==========================================================================

CONCEPT_GROUPS = {

    "bird": {
        "bird",
        "birds",
        "avian",
        "passerine",
        "songbird",
        "songbirds",
        "waterfowl",
        "shorebird",
        "shorebirds",
        "raptor",
        "raptors",
        "pigeon",
        "pigeons",
        "swift",
        "swifts",
    },

    "navigation": {
        "navigate",
        "navigates",
        "navigated",
        "navigating",
        "navigation",
        "navigational",
        "orientation",
        "orient",
        "orients",
        "oriented",
        "compass",
        "directional",
        "direction",
        "directions",
    },

    "migration": {
        "migration",
        "migrations",
        "migratory",
        "migrate",
        "migrates",
        "migrated",
        "migrating",
        "migrant",
        "migrants",
    },

    "flight": {
        "flight",
        "flights",
        "flying",
        "fly",
        "flies",
        "flew",
        "aerial",
        "transoceanic",
    },

    "magnetic": {
        "magnetic",
        "magnetism",
        "magnetoreception",
        "geomagnetic",
        "magneticfield",
    },

    "brain": {
        "brain",
        "brains",
        "neural",
        "neuronal",
        "neuroscience",
        "hippocampus",
        "nidopallium",
        "neuron",
        "neurons",
    },

    "climate": {
        "climate",
        "climatic",
        "warming",
        "temperature",
        "temperatures",
        "environmental",
    },

    "roots": {
        "root",
        "roots",
        "rooting",
        "gravitropism",
        "gravitropic",
        "gravity",
    },

    "plants": {
        "plant",
        "plants",
        "vegetation",
        "seedling",
        "seedlings",
    },

    "pressure": {
        "pressure",
        "pressures",
        "depth",
        "deep",
        "deepsea",
    },

    "ocean": {
        "ocean",
        "oceans",
        "marine",
        "underwater",
        "sea",
        "seas",
    },

    "space": {
        "space",
        "planet",
        "planets",
        "star",
        "stars",
        "galaxy",
        "galaxies",
        "cosmic",
        "astronomy",
        "astronomical",
    },

    "quantum": {
        "quantum",
        "photons",
        "photon",
        "entanglement",
        "superposition",
    },

    "human": {
        "human",
        "humans",
        "people",
        "person",
        "persons",
    },

    "medical": {
        "medical",
        "medicine",
        "clinical",
        "patient",
        "patients",
        "health",
        "disease",
        "diseases",
        "treatment",
    },

    "technology": {
        "technology",
        "technological",
        "computer",
        "computers",
        "software",
        "hardware",
        "algorithm",
        "algorithms",
        "machine",
        "machines",
    },
}


# ==========================================================================
# TOPIC CONCEPT EXTRACTION
# ==========================================================================

def _tokenize(text):

    return [
        token
        for token in re.findall(
            r"[a-z0-9]+",
            _clean(text).lower(),
        )
        if token not in STOPWORDS
        and len(token) >= 3
    ]


def _concepts_from_text(text):

    tokens = set(
        _tokenize(text)
    )

    concepts = set()

    for concept, words in CONCEPT_GROUPS.items():

        if tokens.intersection(words):

            concepts.add(
                concept
            )

    return concepts


def _topic_terms(topic):

    return set(
        _tokenize(topic)
    )


def _topic_concepts(topic):

    return _concepts_from_text(
        topic
    )


# ==========================================================================
# MORPHOLOGICAL MATCH
# ==========================================================================

def _stem_like_match(
    term,
    text,
):

    if not term:
        return False

    candidates = {
        term
    }

    if term.endswith("ies") and len(term) > 4:
        candidates.add(
            term[:-3] + "y"
        )

    if term.endswith("ing") and len(term) > 5:
        candidates.add(
            term[:-3]
        )

    if term.endswith("ed") and len(term) > 4:
        candidates.add(
            term[:-2]
        )

    if term.endswith("s") and len(term) > 4:
        candidates.add(
            term[:-1]
        )

    for candidate in candidates:

        if len(candidate) < 4:
            continue

        if re.search(
            rf"\b{re.escape(candidate)}\w*\b",
            text,
        ):

            return True

    return False


# ==========================================================================
# RELEVANCE
# ==========================================================================

def _relevance_score(
    topic,
    source,
):

    title = _clean(
        source.get(
            "title",
            "",
        )
    ).lower()

    abstract = _clean(
        source.get(
            "evidence_text",
            ""
        )
        or source.get(
            "abstract",
            "",
        )
    ).lower()

    title_clean = re.sub(
        r"[^a-z0-9\s]",
        " ",
        title,
    )

    abstract_clean = re.sub(
        r"[^a-z0-9\s]",
        " ",
        abstract,
    )

    title_clean = re.sub(
        r"\s+",
        " ",
        title_clean,
    ).strip()

    abstract_clean = re.sub(
        r"\s+",
        " ",
        abstract_clean,
    ).strip()

    topic_terms = _topic_terms(
        topic
    )

    topic_concepts = _topic_concepts(
        topic
    )

    title_concepts = _concepts_from_text(
        title_clean
    )

    abstract_concepts = _concepts_from_text(
        abstract_clean
    )

    title_concept_matches = (
        topic_concepts
        .intersection(
            title_concepts
        )
    )

    abstract_concept_matches = (
        topic_concepts
        .intersection(
            abstract_concepts
        )
    )

    score = 0

    matched_terms = []

    title_term_matches = 0

    abstract_term_matches = 0

    # ------------------------------------------------------------------
    # TERM MATCHES
    # ------------------------------------------------------------------

    for term in topic_terms:

        if _stem_like_match(
            term,
            title_clean,
        ):

            title_term_matches += 1

            matched_terms.append(
                term
            )

            score += 3

        elif _stem_like_match(
            term,
            abstract_clean,
        ):

            abstract_term_matches += 1

            matched_terms.append(
                term
            )

            score += 1

    # ------------------------------------------------------------------
    # CONCEPT MATCHES
    # ------------------------------------------------------------------

    score += (
        len(title_concept_matches) * 5
    )

    score += (
        len(
            abstract_concept_matches
            - title_concept_matches
        ) * 2
    )

    # ------------------------------------------------------------------
    # EXACT PHRASE
    # ------------------------------------------------------------------

    normalized_topic = _normalize_title(
        topic
    )

    normalized_title = _normalize_title(
        title
    )

    if (
        normalized_topic
        and normalized_topic
        in normalized_title
    ):

        score += 12

    # ------------------------------------------------------------------
    # ADJACENT TERM PAIRS
    # ------------------------------------------------------------------

    topic_tokens = list(
        _tokenize(topic)
    )

    for index in range(
        len(topic_tokens) - 1
    ):

        phrase = (
            topic_tokens[index]
            + " "
            + topic_tokens[index + 1]
        )

        if phrase in title_clean:

            score += 5

    # ------------------------------------------------------------------
    # CLASSIFICATION
    # ------------------------------------------------------------------

    concept_count = len(
        topic_concepts
    )

    title_concept_count = len(
        title_concept_matches
    )

    abstract_concept_count = len(
        abstract_concept_matches
    )

    if concept_count >= 2:

        if title_concept_count >= 2:

            relevance_class = "strong"

        elif (
            title_concept_count >= 1
            and abstract_concept_count >= 2
        ):

            relevance_class = "strong"

        elif (
            title_concept_count >= 1
            and abstract_concept_count >= 1
        ):

            relevance_class = "moderate"

        elif title_term_matches >= 2:

            relevance_class = "moderate"

        else:

            relevance_class = "weak"

    else:

        if (
            title_term_matches >= 2
            or title_concept_count >= 1
        ):

            relevance_class = "moderate"

        elif (
            title_term_matches >= 1
            and abstract_term_matches >= 2
        ):

            relevance_class = "moderate"

        else:

            relevance_class = "weak"

    # ------------------------------------------------------------------
    # DOMAIN PROTECTION
    # ------------------------------------------------------------------

    domain_concepts = {
        "bird",
        "plants",
        "space",
        "ocean",
    }

    topic_domains = (
        topic_concepts
        .intersection(
            domain_concepts
        )
    )

    if topic_domains:

        matched_domains = (
            title_concept_matches
            .union(
                abstract_concept_matches
            )
            .intersection(
                topic_domains
            )
        )

        if not matched_domains:

            relevance_class = "mismatch"
            score = 0

    # ------------------------------------------------------------------
    # STORE DIAGNOSTICS
    # ------------------------------------------------------------------

    source[
        "matched_terms"
    ] = sorted(
        set(
            matched_terms
        )
    )

    source[
        "topic_concepts"
    ] = sorted(
        topic_concepts
    )

    source[
        "title_concepts"
    ] = sorted(
        title_concept_matches
    )

    source[
        "abstract_concepts"
    ] = sorted(
        abstract_concept_matches
    )

    source[
        "title_match_count"
    ] = title_term_matches

    source[
        "abstract_match_count"
    ] = abstract_term_matches

    source[
        "topic_concept_coverage"
    ] = round(
        (
            len(
                title_concept_matches
                .union(
                    abstract_concept_matches
                )
            )
            /
            max(
                len(topic_concepts),
                1,
            )
        ),
        3,
    )

    source[
        "relevance_class"
    ] = relevance_class

    return score


def _is_relevant(source):

    return source.get(
        "relevance_class"
    ) in {
        "strong",
        "moderate",
    }


def relevance_filter(
    topic,
    sources,
):

    accepted = []

    print("=" * 80)
    print("🎯 STRICT TOPIC RELEVANCE FILTER")
    print("=" * 80)

    topic_concepts = _topic_concepts(
        topic
    )

    print(
        f"Topic concepts: "
        f"{', '.join(sorted(topic_concepts)) or 'none'}"
    )

    for source in sources:

        score = _relevance_score(
            topic,
            source,
        )

        source[
            "relevance_score"
        ] = score

        title = source.get(
            "title",
            "",
        )

        classification = source.get(
            "relevance_class",
            "unknown",
        )

        if _is_relevant(
            source
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
                f"   Title concepts: "
                f"{source.get('title_concepts', [])}"
            )

            print(
                f"   Abstract concepts: "
                f"{source.get('abstract_concepts', [])}"
            )

        else:

            print(
                f"❌ REJECTED: {title}"
            )

            print(
                f"   Score: {score}"
            )

            print(
                f"   Class: {classification}"
            )

    print(
        f"Relevant candidates: "
        f"{len(accepted)}"
    )

    return accepted


# ==========================================================================
# AUTHORS
# ==========================================================================

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
            x
            for x in (
                given,
                family,
            )
            if x
        )

        if name:
            authors.append(name)

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
            authors.append(name)

    return ", ".join(
        authors
    )


# ==========================================================================
# YEAR
# ==========================================================================

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

        date_parts = date_info.get(
            "date-parts",
            [],
        )

        if (
            date_parts
            and date_parts[0]
        ):

            try:

                return int(
                    date_parts[0][0]
                )

            except Exception:
                pass

    return None


# ==========================================================================
# OPENALEX ABSTRACT
# ==========================================================================

def _openalex_abstract_text(
    inverted_index,
):

    if not isinstance(
        inverted_index,
        dict,
    ):
        return ""

    words = []

    for word, positions in inverted_index.items():

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


# ==========================================================================
# EVIDENCE PACKAGE
# ==========================================================================

def _build_evidence_package(
    source,
):

    abstract = _clean_abstract(
        source.get(
            "abstract",
            "",
        )
    )

    if abstract:

        evidence_available = True
        evidence_type = "abstract"
        evidence_quality = (
            EVIDENCE_QUALITY_MODERATE
        )
        evidence_text = abstract

        evidence_notes = (
            "Evidence text is the scholarly "
            "abstract retrieved from a research "
            "metadata database. It is not the "
            "full paper."
        )

    else:

        evidence_available = False
        evidence_type = "metadata_only"
        evidence_quality = (
            EVIDENCE_QUALITY_NONE
        )
        evidence_text = ""

        evidence_notes = (
            "No abstract or evidence text was "
            "available. Metadata alone must not "
            "be used to support detailed claims."
        )

    if len(
        evidence_text
    ) > MAX_EVIDENCE_TEXT_CHARACTERS:

        evidence_text = evidence_text[
            :MAX_EVIDENCE_TEXT_CHARACTERS
        ]

        evidence_notes += (
            " Evidence text was truncated."
        )

    source[
        "evidence_available"
    ] = evidence_available

    source[
        "evidence_type"
    ] = evidence_type

    source[
        "evidence_quality"
    ] = evidence_quality

    source[
        "evidence_text"
    ] = evidence_text

    source[
        "evidence_notes"
    ] = evidence_notes

    source[
        "abstract"
    ] = abstract

    source[
        "abstract_source"
    ] = source.get(
        "evidence_source",
        "",
    )

    return source


# ==========================================================================
# CROSSREF SEARCH
# ==========================================================================

def search_crossref(
    topic,
):

    print("=" * 80)
    print("🔎 CROSSREF SEARCH")
    print("=" * 80)

    params = {

        "query.bibliographic":
            topic,

        "rows":
            MAX_CROSSREF_RESULTS,

        "select":
            (
                "DOI,title,author,"
                "container-title,"
                "publisher,type,"
                "published,published-print,"
                "published-online,"
                "URL,abstract"
            ),
    }

    data = _get(
        CROSSREF_URL,
        params,
        retries=2,
        backoff=2,
    )

    items = (
        data
        .get(
            "message",
            {}
        )
        .get(
            "items",
            []
        )
    )

    results = []

    for item in items:

        titles = item.get(
            "title",
            [],
        )

        title = (
            _clean(
                titles[0]
            )
            if titles
            else ""
        )

        doi = _normalize_doi(
            item.get(
                "DOI",
                "",
            )
        )

        if not title or not doi:
            continue

        abstract = _clean_abstract(
            item.get(
                "abstract",
                "",
            )
        )

        source = {

            "source_database":
                "Crossref",

            "title":
                title,

            "authors":
                _authors_crossref(
                    item
                ),

            "journal":
                _clean(
                    (
                        item.get(
                            "container-title",
                            [],
                        )
                        or [""]
                    )[0]
                ),

            "publisher":
                _clean(
                    item.get(
                        "publisher",
                        "",
                    )
                ),

            "year":
                _extract_year(
                    item
                ),

            "doi":
                doi,

            "url":
                (
                    _clean(
                        item.get(
                            "URL",
                            "",
                        )
                    )
                    or
                    f"https://doi.org/{doi}"
                ),

            "type":
                _clean(
                    item.get(
                        "type",
                        "",
                    )
                ),

            "publication_type":
                _clean(
                    item.get(
                        "type",
                        "",
                    )
                ),

            "abstract":
                abstract,

            "evidence_source":
                (
                    "Crossref abstract"
                    if abstract
                    else ""
                ),

            "metadata_verified":
                False,

            "evidence_verified":
                False,

            "verified":
                False,
        }

        results.append(
            _build_evidence_package(
                source
            )
        )

    print(
        f"Crossref results: {len(results)}"
    )

    return results


# ==========================================================================
# SEMANTIC SCHOLAR SEARCH
# ==========================================================================

def search_semantic_scholar(
    topic,
):

    print("=" * 80)
    print("🔎 SEMANTIC SCHOLAR SEARCH")
    print("=" * 80)

    params = {

        "query":
            topic,

        "limit":
            MAX_SEMANTIC_RESULTS,

        "fields":
            (
                "title,"
                "authors,"
                "year,"
                "abstract,"
                "url,"
                "externalIds,"
                "publicationTypes,"
                "venue,"
                "citationCount"
            ),
    }

    try:

        data = _get(
            SEMANTIC_SCHOLAR_URL,
            params,
            retries=SEMANTIC_RETRIES,
            backoff=SEMANTIC_BACKOFF_SECONDS,
        )

    except Exception as error:

        print(
            "⚠️ Semantic Scholar unavailable:"
        )

        print(error)

        return []

    results = []

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

        if not title:
            continue

        external_ids = (
            paper.get(
                "externalIds",
                {}
            )
            or {}
        )

        doi = _normalize_doi(
            external_ids.get(
                "DOI",
                "",
            )
        )

        url = _clean(
            paper.get(
                "url",
                "",
            )
        )

        citation_url = (
            f"https://doi.org/{doi}"
            if doi
            else url
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

            "source_database":
                "Semantic Scholar",

            "title":
                title,

            "authors":
                _authors_semantic(
                    paper
                ),

            "journal":
                _clean(
                    paper.get(
                        "venue",
                        "",
                    )
                ),

            "publisher":
                "",

            "year":
                paper.get(
                    "year"
                ),

            "doi":
                doi,

            "url":
                citation_url,

            "semantic_scholar_url":
                url,

            "abstract":
                abstract,

            "publication_types":
                publication_types,

            "publication_type":
                (
                    publication_types[0]
                    if publication_types
                    else ""
                ),

            "citation_count":
                paper.get(
                    "citationCount",
                    0,
                )
                or 0,

            "evidence_source":
                (
                    "Semantic Scholar abstract"
                    if abstract
                    else ""
                ),

            "metadata_verified":
                False,

            "evidence_verified":
                False,

            "verified":
                False,
        }

        results.append(
            _build_evidence_package(
                source
            )
        )

    print(
        f"Semantic Scholar results: "
        f"{len(results)}"
    )

    return results


# ==========================================================================
# OPENALEX SEARCH
# ==========================================================================

def search_openalex(
    topic,
):

    print("=" * 80)
    print("🔎 OPENALEX SEARCH")
    print("=" * 80)

    params = {

        "search":
            topic,

        "per-page":
            MAX_OPENALEX_RESULTS,
    }

    try:

        data = _get(
            OPENALEX_URL,
            params,
            retries=2,
            backoff=2,
        )

    except Exception as error:

        print(
            "⚠️ OpenAlex search failed:"
        )

        print(error)

        return []

    results = []

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

        if not title:
            continue

        ids = (
            item.get(
                "ids",
                {}
            )
            or {}
        )

        doi = _normalize_doi(
            ids.get(
                "doi",
                "",
            )
        )

        if not doi:
            continue

        abstract = _openalex_abstract_text(
            item.get(
                "abstract_inverted_index"
            )
        )

        authors = []

        for authorship in item.get(
            "authorships",
            [],
        ):

            author = (
                authorship
                .get(
                    "author",
                    {}
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
                authors.append(name)

        primary_location = (
            item.get(
                "primary_location",
                {}
            )
            or {}
        )

        source_info = (
            primary_location.get(
                "source",
                {}
            )
            or {}
        )

        journal = _clean(
            source_info.get(
                "display_name",
                "",
            )
        )

        open_access = (
            item.get(
                "open_access",
                {}
            )
            or {}
        )

        source = {

            "source_database":
                "OpenAlex",

            "title":
                title,

            "authors":
                ", ".join(authors),

            "journal":
                journal,

            "publisher":
                "",

            "year":
                item.get(
                    "publication_year"
                ),

            "doi":
                doi,

            "url":
                f"https://doi.org/{doi}",

            "openalex_url":
                _clean(
                    ids.get(
                        "openalex",
                        "",
                    )
                ),

            "abstract":
                abstract,

            "publication_type":
                _clean(
                    item.get(
                        "type",
                        "",
                    )
                ),

            "citation_count":
                item.get(
                    "cited_by_count",
                    0,
                )
                or 0,

            "open_access":
                bool(
                    open_access.get(
                        "is_oa",
                        False,
                    )
                ),

            "evidence_source":
                (
                    "OpenAlex abstract"
                    if abstract
                    else ""
                ),

            "metadata_verified":
                False,

            "evidence_verified":
                False,

            "verified":
                False,
        }

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


# ==========================================================================
# DEDUPLICATION / MERGING
# ==========================================================================

def _merge_sources(
    primary,
    secondary,
):

    # Keep better title.
    if not primary.get("title") and secondary.get("title"):
        primary["title"] = secondary["title"]

    # Keep metadata fields when missing.
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

        if not primary.get(field) and secondary.get(field):

            primary[field] = secondary[field]

    # Keep longest abstract.
    primary_abstract = _clean_abstract(
        primary.get(
            "abstract",
            "",
        )
    )

    secondary_abstract = _clean_abstract(
        secondary.get(
            "abstract",
            "",
        )
    )

    if len(secondary_abstract) > len(primary_abstract):

        primary[
            "abstract"
        ] = secondary_abstract

        primary[
            "evidence_source"
        ] = secondary.get(
            "evidence_source",
            "",
        )

    # Keep highest citation count.
    primary["citation_count"] = max(
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

    primary["openalex_citation_count"] = max(
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

    # Track databases.
    databases = set(
        primary.get(
            "source_databases",
            [],
        )
    )

    if primary.get("source_database"):
        databases.add(
            primary["source_database"]
        )

    if secondary.get("source_database"):
        databases.add(
            secondary["source_database"]
        )

    primary[
        "source_databases"
    ] = sorted(
        databases
    )

    return _build_evidence_package(
        primary
    )


def deduplicate_sources(
    sources,
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

        if doi and doi in by_doi:

            existing = by_doi[doi]

        elif title and title in by_title:

            existing = by_title[title]

        if existing is not None:

            _merge_sources(
                existing,
                source,
            )

            continue

        source[
            "doi"
        ] = doi

        source[
            "source_databases"
        ] = [
            source.get(
                "source_database",
                "",
            )
        ]

        unique.append(
            source
        )

        if doi:
            by_doi[doi] = source

        if title:
            by_title[title] = source

    return unique


# ==========================================================================
# CROSSREF DOI VERIFICATION
# ==========================================================================

def verify_crossref_source(
    source,
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

        url = (
            CROSSREF_URL
            + "/"
            + quote(
                doi,
                safe="",
            )
        )

        data = _get(
            url,
            retries=1,
            backoff=2,
        )

        item = data.get(
            "message",
            {}
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

        if returned_doi != doi:
            return False

        if not returned_title:
            return False

        source[
            "metadata_verified"
        ] = True

        source[
            "verified_title"
        ] = returned_title

        source[
            "doi"
        ] = returned_doi

        # Refresh metadata from authoritative Crossref record.
        crossref_authors = _authors_crossref(
            item
        )

        if crossref_authors:
            source[
                "authors"
            ] = crossref_authors

        crossref_journal = _clean(
            (
                item.get(
                    "container-title",
                    [],
                )
                or [""]
            )[0]
        )

        if crossref_journal:
            source[
                "journal"
            ] = crossref_journal

        crossref_publisher = _clean(
            item.get(
                "publisher",
                "",
            )
        )

        if crossref_publisher:
            source[
                "publisher"
            ] = crossref_publisher

        crossref_year = _extract_year(
            item
        )

        if crossref_year:
            source[
                "year"
            ] = crossref_year

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

        source[
            "verification"
        ] = "DOI resolved through Crossref."

        return _build_evidence_package(
            source
        )

    except Exception as error:

        source[
            "verification_error"
        ] = str(error)

        return False


# ==========================================================================
# SEMANTIC SCHOLAR DOI VERIFICATION
# ==========================================================================

def verify_semantic_source(
    source,
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

        url = (
            SEMANTIC_PAPER_URL
            + "/DOI:"
            + quote(
                doi,
                safe="",
            )
        )

        params = {
            "fields":
                (
                    "title,"
                    "authors,"
                    "year,"
                    "abstract,"
                    "externalIds,"
                    "venue,"
                    "publicationTypes,"
                    "citationCount"
                )
        }

        data = _get(
            url,
            params,
            retries=SEMANTIC_RETRIES,
            backoff=SEMANTIC_BACKOFF_SECONDS,
        )

        returned_title = _clean(
            data.get(
                "title",
                "",
            )
        )

        returned_ids = (
            data.get(
                "externalIds",
                {}
            )
            or {}
        )

        returned_doi = _normalize_doi(
            returned_ids.get(
                "DOI",
                "",
            )
        )

        if not returned_title:
            return False

        if (
            returned_doi
            and returned_doi != doi
        ):
            return False

        source[
            "metadata_verified"
        ] = True

        source[
            "verified_title"
        ] = returned_title

        source[
            "doi"
        ] = doi

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

        if data.get("year"):
            source[
                "year"
            ] = data.get(
                "year"
            )

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

        source[
            "citation_count"
        ] = data.get(
            "citationCount",
            source.get(
                "citation_count",
                0,
            )
        ) or 0

        source[
            "verification"
        ] = (
            "DOI resolved through Semantic Scholar."
        )

        return _build_evidence_package(
            source
        )

    except Exception as error:

        source[
            "verification_error"
        ] = str(error)

        return False


# ==========================================================================
# OPENALEX DOI VERIFICATION
# ==========================================================================

def verify_openalex_source(
    source,
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

        url = (
            OPENALEX_URL
            + "/https://doi.org/"
            + quote(
                doi,
                safe="",
            )
        )

        data = _get(
            url,
            retries=1,
            backoff=2,
        )

        returned_ids = (
            data.get(
                "ids",
                {}
            )
            or {}
        )

        returned_doi = _normalize_doi(
            returned_ids.get(
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

        if not returned_title:
            return False

        if (
            returned_doi
            and returned_doi != doi
        ):
            return False

        source[
            "metadata_verified"
        ] = True

        source[
            "verified_title"
        ] = returned_title

        source[
            "doi"
        ] = doi

        if data.get(
            "publication_year"
        ):

            source[
                "year"
            ] = data.get(
                "publication_year"
            )

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

        source[
            "openalex_citation_count"
        ] = data.get(
            "cited_by_count",
            0,
        ) or 0

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
        ] = "DOI resolved through OpenAlex."

        return _build_evidence_package(
            source
        )

    except Exception as error:

        source[
            "verification_error"
        ] = str(error)

        return False


# ==========================================================================
# OPENALEX ENRICHMENT
# ==========================================================================

def enrich_from_openalex(
    source,
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

        url = (
            OPENALEX_URL
            + "/https://doi.org/"
            + quote(
                doi,
                safe="",
            )
        )

        data = _get(
            url,
            retries=1,
            backoff=2,
        )

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

            source[
                "openalex_enriched"
            ] = True

        source[
            "openalex_citation_count"
        ] = data.get(
            "cited_by_count",
            0,
        ) or 0

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
        ] = str(error)

    return source


# ==========================================================================
# SEMANTIC ENRICHMENT
# ==========================================================================

def enrich_from_semantic(
    source,
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

        url = (
            SEMANTIC_PAPER_URL
            + "/DOI:"
            + quote(
                doi,
                safe="",
            )
        )

        params = {
            "fields":
                (
                    "title,"
                    "abstract,"
                    "year,"
                    "externalIds,"
                    "publicationTypes,"
                    "citationCount"
                )
        }

        data = _get(
            url,
            params,
            retries=SEMANTIC_RETRIES,
            backoff=SEMANTIC_BACKOFF_SECONDS,
        )

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

        source[
            "citation_count"
        ] = data.get(
            "citationCount",
            source.get(
                "citation_count",
                0,
            )
        ) or 0

    except Exception as error:

        source[
            "semantic_enrichment_error"
        ] = str(error)

    return source


# ==========================================================================
# EVIDENCE ENRICHMENT
# ==========================================================================

def enrich_source(
    source,
):

    existing = _clean_abstract(
        source.get(
            "abstract",
            "",
        )
    )

    if existing:

        return _build_evidence_package(
            source
        )

    # Semantic Scholar first.
    source = enrich_from_semantic(
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

    # OpenAlex fallback.
    source = enrich_from_openalex(
        source
    )

    return _build_evidence_package(
        source
    )


def enrich_sources(
    sources,
):

    print("=" * 80)
    print("📚 ENRICHING RESEARCH EVIDENCE")
    print("=" * 80)

    enriched = []

    for index, source in enumerate(
        sources,
        start=1,
    ):

        print(
            f"Evidence {index}/{len(sources)}: "
            f"{source.get('title', '')}"
        )

        source = enrich_source(
            source
        )

        if source.get(
            "evidence_available"
        ):

            print(
                "✅ Evidence available"
            )

            print(
                f"   Source: "
                f"{source.get('evidence_source', '')}"
            )

            print(
                f"   Characters: "
                f"{len(source.get('evidence_text', ''))}"
            )

            enriched.append(
                source
            )

        else:

            print(
                "❌ No evidence available"
            )

    return enriched


# ==========================================================================
# EVIDENCE VERIFICATION
# ==========================================================================

def mark_evidence_verified(
    sources,
):

    accepted = []

    for source in sources:

        title = _clean(
            source.get(
                "title",
                "",
            )
        )

        if not source.get(
            "metadata_verified",
            False,
        ):

            print(
                f"❌ Rejected unverified source: "
                f"{title}"
            )

            continue

        evidence = _clean_abstract(
            source.get(
                "evidence_text",
                ""
            )
        )

        if not evidence:

            print(
                f"❌ Rejected metadata-only source: "
                f"{title}"
            )

            continue

        if len(evidence) < MIN_ABSTRACT_CHARACTERS:

            print(
                f"❌ Rejected insufficient evidence text: "
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

        url = _clean(
            source.get(
                "url",
                "",
            )
        )

        if not authors:

            print(
                f"❌ Rejected source without authors: "
                f"{title}"
            )

            continue

        if not year:

            print(
                f"❌ Rejected source without publication year: "
                f"{title}"
            )

            continue

        if not doi:

            print(
                f"❌ Rejected source without DOI: "
                f"{title}"
            )

            continue

        if not url:

            print(
                f"❌ Rejected source without URL: "
                f"{title}"
            )

            continue

        expected_source_id = _generate_source_id(
            doi
        )

        existing_source_id = _clean(
            source.get(
                "source_id",
                "",
            )
        )

        if (
            existing_source_id
            and
            existing_source_id
            != expected_source_id
        ):

            print(
                f"❌ Rejected source with invalid source_id: "
                f"{title}"
            )

            continue

        source[
            "source_id"
        ] = expected_source_id

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
            "evidence_quality"
        ] = EVIDENCE_QUALITY_MODERATE

        source[
            "evidence_verified"
        ] = True

        source[
            "verified"
        ] = True

        source[
            "verification_level"
        ] = (
            "DOI_METADATA_PLUS_ABSTRACT"
        )

        source[
            "evidence_verification"
        ] = (
            "DOI metadata was verified and "
            "a scholarly abstract was retrieved."
        )

        accepted.append(
            source
        )

    return accepted


# ==========================================================================
# LIMIT SOURCES
# ==========================================================================

def limit_sources(
    sources,
):

    def sort_key(source):

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

        return (

            source.get(
                "relevance_score",
                0,
            ),

            source.get(
                "topic_concept_coverage",
                0,
            ),

            len(
                source.get(
                    "evidence_text",
                    "",
                )
            ),

            citation_count,
        )

    return sorted(
        sources,
        key=sort_key,
        reverse=True,
    )[
        :MAX_EVIDENCE_SOURCES
    ]


# ==========================================================================
# FINAL SOURCE ID VALIDATION
# ==========================================================================

def validate_source_ids(
    sources,
):

    seen_ids = set()

    for source in sources:

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

        if not source_id:

            raise RuntimeError(
                "RESEARCH FAILED: "
                "Final source is missing source_id."
            )

        if not doi:

            raise RuntimeError(
                f"RESEARCH FAILED: "
                f"Source '{source.get('title', '')}' "
                "has no DOI."
            )

        expected_id = _generate_source_id(
            doi
        )

        if source_id != expected_id:

            raise RuntimeError(
                f"RESEARCH FAILED: "
                f"Source ID mismatch for "
                f"'{source.get('title', '')}'. "
                f"Expected '{expected_id}', "
                f"received '{source_id}'."
            )

        if source_id in seen_ids:

            raise RuntimeError(
                f"RESEARCH FAILED: "
                f"Duplicate source_id detected: "
                f"{source_id}"
            )

        seen_ids.add(
            source_id
        )

        if not source.get(
            "evidence_verified",
            False,
        ):

            raise RuntimeError(
                f"RESEARCH FAILED: "
                f"Source '{source.get('title', '')}' "
                "is not evidence verified."
            )

    return True


# ==========================================================================
# RESEARCH
# ==========================================================================

def research_topic(
    topic,
):

    topic = _clean(topic)

    if not topic:

        raise RuntimeError(
            "Research topic cannot be empty."
        )

    print("=" * 80)
    print("🔬 MINT-YT-FACTORY RESEARCH v4.3")
    print("=" * 80)

    print(
        f"Topic: {topic}"
    )

    print(
        f"Topic words: "
        f"{len(topic.split())}"
    )

    # ------------------------------------------------------------------
    # SEARCH
    # ------------------------------------------------------------------

    crossref = []
    semantic = []
    openalex = []

    try:

        crossref = search_crossref(
            topic
        )

    except Exception as error:

        print(
            "⚠️ Crossref search failed:"
        )

        print(error)

    try:

        semantic = search_semantic_scholar(
            topic
        )

    except Exception as error:

        print(
            "⚠️ Semantic Scholar search failed:"
        )

        print(error)

    try:

        openalex = search_openalex(
            topic
        )

    except Exception as error:

        print(
            "⚠️ OpenAlex search failed:"
        )

        print(error)

    # ------------------------------------------------------------------
    # DEDUPLICATE
    # ------------------------------------------------------------------

    candidates = deduplicate_sources(
        crossref
        + semantic
        + openalex
    )

    print(
        f"Unique candidates: "
        f"{len(candidates)}"
    )

    if not candidates:

        raise RuntimeError(
            "RESEARCH FAILED: "
            "No research candidates were found."
        )

    # ------------------------------------------------------------------
    # DOI FILTER
    # ------------------------------------------------------------------

    print("=" * 80)
    print("🆔 FILTERING DOI-ELIGIBLE CANDIDATES")
    print("=" * 80)

    doi_candidates = []

    rejected_no_doi = 0

    for source in candidates:

        doi = _normalize_doi(
            source.get(
                "doi",
                "",
            )
        )

        title = _clean(
            source.get(
                "title",
                "",
            )
        )

        if not doi:

            rejected_no_doi += 1

            print(
                f"⚠️ REJECTED — NO DOI: "
                f"{title}"
            )

            continue

        source[
            "doi"
        ] = doi

        doi_candidates.append(
            source
        )

    print(
        f"DOI-eligible candidates: "
        f"{len(doi_candidates)}"
    )

    print(
        f"Candidates rejected without DOI: "
        f"{rejected_no_doi}"
    )

    if not doi_candidates:

        raise RuntimeError(
            "RESEARCH FAILED: "
            "No candidates with DOI identifiers were found."
        )

    candidates = doi_candidates

    # ------------------------------------------------------------------
    # SOURCE IDS
    # ------------------------------------------------------------------

    for source in candidates:

        source[
            "source_id"
        ] = _generate_source_id(
            source[
                "doi"
            ]
        )

    # ------------------------------------------------------------------
    # STRICT RELEVANCE
    # ------------------------------------------------------------------

    relevant = relevance_filter(
        topic,
        candidates,
    )

    if not relevant:

        raise RuntimeError(
            "RESEARCH FAILED: "
            "No sufficiently relevant sources found."
        )

    print("=" * 80)
    print(
        f"🎯 RELEVANT DOI SOURCES: "
        f"{len(relevant)}"
    )
    print("=" * 80)

    # ------------------------------------------------------------------
    # DOI / METADATA VERIFICATION
    # ------------------------------------------------------------------

    print("=" * 80)
    print("🧪 VERIFYING SOURCES")
    print("=" * 80)

    verified_metadata = []

    for index, source in enumerate(
        relevant,
        start=1,
    ):

        title = source.get(
            "title",
            "",
        )

        doi = _normalize_doi(
            source.get(
                "doi",
                "",
            )
        )

        print(
            f"Checking source "
            f"{index}/{len(relevant)}: "
            f"{title}"
        )

        print(
            f"   DOI: {doi}"
        )

        databases = set(
            source.get(
                "source_databases",
                [],
            )
        )

        if source.get(
            "source_database"
        ):

            databases.add(
                source[
                    "source_database"
                ]
            )

        verified_ok = False

        # --------------------------------------------------------------
        # Prefer Crossref as DOI registry verification when available.
        # --------------------------------------------------------------

        verified_ok = (
            verify_crossref_source(
                source
            )
        )

        # --------------------------------------------------------------
        # If Crossref fails, verify using originating database.
        # --------------------------------------------------------------

        if not verified_ok:

            if "Semantic Scholar" in databases:

                verified_ok = (
                    verify_semantic_source(
                        source
                    )
                )

            elif "OpenAlex" in databases:

                verified_ok = (
                    verify_openalex_source(
                        source
                    )
                )

        if verified_ok:

            print(
                "✅ METADATA VERIFIED"
            )

            verified_metadata.append(
                source
            )

        else:

            print(
                "❌ NOT VERIFIED"
            )

    if not verified_metadata:

        raise RuntimeError(
            "RESEARCH FAILED: "
            "No DOI-verified sources remained."
        )

    print(
        f"DOI-verified sources: "
        f"{len(verified_metadata)}"
    )

    # ------------------------------------------------------------------
    # EVIDENCE ENRICHMENT
    # ------------------------------------------------------------------

    verified_metadata = enrich_sources(
        verified_metadata
    )

    # ------------------------------------------------------------------
    # EVIDENCE VERIFICATION
    # ------------------------------------------------------------------

    evidence_sources = (
        mark_evidence_verified(
            verified_metadata
        )
    )

    if not evidence_sources:

        raise RuntimeError(
            "RESEARCH FAILED: "
            "No evidence-backed sources remained."
        )

    print(
        f"Evidence-backed sources: "
        f"{len(evidence_sources)}"
    )

    # ------------------------------------------------------------------
    # FINAL RELEVANCE RECHECK
    # ------------------------------------------------------------------

    print("=" * 80)
    print("🔍 FINAL EVIDENCE RELEVANCE CHECK")
    print("=" * 80)

    evidence_sources = relevance_filter(
        topic,
        evidence_sources,
    )

    evidence_sources = [
        source
        for source in evidence_sources
        if source.get(
            "evidence_verified",
            False,
        )
    ]

    print(
        f"Final relevant evidence sources: "
        f"{len(evidence_sources)}"
    )

    # ------------------------------------------------------------------
    # LIMIT
    # ------------------------------------------------------------------

    evidence_sources = limit_sources(
        evidence_sources
    )

    print(
        f"Sources selected for final package: "
        f"{len(evidence_sources)}"
    )

    # ------------------------------------------------------------------
    # MINIMUM SOURCE GATE
    # ------------------------------------------------------------------

    if len(
        evidence_sources
    ) < MIN_ACCEPTED_SOURCES:

        print("=" * 80)
        print("❌ RESEARCH FAILED")
        print("=" * 80)

        print(
            f"Only "
            f"{len(evidence_sources)} "
            "evidence-backed relevant source(s) found."
        )

        print(
            f"At least "
            f"{MIN_ACCEPTED_SOURCES} "
            "are required."
        )

        raise RuntimeError(
            "RESEARCH FAILED: "
            f"Only {len(evidence_sources)} "
            "evidence-backed relevant source(s) found."
        )

    # ------------------------------------------------------------------
    # SOURCE ID VALIDATION
    # ------------------------------------------------------------------

    print("=" * 80)
    print("🆔 VALIDATING AUTHORITATIVE SOURCE IDs")
    print("=" * 80)

    validate_source_ids(
        evidence_sources
    )

    print(
        "✅ All final sources have valid stable source_id values."
    )

    # ------------------------------------------------------------------
    # FINAL PACKAGE
    # ------------------------------------------------------------------

    package = {

        "topic":
            topic,

        "status":
            "VERIFIED",

        "verified":
            True,

        "verified_at":
            int(
                time.time()
            ),

        "verification_policy": {

            "minimum_sources":
                MIN_ACCEPTED_SOURCES,

            "metadata_required":
                True,

            "doi_required":
                True,

            "abstract_required":
                True,

            "minimum_abstract_characters":
                MIN_ABSTRACT_CHARACTERS,

            "metadata_only_sources_allowed":
                False,

            "evidence_verification_required":
                True,

            "strict_topic_relevance":
                True,

            "final_relevance_recheck":
                True,

            "full_text_required":
                False,

            "abstract_is_full_text":
                False,

            "authoritative_source_id_required":
                True,

            "source_id_algorithm":
                "sha256(normalized_doi)[:12]",
        },

        "source_count":
            len(
                evidence_sources
            ),

        "evidence_source_count":
            len(
                evidence_sources
            ),

        "sources":
            evidence_sources,
    }

    # ------------------------------------------------------------------
    # OUTPUT
    # ------------------------------------------------------------------

    print("=" * 80)
    print("✅ RESEARCH VERIFIED")
    print("=" * 80)

    print(
        f"Evidence-backed relevant sources: "
        f"{len(evidence_sources)}"
    )

    for index, source in enumerate(
        evidence_sources,
        start=1,
    ):

        print(
            f"{index}. "
            f"{source['title']}"
        )

        print(
            f"   Source ID: "
            f"{source['source_id']}"
        )

        print(
            f"   DOI: "
            f"{source['doi']}"
        )

        print(
            f"   Databases: "
            f"{', '.join(source.get('source_databases', []))}"
        )

        print(
            f"   Relevance: "
            f"{source.get('relevance_class', '')}"
        )

        print(
            f"   Score: "
            f"{source.get('relevance_score', 0)}"
        )

        print(
            f"   Concept coverage: "
            f"{source.get('topic_concept_coverage', 0):.1%}"
        )

        print(
            f"   Evidence: "
            f"{source.get('evidence_source', '')}"
        )

        print(
            f"   Evidence characters: "
            f"{len(source.get('evidence_text', ''))}"
        )

    print("=" * 80)

    return package


# ==========================================================================
# SAVE
# ==========================================================================

def save_research(
    research,
    output_path,
):

    output_dir = os.path.dirname(
        output_path
    )

    if output_dir:

        os.makedirs(
            output_dir,
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


# ==========================================================================
# CLI
# ==========================================================================

if __name__ == "__main__":

    if len(sys.argv) < 2:

        print(
            "Usage:"
        )

        print(
            'python research.py "your topic"'
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