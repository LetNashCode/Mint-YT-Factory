"""
research.py
Mint-YT-Factory

Version 2.0

Research-first evidence layer.

FLOW:

Topic
 ↓
Crossref + Semantic Scholar
 ↓
Verify paper/DOI
 ↓
Retrieve abstract/evidence
 ↓
Build verified research package
 ↓
verify_claims.py will later check claims against this evidence

IMPORTANT:
- A verified DOI means the source exists.
- This file does NOT by itself prove every claim.
- Claim-level verification is handled by verify_claims.py.
- No invented citations.
- Pipeline fails when sufficient evidence is unavailable.
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

SEMANTIC_SCHOLAR_SEARCH_URL = (
    "https://api.semanticscholar.org/graph/v1/paper/search"
)

SEMANTIC_SCHOLAR_PAPER_URL = (
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
                "URL"
            ),
    }

    data = _get(
        CROSSREF_URL,
        params,
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

            "abstract":
                "",

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

    data = _get(
        SEMANTIC_SCHOLAR_SEARCH_URL,
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
                )
                or [],

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
                    []
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

        source[
            "verification"
        ] = (
            "DOI independently verified "
            "through Crossref."
        )

        return True

    except Exception as error:

        source[
            "verification_error"
        ] = str(error)

        return False


# ==========================================================================
# SEMANTIC SCHOLAR VERIFICATION + EVIDENCE
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
            SEMANTIC_SCHOLAR_PAPER_URL
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
                    "url"
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

        abstract = _clean(
            data.get(
                "abstract",
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

        source[
            "abstract"
        ] = abstract

        if data.get(
            "venue"
        ):

            source[
                "journal"
            ] = _clean(
                data.get(
                    "venue"
                )
            )

        if data.get(
            "publicationTypes"
        ):

            source[
                "publication_types"
            ] = (
                data.get(
                    "publicationTypes"
                )
                or []
            )

        source[
            "semantic_scholar_url"
        ] = _clean(
            data.get(
                "url",
                "",
            )
        )

        source[
            "verification"
        ] = (
            "DOI and bibliographic record "
            "verified through Semantic Scholar."
        )

        return True

    except Exception as error:

        source[
            "verification_error"
        ] = str(error)

        return False


# ==========================================================================
# SOURCE VERIFICATION
# ==========================================================================

def verify_sources(
    sources
):

    print("=" * 80)
    print("🧪 VERIFYING SOURCES + EVIDENCE")
    print("=" * 80)

    verified = []

    for index, source in enumerate(
        sources,
        start=1,
    ):

        print(
            f"Checking "
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

            # ----------------------------------------------------------
            # Crossref verifies existence.
            # Semantic Scholar supplies the evidence abstract.
            # ----------------------------------------------------------

            if verified_ok:

                verified_ok = (
                    verify_semantic_source(
                        source
                    )
                )

        elif database == "Semantic Scholar":

            verified_ok = (
                verify_semantic_source(
                    source
                )
            )

            # ----------------------------------------------------------
            # Independently confirm DOI with Crossref.
            # ----------------------------------------------------------

            if verified_ok:

                verified_ok = (
                    verify_crossref_source(
                        source
                    )
                )

        if verified_ok:

            abstract = _clean(
                source.get(
                    "abstract",
                    "",
                )
            )

            if not abstract:

                print(
                    "❌ VERIFIED PAPER BUT "
                    "NO ABSTRACT EVIDENCE"
                )

                continue

            print(
                "✅ VERIFIED + EVIDENCE FOUND"
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

        abstract = _clean(
            source.get(
                "abstract",
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

        if not abstract:
            continue

        accepted.append(
            source
        )

    return accepted


# ==========================================================================
# EVIDENCE PACKAGE
# ==========================================================================

def build_evidence_package(
    sources
):

    evidence = []

    for index, source in enumerate(
        sources,
        start=1,
    ):

        abstract = _clean(
            source.get(
                "abstract",
                "",
            )
        )

        evidence.append({

            "evidence_id":
                f"evidence_{index}",

            "source_id":
                f"source_{index}",

            "title":
                source.get(
                    "title",
                    "",
                ),

            "evidence_type":
                "abstract",

            "text":
                abstract,

            "supports_claims":
                "Claims directly supported "
                "by the supplied abstract "
                "must be checked by "
                "verify_claims.py.",

        })

    return evidence


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
    # REQUIRE MULTIPLE SOURCES
    # ----------------------------------------------------------------------

    if len(
        verified
    ) < MIN_ACCEPTED_SOURCES:

        raise RuntimeError(

            "RESEARCH FAILED: "
            f"Only {len(verified)} "
            "sources have verified "
            "bibliographic records AND "
            "usable abstract evidence. "
            f"At least "
            f"{MIN_ACCEPTED_SOURCES} "
            "are required."
        )

    # ----------------------------------------------------------------------
    # LIMIT TO STRONGEST SOURCES
    # ----------------------------------------------------------------------

    verified = verified[:8]

    # ----------------------------------------------------------------------
    # ASSIGN STABLE SOURCE IDS
    # ----------------------------------------------------------------------

    for index, source in enumerate(
        verified,
        start=1,
    ):

        source[
            "source_id"
        ] = f"source_{index}"

        source[
            "evidence_available"
        ] = True

        source[
            "evidence_type"
        ] = "abstract"

    # ----------------------------------------------------------------------
    # BUILD EVIDENCE
    # ----------------------------------------------------------------------

    evidence = build_evidence_package(
        verified
    )

    # ----------------------------------------------------------------------
    # PACKAGE
    # ----------------------------------------------------------------------

    package = {

        "topic":
            topic,

        "status":
            "VERIFIED",

        "verified":
            True,

        "verification_level":
            "SOURCE_AND_ABSTRACT_VERIFIED",

        "verified_at":
            int(
                time.time()
            ),

        "source_count":
            len(verified),

        "evidence_count":
            len(evidence),

        "sources":
            verified,

        "evidence":
            evidence,

    }

    print("=" * 80)
    print("✅ RESEARCH VERIFIED")
    print("=" * 80)

    print(
        f"Verified sources: "
        f"{len(verified)}"
    )

    print(
        f"Evidence records: "
        f"{len(evidence)}"
    )

    for source in verified:

        print(
            f"✅ {source['source_id']}: "
            f"{source['title']}"
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