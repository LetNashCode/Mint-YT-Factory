"""
research.py
Mint-YT-Factory

Version 2.3

Research-first scientific evidence layer.

FLOW:

Topic
  ↓
Crossref + Semantic Scholar + OpenAlex
  ↓
Deduplicate
  ↓
Verify DOI / identity
  ↓
Enrich abstract/evidence
  ↓
Build structured evidence package
  ↓
Relevance filter
  ↓
Evidence-quality filter
  ↓
Minimum 2 evidence-backed sources
  ↓
Verified research package

IMPORTANT:

- DOI verification is NOT the same as evidence verification.
- Metadata-only sources are NEVER accepted as verified evidence.
- Abstracts are NEVER invented.
- Sources must actually exist.
- Minimum 2 evidence-backed sources are required.
- Semantic Scholar rate limits are handled gracefully.
- OpenAlex is used as a free evidence fallback.
- Long research topics are fully supported.
- next_short.topic is treated as the complete research topic.
- Evidence text is explicitly separated from metadata.
- Gemini is NOT used to create or summarize evidence here.
"""


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

MAX_CROSSREF_RESULTS = 10

MAX_SEMANTIC_RESULTS = 8

MAX_OPENALEX_RESULTS = 8

MIN_ACCEPTED_SOURCES = 2

MAX_EVIDENCE_SOURCES = 5

SEMANTIC_RETRIES = 3

SEMANTIC_BACKOFF_SECONDS = 3

# --------------------------------------------------------------------------
# Evidence requirements
# --------------------------------------------------------------------------

MIN_ABSTRACT_CHARACTERS = 120

MAX_EVIDENCE_TEXT_CHARACTERS = 12000

EVIDENCE_QUALITY_HIGH = "high"

EVIDENCE_QUALITY_MODERATE = "moderate"

EVIDENCE_QUALITY_NONE = "none"

# --------------------------------------------------------------------------
# OpenAlex polite pool
# --------------------------------------------------------------------------

OPENALEX_EMAIL = (
    "mint-yt-factory@example.com"
)

