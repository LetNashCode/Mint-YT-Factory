"""
research.py
Mint-YT-Factory

Version 5.0

Research-first scientific evidence layer.

Pipeline:

Topic
  -> Crossref + Semantic Scholar + OpenAlex
  -> DOI filtering
  -> Deduplication / merge
  -> Strict relevance scoring
  -> DOI / identity verification
  -> Evidence enrichment
  -> Evidence quality + study-design classification
  -> Final relevance recheck
  -> Independent-source validation
  -> Stable authoritative source_id
  -> Final validation
  -> VERIFIED research package

Design goals:
- DOI verification is separate from evidence verification.
- Metadata is never treated as scientific evidence.
- Abstracts are accepted only when actually retrieved from a source.
- No evidence is invented or summarized by Gemini.
- Stable source_id is derived from normalized DOI.
- Scene/claim verification remains compatible with verify_claims.py.
- At least two relevant, evidence-backed sources are required.
- Crossref failure falls back through Semantic Scholar and OpenAlex.
- Source identity is checked against authoritative metadata.
- Relevance is recalculated after evidence enrichment.
- Weak or unrelated sources are rejected.
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

CROSSREF_URL = "https://api.crossref.org/v1/works"

SEMANTIC_SCHOLAR_URL = (
    "https://api.semanticscholar.org/graph/v1/paper/search"
)

SEMANTIC_PAPER_URL = (
    "https://api.semanticscholar.org/graph/v1/paper"
)

OPENALEX_URL = "https://api.openalex.org/works"

TIMEOUT = 30

MAX_CROSSREF_RESULTS = 15
MAX_SEMANTIC_RESULTS = 10
MAX_OPENALEX_RESULTS = 12

MIN_ACCEPTED_SOURCES = 2
MAX_EVIDENCE_SOURCES = 5

MIN_ABSTRACT_CHARACTERS = 120
MAX_EVIDENCE_TEXT_CHARACTERS = 12000

SEMANTIC_RETRIES = 2
SEMANTIC_BACKOFF_SECONDS = 4

TITLE_SIMILARITY_MINIMUM = 0.55


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
    "Mint-YT-Factory/5.0 "
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


def _title_tokens(title):

    return set(
        token
        for token in re.findall(
            r"[a-z0-9]+",
            _normalize_title(title),
        )
        if len(token) >= 3
    )


def _title_similarity(
    title_a,
    title_b,
):

    tokens_a = _title_tokens(
        title_a
    )

    tokens_b = _title_tokens(
        title_b
    )

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = len(
        tokens_a.intersection(
            tokens_b
        )
    )

    union = len(
        tokens_a.union(
            tokens_b
        )
    )

    if not union:
        return 0.0

    return (
        intersection / union
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

    "happen",
    "happens",
    "really",
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

    "memory": {
        "memory",
        "memories",
        "remember",
        "remembering",
        "recall",
        "learning",
        "learned",
    },

    "sleep": {
        "sleep",
        "sleeping",
        "dream",
        "dreaming",
        "circadian",
        "insomnia",
    },

    "sound": {
        "sound",
        "sounds",
        "hearing",
        "auditory",
        "acoustic",
        "frequency",
        "frequencies",
    },

    "light": {
        "light",
        "visual",
        "vision",
        "photoreceptor",
        "photoreceptors",
        "wavelength",
        "wavelengths",
    },

    "gravity": {
        "gravity",
        "gravitational",
        "gravitation",
        "weight",
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

    evidence = _clean(
        source.get(
            "evidence_text"
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

    evidence_clean = re.sub(
        r"[^a-z0-9\s]",
        " ",
        evidence,
    )

    title_clean = re.sub(
        r"\s+",
        " ",
        title_clean,
    ).strip()

    evidence_clean = re.sub(
        r"\s+",
        " ",
        evidence_clean,
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

    evidence_concepts = _concepts_from_text(
        evidence_clean
    )

    title_concept_matches = (
        topic_concepts
        .intersection(
            title_concepts
        )
    )

    evidence_concept_matches = (
        topic_concepts
        .intersection(
            evidence_concepts
        )
    )

    score = 0

    matched_terms = []

    title_term_matches = 0

    evidence_term_matches = 0

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

            score += 4

        elif _stem_like_match(
            term,
            evidence_clean,
        ):

            evidence_term_matches += 1

            matched_terms.append(
                term
            )

            score += 1

    # ------------------------------------------------------------------
    # CONCEPT MATCHES
    # ------------------------------------------------------------------

    score += (
        len(title_concept_matches) * 6
    )

    score += (
        len(
            evidence_concept_matches
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

    evidence_concept_count = len(
        evidence_concept_matches
    )

    if concept_count >= 2:

        if title_concept_count >= 2:

            relevance_class = "strong"

        elif (
            title_concept_count >= 1
            and evidence_concept_count >= 2
        ):

            relevance_class = "strong"

        elif (
            title_concept_count >= 1
            and evidence_concept_count >= 1
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
            and evidence_term_matches >= 2
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
        "human",
        "technology",
        "quantum",
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
                evidence_concept_matches
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
        evidence_concept_matches
    )

    source[
        "title_match_count"
    ] = title_term_matches

    source[
        "abstract_match_count"
    ] = evidence_term_matches

    source[
        "topic_concept_coverage"
    ] = round(
        (
            len(
                title_concept_matches
                .union(
                    evidence_concept_matches
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

    source[
        "relevance_score"
    ] = score

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
    label="STRICT RELEVANCE FILTER",
):

    accepted = []

    print("=" * 80)
    print(
        f"🎯 {label}"
    )
    print("=" * 80)

    topic_concepts = _topic_concepts(
        topic
    )

    print(
        "Topic concepts: "
        + (
            ", ".join(
                sorted(
                    topic_concepts
                )
            )
            or "none"
        )
    )

    for source in sources:

        score = _relevance_score(
            topic,
            source,
        )

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
                f"   Evidence concepts: "
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
            "Evidence text is a retrieved scholarly "
            "abstract. It is not the full paper."
        )

    else:

        evidence_available = False

        evidence_type = "metadata_only"

        evidence_quality = (
            EVIDENCE_QUALITY_NONE
        )

        evidence_text = ""

        evidence_notes = (
            "No abstract/evidence text was retrieved. "
            "Metadata alone is not evidence."
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

        if not doi:
            continue

        url = _clean(
            paper.get(
                "url",
                "",
            )
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
                f"https://doi.org/{doi}",

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
                authors.append(
                    name
                )

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
                ""
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
                ", ".join(
                    authors
                ),

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
            not primary.get(field)
            and secondary.get(field)
        ):

            primary[field] = secondary[field]

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

    databases = set(
        primary.get(
            "source_databases",
            [],
        )
    )

    if primary.get(
        "source_database"
    ):

        databases.add(
            primary[
                "source_database"
            ]
        )

    if secondary.get(
        "source_database"
    ):

        databases.add(
            secondary[
                "source_database"
            ]
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

            existing = by_doi[
                doi
            ]

        elif title and title in by_title:

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
            by_doi[
                doi
            ] = source

        if title:
            by_title[
                title
            ] = source

    return unique


# ==========================================================================
# DOI / IDENTITY VERIFICATION
# ==========================================================================

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

    if not expected_doi or not returned_doi:

        source[
            "identity_error"
        ] = (
            f"{provider}: missing DOI "
            "in verification response."
        )

        return False

    if expected_doi != returned_doi:

        source[
            "identity_error"
        ] = (
            f"{provider}: DOI mismatch. "
            f"Expected {expected_doi}, "
            f"got {returned_doi}."
        )

        return False

    original_title = _clean(
        source.get(
            "title",
            "",
        )
    )

    returned_title = _clean(
        returned_title
    )

    similarity = _title_similarity(
        original_title,
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
            f"{provider}: title mismatch. "
            f"Similarity {similarity:.3f} < "
            f"{TITLE_SIMILARITY_MINIMUM:.2f}."
        )

        return False

    return True


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

        if not returned_doi:
            returned_doi = doi

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

        if data.get(
            "year"
        ):

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
            ] = (
                "Semantic Scholar abstract"
            )

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
            "DOI and publication identity "
            "verified through Semantic Scholar."
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

        if not returned_doi:
            returned_doi = doi

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
        ] = (
            "DOI and publication identity "
            "verified through OpenAlex."
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
# STUDY DESIGN
# ==========================================================================

def _classify_study_design(
    source,
):

    title = _clean(
        source.get(
            "title",
            "",
        )
    ).lower()

    publication_types = source.get(
        "publication_types",
        [],
    ) or []

    publication_types_text = " ".join(
        _clean(item).lower()
        for item in publication_types
    )

    text = (
        f"{title} "
        f"{publication_types_text}"
    )

    if any(
        phrase in text
        for phrase in (
            "systematic review",
            "meta-analysis",
            "meta analysis",
        )
    ):

        design = (
            "systematic_review_or_meta_analysis"
        )

    elif "review" in text:

        design = "review"

    elif any(
        phrase in text
        for phrase in (
            "randomized controlled trial",
            "randomised controlled trial",
            "randomized trial",
            "randomised trial",
        )
    ):

        design = "randomized_trial"

    elif any(
        phrase in text
        for phrase in (
            "clinical trial",
            "controlled trial",
        )
    ):

        design = (
            "clinical_or_controlled_trial"
        )

    elif any(
        phrase in text
        for phrase in (
            "longitudinal",
            "cohort",
        )
    ):

        design = "observational_cohort"

    elif any(
        phrase in text
        for phrase in (
            "cross-sectional",
            "cross sectional",
        )
    ):

        design = "cross_sectional"

    elif any(
        phrase in text
        for phrase in (
            "case report",
            "case study",
        )
    ):

        design = (
            "case_report_or_case_study"
        )

    else:

        design = (
            "research_article_or_unspecified"
        )

    source[
        "study_design"
    ] = design

    return source


def _assign_evidence_quality(
    source,
):

    evidence = _clean(
        source.get(
            "evidence_text",
            "",
        )
    )

    if not evidence:

        source[
            "evidence_quality"
        ] = EVIDENCE_QUALITY_NONE

        return source

    # Abstract-only evidence remains moderate.
    source[
        "evidence_quality"
    ] = EVIDENCE_QUALITY_MODERATE

    return source


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

        if not evidence:

            print(
                f"❌ Rejected metadata-only source: "
                f"{title}"
            )

            continue

        if len(
            evidence
        ) < MIN_ABSTRACT_CHARACTERS:

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
            "DOI/publication identity was verified "
            "and a scholarly abstract was retrieved."
        )

        _classify_study_design(
            source
        )

        _assign_evidence_quality(
            source
        )

        accepted.append(
            source
        )

    return accepted


# ==========================================================================
# SOURCE DIVERSITY
# ==========================================================================

def _source_family_key(
    source,
):

    publisher = _clean(
        source.get(
            "publisher",
            "",
        )
    ).lower()

    journal = _clean(
        source.get(
            "journal",
            "",
        )
    ).lower()

    return (
        publisher,
        journal,
    )


def validate_independent_sources(
    sources,
):

    unique_dois = {
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
        unique_dois
    ) < MIN_ACCEPTED_SOURCES:

        raise RuntimeError(
            "RESEARCH FAILED: fewer than two "
            "distinct DOI-backed sources remain."
        )

    families = {
        _source_family_key(
            source
        )
        for source in sources
    }

    return {
        "distinct_doi_count":
            len(
                unique_dois
            ),

        "distinct_publisher_journal_pairs":
            len(
                families
            ),
    }


# ==========================================================================
# LIMIT SOURCES
# ==========================================================================

def limit_sources(
    sources,
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

        quality_rank = {

            EVIDENCE_QUALITY_HIGH:
                2,

            EVIDENCE_QUALITY_MODERATE:
                1,

            EVIDENCE_QUALITY_NONE:
                0,

        }.get(
            source.get(
                "evidence_quality"
            ),
            0,
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

            quality_rank,

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
                "final source is missing source_id."
            )

        if not doi:

            raise RuntimeError(
                f"RESEARCH FAILED: "
                f"source '{source.get('title', '')}' "
                "has no DOI."
            )

        expected_id = _generate_source_id(
            doi
        )

        if source_id != expected_id:

            raise RuntimeError(
                f"RESEARCH FAILED: "
                f"source ID mismatch for "
                f"'{source.get('title', '')}'. "
                f"Expected '{expected_id}', "
                f"received '{source_id}'."
            )

        if source_id in seen_ids:

            raise RuntimeError(
                f"RESEARCH FAILED: "
                f"duplicate source_id detected: "
                f"{source_id}"
            )

        seen_ids.add(
            source_id
        )

        if source.get(
            "metadata_verified"
        ) is not True:

            raise RuntimeError(
                f"RESEARCH FAILED: "
                f"source '{source.get('title', '')}' "
                "is not metadata verified."
            )

        if source.get(
            "evidence_verified"
        ) is not True:

            raise RuntimeError(
                f"RESEARCH FAILED: "
                f"source '{source.get('title', '')}' "
                "is not evidence verified."
            )

        if source.get(
            "evidence_available"
        ) is not True:

            raise RuntimeError(
                f"RESEARCH FAILED: "
                f"source '{source.get('title', '')}' "
                "does not have evidence_available=True."
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
                f"RESEARCH FAILED: "
                f"source '{source.get('title', '')}' "
                "has insufficient evidence text."
            )

        if not source.get(
            "verified"
        ):

            raise RuntimeError(
                f"RESEARCH FAILED: "
                f"source '{source.get('title', '')}' "
                "does not have verified=True."
            )

    return True


# ==========================================================================
# FINAL PACKAGE VALIDATION
# ==========================================================================

def validate_research_package(
    package,
):

    if not isinstance(
        package,
        dict,
    ):

        raise RuntimeError(
            "RESEARCH FAILED: "
            "package is not a dictionary."
        )

    if package.get(
        "status"
    ) != "VERIFIED":

        raise RuntimeError(
            "RESEARCH FAILED: "
            "package status is not VERIFIED."
        )

    if package.get(
        "verified"
    ) is not True:

        raise RuntimeError(
            "RESEARCH FAILED: "
            "package verified flag is not True."
        )

    sources = package.get(
        "sources",
        []
    )

    if not isinstance(
        sources,
        list,
    ):

        raise RuntimeError(
            "RESEARCH FAILED: "
            "package sources are invalid."
        )

    if len(
        sources
    ) < MIN_ACCEPTED_SOURCES:

        raise RuntimeError(
            "RESEARCH FAILED: "
            "package has fewer than two sources."
        )

    validate_source_ids(
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
                f"RESEARCH FAILED: "
                f"final source is not relevant: "
                f"{source.get('title', '')}"
            )

    return True


# ==========================================================================
# RESEARCH
# ==========================================================================

def research_topic(
    topic,
):

    topic = _clean(
        topic
    )

    if not topic:

        raise RuntimeError(
            "Research topic cannot be empty."
        )

    print("=" * 80)
    print("🔬 MINT-YT-FACTORY RESEARCH v5.0")
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
            "no research candidates were found."
        )

    # ------------------------------------------------------------------
    # DOI FILTER
    # ------------------------------------------------------------------

    print("=" * 80)
    print("🆔 FILTERING DOI-ELIGIBLE CANDIDATES")
    print("=" * 80)

    doi_candidates = []

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

            print(
                f"⚠️ REJECTED — NO DOI: "
                f"{title}"
            )

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
            "RESEARCH FAILED: "
            "no candidates with DOI identifiers."
        )

    # ------------------------------------------------------------------
    # STRICT RELEVANCE
    # ------------------------------------------------------------------

    relevant = relevance_filter(
        topic,
        doi_candidates,
        label="STRICT TOPIC RELEVANCE FILTER",
    )

    if not relevant:

        raise RuntimeError(
            "RESEARCH FAILED: "
            "no sufficiently relevant sources found."
        )

    # ------------------------------------------------------------------
    # DOI / IDENTITY VERIFICATION
    # ------------------------------------------------------------------

    print("=" * 80)
    print("🧪 VERIFYING DOI + PUBLICATION IDENTITY")
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
        # CROSSREF FIRST
        # --------------------------------------------------------------

        verified_ok = (
            verify_crossref_source(
                source
            )
        )

        # --------------------------------------------------------------
        # SEMANTIC FALLBACK
        # --------------------------------------------------------------

        if not verified_ok:

            if (
                "Semantic Scholar"
                in databases
            ):

                print(
                    "   ↪ Trying Semantic Scholar fallback..."
                )

                verified_ok = (
                    verify_semantic_source(
                        source
                    )
                )

        # --------------------------------------------------------------
        # OPENALEX FALLBACK
        # --------------------------------------------------------------

        if not verified_ok:

            if (
                "OpenAlex"
                in databases
            ):

                print(
                    "   ↪ Trying OpenAlex fallback..."
                )

                verified_ok = (
                    verify_openalex_source(
                        source
                    )
                )

        if verified_ok:

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
        f"DOI/identity-verified sources: "
        f"{len(verified_metadata)}"
    )

    if not verified_metadata:

        raise RuntimeError(
            "RESEARCH FAILED: "
            "no DOI-verified sources remained."
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

    print(
        f"Evidence-backed sources: "
        f"{len(evidence_sources)}"
    )

    if not evidence_sources:

        raise RuntimeError(
            "RESEARCH FAILED: "
            "no evidence-backed sources remained."
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
        label="FINAL EVIDENCE RELEVANCE CHECK",
    )

    evidence_sources = [
        source
        for source in evidence_sources
        if source.get(
            "evidence_verified"
        ) is True
        and source.get(
            "metadata_verified"
        ) is True
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

        raise RuntimeError(
            "RESEARCH FAILED: "
            f"fewer than {MIN_ACCEPTED_SOURCES} "
            "evidence-backed relevant "
            "sources remained."
        )

    # ------------------------------------------------------------------
    # SOURCE DIVERSITY
    # ------------------------------------------------------------------

    diversity = validate_independent_sources(
        evidence_sources
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

            "identity_verification_required":
                True,

            "title_identity_similarity_minimum":
                TITLE_SIMILARITY_MINIMUM,

            "authoritative_source_id_required":
                True,

            "source_id_algorithm":
                "sha256(normalized_doi)[:12]",

            "gemini_used_for_evidence":
                False,
        },

        "source_count":
            len(
                evidence_sources
            ),

        "evidence_source_count":
            len(
                evidence_sources
            ),

        "source_diversity":
            diversity,

        "sources":
            evidence_sources,
    }

    # ------------------------------------------------------------------
    # FINAL PACKAGE VALIDATION
    # ------------------------------------------------------------------

    validate_research_package(
        package
    )

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
            f"   Evidence quality: "
            f"{source.get('evidence_quality', '')}"
        )

        print(
            f"   Study design: "
            f"{source.get('study_design', '')}"
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