"""
research.py - Mint-YT-Factory v9.1

Dynamic research-first evidence layer.

Research is driven entirely by the generated question.
No fixed subject/topic vocabulary is used.

Pipeline:
    topics.py
        ↓
    research.py
        ↓
    verified DOI-backed evidence
        ↓
    script generation
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

VERSION = "9.1"

CROSSREF_URL = "https://api.crossref.org/v1/works"
SEMANTIC_SEARCH_URL = (
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

MAX_VERIFICATION_CANDIDATES = 20
MAX_EVIDENCE_SOURCES = 5

MIN_ACCEPTED_SOURCES = 2
MIN_ABSTRACT_CHARACTERS = 120
MAX_EVIDENCE_TEXT_CHARACTERS = 12000

TITLE_SIMILARITY_MINIMUM = 0.55

# Minimum dynamic relevance requirements.
MIN_CORE_TERM_MATCHES = 2
MIN_TITLE_CORE_MATCHES = 1
MIN_ABSTRACT_CORE_MATCHES = 1
MIN_QUESTION_FOCUS_SCORE = 4

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

def _get(url, params=None, retries=2, backoff=2, provider=None):
    global SEMANTIC_RATE_LIMITED

    if provider == "Semantic Scholar" and SEMANTIC_RATE_LIMITED:
        raise RuntimeError(
            "Semantic Scholar skipped: rate limited earlier in this run."
        )

    last_error = None

    for attempt in range(retries + 1):
        try:
            response = SESSION.get(
                url,
                params=params,
                timeout=TIMEOUT,
            )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")

                try:
                    delay = float(retry_after)
                except (TypeError, ValueError):
                    delay = backoff * (attempt + 1)

                if provider == "Semantic Scholar":
                    SEMANTIC_RATE_LIMITED = True
                    raise RuntimeError(
                        "Semantic Scholar HTTP 429 rate limit exceeded."
                    )

                if attempt < retries:
                    print(
                        f"⚠️ HTTP 429. Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    continue

                raise RuntimeError(
                    "HTTP 429 rate limit exceeded."
                )

            if response.status_code >= 500 and attempt < retries:
                delay = backoff * (attempt + 1)

                print(
                    f"⚠️ HTTP {response.status_code}. "
                    f"Retrying in {delay:.1f}s..."
                )

                time.sleep(delay)
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
                delay = backoff * (attempt + 1)

                print(
                    f"⚠️ Request failed. "
                    f"Retrying in {delay:.1f}s..."
                )

                time.sleep(delay)
                continue

            raise last_error

    raise RuntimeError("HTTP request failed.")


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
    text = _clean(text)

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

    return doi.strip().rstrip(".,;:)").lower()


def _generate_source_id(doi):
    doi = _normalize_doi(doi)

    if not doi:
        raise RuntimeError(
            "Cannot generate source_id without DOI."
        )

    digest = hashlib.sha256(
        doi.encode("utf-8")
    ).hexdigest()[:12]

    return f"doi_{digest}"


def _normalize_title(title):
    title = _clean(title).lower()

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
            _normalize_title(title),
        )
        if len(token) >= 3
    }


def _title_similarity(title_a, title_b):
    a = _title_tokens(title_a)
    b = _title_tokens(title_b)

    if not a or not b:
        return 0.0

    return len(a & b) / len(a | b)


def _text_clean_for_matching(text):
    text = _clean(text).lower()

    return " ".join(
        re.sub(
            r"[^a-z0-9\s-]",
            " ",
            text,
        ).split()
    )


# ============================================================================
# QUESTION TERMS
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
}


# Generic words that frequently appear in scholarly writing
# but should not independently establish relevance.
GENERIC_RESEARCH_TERMS = {
    "study",
    "studies",
    "research",
    "result",
    "results",
    "finding",
    "findings",
    "analysis",
    "analyses",
    "data",
    "paper",
    "article",
    "review",
    "effect",
    "effects",
    "impact",
    "association",
    "associated",
    "relationship",
    "relationships",
    "role",
    "roles",
    "factor",
    "factors",
    "mechanism",
    "mechanisms",
    "cause",
    "causes",
    "causal",
    "process",
    "processes",
    "explanation",
    "explanations",
    "evidence",
    "population",
    "participants",
    "people",
    "individuals",
    "human",
    "humans",
    "model",
    "models",
    "system",
    "systems",
    "method",
    "methods",
    "resulting",
}


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


def _topic_terms(topic):
    return set(
        _tokenize(topic)
    )


def _core_topic_terms(topic):
    return {
        term
        for term in _topic_terms(topic)
        if term not in GENERIC_RESEARCH_TERMS
    }


def _stem_variants(term):
    variants = {term}

    if term.endswith("ies") and len(term) > 4:
        variants.add(
            term[:-3] + "y"
        )

    if term.endswith("ing") and len(term) > 5:
        variants.add(
            term[:-3]
        )

    if term.endswith("ed") and len(term) > 4:
        variants.add(
            term[:-2]
        )

    if term.endswith("s") and len(term) > 4:
        variants.add(
            term[:-1]
        )

    return variants


def _expanded_topic_terms(topic):
    base = _topic_terms(topic)
    expanded = set(base)

    for term in list(base):
        expanded.update(
            _stem_variants(term)
        )

    return expanded


def _core_expanded_topic_terms(topic):
    return {
        term
        for term in _expanded_topic_terms(topic)
        if term not in GENERIC_RESEARCH_TERMS
    }


def _stem_like_match(term, text):
    if not term:
        return False

    term = term.lower().strip()
    text = text.lower()

    if " " in term:
        return term in text

    for candidate in _stem_variants(term):
        if len(candidate) < 3:
            continue

        if re.search(
            rf"\b{re.escape(candidate)}\w*\b",
            text,
        ):
            return True

    return False


def _matched_terms(terms, text):
    clean_text = _text_clean_for_matching(text)

    return {
        term
        for term in terms
        if _stem_like_match(
            term,
            clean_text,
        )
    }


def _matched_phrases(topic, text):
    """
    Find meaningful 2- and 3-word phrases from the question.

    This is intentionally generated dynamically from the question.
    """

    tokens = _tokenize(topic)
    clean_text = _text_clean_for_matching(text)

    phrases = set()

    for size in (3, 2):
        for index in range(
            len(tokens) - size + 1
        ):
            phrase = " ".join(
                tokens[
                    index:index + size
                ]
            )

            if len(phrase) >= 6 and phrase in clean_text:
                phrases.add(phrase)

    return phrases


# ============================================================================
# QUERY GENERATION
# ============================================================================

def build_scholarly_queries(topic):
    """
    Generate several research queries from the actual question.

    No fixed subject vocabulary is used.
    """

    topic = _clean(topic)

    base = sorted(
        _topic_terms(topic)
    )

    core = sorted(
        _core_topic_terms(topic)
    )

    expanded = sorted(
        _expanded_topic_terms(topic)
        - set(base)
    )

    queries = []

    if topic:
        queries.append(topic)

    if base:
        queries.append(
            " ".join(
                base[:10]
            )
        )

    if core:
        queries.append(
            " ".join(
                core[:10]
            )
        )

    if core and expanded:
        queries.append(
            " ".join(
                core[:7]
                + expanded[:7]
            )
        )

    # Mechanism-oriented query.
    if core:
        queries.append(
            " ".join(
                core[:8]
                + [
                    "mechanism",
                    "cause",
                    "process",
                ]
            )
        )

    # Effect-oriented query.
    if core:
        queries.append(
            " ".join(
                core[:8]
                + [
                    "effect",
                    "explanation",
                ]
            )
        )

    final = []
    seen = set()

    for query in queries:
        query = _clean(query)

        if not query:
            continue

        key = query.lower()

        if key in seen:
            continue

        seen.add(key)
        final.append(query)

    return final[:5]


# ============================================================================
# DYNAMIC RELEVANCE
# ============================================================================

def _calculate_question_focus(topic):
    """
    Determine how specific the question is.

    Longer questions contain more information and therefore require
    stronger evidence overlap.
    """

    tokens = _tokenize(topic)
    core = _core_topic_terms(topic)

    score = 0

    score += min(
        len(tokens),
        8,
    )

    score += min(
        len(core),
        8,
    )

    if len(tokens) >= 6:
        score += 2

    if len(core) >= 4:
        score += 2

    return score


def _relevance_score(topic, source):
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

    title_clean = _text_clean_for_matching(
        title
    )

    evidence_clean = _text_clean_for_matching(
        evidence
    )

    terms = _topic_terms(topic)
    core_terms = _core_topic_terms(topic)

    expanded = _expanded_topic_terms(topic)
    core_expanded = _core_expanded_topic_terms(topic)

    title_matches = _matched_terms(
        terms,
        title_clean,
    )

    evidence_matches = _matched_terms(
        terms,
        evidence_clean,
    )

    core_title_matches = _matched_terms(
        core_terms,
        title_clean,
    )

    core_evidence_matches = _matched_terms(
        core_terms,
        evidence_clean,
    )

    expanded_title_matches = _matched_terms(
        expanded - terms,
        title_clean,
    )

    expanded_evidence_matches = _matched_terms(
        expanded - terms,
        evidence_clean,
    )

    core_expanded_title_matches = _matched_terms(
        core_expanded - core_terms,
        title_clean,
    )

    core_expanded_evidence_matches = _matched_terms(
        core_expanded - core_terms,
        evidence_clean,
    )

    title_phrases = _matched_phrases(
        topic,
        title_clean,
    )

    evidence_phrases = _matched_phrases(
        topic,
        evidence_clean,
    )

    score = 0

    # Core terms carry the majority of the relevance weight.
    score += len(core_title_matches) * 12
    score += len(core_evidence_matches) * 5

    # Morphological variants.
    score += len(core_expanded_title_matches) * 7
    score += len(core_expanded_evidence_matches) * 2

    # Non-core terms have lower influence.
    score += len(title_matches - core_terms) * 2
    score += len(evidence_matches - core_terms)

    # Phrase matches are strong evidence of contextual relevance.
    score += len(title_phrases) * 10
    score += len(evidence_phrases) * 4

    normalized_topic = _normalize_title(topic)
    normalized_title = _normalize_title(title)

    if (
        normalized_topic
        and normalized_topic in normalized_title
    ):
        score += 30

    # Exact ordered core phrase.
    core_tokens = sorted(
        core_terms
    )

    for size in (3, 2):
        for index in range(
            len(core_tokens) - size + 1
        ):
            phrase = " ".join(
                core_tokens[
                    index:index + size
                ]
            )

            if phrase in title_clean:
                score += 8 if size == 3 else 4

    matched_core_total = (
        core_title_matches
        | core_evidence_matches
        | core_expanded_title_matches
        | core_expanded_evidence_matches
    )

    matched_total = (
        title_matches
        | evidence_matches
        | expanded_title_matches
        | expanded_evidence_matches
    )

    question_focus_score = _calculate_question_focus(
        topic
    )

    # ----------------------------------------------------------------------
    # ACTUAL INTENT PASS
    # ----------------------------------------------------------------------

    intent_pass = False
    relevance_class = "weak"

    if not core_terms:
        intent_pass = bool(
            matched_total
            or title_phrases
            or evidence_phrases
        )

    elif len(core_terms) == 1:
        intent_pass = bool(
            core_title_matches
            or core_evidence_matches
        )

    elif len(core_terms) == 2:
        intent_pass = (
            len(matched_core_total) >= 2
            and (
                len(core_title_matches) >= 1
                or len(core_evidence_matches) >= 2
            )
        )

    else:
        # For specific questions, require multiple core concepts.
        intent_pass = (
            len(matched_core_total)
            >= min(
                MIN_CORE_TERM_MATCHES,
                len(core_terms),
            )
            and (
                len(core_title_matches)
                >= MIN_TITLE_CORE_MATCHES
                or len(core_evidence_matches)
                >= MIN_ABSTRACT_CORE_MATCHES
            )
        )

        # Stronger requirement for highly specific questions.
        if (
            question_focus_score
            >= MIN_QUESTION_FOCUS_SCORE + 6
        ):
            intent_pass = (
                intent_pass
                and len(matched_core_total) >= 3
            )

    # ----------------------------------------------------------------------
    # CLASSIFICATION
    # ----------------------------------------------------------------------

    if intent_pass:
        if (
            len(core_title_matches) >= 2
            and len(core_evidence_matches) >= 2
        ):
            relevance_class = "strong"

        elif (
            len(core_title_matches) >= 1
            and len(matched_core_total) >= 3
        ):
            relevance_class = "strong"

        elif (
            len(matched_core_total) >= 2
            and (
                len(core_title_matches) >= 1
                or len(core_evidence_matches) >= 2
            )
        ):
            relevance_class = "moderate"

    # Explicitly reject keyword-only matches.
    if (
        len(core_terms) >= 3
        and len(matched_core_total) < 2
    ):
        intent_pass = False
        relevance_class = "weak"

    source.update(
        {
            "matched_terms": sorted(
                matched_total
            ),
            "core_matched_terms": sorted(
                matched_core_total
            ),
            "topic_terms": sorted(
                terms
            ),
            "core_topic_terms": sorted(
                core_terms
            ),
            "expanded_topic_terms": sorted(
                expanded
            ),
            "title_match_count": len(
                title_matches
            ),
            "abstract_match_count": len(
                evidence_matches
            ),
            "core_title_match_count": len(
                core_title_matches
            ),
            "core_abstract_match_count": len(
                core_evidence_matches
            ),
            "expanded_title_match_count": len(
                expanded_title_matches
            ),
            "expanded_abstract_match_count": len(
                expanded_evidence_matches
            ),
            "title_phrase_matches": sorted(
                title_phrases
            ),
            "abstract_phrase_matches": sorted(
                evidence_phrases
            ),
            "question_focus_score": question_focus_score,
            "relevance_class": relevance_class,
            "relevance_score": score,
            "intent_pass": intent_pass,
            "intent_class": (
                "question_focused"
                if intent_pass
                else "insufficient_question_alignment"
            ),
            "question_intents": [],
            "intent_score": score,
            "intent_mechanism_matches": sorted(
                matched_core_total
            ),
            "intent_event_matches": [],
            "intent_target_matches": [],
            "intent_negative_matches": [],
        }
    )

    return score


def relevance_filter(
    topic,
    sources,
    label="STRICT QUESTION RELEVANCE FILTER",
):
    print("=" * 80)
    print(label)
    print("=" * 80)

    print(
        "Question: "
        + topic
    )

    print(
        "Core terms: "
        + (
            ", ".join(
                sorted(
                    _core_topic_terms(topic)
                )
            )
            or "none"
        )
    )

    accepted = []

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
            "weak",
        )

        intent_pass = source.get(
            "intent_pass",
            False,
        )

        print(
            f"\n   Source: {title}"
        )

        print(
            f"   Score: {score}"
        )

        print(
            f"   Class: {classification}"
        )

        print(
            "   Core matches: "
            + ", ".join(
                source.get(
                    "core_matched_terms",
                    [],
                )
            )
            or "none"
        )

        print(
            f"   Intent pass: {intent_pass}"
        )

        if (
            classification in {
                "strong",
                "moderate",
            }
            and intent_pass is True
        ):
            accepted.append(
                source
            )

            print(
                "   ✅ RELEVANT"
            )

        else:
            print(
                "   ❌ REJECTED"
            )

    print(
        f"\nRelevant candidates: {len(accepted)}"
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

    providers.add(provider)

    source[
        "evidence_providers"
    ] = sorted(providers)

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
        isinstance(record, dict)
        and record.get("provider") == provider
        for record in records
    ):
        records.append(
            {
                "provider": provider,
                "characters": len(abstract),
            }
        )

    source[
        "evidence_records"
    ] = records


def _build_evidence_package(source):
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

def _crossref_search_once(query):
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

    return data.get(
        "message",
        {},
    ).get(
        "items",
        [],
    )


def search_crossref(topic):
    print("=" * 80)
    print("🔎 CROSSREF SEARCH")
    print("=" * 80)

    results = []
    seen = set()

    for query in build_scholarly_queries(topic):
        print(
            f"   • {query}"
        )

        try:
            items = _crossref_search_once(
                query
            )
        except Exception as error:
            print(
                f"⚠️ Crossref query failed: {error}"
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

            seen.add(doi)

            abstract = _clean_abstract(
                item.get(
                    "abstract",
                    "",
                )
            )

            source = {
                "source_database": "Crossref",
                "source_databases": ["Crossref"],
                "discovery_provider": "Crossref",
                "discovery_providers": [
                    "Crossref"
                ],
                "title": title,
                "authors": _authors_crossref(item),
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
                "year": _extract_year(item),
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
        f"Crossref results: {len(results)}"
    )

    return results


def search_semantic_scholar(topic):
    global SEMANTIC_RATE_LIMITED

    print("=" * 80)
    print("🔎 SEMANTIC SCHOLAR SEARCH")
    print("=" * 80)

    if SEMANTIC_RATE_LIMITED:
        print(
            "⚠️ Semantic Scholar rate limited; skipping."
        )
        return []

    results = []
    seen = set()

    for query in build_scholarly_queries(topic):
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
                f"⚠️ Semantic Scholar unavailable: {error}"
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

            seen.add(doi)

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
                "authors": _authors_semantic(paper),
                "journal": _clean(
                    paper.get(
                        "venue",
                        "",
                    )
                ),
                "publisher": "",
                "year": paper.get("year"),
                "doi": doi,
                "url": f"https://doi.org/{doi}",
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


def search_openalex(topic):
    print("=" * 80)
    print("🔎 OPENALEX SEARCH")
    print("=" * 80)

    results = []
    seen = set()

    for query in build_scholarly_queries(topic):
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
                f"⚠️ OpenAlex search failed: {error}"
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

            seen.add(doi)

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
                    authors.append(name)

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
                "source_databases": ["OpenAlex"],
                "discovery_provider": "OpenAlex",
                "discovery_providers": ["OpenAlex"],
                "title": title,
                "authors": ", ".join(authors),
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
                "url": f"https://doi.org/{doi}",
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
        f"OpenAlex results: {len(results)}"
    )

    return results


# ============================================================================
# DEDUPLICATION
# ============================================================================

def _merge_sources(primary, secondary):
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

    if secondary_abstract:
        _record_evidence_provider(
            primary,
            secondary.get(
                "source_database",
                "unknown",
            ),
            secondary_abstract,
        )

    if len(secondary_abstract) > len(
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


def deduplicate_sources(sources):
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

        elif (
            not doi
            and title
            and title in by_title
        ):
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

        unique.append(source)

        if doi:
            by_doi[doi] = source

        if title:
            by_title[title] = source

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

    if similarity < TITLE_SIMILARITY_MINIMUM:
        source[
            "identity_error"
        ] = (
            f"{provider}: title mismatch."
        )
        return False

    return True


def verify_crossref_source(source):
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

        authors = _authors_crossref(item)

        if authors:
            source["authors"] = authors

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
            source["journal"] = journal

        publisher = _clean(
            item.get(
                "publisher",
                "",
            )
        )

        if publisher:
            source["publisher"] = publisher

        year = _extract_year(item)

        if year:
            source["year"] = year

        abstract = _clean_abstract(
            item.get(
                "abstract",
                "",
            )
        )

        if abstract:
            source["abstract"] = abstract
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
            "DOI and publication identity verified through Crossref."
        )

        return _build_evidence_package(
            source
        )

    except Exception as error:
        source[
            "crossref_verification_error"
        ] = str(error)

        return False


def verify_semantic_source(source):
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

        authors = _authors_semantic(data)

        if authors:
            source["authors"] = authors

        venue = _clean(
            data.get(
                "venue",
                "",
            )
        )

        if venue:
            source["journal"] = venue

        if data.get("year"):
            source["year"] = data["year"]

        abstract = _clean_abstract(
            data.get(
                "abstract",
                "",
            )
        )

        if abstract:
            source["abstract"] = abstract

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
            "DOI and publication identity verified "
            "through Semantic Scholar."
        )

        return _build_evidence_package(
            source
        )

    except Exception as error:
        if "429" in str(error):
            SEMANTIC_RATE_LIMITED = True

        source[
            "semantic_verification_error"
        ] = str(error)

        return False


def verify_openalex_source(source):
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
            "DOI and publication identity verified "
            "through OpenAlex."
        )

        return _build_evidence_package(
            source
        )

    except Exception as error:
        source[
            "openalex_verification_error"
        ] = str(error)

        return False


def verify_source_identity(source):
    discovery = source.get(
        "discovery_provider",
        "",
    )

    providers = []

    if discovery:
        providers.append(discovery)

    for provider in (
        "Crossref",
        "OpenAlex",
        "Semantic Scholar",
    ):
        if provider not in providers:
            providers.append(provider)

    errors = []

    for provider in providers:
        print(
            f"   ↪ Trying {provider}..."
        )

        if provider == "Crossref":
            verified = verify_crossref_source(
                source
            )

        elif provider == "OpenAlex":
            verified = verify_openalex_source(
                source
            )

        elif provider == "Semantic Scholar":
            verified = verify_semantic_source(
                source
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
                source["identity_error"]
            )

    source[
        "verification_attempts"
    ] = providers

    source[
        "verification_errors"
    ] = list(
        dict.fromkeys(errors)
    )

    return False


# ============================================================================
# EVIDENCE ENRICHMENT
# ============================================================================

def enrich_from_crossref(source):
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

            if len(abstract) > len(current):
                source[
                    "abstract"
                ] = abstract

                source[
                    "evidence_source"
                ] = "Crossref abstract"

    except Exception as error:
        source[
            "crossref_enrichment_error"
        ] = str(error)

    return source


def enrich_from_openalex(source):
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

            if len(abstract) > len(current):
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
        ] = str(error)

    return source


def enrich_from_semantic(source):
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

            if len(abstract) > len(current):
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
        if "429" in str(error):
            SEMANTIC_RATE_LIMITED = True

        source[
            "semantic_enrichment_error"
        ] = str(error)

    return source


def enrich_source(source):
    if _clean_abstract(
        source.get(
            "abstract",
            "",
        )
    ):
        return _build_evidence_package(
            source
        )

    source = enrich_from_openalex(source)

    if _clean_abstract(
        source.get(
            "abstract",
            "",
        )
    ):
        return _build_evidence_package(
            source
        )

    source = enrich_from_crossref(source)

    if _clean_abstract(
        source.get(
            "abstract",
            "",
        )
    ):
        return _build_evidence_package(
            source
        )

    source = enrich_from_semantic(source)

    return _build_evidence_package(
        source
    )


def enrich_sources(sources):
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

        source = enrich_source(source)

        if source.get(
            "evidence_available"
        ):
            print(
                "✅ Evidence available "
                f"({len(source.get('evidence_text', ''))} chars)"
            )

            enriched.append(source)

        else:
            print(
                "❌ No evidence available"
            )

    return enriched


# ============================================================================
# EVIDENCE VALIDATION
# ============================================================================

def mark_evidence_verified(sources):
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
                f"❌ Rejected unverified source: {title}"
            )
            continue

        evidence = _clean_abstract(
            source.get(
                "evidence_text",
                "",
            )
        )

        if len(evidence) < MIN_ABSTRACT_CHARACTERS:
            print(
                f"❌ Rejected insufficient evidence: {title}"
            )
            continue

        authors = _clean(
            source.get(
                "authors",
                "",
            )
        )

        year = source.get("year")

        doi = _normalize_doi(
            source.get(
                "doi",
                "",
            )
        )

        if not authors or not year or not doi:
            print(
                f"❌ Rejected incomplete source: {title}"
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

        accepted.append(source)

    return accepted


# ============================================================================
# SOURCE SELECTION
# ============================================================================

def limit_sources(sources):
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

        return (
            relevance_rank,
            source.get(
                "relevance_score",
                0,
            ),
            source.get(
                "question_focus_score",
                0,
            ),
            evidence_provider_count,
            citation_count,
        )

    return sorted(
        sources,
        key=sort_key,
        reverse=True,
    )[:MAX_EVIDENCE_SOURCES]


def validate_independent_sources(sources):
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

    if len(dois) < MIN_ACCEPTED_SOURCES:
        raise RuntimeError(
            "RESEARCH FAILED: fewer than two "
            "distinct DOI-backed sources remain."
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
            provider_families.add(providers)

    return {
        "distinct_doi_count": len(dois),
        "independence_basis": "distinct_normalized_dois",
        "independent_source_count": len(dois),
        "discovery_provider_families": len(
            provider_families
        ),
    }


def validate_source_ids(sources):
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

        if not source_id or not doi:
            raise RuntimeError(
                f"RESEARCH FAILED: source '{title}' "
                "missing source_id or DOI."
            )

        expected_id = _generate_source_id(
            doi
        )

        if source_id != expected_id:
            raise RuntimeError(
                f"RESEARCH FAILED: source ID mismatch "
                f"for '{title}'."
            )

        if source_id in seen_ids:
            raise RuntimeError(
                "RESEARCH FAILED: duplicate source_id."
            )

        if doi in seen_dois:
            raise RuntimeError(
                "RESEARCH FAILED: duplicate DOI."
            )

        seen_ids.add(source_id)
        seen_dois.add(doi)

        for flag in (
            "metadata_verified",
            "evidence_verified",
            "evidence_available",
            "verified",
        ):
            if source.get(flag) is not True:
                raise RuntimeError(
                    f"RESEARCH FAILED: source '{title}' "
                    f"does not have {flag}=True."
                )

        evidence = _clean(
            source.get(
                "evidence_text",
                "",
            )
        )

        if len(evidence) < MIN_ABSTRACT_CHARACTERS:
            raise RuntimeError(
                f"RESEARCH FAILED: source '{title}' "
                "has insufficient evidence."
            )

        if source.get(
            "evidence_type"
        ) != "abstract":
            raise RuntimeError(
                f"RESEARCH FAILED: source '{title}' "
                "does not contain abstract evidence."
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
                f"RESEARCH FAILED: source '{title}' "
                "has no authors."
            )

        if not source.get("year"):
            raise RuntimeError(
                f"RESEARCH FAILED: source '{title}' "
                "has no publication year."
            )

        if not _clean(
            source.get(
                "url",
                "",
            )
        ):
            source[
                "url"
            ] = f"https://doi.org/{doi}"

    return True


def validate_research_package(package):
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

    if len(sources) < MIN_ACCEPTED_SOURCES:
        raise RuntimeError(
            "RESEARCH FAILED: fewer than two sources."
        )

    if package.get(
        "source_count"
    ) != len(sources):
        raise RuntimeError(
            "RESEARCH FAILED: source_count mismatch."
        )

    if package.get(
        "evidence_source_count"
    ) != len(sources):
        raise RuntimeError(
            "RESEARCH FAILED: evidence_source_count mismatch."
        )

    validate_source_ids(sources)
    validate_independent_sources(sources)

    for source in sources:
        if source.get(
            "relevance_class"
        ) not in {
            "strong",
            "moderate",
        }:
            raise RuntimeError(
                "RESEARCH FAILED: final source "
                f"is not relevant: {source.get('title', '')}"
            )

        if source.get(
            "intent_pass"
        ) is not True:
            raise RuntimeError(
                "RESEARCH FAILED: source failed "
                "question relevance."
            )

    return True


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def research_topic(topic):
    global SEMANTIC_RATE_LIMITED

    SEMANTIC_RATE_LIMITED = False

    topic = _clean(topic)

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

    scholarly_queries = build_scholarly_queries(
        topic
    )

    print("=" * 80)
    print("🧠 DYNAMIC RESEARCH QUERIES")
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
                search_function(topic)
            )
        except Exception as error:
            print(
                f"⚠️ {search_function.__name__} failed: {error}"
            )

    candidates = deduplicate_sources(
        all_sources
    )

    print(
        f"Unique candidates: {len(candidates)}"
    )

    if not candidates:
        raise RuntimeError(
            "RESEARCH FAILED: no research candidates found."
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

        doi_candidates.append(source)

    print(
        f"DOI-eligible candidates: "
        f"{len(doi_candidates)}"
    )

    if not doi_candidates:
        raise RuntimeError(
            "RESEARCH FAILED: no DOI candidates."
        )

    # ----------------------------------------------------------------------
    # FIRST RELEVANCE PASS
    # ----------------------------------------------------------------------

    relevant = relevance_filter(
        topic,
        doi_candidates,
        label="STRICT QUESTION RELEVANCE FILTER",
    )

    if not relevant:
        raise RuntimeError(
            "RESEARCH FAILED: no sufficiently "
            "relevant sources found."
        )

    relevant = sorted(
        relevant,
        key=lambda source: (
            source.get(
                "relevance_score",
                0,
            ),
            source.get(
                "question_focus_score",
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
    )[:MAX_VERIFICATION_CANDIDATES]

    # ----------------------------------------------------------------------
    # IDENTITY VERIFICATION
    # ----------------------------------------------------------------------

    print("=" * 80)
    print("🧪 VERIFYING DOI + PUBLICATION IDENTITY")
    print("=" * 80)

    verified_metadata = []

    for index, source in enumerate(
        relevant,
        start=1,
    ):
        print(
            f"Checking source {index}/{len(relevant)}: "
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
            "RESEARCH FAILED: no DOI-verified sources remained."
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
            "RESEARCH FAILED: no evidence-backed sources remained."
        )

    # ----------------------------------------------------------------------
    # FINAL RELEVANCE PASS
    # ----------------------------------------------------------------------

    evidence_sources = relevance_filter(
        topic,
        evidence_sources,
        label="FINAL EVIDENCE RELEVANCE CHECK",
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
                "intent_pass"
            ) is True
        )
    ]

    evidence_sources = limit_sources(
        evidence_sources
    )

    print(
        f"Final sources: "
        f"{len(evidence_sources)}"
    )

    if len(evidence_sources) < MIN_ACCEPTED_SOURCES:
        raise RuntimeError(
            "RESEARCH FAILED: fewer than two "
            "evidence-backed relevant sources remained."
        )

    diversity = validate_independent_sources(
        evidence_sources
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
                _topic_terms(topic)
            ),

            "core_topic_terms": sorted(
                _core_topic_terms(topic)
            ),

            "expanded_terms": sorted(
                _expanded_topic_terms(topic)
            ),

            "topic_concepts": [],

            "scholarly_queries": scholarly_queries,

            "question_intents": [],

            "mechanism_terms": sorted(
                _core_topic_terms(topic)
            ),

            "event_terms": [],

            "target_terms": [],

            "negative_topic_drift_terms": [],
        },

        "verification_policy": {
            "minimum_sources": MIN_ACCEPTED_SOURCES,

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

            "keyword_only_relevance_allowed": False,

            "question_focus_relevance_enabled": True,

            "core_term_relevance_enabled": True,

            "phrase_relevance_enabled": True,
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

    validate_research_package(
        package
    )

    print("=" * 80)
    print("✅ RESEARCH VERIFIED")
    print("=" * 80)

    for index, source in enumerate(
        evidence_sources,
        start=1,
    ):
        print(
            f"{index}. {source['title']}"
        )

        print(
            f"   DOI: {source['doi']}"
        )

        print(
            f"   Source ID: {source['source_id']}"
        )

        print(
            f"   Relevance: "
            f"{source.get('relevance_class', '')} "
            f"({source.get('relevance_score', 0)})"
        )

        print(
            f"   Intent: "
            f"{source.get('intent_pass', False)}"
        )

        print(
            f"   Evidence: "
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

    if len(sys.argv) < 2:
        print(
            'Usage: python research.py "your topic"'
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