"""
research.py
Mint-YT-Factory

Version 2.0

Research-first verification layer.

FLOW:

Topic
  ↓
Crossref + Semantic Scholar
  ↓
Deduplicate
  ↓
Verify DOI
  ↓
Enrich abstract/evidence
  ↓
Quality filter
  ↓
Verified research package

IMPORTANT:
- Never invent citations.
- Never invent abstracts.
- Sources must actually exist.
- Minimum 2 verified sources.
- Abstract/evidence is attached whenever available.
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

TIMEOUT = 30

MAX_CROSSREF_RESULTS = 8
MAX_SEMANTIC_RESULTS = 8

MIN_ACCEPTED_SOURCES = 2

USER_AGENT = (
    "Mint-YT-Factory/2.0 "
    "(educational research verification)"
)


# ==========================================================================
# HTTP
# ==========================================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
)


def _get(url, params=None):

    response = SESSION.get(
        url,
        params=params,
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    return response.json()


# ==========================================================================
# TEXT HELPERS
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
            x for x in [given, family]
            if x
        )

        if name:
            authors.append(name)

    return ", ".join(authors)


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

    return ", ".join(authors)


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

        date_parts = date_info.get(
            "date-parts",
            [],
        )

        if date_parts and date_parts[0]:

            try:

                return int(
                    date_parts[0][0]
                )

            except Exception:
                pass

    return None


def _clean_abstract(text):

    text = _clean(text)

    if not text:
        return ""

    # Crossref sometimes returns JATS XML.
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
# CROSSREF SEARCH
# ==========================================================================

def search_crossref(topic):

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
    )

    items = (
        data
        .get("message", {})
        .get("items", [])
    )

    results = []

    for item in items:

        titles = item.get(
            "title",
            [],
        )

        title = (
            _clean(titles[0])
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
                    "Crossref metadata"
                    if abstract
                    else ""
                ),

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

def search_semantic_scholar(topic):

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

    data = _get(
        SEMANTIC_SCHOLAR_URL,
        params,
    )

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

        external_ids = paper.get(
            "externalIds",
            {}
        ) or {}

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

        if doi:

            citation_url = (
                f"https://doi.org/{doi}"
            )

        else:

            citation_url = url

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
                _clean_abstract(
                    paper.get(
                        "abstract",
                        "",
                    )
                ),

            "publication_types":
                paper.get(
                    "publicationTypes",
                    [],
                ) or [],

            "evidence_source":
                (
                    "Semantic Scholar abstract"
                    if paper.get("abstract")
                    else ""
                ),

            "verified":
                False,
        })

    print(
        f"Semantic Scholar results: "
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

        if doi and doi in seen_dois:
            continue

        if title and title in seen_titles:
            continue

        if doi:
            seen_dois.add(doi)

        if title:
            seen_titles.add(title)

        unique.append(
            source
        )

    return unique


# ==========================================================================
# CROSSREF VERIFICATION
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
            url
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
            "verified"
        ] = True

        source[
            "verified_title"
        ] = returned_title

        # Crossref may contain an abstract.
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
            "verified"
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
# ABSTRACT / EVIDENCE ENRICHMENT
# ==========================================================================

def enrich_source(
    source
):

    """
    Try to obtain an abstract for a verified source.

    Crossref sometimes provides one.
    Semantic Scholar is used as a second evidence layer.
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

    except Exception as error:

        source[
            "enrichment_error"
        ] = str(error)

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
                "⚠️ No abstract available"
            )

    return sources


# ==========================================================================
# SOURCE VERIFICATION
# ==========================================================================

def verify_sources(
    sources
):

    print("=" * 80)
    print("🧪 VERIFYING SOURCES")
    print("=" * 80)

    verified = []

    for index, source in enumerate(
        sources,
        start=1,
    ):

        print(
            f"Checking source "
            f"{index}/{len(sources)}: "
            f"{source.get('title', '')}"
        )

        verified_ok = False

        database = source.get(
            "source_database",
            "",
        )

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

        if verified_ok:

            print(
                "✅ VERIFIED"
            )

            verified.append(
                source
            )

        else:

            print(
                "❌ NOT VERIFIED"
            )

    return verified


# ==========================================================================
# QUALITY FILTER
# ==========================================================================

def quality_filter(
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

        authors = _clean(
            source.get(
                "authors",
                "",
            )
        )

        year = source.get(
            "year"
        )

        url = _clean(
            source.get(
                "url",
                "",
            )
        )

        doi = _clean(
            source.get(
                "doi",
                "",
            )
        )

        if not title:
            continue

        if not authors:
            continue

        if not year:
            continue

        if not url:
            continue

        if not doi:
            continue

        accepted.append(
            source
        )

    return accepted


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

    candidates = deduplicate_sources(
        crossref + semantic
    )

    print(
        f"Unique candidates: "
        f"{len(candidates)}"
    )

    # ----------------------------------------------------------------------
    # VERIFY
    # ----------------------------------------------------------------------

    verified = verify_sources(
        candidates
    )

    verified = quality_filter(
        verified
    )

    # ----------------------------------------------------------------------
    # ENRICH
    # ----------------------------------------------------------------------

    verified = enrich_sources(
        verified
    )

    # ----------------------------------------------------------------------
    # REQUIRE MULTIPLE SOURCES
    # ----------------------------------------------------------------------

    if len(verified) < MIN_ACCEPTED_SOURCES:

        raise RuntimeError(

            "RESEARCH FAILED: "
            f"Only {len(verified)} credible "
            "verified source(s) found. "
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
            len(verified),

        "sources":
            verified,
    }

    print("=" * 80)
    print("✅ RESEARCH VERIFIED")
    print("=" * 80)

    print(
        f"Verified sources: "
        f"{len(verified)}"
    )

    for index, source in enumerate(
        verified,
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

        if source.get(
            "abstract"
        ):

            print(
                "   Evidence: ABSTRACT AVAILABLE"
            )

        else:

            print(
                "   Evidence: METADATA ONLY"
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