USER_AGENT = (
    "Mint-YT-Factory/2.3 "
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

    - transient failures
    - 429 rate limits
    - temporary 5xx errors
    """

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

                    time.sleep(
                        delay
                    )

                    continue

            # --------------------------------------------------------------
            # SERVER ERROR
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

                time.sleep(
                    delay
                )

                continue

            response.raise_for_status()

            return response.json()

        except Exception as error:

            last_error = error

            if attempt < retries:

                delay = backoff * (
                    attempt + 1
                )

                time.sleep(
                    delay
                )

                continue

            raise last_error


# ==========================================================================
# TEXT HELPERS
# ==========================================================================

def _clean(
    text
):

    if text is None:

        return ""

    text = str(
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def _clean_abstract(
    text
):

    text = _clean(
        text
    )

    if not text:

        return ""

    # Remove HTML tags sometimes returned by Crossref.

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


def _normalize_doi(
    doi
):
    """
    Normalize DOI values.

    Examples:

        10.1234/example

        https://doi.org/10.1234/example

        doi:10.1234/example

    become:

        10.1234/example
    """

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
        r"^doi:\s*",
        "",
        doi,
        flags=re.IGNORECASE,
    )

    return doi.strip().rstrip(
        "."
    ).lower()


def _normalize_title(
    title
):

    title = _clean(
        title
    ).lower()

    title = re.sub(
        r"[^a-z0-9\s]",
        "",
        title,
    )

    return " ".join(
        title.split()
    )


# ==========================================================================
# AUTHOR HELPERS
# ==========================================================================

def _authors_crossref(
    item
):

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
            for x in [
                given,
                family,
            ]
            if x
        )

        if name:

            authors.append(
                name
            )

    return ", ".join(
        authors
    )


def _authors_semantic(
    item
):

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

def _extract_year(
    item
):

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
    inverted_index
):
    """
    OpenAlex stores abstracts as an inverted index.

    Convert it back into normal text.
    """

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
        key=lambda x: x[0]
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
    source
):
    """
    Build a structured evidence package.

    IMPORTANT:

    This function NEVER creates scientific findings.

    It only packages evidence that was actually retrieved from
    scholarly databases.
    """

    abstract = _clean_abstract(
        source.get(
            "abstract",
            "",
        )
    )

    # ----------------------------------------------------------------------
    # Evidence available
    # ----------------------------------------------------------------------

    if abstract:

        evidence_available = True

        evidence_type = (
            "abstract"
        )

        evidence_quality = (
            EVIDENCE_QUALITY_HIGH
        )

        evidence_text = abstract

        evidence_notes = (
            "Evidence text is the scholarly "
            "abstract retrieved from a research "
            "metadata database."
        )

    else:

        evidence_available = False

        evidence_type = (
            "metadata_only"
        )

        evidence_quality = (
            EVIDENCE_QUALITY_NONE
        )

        evidence_text = ""

        evidence_notes = (
            "No abstract or evidence text was "
            "available. Metadata alone must NOT "
            "be used to support detailed scientific "
            "claims."
        )

    # ----------------------------------------------------------------------
    # Safety limit
    # ----------------------------------------------------------------------

    if len(
        evidence_text
    ) > MAX_EVIDENCE_TEXT_CHARACTERS:

        evidence_text = evidence_text[
            :MAX_EVIDENCE_TEXT_CHARACTERS
        ]

        evidence_notes += (
            " Evidence text was safely truncated "
            "to the configured character limit."
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
# TOPIC RELEVANCE
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
    "does",
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
    "survive",
}


def _topic_terms(
    topic
):

    words = re.findall(
        r"[a-zA-Z0-9]+",
        _clean(
            topic
        ).lower(),
    )

    return {
        word
        for word in words
        if len(word) >= 3
        and word not in STOPWORDS
    }


def _topic_phrases(
    topic
):
    """
    Extract useful adjacent 2-word phrases.

    Helps long continuation topics.
    """

    words = re.findall(
        r"[a-zA-Z0-9]+",
        _clean(
            topic
        ).lower(),
    )

    words = [
        word
        for word in words
        if len(word) >= 3
        and word not in STOPWORDS
    ]

    phrases = set()

    for index in range(
        len(words) - 1
    ):

        phrases.add(
            f"{words[index]} "
            f"{words[index + 1]}"
        )

    return phrases


def _relevance_score(
    topic,
    source
):
    """
    Relevance scoring for both short and long topics.

    Title matches are weighted more heavily.

    Abstract matches provide supporting evidence.

    Meaningful two-word phrases receive extra weight.
    """

    terms = _topic_terms(
        topic
    )

    phrases = _topic_phrases(
        topic
    )

    if not terms:

        return 0

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

    title = re.sub(
        r"[^a-z0-9\s]",
        " ",
        title,
    )

    abstract = re.sub(
        r"[^a-z0-9\s]",
        " ",
        abstract,
    )

    title = re.sub(
        r"\s+",
        " ",
        title,
    ).strip()

    abstract = re.sub(
        r"\s+",
        " ",
        abstract,
    ).strip()

    score = 0

    matched_terms = []

    title_matches = 0

    abstract_matches = 0

    # ----------------------------------------------------------------------
    # Individual term matches
    # ----------------------------------------------------------------------

    for term in terms:

        pattern = (
            rf"\b{re.escape(term)}\b"
        )

        in_title = bool(
            re.search(
                pattern,
                title,
            )
        )

        in_abstract = bool(
            re.search(
                pattern,
                abstract,
            )
        )

        if in_title:

            title_matches += 1

            score += 3

            matched_terms.append(
                term
            )

        elif in_abstract:

            abstract_matches += 1

            score += 1

            matched_terms.append(
                term
            )

    # ----------------------------------------------------------------------
    # Phrase matches
    # ----------------------------------------------------------------------

    phrase_matches = 0

    for phrase in phrases:

        pattern = (
            rf"\b{re.escape(phrase)}\b"
        )

        if re.search(
            pattern,
            title,
        ):

            score += 4

            phrase_matches += 1

        elif re.search(
            pattern,
            abstract,
        ):

            score += 2

            phrase_matches += 1

    # ----------------------------------------------------------------------
    # Coverage
    # ----------------------------------------------------------------------

    matched_count = len(
        set(
            matched_terms
        )
    )

    coverage = (
        matched_count
        / max(
            len(terms),
            1,
        )
    )

    # ----------------------------------------------------------------------
    # Strong title relevance
    # ----------------------------------------------------------------------

    if title_matches >= 2:

        score += 3

    if phrase_matches >= 1:

        score += 2

    source[
        "matched_terms"
    ] = sorted(
        set(
            matched_terms
        )
    )

    source[
        "title_match_count"
    ] = title_matches

    source[
        "abstract_match_count"
    ] = abstract_matches

    source[
        "phrase_match_count"
    ] = phrase_matches

    source[
        "topic_term_coverage"
    ] = round(
        coverage,
        3,
    )

    return score


def _minimum_relevance_score(
    topic
):

    terms = _topic_terms(
        topic
    )

    term_count = len(
        terms
    )

    if term_count <= 2:

        return 3

    if term_count <= 4:

        return 5

    if term_count <= 7:

        return 6

    if term_count <= 10:

        return 7

    return 8


def relevance_filter(
    topic,
    sources
):

    accepted = []

    minimum_score = (
        _minimum_relevance_score(
            topic
        )
    )

    for source in sources:

        score = _relevance_score(
            topic,
            source,
        )

        source[
            "relevance_score"
        ] = score

        if score >= minimum_score:

            accepted.append(
                source
            )

        else:

            print(
                f"⚠️ Rejected low-relevance source: "
                f"{source.get('title', '')}"
            )

            print(
                f"   Score: {score} "
                f"/ Required: {minimum_score}"
            )

    return accepted


# ==========================================================================
# CROSSREF SEARCH
# ==========================================================================

def search_crossref(
    topic
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
                "URL,link,abstract"
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

        source = _build_evidence_package(
            source
        )

        results.append(
            source
        )

    print(
        f"Crossref results: "
        f"{len(results)}"
    )

    return results


# ==========================================================================
# SEMANTIC SCHOLAR SEARCH
# ==========================================================================

def search_semantic_scholar(
    topic
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
            "⚠️ Semantic Scholar search failed:"
        )

        print(
            error
        )

        return []

    papers = data.get(
        "data",
        [],
    )

    results = []

    for paper in papers:

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

        source = _build_evidence_package(
            source
        )

        results.append(
            source
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
    topic
):

    print("=" * 80)
    print("🔎 OPENALEX SEARCH")
    print("=" * 80)

    params = {

        "search":
            topic,

        "per-page":
            MAX_OPENALEX_RESULTS,

        "mailto":
            OPENALEX_EMAIL,
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

        print(
            error
        )

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
                "",
            )
        )

        publication_year = item.get(
            "publication_year"
        )

        url = _clean(
            ids.get(
                "openalex",
                "",
            )
        )

        if not url:

            item_id = _clean(
                item.get(
                    "id",
                    "",
                )
            )

            if item_id:

                url = item_id

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
                publication_year,

            "doi":
                doi,

            "url":
                f"https://doi.org/{doi}",

            "openalex_url":
                url,

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

        source = _build_evidence_package(
            source
        )

        results.append(
            source
        )

    print(
        f"OpenAlex results: "
        f"{len(results)}"
    )

    return results


# ==========================================================================
# DEDUPLICATION
# ==========================================================================

def deduplicate_sources(
    sources
):

    seen_dois = set()

    seen_titles = set()

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

        if (
            doi
            and doi in seen_dois
        ):

            continue

        if (
            title
            and title in seen_titles
        ):

            continue

        if doi:

            seen_dois.add(
                doi
            )

        if title:

            seen_titles.add(
                title
            )

        unique.append(
            source
        )

    return unique


# ==========================================================================
# CROSSREF DOI VERIFICATION
# ==========================================================================

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
            retries=2,
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

        if (
            returned_doi
            != doi
        ):

            return False

        if not returned_title:

            return False

        source[
            "metadata_verified"
        ] = True

        source[
            "verified_title"
        ] = returned_title

        # ------------------------------------------------------------------
        # Prefer the verified Crossref abstract if available.
        # ------------------------------------------------------------------

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
            "doi"
        ] = returned_doi

        source[
            "verification"
        ] = (
            "DOI resolved through Crossref."
        )

        source = _build_evidence_package(
            source
        )

        return True

    except Exception as error:

        source[
            "verification_error"
        ] = str(error)

        return False


# ==========================================================================
# SEMANTIC SCHOLAR DOI VERIFICATION
# ==========================================================================

def verify_semantic_source(
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

        # --------------------------------------------------------------
        # If Semantic Scholar gives us a DOI, it must agree.
        # --------------------------------------------------------------

        if (
            returned_doi
            and
            returned_doi != doi
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

        publication_types = (
            data.get(
                "publicationTypes",
                [],
            )
            or []
        )

        if publication_types:

            source[
                "publication_types"
            ] = publication_types

            source[
                "publication_type"
            ] = publication_types[
                0
            ]

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

        source = _build_evidence_package(
            source
        )

        return True

    except Exception as error:

        source[
            "verification_error"
        ] = str(error)

        return False


# ==========================================================================
# OPENALEX DOI ENRICHMENT
# ==========================================================================

def enrich_from_openalex(
    source
):

    """
    Retrieve an abstract from OpenAlex using DOI.

    Used as an evidence fallback.
    """

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

        params = {
            "mailto":
                OPENALEX_EMAIL
        }

        data = _get(
            url,
            params,
            retries=2,
            backoff=2,
        )

        # --------------------------------------------------------------
        # Abstract
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # Additional metadata
        # --------------------------------------------------------------

        source[
            "openalex_citation_count"
        ] = data.get(
            "cited_by_count",
            0,
        ) or 0

        open_access = (
            data.get(
                "open_access",
                {}
            )
            or {}
        )

        source[
            "open_access"
        ] = bool(
            open_access.get(
                "is_oa",
                False,
            )
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
        ] = str(error)

    return source


# ==========================================================================
# EVIDENCE ENRICHMENT
# ==========================================================================

def enrich_source(
    source
):
    """
    Evidence priority:

    1. Existing abstract
    2. Semantic Scholar abstract
    3. OpenAlex abstract

    No evidence is invented.
    """

    existing = _clean_abstract(
        source.get(
            "abstract",
            "",
        )
    )

    if existing:

        source[
            "abstract"
        ] = existing

        return _build_evidence_package(
            source
        )

    doi = _normalize_doi(
        source.get(
            "doi",
            "",
        )
    )

    if not doi:

        return _build_evidence_package(
            source
        )

    source[
        "doi"
    ] = doi

    database = source.get(
        "source_database",
        "",
    )

    # ----------------------------------------------------------------------
    # Semantic Scholar
    # ----------------------------------------------------------------------

    if database != "Semantic Scholar":

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

                publication_types = (
                    data.get(
                        "publicationTypes",
                        [],
                    )
                    or []
                )

                if publication_types:

                    source[
                        "publication_types"
                    ] = publication_types

                    source[
                        "publication_type"
                    ] = publication_types[
                        0
                    ]

                return _build_evidence_package(
                    source
                )

        except Exception as error:

            source[
                "semantic_enrichment_error"
            ] = str(error)

    # ----------------------------------------------------------------------
    # OpenAlex fallback
    # ----------------------------------------------------------------------

    source = enrich_from_openalex(
        source
    )

    return _build_evidence_package(
        source
    )


def enrich_sources(
    sources
):

    print("=" * 80)
    print("📚 ENRICHING RESEARCH EVIDENCE")
    print("=" * 80)

    for index, source in enumerate(
        sources,
        start=1,
    ):

        print(
            f"Evidence {index}/{len(sources)}: "
            f"{source.get('title', '')}"
        )

        enrich_source(
            source
        )

        source = _build_evidence_package(
            source
        )

        if source.get(
            "evidence_available"
        ):

            print(
                "✅ Evidence available"
            )

            print(
                f"   Type: "
                f"{source.get('evidence_type', 'unknown')}"
            )

            print(
                f"   Quality: "
                f"{source.get('evidence_quality', 'unknown')}"
            )

            print(
                f"   Characters: "
                f"{len(source.get('evidence_text', ''))}"
            )

        else:

            print(
                "❌ No evidence available"
            )

    return sources


# ==========================================================================
# EVIDENCE VERIFICATION
# ==========================================================================

def mark_evidence_verified(
    sources
):
    """
    A source becomes evidence-verified ONLY when:

    - DOI metadata is verified
    - authors exist
    - year exists
    - DOI exists
    - URL exists
    - actual evidence text exists
    - evidence text is sufficiently substantial

    IMPORTANT:

    DOI verification alone is NEVER evidence verification.
    """

    accepted = []

    for source in sources:

        title = _clean(
            source.get(
                "title",
                "",
            )
        )

        # ------------------------------------------------------------------
        # Metadata verification
        # ------------------------------------------------------------------

        if not source.get(
            "metadata_verified",
            False,
        ):

            print(
                f"❌ Rejected unverified source: "
                f"{title}"
            )

            continue

        # ------------------------------------------------------------------
        # Evidence text
        # ------------------------------------------------------------------

        abstract = _clean_abstract(
            source.get(
                "evidence_text",
                ""
            )
            or source.get(
                "abstract",
                "",
            )
        )

        if not abstract:

            print(
                f"❌ Rejected metadata-only source: "
                f"{title}"
            )

            source[
                "evidence_available"
            ] = False

            source[
                "evidence_quality"
            ] = EVIDENCE_QUALITY_NONE

            continue

        if len(
            abstract
        ) < MIN_ABSTRACT_CHARACTERS:

            print(
                f"❌ Rejected insufficient evidence text: "
                f"{title}"
            )

            print(
                f"   Evidence characters: "
                f"{len(abstract)}"
            )

            continue

        # ------------------------------------------------------------------
        # Required metadata
        # ------------------------------------------------------------------

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
                f"❌ Rejected source without year: "
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

        # ------------------------------------------------------------------
        # Final evidence package
        # ------------------------------------------------------------------

        source[
            "doi"
        ] = doi

        source[
            "abstract"
        ] = abstract

        source[
            "evidence_text"
        ] = abstract

        source[
            "evidence_available"
        ] = True

        source[
            "evidence_type"
        ] = "abstract"

        source[
            "evidence_quality"
        ] = EVIDENCE_QUALITY_HIGH

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
            "A non-empty scholarly abstract "
            "was retrieved and attached to "
            "verified DOI metadata."
        )

        accepted.append(
            source
        )

    return accepted


# ==========================================================================
# LIMIT EVIDENCE SOURCES
# ==========================================================================

def limit_sources(
    sources
):
    """
    Keep the strongest evidence-backed sources.

    Priority:

    1. relevance score
    2. topic coverage
    3. evidence quality
    4. evidence length
    5. citation count
    """

    def sort_key(
        source
    ):

        evidence_quality = (
            1
            if source.get(
                "evidence_quality"
            )
            == EVIDENCE_QUALITY_HIGH
            else 0
        )

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
                "topic_term_coverage",
                0,
            ),

            evidence_quality,

            len(
                source.get(
                    "evidence_text",
                    "",
                )
            ),

            citation_count,
        )

    sources = sorted(
        sources,
        key=sort_key,
        reverse=True,
    )

    return sources[
        :MAX_EVIDENCE_SOURCES
    ]


# ==========================================================================
# RESEARCH PACKAGE
# ==========================================================================

def research_topic(
    topic
):

    topic = _clean(
        topic
    )

    if not topic:

        raise RuntimeError(
            "Research topic cannot be empty."
        )

    print("=" * 80)
    print("🔬 MINT-YT-FACTORY RESEARCH")
    print("=" * 80)

    print(
        f"Topic: {topic}"
    )

    print(
        f"Topic words: "
        f"{len(topic.split())}"
    )

    # ----------------------------------------------------------------------
    # SEARCH
    # ----------------------------------------------------------------------

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

        print(
            error
        )

    try:

        semantic = search_semantic_scholar(
            topic
        )

    except Exception as error:

        print(
            "⚠️ Semantic Scholar search failed:"
        )

        print(
            error
        )

    try:

        openalex = search_openalex(
            topic
        )

    except Exception as error:

        print(
            "⚠️ OpenAlex search failed:"
        )

        print(
            error
        )

    candidates = deduplicate_sources(
        crossref
        + semantic
        + openalex
    )

    print(
        f"Unique candidates: "
        f"{len(candidates)}"
    )

    # ----------------------------------------------------------------------
    # FIRST RELEVANCE FILTER
    # ----------------------------------------------------------------------

    relevant = relevance_filter(
        topic,
        candidates,
    )

    print(
        f"Relevant candidates: "
        f"{len(relevant)}"
    )

    if not relevant:

        raise RuntimeError(
            "RESEARCH FAILED: "
            "No sufficiently relevant sources found."
        )

    # ----------------------------------------------------------------------
    # VERIFY DOI / SOURCE IDENTITY
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🧪 VERIFYING SOURCES")
    print("=" * 80)

    verified_metadata = []

    for index, source in enumerate(
        relevant,
        start=1,
    ):

        print(
            f"Checking source "
            f"{index}/{len(relevant)}: "
            f"{source.get('title', '')}"
        )

        database = source.get(
            "source_database",
            "",
        )

        verified_ok = False

        if database == "Crossref":

            verified_ok = (
                verify_crossref_source(
                    source
                )
            )

        elif database == "Semantic Scholar":

            verified_ok = (
                verify_semantic_source(
                    source
                )
            )

        elif database == "OpenAlex":

            # --------------------------------------------------------------
            # OpenAlex DOI identity is cross-checked against Crossref.
            # --------------------------------------------------------------

            verified_ok = (
                verify_crossref_source(
                    source
                )
            )

            # --------------------------------------------------------------
            # If Crossref is unavailable, retain OpenAlex identity only
            # when DOI + title exist.
            #
            # Evidence verification still requires actual evidence text.
            # --------------------------------------------------------------

            if not verified_ok:

                verified_ok = bool(
                    source.get(
                        "doi"
                    )
                    and source.get(
                        "title"
                    )
                )

                if verified_ok:

                    source[
                        "metadata_verified"
                    ] = True

                    source[
                        "verification"
                    ] = (
                        "OpenAlex DOI metadata accepted "
                        "after Crossref verification was "
                        "unavailable."
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

    # ----------------------------------------------------------------------
    # ENRICH ABSTRACTS / EVIDENCE
    # ----------------------------------------------------------------------

    verified_metadata = enrich_sources(
        verified_metadata
    )

    # ----------------------------------------------------------------------
    # EVIDENCE GATE
    # ----------------------------------------------------------------------

    evidence_sources = (
        mark_evidence_verified(
            verified_metadata
        )
    )

    # ----------------------------------------------------------------------
    # RELEVANCE AGAIN AFTER ENRICHMENT
    # ----------------------------------------------------------------------

    evidence_sources = relevance_filter(
        topic,
        evidence_sources,
    )

    # ----------------------------------------------------------------------
    # LIMIT
    # ----------------------------------------------------------------------

    evidence_sources = limit_sources(
        evidence_sources
    )

    # ----------------------------------------------------------------------
    # REQUIRE MULTIPLE EVIDENCE SOURCES
    # ----------------------------------------------------------------------

    if len(
        evidence_sources
    ) < MIN_ACCEPTED_SOURCES:

        print("=" * 80)
        print("❌ RESEARCH FAILED")
        print("=" * 80)

        print(
            f"Only "
            f"{len(evidence_sources)} "
            "evidence-backed source(s) found."
        )

        print(
            f"At least "
            f"{MIN_ACCEPTED_SOURCES} "
            "are required."
        )

        raise RuntimeError(

            "RESEARCH FAILED: "
            f"Only {len(evidence_sources)} "
            "evidence-backed source(s) found. "
            f"At least {MIN_ACCEPTED_SOURCES} "
            "are required."
        )

    # ----------------------------------------------------------------------
    # FINAL EVIDENCE PACKAGE
    # ----------------------------------------------------------------------

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

    # ----------------------------------------------------------------------
    # FINAL OUTPUT
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("✅ RESEARCH VERIFIED")
    print("=" * 80)

    print(
        f"Evidence-backed sources: "
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
            f"   DOI: "
            f"{source['doi']}"
        )

        print(
            f"   Source: "
            f"{source['source_database']}"
        )

        print(
            f"   Relevance score: "
            f"{source.get('relevance_score', 0)}"
        )

        print(
            f"   Topic coverage: "
            f"{source.get('topic_term_coverage', 0):.1%}"
        )

        print(
            f"   Evidence source: "
            f"{source.get('evidence_source', 'UNKNOWN')}"
        )

        print(
            f"   Evidence type: "
            f"{source.get('evidence_type', 'UNKNOWN')}"
        )

        print(
            f"   Evidence quality: "
            f"{source.get('evidence_quality', 'UNKNOWN')}"
        )

        print(
            f"   Evidence characters: "
            f"{len(source.get('evidence_text', ''))}"
        )

        print(
            f"   Evidence verified: "
            f"{source.get('evidence_verified', False)}"
        )

        print(
            f"   Verification level: "
            f"{source.get('verification_level', 'UNKNOWN')}"
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
# CLI TEST
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

        print(
            output
        )

    except Exception as error:

        print("=" * 80)
        print("❌ RESEARCH FAILED")
        print("=" * 80)

        print(
            error
        )

        sys.exit(1)