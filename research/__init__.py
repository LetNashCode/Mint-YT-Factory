"""
Mint-YT-Factory research compatibility wrapper.

The project keeps the existing research.py implementation intact and exposes
its public API through this package. The wrapper tightens question parsing so
that a generic phenomenon term (for example, "smell") cannot accidentally
be treated as the subject of the question and allow an unrelated paper to
pass the scientific relevance gate.
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
# The original extractor already tries to isolate the subject before verbs
# such as "sound" and "feel", but it did not include "smell". That meant a
# topic such as "why does fresh bread smell..." could produce "smell" as a
# subject token. An unrelated smell paper could then satisfy the subject gate.
# Keep the original algorithm and add the missing observable predicates.
# ---------------------------------------------------------------------------

_EXTRA_SUBJECT_SEPARATORS = (
    " smell ",
    " smells ",
    " taste ",
    " tastes ",
    " get ",
    " gets ",
    " appear ",
    " appears ",
    " seem ",
    " seems ",
    " turn ",
    " turns ",
)


def _strict_extract_subject(topic):
    lowered = _original._clean(topic).lower()

    subject = _original._extract_subject(topic)

    # Prefer the precise subject phrase before an observable predicate.
    for separator in _EXTRA_SUBJECT_SEPARATORS:
        if separator not in lowered:
            continue

        left = lowered.split(separator, 1)[0]
        left_tokens = [
            token
            for token in _original._tokens(left)
            if token not in {
                "slow", "slows", "slowing", "speed", "speeding",
                "faster", "starting", "stopping", "stopped", "turning",
                "during", "while", "after", "before", "cold", "hot",
            }
        ]

        if left_tokens:
            return [" ".join(left_tokens), *left_tokens]

    return subject


_original._extract_subject = _strict_extract_subject


# ---------------------------------------------------------------------------
# Final topic-identity guard
# ---------------------------------------------------------------------------
# This is deliberately concept-based rather than a single keyword check.
# A source must support both the concrete subject and the observable
# phenomenon. For example, a COVID smell-loss paper contains "smell" but not
# the concrete subject "bread", so it cannot pass a bread-aroma question.
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
    "feel": {"feel", "feels", "feeling", "cold", "colder", "temperature", "sensation", "perception"},
    "taste": {"taste", "tastes", "flavor", "flavour", "flavors", "flavours", "taste"},
    "get": {"get", "gets", "become", "becomes", "change", "changes"},
}


def _content_terms(text):
    return set(re.findall(r"[a-z0-9]+", _original._clean(text).lower()))


def _topic_identity(topic):
    structure = _original._question_structure(topic)
    subject_phrase = structure.get("subject", [])[:1]
    subject_phrase = subject_phrase[0] if subject_phrase else ""
    subject_terms = [
        token
        for token in _original._tokens(subject_phrase)
        if token not in _GENERIC_SUBJECT_WORDS
    ]

    phenomenon = structure.get("phenomenon", [])
    phenomenon_terms = set()
    for item in phenomenon:
        words = _content_terms(item)
        for word in words:
            phenomenon_terms.update(
                _PHENOMENON_SYNONYMS.get(word, {word})
            )

    # If the parser has no explicit phenomenon, use the remaining topic
    # content after the subject as a conservative fallback.
    if not phenomenon_terms:
        topic_terms = _original._tokens(topic)
        phenomenon_terms.update(
            token for token in topic_terms
            if token not in subject_terms
            and token not in _GENERIC_SUBJECT_WORDS
        )

    return subject_terms, phenomenon_terms


def _source_matches_current_topic(topic, source):
    subject_terms, phenomenon_terms = _topic_identity(topic)

    if not subject_terms or not phenomenon_terms:
        return True

    title = _original._clean(source.get("title", ""))
    evidence = _original._clean_abstract(
        source.get("evidence_text", "") or source.get("abstract", "")
    )

    combined = f"{title} {evidence}"
    combined_terms = _content_terms(combined)

    subject_hit = any(
        _original._term_match(term, combined)
        for term in subject_terms
    )

    phenomenon_hit = any(
        _original._term_match(term, combined)
        for term in phenomenon_terms
    )

    return subject_hit and phenomenon_hit


_original_research_topic = _original.research_topic


def research_topic(topic):
    package = _original_research_topic(topic)

    sources = package.get("sources", [])
    if not isinstance(sources, list):
        raise RuntimeError("RESEARCH FAILED: verified sources are not a list.")

    filtered = [
        source
        for source in sources
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


# Expose the original module API while overriding research_topic.
for _name, _value in vars(_original).items():
    if _name.startswith("__") or _name == "research_topic":
        continue
    globals()[_name] = _value

globals()["research_topic"] = research_topic

__all__ = ["research_topic"]
