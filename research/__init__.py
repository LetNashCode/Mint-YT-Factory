"""Compatibility wrapper for the existing research.py evidence engine.

The original research.py remains intact. This wrapper strengthens the
question parser and source relevance gate so a generic phenomenon word such
as "smell" cannot make an unrelated paper pass a topic-specific question.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re


_ROOT = Path(__file__).resolve().parent.parent
_ORIGINAL_PATH = _ROOT / "research.py"

_spec = importlib.util.spec_from_file_location(
    "_mint_original_research",
    _ORIGINAL_PATH,
)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load original research module: {_ORIGINAL_PATH}")

_original = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_original)


# ---------------------------------------------------------------------------
# Improved question parsing
# ---------------------------------------------------------------------------
# research.py already isolates the subject before predicates such as "sound"
# and "feel", but it did not include "smell". For a topic such as
# "why does fresh bread smell...", that could leave "smell" as a subject-like
# concept and allow unrelated smell papers to score highly.
# ---------------------------------------------------------------------------

_EXTRA_SUBJECT_SEPARATORS = (
    " smell ", " smells ", " taste ", " tastes ",
    " get ", " gets ", " appear ", " appears ",
    " seem ", " seems ", " turn ", " turns ",
)


def _strict_extract_subject(topic):
    lowered = _original._clean(topic).lower()
    subject = _original._extract_subject(topic)

    excluded = {
        "slow", "slows", "slowing", "speed", "speeding", "faster",
        "starting", "stopping", "stopped", "turning", "during", "while",
        "after", "before", "cold", "hot",
    }

    for separator in _EXTRA_SUBJECT_SEPARATORS:
        if separator not in lowered:
            continue

        left = lowered.split(separator, 1)[0]
        left_tokens = [
            token for token in _original._tokens(left)
            if token not in excluded
        ]

        if left_tokens:
            return [" ".join(left_tokens), *left_tokens]

    return subject


_original._extract_subject = _strict_extract_subject


# ---------------------------------------------------------------------------
# Topic identity model
# ---------------------------------------------------------------------------

_GENERIC_SUBJECT_WORDS = {
    "fresh", "good", "right", "different", "cold", "hot", "new",
    "real", "normal", "common", "everyday", "often", "sometimes",
}

_PHENOMENON_SYNONYMS = {
    "smell": {"smell", "smells", "odor", "odour", "aroma", "aromas", "fragrance"},
    "odor": {"smell", "smells", "odor", "odour", "aroma", "aromas", "fragrance"},
    "odour": {"smell", "smells", "odor", "odour", "aroma", "aromas", "fragrance"},
    "sound": {"sound", "sounds", "noise", "noises", "acoustic", "audio", "echo", "echoes"},
    "sounds": {"sound", "sounds", "noise", "noises", "acoustic", "audio", "echo", "echoes"},
    "feel": {"feel", "feels", "feeling", "cold", "colder", "temperature", "sensation", "perception"},
    "feels": {"feel", "feels", "feeling", "cold", "colder", "temperature", "sensation", "perception"},
    "taste": {"taste", "tastes", "flavor", "flavour", "flavors", "flavours"},
    "tastes": {"taste", "tastes", "flavor", "flavour", "flavors", "flavours"},
}


def _content_terms(text):
    return set(re.findall(r"[a-z0-9]+", _original._clean(text).lower()))


def _topic_identity(topic):
    structure = _original._question_structure(topic)

    subject_phrases = structure.get("subject", [])
    subject_phrase = subject_phrases[0] if subject_phrases else ""

    subject_terms = [
        token for token in _original._tokens(subject_phrase)
        if token not in _GENERIC_SUBJECT_WORDS
    ]

    phenomenon_terms = set()
    for item in structure.get("phenomenon", []):
        for word in _content_terms(item):
            phenomenon_terms.update(
                _PHENOMENON_SYNONYMS.get(word, {word})
            )

    # Keep the identity guard conservative: if there is no explicit
    # phenomenon, use remaining concrete topic terms rather than allowing
    # generic words such as "good" or "different" to define relevance.
    if not phenomenon_terms:
        phenomenon_terms.update(
            token for token in _original._tokens(topic)
            if token not in subject_terms
            and token not in _GENERIC_SUBJECT_WORDS
        )

    return subject_terms, phenomenon_terms


def _source_matches_current_topic(topic, source):
    subject_terms, phenomenon_terms = _topic_identity(topic)

    # If the topic parser cannot establish a concrete identity, leave the
    # existing scientific relevance engine in charge rather than guessing.
    if not subject_terms or not phenomenon_terms:
        return True

    title = _original._clean(source.get("title", ""))
    evidence = _original._clean_abstract(
        source.get("evidence_text", "") or source.get("abstract", "")
    )
    combined = f"{title} {evidence}"

    subject_hit = any(
        _original._term_match(term, combined)
        for term in subject_terms
    )
    phenomenon_hit = any(
        _original._term_match(term, combined)
        for term in phenomenon_terms
    )

    return subject_hit and phenomenon_hit


# ---------------------------------------------------------------------------
# Apply the identity guard DURING the original scoring pipeline, before
# source selection. This is important: filtering only the final five sources
# could leave us with fewer than two sources even though relevant candidates
# existed earlier in the discovery pool.
# ---------------------------------------------------------------------------

_original_score_source = _original._score_source


def _strict_score_source(topic, source):
    result = _original_score_source(topic, source)

    if not _source_matches_current_topic(topic, source):
        result["scientific_relevance_pass"] = False
        result["concept_coverage_pass"] = False
        result["intent_pass"] = False
        result["relevance_class"] = "weak"
        result.setdefault("rejection_reasons", []).append(
            "current_topic_identity_mismatch"
        )

    return result


_original._score_source = _strict_score_source
_original_research_topic = _original.research_topic


def research_topic(topic):
    package = _original_research_topic(topic)

    sources = package.get("sources", [])
    if not isinstance(sources, list):
        raise RuntimeError("RESEARCH FAILED: verified sources are not a list.")

    # Final defensive check: the package must never leave this module with a
    # source that is scientifically credible but unrelated to the current
    # question.
    filtered = [
        source for source in sources
        if _source_matches_current_topic(topic, source)
    ]

    rejected = [
        source.get("title", "")
        for source in sources
        if source not in filtered
    ]

    if rejected:
        print("=" * 80)
        print("🛡️ CURRENT-TOPIC RESEARCH IDENTITY GUARD")
        print("=" * 80)
        for title in rejected:
            print(f"❌ Rejected topical mismatch: {title}")
        print(f"Remaining topic-matched sources: {len(filtered)}")
        print("=" * 80)

    if len(filtered) < 2:
        raise RuntimeError(
            "RESEARCH FAILED: fewer than two verified sources remain "
            "after the current-topic identity guard. The pipeline will "
            "not publish a scientifically valid but topically unrelated story."
        )

    package["sources"] = filtered
    package["source_count"] = len(filtered)
    package["evidence_source_count"] = len(filtered)
    return package


# Export the complete original API while overriding research_topic and the
# scoring/parser helpers used internally by the original pipeline.
for _name, _value in vars(_original).items():
    if _name.startswith("__") or _name == "research_topic":
        continue
    globals()[_name] = _value

globals()["research_topic"] = research_topic

globals()["_score_source"] = _strict_score_source

globals()["_extract_subject"] = _strict_extract_subject

__all__ = ["research_topic"]
