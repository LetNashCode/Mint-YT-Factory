"""
research.py
Mint-YT-Factory

Version 2.1

Research-first scientific evidence layer.

FLOW:

Topic
  ↓
Crossref + Semantic Scholar
  ↓
Deduplicate
  ↓
Verify DOI / identity
  ↓
Enrich abstract/evidence
  ↓
OpenAlex fallback
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

CROSSREF_URL = "https://api.crossref.org/v1/works"

SEMANTIC_SCHOLAR_URL = (
    "https://api.semanticscholar.org/graph/v1/paper/search"
)

SEMANTIC_PAPER_URL = (
    "https://api.semanticscholar.org/graph/v1/paper"
)

OPENALEX_URL = "https://api.openalex.org/works"

TIMEOUT = 30

MAX_CROSSREF_RESULTS = 10

MAX_SEMANTIC_RESULTS = 8

MAX_OPENALEX_RESULTS = 8

MIN_ACCEPTED_SOURCES = 2

MAX_EVIDENCE_SOURCES = 5

SEMANTIC_RETRIES = 3

SEMANTIC_BACKOFF_SECONDS = 3

USER_AGENT = (
    "Mint-YT-Factory/2.1 "
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
    GET JSON with small retry support.

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

def _clean(text):

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


def _normalize_title(title):

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

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


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
    "survive",
}


def _topic_terms(topic):

    words = re.findall(
        r"[a-zA-Z0-9]+",
        _clean(topic).lower(),
    )

    return {
        word
        for word in words
        if len(word) >= 3
        and word not in STOPWORDS
    }


def _relevance_score(
    topic,
    source,
):
    """
    Lightweight local relevance check.

    This is deliberately conservative.

    It prevents obviously unrelated papers from being
    accepted simply because Crossref returned them.
    """

    terms = _topic_terms(
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
            "abstract",
            "",
        )
    ).lower()

    combined = (
        title
        + " "
        + abstract
    )

    matched = 0

    for term in terms:

        if re.search(
            rf"\b{re.escape(term)}\b",
            combined,
        ):

            matched += 1

    return matched


def relevance_filter(
    topic,
    sources,
):

    accepted = []

    terms = _topic_terms(
        topic
    )

    minimum_matches = 1

    if len(terms) >= 4:

        minimum_matches = 2

    for source in sources:

        score = _relevance_score(
            topic,
            source,
        )

        source[
            "relevance_score"
        ] = score

        if score >= minimum_matches:

            accepted.append(
                source
            )

        else:

            print(
                f"⚠️ Rejected low-relevance source: "
                f"{source.get('title', '')}"
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

        doi = _clean(
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

        results.append({

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
        })

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
                "venue"
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

        doi = _clean(
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

        results.append({

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
                paper.get(
                    "publicationTypes",
                    [],
                )
                or [],

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
        })

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
            "mint-yt-factory@example.com",
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

        doi = _clean(
            ids.get(
                "doi",
                "",
            )
        )

        if doi.startswith(
            "https://doi.org/"
        ):

            doi = doi[
                len(
                    "https://doi.org/"
                ):
            ]

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

        journal = ""

        primary_location = (
            item.get(
                "primary_location",
                {}
            )
            or {}
        )

        source = (
            primary_location.get(
                "source",
                {}
            )
            or {}
        )

        journal = _clean(
            source.get(
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

            url = (
                f"https://openalex.org/"
                f"{item.get('id', '').split('/')[-1]}"
            )

        if not doi:

            continue

        results.append({

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
        })

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

        doi = _clean(
            source.get(
                "doi",
                "",
            )
        ).lower()

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

    doi = _clean(
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

        returned_doi = _clean(
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
            returned_doi.lower()
            != doi.lower()
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
            "DOI resolved through Crossref."
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

    doi = _clean(
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
                    "venue"
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

        returned_doi = _clean(
            returned_ids.get(
                "DOI",
                "",
            )
        )

        if not returned_title:

            return False

        if (
            returned_doi
            and
            returned_doi.lower()
            != doi.lower()
        ):

            return False

        source[
            "metadata_verified"
        ] = True

        source[
            "verified_title"
        ] = returned_title

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
            "verification"
        ] = (
            "DOI resolved through Semantic Scholar."
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

    This is the important fallback for sources where
    Crossref and Semantic Scholar do not provide an abstract.
    """

    doi = _clean(
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
                "mint-yt-factory@example.com"
        }

        data = _get(
            url,
            params,
            retries=2,
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

    1. Existing Crossref abstract
    2. Semantic Scholar abstract
    3. OpenAlex abstract
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

        return source

    doi = _clean(
        source.get(
            "doi",
            "",
        )
    )

    if not doi:

        return source

    database = source.get(
        "source_database",
        "",
    )

    # --------------------------------------------------------------
    # Semantic Scholar
    # --------------------------------------------------------------

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
                    "title,abstract,year,externalIds"
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

                return source

        except Exception as error:

            source[
                "semantic_enrichment_error"
            ] = str(error)

    # --------------------------------------------------------------
    # OpenAlex fallback
    # --------------------------------------------------------------

    enrich_from_openalex(
        source
    )

    return source


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

        if source.get(
            "abstract"
        ):

            print(
                "✅ Abstract available"
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
    - URL exists
    - abstract/evidence exists
    """

    accepted = []

    for source in sources:

        abstract = _clean_abstract(
            source.get(
                "abstract",
                "",
            )
        )

        if not abstract:

            print(
                f"❌ Rejected metadata-only source: "
                f"{source.get('title', '')}"
            )

            continue

        if not source.get(
            "metadata_verified",
            False,
        ):

            print(
                f"❌ Rejected unverified source: "
                f"{source.get('title', '')}"
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

        doi = _clean(
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
                f"{source.get('title', '')}"
            )

            continue

        if not year:

            print(
                f"❌ Rejected source without year: "
                f"{source.get('title', '')}"
            )

            continue

        if not doi:

            print(
                f"❌ Rejected source without DOI: "
                f"{source.get('title', '')}"
            )

            continue

        if not url:

            print(
                f"❌ Rejected source without URL: "
                f"{source.get('title', '')}"
            )

            continue

        source[
            "abstract"
        ] = abstract

        source[
            "evidence_verified"
        ] = True

        source[
            "verified"
        ] = True

        source[
            "verification_level"
        ] = "ABSTRACT_EVIDENCE"

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

    Relevance score is preferred.
    """

    sources = sorted(
        sources,
        key=lambda source: (
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
        ),
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

    # OpenAlex is intentionally searched as an additional
    # independent evidence source.

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
    # RELEVANCE FILTER
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

            # OpenAlex records already contain
            # DOI-backed metadata. We still verify
            # identity through Crossref when possible.

            verified_ok = (
                verify_crossref_source(
                    source
                )
            )

            if not verified_ok:

                # OpenAlex itself is still a valid
                # bibliographic source.

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
                        "OpenAlex DOI metadata "
                        "accepted after Crossref "
                        "verification was unavailable."
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
    # ENRICH ABSTRACTS
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
    # BUILD PACKAGE
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
            f"   Evidence: "
            f"{source.get('evidence_source', 'UNKNOWN')}"
        )

        print(
            "   Verification: "
            "ABSTRACT EVIDENCE"
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