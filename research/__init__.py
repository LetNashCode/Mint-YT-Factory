"""Compatibility wrapper for the existing research.py evidence engine."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re

_ROOT = Path(__file__).resolve().parent.parent
_ORIGINAL_PATH = _ROOT / "research.py"
_spec = importlib.util.spec_from_file_location("_mint_original_research", _ORIGINAL_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load original research module: {_ORIGINAL_PATH}")
_original = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_original)

_ORIGINAL_EXTRACT_SUBJECT = _original._extract_subject
_ORIGINAL_EXTRACT_PHENOMENON = _original._extract_phenomenon
_ORIGINAL_SCORE_SOURCE = _original._score_source

_EXTRA_SUBJECT_SEPARATORS = (
    " smell ", " smells ", " taste ", " tastes ",
    " get ", " gets ", " appear ", " appears ",
    " seem ", " seems ", " turn ", " turns ",
)


def _strict_extract_subject(topic):
    lowered = _original._clean(topic).lower()
    subject = _ORIGINAL_EXTRACT_SUBJECT(topic)
    excluded = {
        "slow", "slows", "slowing", "speed", "speeding", "faster",
        "starting", "stopping", "stopped", "turning", "during", "while",
        "after", "before", "cold", "hot",
    }
    for separator in _EXTRA_SUBJECT_SEPARATORS:
        if separator not in lowered:
            continue
        left = lowered.split(separator, 1)[0]
        left_tokens = [t for t in _original._tokens(left) if t not in excluded]
        if left_tokens:
            return [" ".join(left_tokens), *left_tokens]
    return subject


def _strict_extract_phenomenon(topic):
    lowered = _original._clean(topic).lower()
    original = list(_ORIGINAL_EXTRACT_PHENOMENON(topic) or [])
    rules = (
        (("feel prickly", "feels prickly", "prickly tongue", "prickling"),
         ["prickly", "prickling", "tingling", "tingly", "stinging", "stinging sensation", "oral irritation", "irritation", "tongue"]),
        (("feel tingly", "feels tingly", "tingling tongue"),
         ["tingling", "tingly", "prickling", "stinging", "oral irritation", "tongue"]),
        (("feel burning", "feels burning", "burning tongue"),
         ["burning", "burning sensation", "oral irritation", "irritation", "tongue"]),
        (("eyes water", "eye water", "watery eyes", "make your eyes water"),
         ["tearing", "tear", "lacrimation", "watery eyes", "ocular irritation", "eye irritation"]),
    )
    for phrases, expanded in rules:
        if any(phrase in lowered for phrase in phrases):
            return expanded
    return original


_original._extract_subject = _strict_extract_subject
_original._extract_phenomenon = _strict_extract_phenomenon

_GENERIC_SUBJECT_WORDS = {
    "fresh", "good", "right", "different", "cold", "hot", "new",
    "real", "normal", "common", "everyday", "often", "sometimes",
}

_TOPIC_ALIASES = {
    "pineapple": {"pineapple", "pineapples", "ananas", "ananas comosus", "bromelain", "bromelains", "protease", "proteases"},
    "pineapples": {"pineapple", "pineapples", "ananas", "ananas comosus", "bromelain", "bromelains", "protease", "proteases"},
    "onion": {"onion", "onions", "allium", "allium cepa"},
    "onions": {"onion", "onions", "allium", "allium cepa"},
}

_PHENOMENON_SYNONYMS = {
    "smell": {"smell", "smells", "odor", "odour", "aroma", "aromas", "fragrance"},
    "odor": {"smell", "smells", "odor", "odour", "aroma", "aromas", "fragrance"},
    "odour": {"smell", "smells", "odor", "odour", "aroma", "aromas", "fragrance"},
    "sound": {"sound", "sounds", "noise", "noises", "acoustic", "audio", "echo", "echoes"},
    "sounds": {"sound", "sounds", "noise", "noises", "acoustic", "audio", "echo", "echoes"},
    "feel": {"feel", "feels", "feeling", "sensation", "perception"},
    "feels": {"feel", "feels", "feeling", "sensation", "perception"},
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
    expanded_subject = set(subject_terms)
    for term in subject_terms:
        expanded_subject.update(_TOPIC_ALIASES.get(term, {term}))

    phenomenon_terms = set()
    for item in structure.get("phenomenon", []):
        for word in _content_terms(item):
            phenomenon_terms.update(_PHENOMENON_SYNONYMS.get(word, {word}))

    lowered = _original._clean(topic).lower()
    if "tongue" in lowered:
        phenomenon_terms.update({"tongue", "oral", "mouth", "oral irritation", "irritation", "tingling", "prickling", "stinging"})
    if "eyes water" in lowered or "watery eyes" in lowered:
        phenomenon_terms.update({"eye", "eyes", "tear", "tears", "tearing", "lacrimation", "ocular irritation", "eye irritation"})

    if not phenomenon_terms:
        phenomenon_terms.update(
            token for token in _original._tokens(topic)
            if token not in subject_terms and token not in _GENERIC_SUBJECT_WORDS
        )
    return expanded_subject, phenomenon_terms


def _source_matches_current_topic(topic, source):
    subject_terms, phenomenon_terms = _topic_identity(topic)
    if not subject_terms or not phenomenon_terms:
        return True
    title = _original._clean(source.get("title", ""))
    evidence = _original._clean_abstract(source.get("evidence_text", "") or source.get("abstract", ""))
    combined = f"{title} {evidence}"
    subject_hit = any(_original._term_match(term, combined) for term in subject_terms)
    phenomenon_hit = any(_original._term_match(term, combined) for term in phenomenon_terms)
    return subject_hit and phenomenon_hit


def _strict_score_source(topic, source):
    result = _ORIGINAL_SCORE_SOURCE(topic, source)
    if not _source_matches_current_topic(topic, source):
        result["scientific_relevance_pass"] = False
        result["concept_coverage_pass"] = False
        result["intent_pass"] = False
        result["relevance_class"] = "weak"
        result.setdefault("rejection_reasons", []).append("current_topic_identity_mismatch")
    return result

_original._score_source = _strict_score_source
_original_research_topic = _original.research_topic


def research_topic(topic):
    package = _original_research_topic(topic)
    sources = package.get("sources", [])
    if not isinstance(sources, list):
        raise RuntimeError("RESEARCH FAILED: verified sources are not a list.")
    filtered = [source for source in sources if _source_matches_current_topic(topic, source)]
    rejected = [source.get("title", "") for source in sources if source not in filtered]
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

for _name, _value in vars(_original).items():
    if _name.startswith("__") or _name in {"research_topic", "_extract_subject", "_extract_phenomenon", "_score_source"}:
        continue
    globals()[_name] = _value

globals()["research_topic"] = research_topic
globals()["_score_source"] = _strict_score_source
globals()["_extract_subject"] = _strict_extract_subject
globals()["_extract_phenomenon"] = _strict_extract_phenomenon

__all__ = ["research_topic"]
