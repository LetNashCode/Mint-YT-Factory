"""
research.py
Mint-YT-Factory

Version 1.0

Research-first verification layer.

Purpose:
- Search real scholarly sources.
- Use Crossref + Semantic Scholar.
- Verify that sources actually exist.
- Prefer peer-reviewed/scientific literature.
- Return structured research evidence.
- NEVER invent citations.
- FAIL when insufficient credible evidence is found.

This is the first research layer.
The script-writing pipeline will be connected later.
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

TIMEOUT = 30

MAX_CROSSREF_RESULTS = 8
MAX_SEMANTIC_RESULTS = 8

MIN_ACCEPTED_SOURCES = 2

USER_AGENT = (
    "Mint-YT-Factory/1.0 "
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


# ==========================================================================
# CROSSREF
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
                "URL,link"
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
                            []
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

            "verified":
                False,
        })

    print(
        f"Crossref results: "
        f"{len(results)}"
    )

    return results


# ==========================================================================
# SEMANTIC SCHOLAR
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
                _clean(
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
# SOURCE VERIFICATION
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

        returned_title = (
            _clean(
                (
                    item.get(
                        "title",
                        []
                    )
                    or [""]
                )[0]
            )
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
            SEMANTIC_SCHOLAR_URL.replace(
                "/paper/search",
                "/paper/DOI:"
            )
            + quote(
                doi,
                safe="",
            )
        )

        params = {
            "fields":
                "title,authors,year,abstract,externalIds"
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
            and returned_doi.lower()
            != doi.lower()
        ):
            return False

        source[
            "verified"
        ] = True

        source[
            "verified_title"
        ] = returned_title

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

            print("✅ VERIFIED")

            verified.append(
                source
            )

        else:

            print("❌ NOT VERIFIED")

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

        if not title:
            continue

        if not authors:
            continue

        if not year:
            continue

        if not url:
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
    # Search
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
    # Verify
    # ----------------------------------------------------------------------

    verified = verify_sources(
        candidates
    )

    verified = quality_filter(
        verified
    )

    # ----------------------------------------------------------------------
    # Require multiple sources
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
    # Build package
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

        if source.get("doi"):

            print(
                f"   DOI: "
                f"{source['doi']}"
            )

        print(
            f"   Source: "
            f"{source['source_database']}"
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