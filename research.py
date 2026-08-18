"""
research.py
Mint-YT-Factory

Version 7.3

Hardened research/evidence layer.

v7.3 improvements:
- Question-intent aware relevance
- Mechanism-first topic matching
- Separates subject from question mechanism
- Prevents generic subject-only papers from passing
- Strong protection against agriculture/production/topic drift
- Deterministic scholarly query expansion
- Better question-to-paper matching
- Semantic concept expansion without Gemini
- DOI remains the authoritative identity key
- At least two distinct DOI-backed papers required
- Abstract evidence remains mandatory
- Crossref/OpenAlex/Semantic Scholar remain independent providers
- Semantic Scholar 429 circuit breaker
- DOI identity verification remains strict
- Final relevance is checked again after evidence enrichment
- Final source IDs remain deterministic
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

VERSION = "7.3"

CROSSREF_URL = "https://api.crossref.org/v1/works"
SEMANTIC_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_PAPER_URL = "https://api.semanticscholar.org/graph/v1/paper"
OPENALEX_URL = "https://api.openalex.org/works"

TIMEOUT = 30

MAX_CROSSREF_RESULTS = 15
MAX_SEMANTIC_RESULTS = 10
MAX_OPENALEX_RESULTS = 12

MAX_VERIFICATION_CANDIDATES = 12
MAX_EVIDENCE_SOURCES = 5

MIN_ACCEPTED_SOURCES = 2
MIN_ABSTRACT_CHARACTERS = 120
MAX_EVIDENCE_TEXT_CHARACTERS = 12000

TITLE_SIMILARITY_MINIMUM = 0.55

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


# ==========================================================================
# HTTP
# ==========================================================================

def _get(
    url,
    params=None,
    retries=1,
    backoff=2,
    provider=None,
):
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

                if provider == "Semantic Scholar":
                    SEMANTIC_RATE_LIMITED = True

                    raise RuntimeError(
                        "Semantic Scholar HTTP 429 rate limit exceeded."
                    )

                if retry_after:
                    try:
                        delay = float(retry_after)
                    except Exception:
                        delay = backoff * (attempt + 1)
                else:
                    delay = backoff * (attempt + 1)

                if attempt < retries:
                    print(
                        f"⚠️ HTTP 429. Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    continue

                raise RuntimeError("HTTP 429 rate limit exceeded.")

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


# ==========================================================================
# TEXT / DOI
# ==========================================================================

def _clean(text):

    if text is None:
        return ""

    return re.sub(r"\s+", " ", str(text)).strip()


def _clean_abstract(text):

    text = _clean(text)

    if not text:
        return ""

    text = re.sub(r"<[^>]+>", " ", text)

    return re.sub(r"\s+", " ", text).strip()


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

    return " ".join(title.split())


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


# ==========================================================================
# STOPWORDS
# ==========================================================================

STOPWORDS = {
    "how", "do", "does", "did", "can", "could", "would",
    "should", "the", "a", "an", "and", "or", "to", "of",
    "in", "on", "for", "with", "from", "why", "what", "is",
    "are", "be", "their", "they", "them", "these", "those",
    "this", "that", "about", "into", "through", "will",
    "your", "our", "its", "it", "as", "by", "at", "over",
    "under", "than", "then", "when", "where", "which",
    "who", "during", "using", "long", "way", "ways",
    "happen", "happens", "really", "not", "doesnt", "don't",
    "you", "yourself",
}


# ==========================================================================
# QUESTION INTENT
# ==========================================================================

"""
The most important v7.3 change.

The old system treated the topic mostly as a bag of words.

That means:

    why do your eyes water when cutting onions

could match:

    onion production
    onion agriculture
    onion yield
    onion cultivation

because all of those contain "onion".

v7.3 explicitly identifies:

    SUBJECT
    ACTION / EVENT
    TARGET
    MECHANISM / EFFECT
    QUESTION TYPE

These are used for relevance protection.

They are NOT evidence themselves.
"""

QUESTION_INTENT_RULES = {

    "watering": {
        "trigger": {
            "water",
            "watering",
            "watery",
            "tears",
            "tearing",
            "cry",
            "crying",
            "lacrimation",
            "lachrymation",
        },

        "required": {
            "eye",
            "onion",
        },

        "mechanism": {
            "tear",
            "tears",
            "tearing",
            "lacrimation",
            "lachrymation",
            "lachrymatory",
            "lachrymator",
            "irritation",
            "irritant",
            "volatile",
            "volatiles",
            "sulfur",
            "sulphur",
            "syn-propanethial-s-oxide",
            "propanethial",
            "sulfenic",
            "sulfenic acid",
        },

        "event": {
            "cut",
            "cutting",
            "slice",
            "slicing",
            "chop",
            "chopping",
            "damage",
            "damaged",
            "tissue",
            "plant tissue",
        },

        "target": {
            "eye",
            "eyes",
            "ocular",
            "ophthalmic",
            "lacrimal",
        },

        "negative": {
            "production",
            "agriculture",
            "agricultural",
            "cultivation",
            "cultivating",
            "yield",
            "harvest",
            "harvesting",
            "fertilizer",
            "fertilisation",
            "fertilization",
            "irrigation",
            "crop",
            "crops",
            "farm",
            "farming",
            "soil",
            "field",
            "fields",
            "breeding",
            "storage",
            "postharvest",
            "postharvest",
        },
    },
}


def _detect_question_intent(topic):

    text = _clean(topic).lower()

    tokens = set(
        re.findall(
            r"[a-z0-9-]+",
            text,
        )
    )

    intents = []

    for intent_name, rules in QUESTION_INTENT_RULES.items():

        if tokens & rules["trigger"]:

            intents.append(intent_name)

    # Special high-confidence pattern:
    #
    # "eyes water when cutting onions"
    # "eyes water while cutting onion"
    # "onions make eyes water"
    #
    if (
        (
            "eye" in tokens
            or "eyes" in tokens
        )
        and (
            "water" in tokens
            or "watering" in tokens
            or "tears" in tokens
            or "cry" in tokens
            or "crying" in tokens
        )
        and (
            "onion" in tokens
            or "onions" in tokens
        )
    ):

        if "watering" not in intents:
            intents.append("watering")

    return intents


def _intent_profile(topic):

    intents = _detect_question_intent(topic)

    profile = {
        "intents": intents,
        "required_terms": set(),
        "mechanism_terms": set(),
        "event_terms": set(),
        "target_terms": set(),
        "negative_terms": set(),
    }

    for intent in intents:

        rules = QUESTION_INTENT_RULES.get(
            intent,
            {},
        )

        profile["required_terms"].update(
            rules.get("required", set())
        )

        profile["mechanism_terms"].update(
            rules.get("mechanism", set())
        )

        profile["event_terms"].update(
            rules.get("event", set())
        )

        profile["target_terms"].update(
            rules.get("target", set())
        )

        profile["negative_terms"].update(
            rules.get("negative", set())
        )

    return profile


# ==========================================================================
# DYNAMIC RELATED VOCABULARY
# ==========================================================================

RELATED_TERMS = {

    "eye": {
        "eyes",
        "ocular",
        "ophthalmic",
        "lacrimal",
        "tear",
        "tears",
        "tearing",
        "lachrymation",
    },

    "eyes": {
        "eye",
        "ocular",
        "ophthalmic",
        "lacrimal",
        "tear",
        "tears",
        "tearing",
        "lachrymation",
    },

    "water": {
        "tear",
        "tears",
        "tearing",
        "lacrimation",
        "lachrymation",
    },

    "watering": {
        "tearing",
        "lacrimation",
        "lachrymation",
        "tear",
        "tears",
    },

    "onion": {
        "onions",
        "allium",
        "alliums",
        "bulb",
        "bulbs",
        "volatile",
        "volatiles",
        "sulfur",
        "sulphur",
        "lachrymatory",
        "lachrymator",
        "propanethial",
        "sulfenic",
    },

    "onions": {
        "onion",
        "allium",
        "alliums",
        "bulb",
        "bulbs",
        "volatile",
        "volatiles",
        "sulfur",
        "sulphur",
        "lachrymatory",
        "lachrymator",
        "propanethial",
        "sulfenic",
    },

    "cry": {
        "tears",
        "tearing",
        "lacrimation",
        "lachrymation",
    },

    "crying": {
        "tears",
        "tearing",
        "lacrimation",
        "lachrymation",
    },

    "cutting": {
        "cut",
        "slicing",
        "chopping",
        "processing",
        "tissue",
        "plant tissue",
        "cell damage",
        "wounding",
    },

    "smell": {
        "odor",
        "odour",
        "olfaction",
        "volatile",
        "volatiles",
        "odorant",
        "odorous",
    },

    "smoke": {
        "particulate",
        "aerosol",
        "irritant",
        "irritation",
        "respiratory",
        "volatile",
    },

    "burn": {
        "irritation",
        "irritant",
        "inflammation",
        "inflammatory",
    },

    "pain": {
        "nociception",
        "nociceptive",
        "painful",
        "irritation",
        "inflammation",
    },

    "sleep": {
        "sleeping",
        "circadian",
        "sleep-wake",
        "insomnia",
        "melatonin",
        "sleep duration",
    },

    "dream": {
        "dreaming",
        "dreams",
        "REM",
        "rapid eye movement",
        "sleep",
    },

    "memory": {
        "remembering",
        "recall",
        "learning",
        "retention",
        "cognition",
        "cognitive",
    },

    "heart": {
        "cardiac",
        "cardiovascular",
        "myocardial",
        "heart rate",
    },

    "brain": {
        "neural",
        "neuronal",
        "neurological",
        "cognitive",
        "cognition",
        "neuroscience",
    },

    "stress": {
        "cortisol",
        "physiological",
        "psychological",
        "stress response",
    },

    "cold": {
        "temperature",
        "cooling",
        "cold exposure",
        "thermoregulation",
    },

    "heat": {
        "temperature",
        "thermal",
        "thermoregulation",
        "heat exposure",
    },

    "food": {
        "diet",
        "dietary",
        "nutrition",
        "nutrient",
        "ingestion",
    },

    "sugar": {
        "glucose",
        "glycemic",
        "carbohydrate",
        "metabolic",
        "insulin",
    },

    "coffee": {
        "caffeine",
        "coffee consumption",
        "caffeinated",
    },

    "tea": {
        "tea consumption",
        "polyphenol",
        "caffeine",
        "catechin",
    },

    "salt": {
        "sodium",
        "sodium chloride",
        "electrolyte",
    },

    "exercise": {
        "physical activity",
        "exercise",
        "training",
        "aerobic",
        "physiological",
    },

    "running": {
        "exercise",
        "running",
        "endurance",
        "aerobic",
        "physical activity",
    },

    "walking": {
        "physical activity",
        "gait",
        "locomotion",
        "exercise",
    },

    "aging": {
        "ageing",
        "older adults",
        "senescence",
        "lifespan",
        "longevity",
    },

    "ageing": {
        "aging",
        "older adults",
        "senescence",
        "lifespan",
        "longevity",
    },

    "skin": {
        "dermal",
        "cutaneous",
        "epidermal",
        "dermatological",
    },

    "blood": {
        "hematological",
        "haematological",
        "circulation",
        "vascular",
    },

    "bone": {
        "skeletal",
        "bone tissue",
        "osteoblast",
        "osteoclast",
    },

    "muscle": {
        "muscular",
        "skeletal muscle",
        "myocyte",
        "muscle tissue",
    },

    "virus": {
        "viral",
        "infection",
        "pathogen",
        "pathogenic",
    },

    "bacteria": {
        "bacterial",
        "microbial",
        "microbiome",
        "microorganism",
    },

    "plants": {
        "plant",
        "vegetation",
        "botanical",
        "botany",
        "flora",
    },

    "tree": {
        "trees",
        "woody",
        "forest",
        "woodland",
        "canopy",
    },

    "trees": {
        "tree",
        "woody",
        "forest",
        "woodland",
        "canopy",
    },

    "ocean": {
        "marine",
        "sea",
        "underwater",
        "oceanic",
    },

    "sea": {
        "marine",
        "ocean",
        "underwater",
        "oceanic",
    },

    "space": {
        "astronomy",
        "astronomical",
        "cosmic",
        "planetary",
        "celestial",
    },

    "planet": {
        "planetary",
        "astronomical",
        "celestial",
        "space",
    },

    "quantum": {
        "quantum",
        "photon",
        "photons",
        "entanglement",
        "superposition",
    },

    "magnet": {
        "magnetic",
        "magnetism",
        "magnetoreception",
        "geomagnetic",
    },

    "sound": {
        "acoustic",
        "auditory",
        "hearing",
        "frequency",
    },

    "music": {
        "auditory",
        "acoustic",
        "sound",
        "neural",
        "hearing",
    },

    "light": {
        "visual",
        "vision",
        "photoreceptor",
        "wavelength",
        "optical",
    },

    "gravity": {
        "gravitational",
        "gravitation",
        "weight",
    },

    "technology": {
        "technological",
        "computer",
        "software",
        "algorithm",
        "machine",
    },

    "ai": {
        "artificial intelligence",
        "machine learning",
        "neural network",
        "computational",
    },

    "artificial": {
        "artificial intelligence",
        "machine learning",
        "computational",
    },

    "intelligence": {
        "cognitive",
        "machine learning",
        "artificial intelligence",
    },
}


# ==========================================================================
# GENERIC CONCEPT GROUPS
# ==========================================================================

CONCEPT_GROUPS = {

    "trees": {
        "tree", "trees", "woody", "wood", "forest", "forests",
        "woodland", "woodlands", "canopy", "canopies",
    },

    "plants": {
        "plant", "plants", "vegetation", "seedling", "seedlings",
        "botanical", "botany", "flora",
    },

    "communication": {
        "communicate", "communicates", "communicated",
        "communicating", "communication", "communications",
        "signal", "signals", "signaling", "signalling",
        "chemical", "chemicals", "cue", "cues",
    },

    "mycorrhiza": {
        "mycorrhiza", "mycorrhizae", "mycorrhizal",
        "fungus", "fungi", "fungal", "symbiosis", "symbiotic",
    },

    "fungal_network": {
        "fungal", "fungus", "fungi", "hyphae", "hyphal",
        "mycelium", "mycelial", "network", "networks",
    },

    "underground": {
        "underground", "belowground", "subterranean",
        "soil", "soils", "rhizosphere",
    },

    "wood_wide_web": {
        "wood", "wide", "web", "mycorrhizal",
        "network", "networks", "fungal", "mycelial",
    },

    "roots": {
        "root", "roots", "rooting", "gravitropism",
        "gravitropic", "gravity",
    },

    "bird": {
        "bird", "birds", "avian", "passerine", "songbird",
        "songbirds", "waterfowl", "shorebird", "shorebirds",
        "raptor", "raptors", "pigeon", "pigeons",
    },

    "navigation": {
        "navigate", "navigates", "navigated", "navigating",
        "navigation", "navigational", "orientation",
        "orient", "orients", "oriented", "compass",
        "directional", "direction", "directions",
    },

    "migration": {
        "migration", "migrations", "migratory", "migrate",
        "migrates", "migrated", "migrating",
        "migrant", "migrants",
    },

    "flight": {
        "flight", "flights", "flying", "fly", "flies",
        "flew", "aerial", "transoceanic",
    },

    "magnetic": {
        "magnetic", "magnetism", "magnetoreception",
        "geomagnetic", "magneticfield",
    },

    "brain": {
        "brain", "brains", "neural", "neuronal",
        "neuroscience", "hippocampus", "nidopallium",
        "neuron", "neurons",
    },

    "climate": {
        "climate", "climatic", "warming",
        "temperature", "temperatures", "environmental",
    },

    "pressure": {
        "pressure", "pressures", "depth", "deep", "deepsea",
    },

    "ocean": {
        "ocean", "oceans", "marine", "underwater",
        "sea", "seas",
    },

    "space": {
        "space", "planet", "planets", "star", "stars",
        "galaxy", "galaxies", "cosmic", "astronomy",
        "astronomical",
    },

    "quantum": {
        "quantum", "photons", "photon",
        "entanglement", "superposition",
    },

    "human": {
        "human", "humans", "people", "person", "persons",
    },

    "medical": {
        "medical", "medicine", "clinical", "patient",
        "patients", "health", "disease", "diseases",
        "treatment",
    },

    "technology": {
        "technology", "technological", "computer",
        "computers", "software", "hardware", "algorithm",
        "algorithms", "machine", "machines",
    },

    "memory": {
        "memory", "memories", "remember", "remembering",
        "recall", "learning", "learned",
    },

    "sleep": {
        "sleep", "sleeping", "dream", "dreaming",
        "circadian", "insomnia",
    },

    "sound": {
        "sound", "sounds", "hearing", "auditory",
        "acoustic", "frequency", "frequencies",
    },

    "light": {
        "light", "visual", "vision", "photoreceptor",
        "photoreceptors", "wavelength", "wavelengths",
    },

    "gravity": {
        "gravity", "gravitational", "gravitation", "weight",
    },

    "eye": {
        "eye", "eyes", "ocular", "ophthalmic",
        "lacrimal", "tear", "tears", "tearing",
        "lachrymation",
    },

    "onion": {
        "onion", "onions", "allium", "alliums",
        "bulb", "bulbs", "lachrymatory", "lachrymator",
        "propanethial",
    },

    "irritation": {
        "irritation", "irritant", "irritants",
        "inflammation", "inflammatory",
    },

    "lachrymatory": {
        "lachrymatory", "lachrymator",
        "tear", "tears", "tearing",
        "lacrimation", "lachrymation",
    },
}


DOMAIN_CONCEPTS = {
    "bird",
    "trees",
    "plants",
    "space",
    "ocean",
    "human",
    "technology",
    "quantum",
    "medical",
}


# ==========================================================================
# TOKENIZATION
# ==========================================================================

def _tokenize(text):

    return [
        token
        for token in re.findall(
            r"[a-z0-9]+",
            _clean(text).lower(),
        )
        if token not in STOPWORDS and len(token) >= 3
    ]


def _topic_terms(topic):

    return set(_tokenize(topic))


def _expanded_topic_terms(topic):

    base_terms = _topic_terms(topic)

    expanded = set(base_terms)

    for term in base_terms:

        expanded.update(
            RELATED_TERMS.get(term, set())
        )

    # Simple morphological variants
    for term in list(base_terms):

        if term.endswith("ies") and len(term) > 4:
            expanded.add(term[:-3] + "y")

        if term.endswith("ing") and len(term) > 5:
            expanded.add(term[:-3])

        if term.endswith("ed") and len(term) > 4:
            expanded.add(term[:-2])

        if term.endswith("s") and len(term) > 4:
            expanded.add(term[:-1])

    return {
        term.lower().strip()
        for term in expanded
        if len(term.strip()) >= 3
    }


def _concepts_from_text(text):

    tokens = set(_tokenize(text))

    return {
        concept
        for concept, words in CONCEPT_GROUPS.items()
        if tokens & words
    }


def _topic_concepts(topic):

    concepts = _concepts_from_text(topic)

    expanded_terms = _expanded_topic_terms(topic)

    expanded_text = " ".join(expanded_terms)

    concepts.update(
        _concepts_from_text(expanded_text)
    )

    return concepts


def _stem_like_match(term, text):

    if not term:
        return False

    candidates = {term}

    if " " in term:
        return term.lower() in text.lower()

    if term.endswith("ies") and len(term) > 4:
        candidates.add(term[:-3] + "y")

    if term.endswith("ing") and len(term) > 5:
        candidates.add(term[:-3])

    if term.endswith("ed") and len(term) > 4:
        candidates.add(term[:-2])

    if term.endswith("s") and len(term) > 4:
        candidates.add(term[:-1])

    for candidate in candidates:

        if len(candidate) < 4:
            continue

        if re.search(
            rf"\b{re.escape(candidate)}\w*\b",
            text,
        ):
            return True

    return False


def _term_matches_text(term, text):

    text = _clean(text).lower()

    if not term:
        return False

    term = term.lower().strip()

    if " " in term:
        return term in text

    return _stem_like_match(
        term,
        text,
    )


def _matched_terms(terms, text):

    return {
        term
        for term in terms
        if _term_matches_text(
            term,
            text,
        )
    }


# ==========================================================================
# SCHOLARLY QUERY GENERATION
# ==========================================================================

def build_scholarly_queries(topic):

    base_terms = list(_topic_terms(topic))
    expanded = _expanded_topic_terms(topic)

    profile = _intent_profile(topic)

    subject_terms = [
        term
        for term in base_terms
        if term not in {
            "why",
            "happen",
            "happens",
            "really",
        }
    ]

    related = [
        term
        for term in expanded
        if term not in base_terms
    ]

    queries = []

    # Original natural-language question.
    queries.append(topic)

    # Compact query.
    if subject_terms:
        queries.append(
            " ".join(sorted(subject_terms))
        )

    # ------------------------------------------------------------------
    # INTENT-SPECIFIC SCHOLARLY QUERY
    # ------------------------------------------------------------------

    if "watering" in profile["intents"]:

        queries.append(
            "onion cutting eye tearing "
            "lachrymatory volatile irritation"
        )

        queries.append(
            "Allium onion lachrymatory factor "
            "syn-propanethial-S-oxide tears"
        )

    elif subject_terms and related:

        related_sorted = sorted(
            related,
            key=lambda value: (
                0 if value in {
                    "tear",
                    "tears",
                    "tearing",
                    "lachrymation",
                    "lachrymatory",
                    "irritation",
                    "irritant",
                    "volatile",
                    "volatiles",
                    "sulfur",
                    "sulphur",
                } else 1,
                len(value),
            ),
        )

        selected = related_sorted[:5]

        queries.append(
            " ".join(
                subject_terms[:5] + selected
            )
        )

    # Remove duplicates.
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

    return final[:4]


# ==========================================================================
# INTENT RELEVANCE
# ==========================================================================

def _intent_relevance(topic, source):

    profile = _intent_profile(topic)

    if not profile["intents"]:
        return {
            "intent_score": 0,
            "intent_class": "not_applicable",
            "intent_pass": True,
            "mechanism_matches": [],
            "event_matches": [],
            "target_matches": [],
            "negative_matches": [],
        }

    title = _clean(
        source.get("title", "")
    ).lower()

    evidence = _clean(
        source.get("evidence_text", "")
        or source.get("abstract", "")
    ).lower()

    combined = (
        f"{title} {evidence}"
    )

    mechanism_matches = _matched_terms(
        profile["mechanism_terms"],
        combined,
    )

    event_matches = _matched_terms(
        profile["event_terms"],
        combined,
    )

    target_matches = _matched_terms(
        profile["target_terms"],
        combined,
    )

    negative_matches = _matched_terms(
        profile["negative_terms"],
        combined,
    )

    title_mechanism_matches = _matched_terms(
        profile["mechanism_terms"],
        title,
    )

    evidence_mechanism_matches = _matched_terms(
        profile["mechanism_terms"],
        evidence,
    )

    title_event_matches = _matched_terms(
        profile["event_terms"],
        title,
    )

    evidence_event_matches = _matched_terms(
        profile["event_terms"],
        evidence,
    )

    title_target_matches = _matched_terms(
        profile["target_terms"],
        title,
    )

    evidence_target_matches = _matched_terms(
        profile["target_terms"],
        evidence,
    )

    score = 0

    # --------------------------------------------------------------
    # Mechanism
    # --------------------------------------------------------------

    score += len(
        mechanism_matches
    ) * 7

    score += len(
        title_mechanism_matches
    ) * 5

    # --------------------------------------------------------------
    # Event
    # --------------------------------------------------------------

    score += len(
        event_matches
    ) * 4

    score += len(
        title_event_matches
    ) * 4

    # --------------------------------------------------------------
    # Target
    # --------------------------------------------------------------

    score += len(
        target_matches
    ) * 4

    score += len(
        title_target_matches
    ) * 5

    # --------------------------------------------------------------
    # Negative topic drift
    # --------------------------------------------------------------

    score -= len(
        negative_matches
    ) * 5

    # Strong production/agriculture protection.
    if (
        negative_matches
        and not mechanism_matches
    ):
        score -= 20

    # --------------------------------------------------------------
    # High-confidence mechanism combination
    # --------------------------------------------------------------

    if (
        mechanism_matches
        and (
            event_matches
            or target_matches
        )
    ):
        score += 15

    # --------------------------------------------------------------
    # Classification
    # --------------------------------------------------------------

    if "watering" in profile["intents"]:

        # Strong:
        #
        # mechanism + eye
        #
        # or mechanism + cutting
        #
        # or several mechanism terms.
        if (
            len(mechanism_matches) >= 2
            and (
                target_matches
                or event_matches
            )
        ):

            intent_class = "strong"

        elif (
            mechanism_matches
            and target_matches
            and event_matches
        ):

            intent_class = "strong"

        elif (
            len(mechanism_matches) >= 1
            and (
                target_matches
                or event_matches
            )
        ):

            intent_class = "moderate"

        else:

            intent_class = "weak"

        # ----------------------------------------------------------
        # Hard rejection:
        #
        # Onion production/agriculture papers that don't actually
        # discuss the eye/tearing mechanism cannot pass.
        # ----------------------------------------------------------

        if (
            negative_matches
            and not mechanism_matches
        ):

            intent_class = "mismatch"

        # Another hard protection:
        #
        # Subject-only onion paper = mismatch.
        #
        if (
            not mechanism_matches
            and not target_matches
            and not event_matches
        ):

            intent_class = "mismatch"

    else:

        intent_class = (
            "strong"
            if score >= 20
            else "moderate"
            if score >= 8
            else "weak"
        )

    return {
        "intent_score": score,
        "intent_class": intent_class,
        "intent_pass": intent_class in {
            "strong",
            "moderate",
        },
        "mechanism_matches": sorted(
            mechanism_matches
        ),
        "event_matches": sorted(
            event_matches
        ),
        "target_matches": sorted(
            target_matches
        ),
        "negative_matches": sorted(
            negative_matches
        ),
        "title_mechanism_matches": sorted(
            title_mechanism_matches
        ),
        "evidence_mechanism_matches": sorted(
            evidence_mechanism_matches
        ),
        "title_event_matches": sorted(
            title_event_matches
        ),
        "evidence_event_matches": sorted(
            evidence_event_matches
        ),
        "title_target_matches": sorted(
            title_target_matches
        ),
        "evidence_target_matches": sorted(
            evidence_target_matches
        ),
    }


# ==========================================================================
# RELEVANCE
# ==========================================================================

def _relevance_score(topic, source):

    title = _clean(
        source.get("title", "")
    ).lower()

    evidence = _clean(
        source.get("evidence_text", "")
        or source.get("abstract", "")
    ).lower()

    title_clean = re.sub(
        r"[^a-z0-9\s-]",
        " ",
        title,
    )

    evidence_clean = re.sub(
        r"[^a-z0-9\s-]",
        " ",
        evidence,
    )

    topic_terms = _topic_terms(topic)
    expanded_terms = _expanded_topic_terms(topic)
    topic_concepts = _topic_concepts(topic)

    title_concepts = _concepts_from_text(title_clean)
    evidence_concepts = _concepts_from_text(evidence_clean)

    title_concept_matches = (
        topic_concepts & title_concepts
    )

    evidence_concept_matches = (
        topic_concepts & evidence_concepts
    )

    score = 0
    matched_terms = []

    exact_topic_matches = 0
    expanded_title_matches = 0
    evidence_term_matches = 0

    # --------------------------------------------------------------
    # Original topic terms
    # --------------------------------------------------------------

    for term in topic_terms:

        if _stem_like_match(term, title_clean):

            exact_topic_matches += 1
            matched_terms.append(term)
            score += 5

        elif _stem_like_match(term, evidence_clean):

            evidence_term_matches += 1
            matched_terms.append(term)
            score += 2

    # --------------------------------------------------------------
    # Expanded scholarly vocabulary
    # --------------------------------------------------------------

    for term in expanded_terms - topic_terms:

        if _stem_like_match(term, title_clean):

            expanded_title_matches += 1
            matched_terms.append(term)
            score += 4

        elif _stem_like_match(term, evidence_clean):

            evidence_term_matches += 1
            matched_terms.append(term)
            score += 1

    # --------------------------------------------------------------
    # Concept matching
    # --------------------------------------------------------------

    score += len(title_concept_matches) * 8

    score += (
        len(
            evidence_concept_matches
            - title_concept_matches
        )
        * 2
    )

    # --------------------------------------------------------------
    # Exact topic phrase
    # --------------------------------------------------------------

    normalized_topic = _normalize_title(topic)
    normalized_title = _normalize_title(title)

    if (
        normalized_topic
        and normalized_topic in normalized_title
    ):
        score += 15

    # --------------------------------------------------------------
    # Adjacent original topic terms
    # --------------------------------------------------------------

    topic_tokens = list(_tokenize(topic))

    for i in range(len(topic_tokens) - 1):

        phrase = (
            f"{topic_tokens[i]} "
            f"{topic_tokens[i + 1]}"
        )

        if phrase in title_clean:
            score += 5

    # --------------------------------------------------------------
    # INTENT / MECHANISM PROTECTION
    # --------------------------------------------------------------

    intent = _intent_relevance(
        topic,
        source,
    )

    intent_score = intent["intent_score"]

    score += intent_score

    # --------------------------------------------------------------
    # Determine relevance class
    # --------------------------------------------------------------

    concept_count = len(topic_concepts)
    title_concept_count = len(title_concept_matches)
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
            exact_topic_matches >= 1
            and expanded_title_matches >= 1
        ):
            relevance_class = "strong"

        elif (
            title_concept_count >= 1
            and evidence_concept_count >= 1
        ):
            relevance_class = "moderate"

        elif (
            exact_topic_matches >= 2
        ):
            relevance_class = "moderate"

        elif (
            exact_topic_matches >= 1
            and evidence_term_matches >= 2
        ):
            relevance_class = "moderate"

        elif (
            expanded_title_matches >= 2
            and evidence_term_matches >= 1
        ):
            relevance_class = "moderate"

        else:
            relevance_class = "weak"

    else:

        if (
            exact_topic_matches >= 2
            or title_concept_count >= 1
        ):
            relevance_class = "moderate"

        elif (
            exact_topic_matches >= 1
            and evidence_term_matches >= 2
        ):
            relevance_class = "moderate"

        elif (
            expanded_title_matches >= 2
            and evidence_term_matches >= 1
        ):
            relevance_class = "moderate"

        else:
            relevance_class = "weak"

    # --------------------------------------------------------------
    # DOMAIN PROTECTION
    # --------------------------------------------------------------

    topic_domains = topic_concepts & DOMAIN_CONCEPTS

    if topic_domains:

        matched_domains = (
            title_concept_matches
            | evidence_concept_matches
        ) & topic_domains

        if not matched_domains:

            relevance_class = "mismatch"
            score = 0

    # --------------------------------------------------------------
    # QUESTION INTENT OVERRIDE
    # --------------------------------------------------------------

    if not intent["intent_pass"]:

        relevance_class = "mismatch"

    # --------------------------------------------------------------
    # HARD SUBJECT-DRIFT PROTECTION
    # --------------------------------------------------------------

    if intent["intent_class"] == "mismatch":

        relevance_class = "mismatch"

    source["matched_terms"] = sorted(
        set(matched_terms)
    )

    source["topic_terms"] = sorted(
        topic_terms
    )

    source["expanded_topic_terms"] = sorted(
        expanded_terms
    )

    source["topic_concepts"] = sorted(
        topic_concepts
    )

    source["title_concepts"] = sorted(
        title_concept_matches
    )

    source["abstract_concepts"] = sorted(
        evidence_concept_matches
    )

    source["title_match_count"] = (
        exact_topic_matches
    )

    source["expanded_title_match_count"] = (
        expanded_title_matches
    )

    source["abstract_match_count"] = (
        evidence_term_matches
    )

    source["topic_concept_coverage"] = round(
        len(
            title_concept_matches
            | evidence_concept_matches
        )
        / max(len(topic_concepts), 1),
        3,
    )

    # Intent metadata
    source["question_intents"] = (
        intent.get("intents", [])
    )

    source["intent_score"] = (
        intent.get("intent_score", 0)
    )

    source["intent_class"] = (
        intent.get(
            "intent_class",
            "not_applicable",
        )
    )

    source["intent_mechanism_matches"] = (
        intent.get(
            "mechanism_matches",
            [],
        )
    )

    source["intent_event_matches"] = (
        intent.get(
            "event_matches",
            [],
        )
    )

    source["intent_target_matches"] = (
        intent.get(
            "target_matches",
            [],
        )
    )

    source["intent_negative_matches"] = (
        intent.get(
            "negative_matches",
            [],
        )
    )

    source["intent_pass"] = bool(
        intent.get(
            "intent_pass",
            True,
        )
    )

    source["relevance_class"] = relevance_class
    source["relevance_score"] = score

    return score


def _is_relevant(source):

    return source.get("relevance_class") in {
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
    print(f"🎯 {label}")
    print("=" * 80)

    topic_concepts = _topic_concepts(topic)
    topic_terms = _topic_terms(topic)
    expanded_terms = _expanded_topic_terms(topic)
    intent_profile = _intent_profile(topic)

    print(
        "Topic terms: "
        + (
            ", ".join(sorted(topic_terms))
            or "none"
        )
    )

    print(
        "Expanded scholarly terms: "
        + (
            ", ".join(sorted(expanded_terms))
            or "none"
        )
    )

    print(
        "Topic concepts: "
        + (
            ", ".join(sorted(topic_concepts))
            or "none"
        )
    )

    print(
        "Question intents: "
        + (
            ", ".join(
                intent_profile["intents"]
            )
            or "none"
        )
    )

    if intent_profile["mechanism_terms"]:

        print(
            "Required mechanism vocabulary: "
            + ", ".join(
                sorted(
                    intent_profile[
                        "mechanism_terms"
                    ]
                )
            )
        )

    for source in sources:

        score = _relevance_score(
            topic,
            source,
        )

        title = source.get("title", "")

        classification = source.get(
            "relevance_class",
            "unknown",
        )

        if _is_relevant(source):

            accepted.append(source)

            print(f"✅ RELEVANT: {title}")
            print(f"   Score: {score}")
            print(f"   Class: {classification}")

            print(
                "   Intent: "
                f"{source.get('intent_class', '')}"
            )

            print(
                "   Mechanism matches: "
                f"{source.get('intent_mechanism_matches', [])}"
            )

            print(
                "   Event matches: "
                f"{source.get('intent_event_matches', [])}"
            )

            print(
                "   Target matches: "
                f"{source.get('intent_target_matches', [])}"
            )

            print(
                "   Negative/drift matches: "
                f"{source.get('intent_negative_matches', [])}"
            )

            print(
                "   Matched terms: "
                f"{source.get('matched_terms', [])}"
            )

            print(
                "   Title concepts: "
                f"{source.get('title_concepts', [])}"
            )

            print(
                "   Evidence concepts: "
                f"{source.get('abstract_concepts', [])}"
            )

        else:

            print(f"❌ REJECTED: {title}")
            print(f"   Score: {score}")
            print(f"   Class: {classification}")

            print(
                "   Intent: "
                f"{source.get('intent_class', '')}"
            )

            if source.get(
                "intent_negative_matches"
            ):

                print(
                    "   🚫 Topic drift detected: "
                    f"{source.get('intent_negative_matches')}"
                )

            if not source.get(
                "intent_mechanism_matches"
            ):

                print(
                    "   🚫 No mechanism evidence."
                )

    print(
        f"Relevant candidates: {len(accepted)}"
    )

    return accepted


# ==========================================================================
# METADATA HELPERS
# ==========================================================================

def _authors_crossref(item):

    authors = []

    for author in item.get("author", []):

        given = _clean(
            author.get("given", "")
        )

        family = _clean(
            author.get("family", "")
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

    for author in item.get("authors", []):

        name = _clean(
            author.get("name", "")
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

        date_info = item.get(key, {})

        if not isinstance(date_info, dict):
            continue

        date_parts = date_info.get(
            "date-parts",
            [],
        )

        if date_parts and date_parts[0]:

            try:
                return int(date_parts[0][0])
            except Exception:
                pass

    return None


def _openalex_abstract_text(inverted_index):

    if not isinstance(inverted_index, dict):
        return ""

    words = []

    for word, positions in inverted_index.items():

        if not isinstance(positions, list):
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

    words.sort(key=lambda x: x[0])

    return _clean_abstract(
        " ".join(
            word
            for _, word in words
        )
    )


def _build_evidence_package(source):

    abstract = _clean_abstract(
        source.get("abstract", "")
    )

    if abstract:

        evidence_available = True
        evidence_type = "abstract"
        evidence_quality = "moderate"
        evidence_text = abstract

        evidence_notes = (
            "Evidence text is a retrieved scholarly "
            "abstract. It is not the full paper."
        )

    else:

        evidence_available = False
        evidence_type = "metadata_only"
        evidence_quality = "none"
        evidence_text = ""

        evidence_notes = (
            "No abstract/evidence text was retrieved. "
            "Metadata alone is not evidence."
        )

    if len(evidence_text) > MAX_EVIDENCE_TEXT_CHARACTERS:

        evidence_text = (
            evidence_text[
                :MAX_EVIDENCE_TEXT_CHARACTERS
            ]
        )

        evidence_notes += (
            " Evidence text was truncated."
        )

    source["evidence_available"] = evidence_available
    source["evidence_type"] = evidence_type
    source["evidence_quality"] = evidence_quality
    source["evidence_text"] = evidence_text
    source["evidence_notes"] = evidence_notes
    source["abstract"] = abstract

    return source


def _record_evidence_provider(
    source,
    provider,
    abstract,
):

    abstract = _clean_abstract(abstract)

    if not abstract:
        return

    providers = set(
        source.get(
            "evidence_providers",
            [],
        )
    )

    providers.add(provider)

    source["evidence_providers"] = sorted(
        providers
    )

    records = source.get(
        "evidence_records",
        [],
    )

    if not isinstance(records, list):
        records = []

    if not any(
        record.get("provider") == provider
        for record in records
        if isinstance(record, dict)
    ):

        records.append(
            {
                "provider": provider,
                "characters": len(abstract),
            }
        )

    source["evidence_records"] = records


# ==========================================================================
# DISCOVERY
# ==========================================================================

def _crossref_search_once(query):

    params = {
        "query.bibliographic": query,
        "rows": MAX_CROSSREF_RESULTS,
        "select": (
            "DOI,title,author,container-title,"
            "publisher,type,published,published-print,"
            "published-online,URL,abstract"
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
        {}
    ).get(
        "items",
        []
    )


def search_crossref(topic):

    print("=" * 80)
    print("🔎 CROSSREF SEARCH")
    print("=" * 80)

    queries = build_scholarly_queries(topic)

    print(
        "Crossref queries:"
    )

    for query in queries:
        print(f"   • {query}")

    all_items = []

    for query in queries:

        try:

            items = _crossref_search_once(
                query
            )

            all_items.extend(items)

        except Exception as error:

            print(
                f"⚠️ Crossref query failed: {query}"
            )

            print(error)

    results = []
    seen = set()

    for item in all_items:

        titles = item.get("title", [])

        title = (
            _clean(titles[0])
            if titles
            else ""
        )

        doi = _normalize_doi(
            item.get("DOI", "")
        )

        if not title or not doi:
            continue

        if doi in seen:
            continue

        seen.add(doi)

        abstract = _clean_abstract(
            item.get("abstract", "")
        )

        source = {
            "source_database": "Crossref",
            "source_databases": ["Crossref"],
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
                item.get("publisher", "")
            ),
            "year": _extract_year(item),
            "doi": doi,
            "url": (
                _clean(item.get("URL", ""))
                or f"https://doi.org/{doi}"
            ),
            "type": _clean(item.get("type", "")),
            "publication_type": _clean(
                item.get("type", "")
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
            "discovery_provider": "Crossref",
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
            _build_evidence_package(source)
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
            "⚠️ Semantic Scholar already "
            "rate-limited; skipping."
        )

        return []

    queries = build_scholarly_queries(topic)

    results = []
    seen = set()

    for query in queries:

        if SEMANTIC_RATE_LIMITED:
            break

        params = {
            "query": query,
            "limit": MAX_SEMANTIC_RESULTS,
            "fields": (
                "title,authors,year,abstract,url,"
                "externalIds,publicationTypes,venue,"
                "citationCount"
            ),
        }

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
                "⚠️ Semantic Scholar unavailable:"
            )

            print(error)

            continue

        for paper in data.get("data", []):

            title = _clean(
                paper.get("title", "")
            )

            if not title:
                continue

            external_ids = (
                paper.get(
                    "externalIds",
                    {},
                )
                or {}
            )

            doi = _normalize_doi(
                external_ids.get("DOI", "")
            )

            if not doi:
                continue

            if doi in seen:
                continue

            seen.add(doi)

            abstract = _clean_abstract(
                paper.get("abstract", "")
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
                "title": title,
                "authors": _authors_semantic(paper),
                "journal": _clean(
                    paper.get("venue", "")
                ),
                "publisher": "",
                "year": paper.get("year"),
                "doi": doi,
                "url": f"https://doi.org/{doi}",
                "semantic_scholar_url": _clean(
                    paper.get("url", "")
                ),
                "abstract": abstract,
                "publication_types": publication_types,
                "publication_type": (
                    publication_types[0]
                    if publication_types
                    else ""
                ),
                "citation_count": (
                    paper.get("citationCount", 0)
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
                "discovery_provider": "Semantic Scholar",
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
                _build_evidence_package(source)
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

    queries = build_scholarly_queries(topic)

    results = []
    seen = set()

    for query in queries:

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
                "⚠️ OpenAlex search failed:"
            )

            print(error)

            continue

        for item in data.get("results", []):

            title = _clean(
                item.get("display_name", "")
            )

            if not title:
                continue

            ids = (
                item.get("ids", {})
                or {}
            )

            doi = _normalize_doi(
                ids.get("doi", "")
            )

            if not doi:
                continue

            if doi in seen:
                continue

            seen.add(doi)

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

            primary_location = (
                item.get(
                    "primary_location",
                    {},
                )
                or {}
            )

            source_info = (
                primary_location.get(
                    "source",
                    {},
                )
                or {}
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
                    ids.get("openalex", "")
                ),
                "abstract": abstract,
                "publication_type": _clean(
                    item.get("type", "")
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
                "discovery_provider": "OpenAlex",
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
                _build_evidence_package(source)
            )

    print(
        f"OpenAlex results: {len(results)}"
    )

    return results


# ==========================================================================
# DEDUPLICATION
# ==========================================================================

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

    if primary.get("source_database"):
        databases.add(
            primary["source_database"]
        )

    if secondary.get("source_database"):
        databases.add(
            secondary["source_database"]
        )

    primary["source_databases"] = sorted(
        x for x in databases if x
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

    for provider in secondary.get(
        "discovery_providers",
        [],
    ):

        primary.setdefault(
            "discovery_providers",
            [],
        )

        if provider not in primary[
            "discovery_providers"
        ]:

            primary[
                "discovery_providers"
            ].append(provider)

    if secondary.get("discovery_provider"):

        primary.setdefault(
            "discovery_providers",
            [],
        )

        if (
            secondary["discovery_provider"]
            not in primary[
                "discovery_providers"
            ]
        ):

            primary[
                "discovery_providers"
            ].append(
                secondary[
                    "discovery_provider"
                ]
            )

    primary_abstract = _clean_abstract(
        primary.get("abstract", "")
    )

    secondary_abstract = _clean_abstract(
        secondary.get("abstract", "")
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

    if len(secondary_abstract) > len(primary_abstract):

        primary["abstract"] = secondary_abstract

        primary["evidence_source"] = (
            secondary.get(
                "evidence_source",
                "",
            )
        )

    primary["citation_count"] = max(
        primary.get("citation_count", 0) or 0,
        secondary.get("citation_count", 0) or 0,
    )

    primary["openalex_citation_count"] = max(
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

    return _build_evidence_package(primary)


def deduplicate_sources(sources):

    by_doi = {}
    by_title = {}
    unique = []

    for source in sources:

        doi = _normalize_doi(
            source.get("doi", "")
        )

        title = _normalize_title(
            source.get("title", "")
        )

        source["doi"] = doi

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

        databases = set(
            source.get(
                "source_databases",
                [],
            )
        )

        source_database = source.get(
            "source_database",
            "",
        )

        if source_database:
            databases.add(source_database)

        source["source_databases"] = sorted(
            databases
        )

        source.setdefault(
            "discovery_providers",
            (
                [
                    source.get(
                        "discovery_provider"
                    )
                ]
                if source.get(
                    "discovery_provider"
                )
                else []
            ),
        )

        unique.append(source)

        if doi:
            by_doi[doi] = source

        if title:
            by_title[title] = source

    return unique


# ==========================================================================
# IDENTITY VERIFICATION
# ==========================================================================

def _identity_matches(
    source,
    returned_title,
    returned_doi,
    provider,
):

    expected_doi = _normalize_doi(
        source.get("doi", "")
    )

    returned_doi = _normalize_doi(
        returned_doi
    )

    if not expected_doi:

        source["identity_error"] = (
            f"{provider}: source has no DOI."
        )

        return False

    if not returned_doi:

        source["identity_error"] = (
            f"{provider}: verification response "
            "did not contain a DOI."
        )

        return False

    if expected_doi != returned_doi:

        source["identity_error"] = (
            f"{provider}: DOI mismatch. "
            f"Expected {expected_doi}, "
            f"got {returned_doi}."
        )

        return False

    original_title = _clean(
        source.get("title", "")
    )

    returned_title = _clean(
        returned_title
    )

    if not returned_title:

        source["identity_error"] = (
            f"{provider}: verification response "
            "did not contain a title."
        )

        return False

    similarity = _title_similarity(
        original_title,
        returned_title,
    )

    source["verified_title_similarity"] = round(
        similarity,
        3,
    )

    if similarity < TITLE_SIMILARITY_MINIMUM:

        source["identity_error"] = (
            f"{provider}: title mismatch. "
            f"Similarity {similarity:.3f} < "
            f"{TITLE_SIMILARITY_MINIMUM:.2f}."
        )

        return False

    return True


def verify_crossref_source(source):

    doi = _normalize_doi(
        source.get("doi", "")
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
            provider="Crossref",
        )

        item = data.get(
            "message",
            {}
        )

        returned_doi = _normalize_doi(
            item.get("DOI", "")
        )

        returned_title = _clean(
            (
                item.get("title", [])
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

        source["metadata_verified"] = True

        source[
            "metadata_verification_provider"
        ] = "Crossref"

        source["verified_title"] = returned_title
        source["doi"] = returned_doi

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
            item.get("publisher", "")
        )

        if publisher:
            source["publisher"] = publisher

        year = _extract_year(item)

        if year:
            source["year"] = year

        abstract = _clean_abstract(
            item.get("abstract", "")
        )

        if abstract:

            source["abstract"] = abstract

            source["evidence_source"] = (
                "Crossref abstract"
            )

            _record_evidence_provider(
                source,
                "Crossref",
                abstract,
            )

        source["verification"] = (
            "DOI and publication identity "
            "verified through Crossref."
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
        source.get("doi", "")
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
            "fields": (
                "title,authors,year,abstract,"
                "externalIds,venue,publicationTypes,"
                "citationCount"
            )
        }

        data = _get(
            url,
            params,
            retries=SEMANTIC_RETRIES,
            backoff=SEMANTIC_BACKOFF_SECONDS,
            provider="Semantic Scholar",
        )

        returned_title = _clean(
            data.get("title", "")
        )

        returned_ids = (
            data.get(
                "externalIds",
                {},
            )
            or {}
        )

        returned_doi = _normalize_doi(
            returned_ids.get("DOI", "")
        )

        if not _identity_matches(
            source,
            returned_title,
            returned_doi,
            "Semantic Scholar",
        ):
            return False

        source["metadata_verified"] = True

        source[
            "metadata_verification_provider"
        ] = "Semantic Scholar"

        source["verified_title"] = returned_title
        source["doi"] = returned_doi

        authors = _authors_semantic(data)

        if authors:
            source["authors"] = authors

        venue = _clean(
            data.get("venue", "")
        )

        if venue:
            source["journal"] = venue

        if data.get("year"):
            source["year"] = data["year"]

        abstract = _clean_abstract(
            data.get("abstract", "")
        )

        if abstract:

            source["abstract"] = abstract

            source["evidence_source"] = (
                "Semantic Scholar abstract"
            )

            _record_evidence_provider(
                source,
                "Semantic Scholar",
                abstract,
            )

        source["citation_count"] = (
            data.get(
                "citationCount",
                source.get(
                    "citation_count",
                    0,
                ),
            )
            or 0
        )

        source["verification"] = (
            "DOI and publication identity "
            "verified through Semantic Scholar."
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
        source.get("doi", "")
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
            provider="OpenAlex",
        )

        returned_ids = (
            data.get("ids", {})
            or {}
        )

        returned_doi = _normalize_doi(
            returned_ids.get("doi", "")
        )

        returned_title = _clean(
            data.get("display_name", "")
        )

        if not _identity_matches(
            source,
            returned_title,
            returned_doi,
            "OpenAlex",
        ):
            return False

        source["metadata_verified"] = True

        source[
            "metadata_verification_provider"
        ] = "OpenAlex"

        source["verified_title"] = returned_title
        source["doi"] = returned_doi

        if data.get("publication_year"):
            source["year"] = data[
                "publication_year"
            ]

        abstract = _openalex_abstract_text(
            data.get(
                "abstract_inverted_index"
            )
        )

        if abstract:

            source["abstract"] = abstract

            source["evidence_source"] = (
                "OpenAlex abstract"
            )

            _record_evidence_provider(
                source,
                "OpenAlex",
                abstract,
            )

        source["openalex_citation_count"] = (
            data.get(
                "cited_by_count",
                0,
            )
            or 0
        )

        source["openalex_id"] = _clean(
            data.get("id", "")
        )

        source["verification"] = (
            "DOI and publication identity "
            "verified through OpenAlex."
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

    ordered = []

    if discovery:
        ordered.append(discovery)

    for provider in (
        "Crossref",
        "OpenAlex",
        "Semantic Scholar",
    ):

        if provider not in ordered:
            ordered.append(provider)

    verification_errors = []

    for provider in ordered:

        print(
            f"   ↪ Trying {provider}..."
        )

        if provider == "Crossref":

            verified = verify_crossref_source(
                source
            )

        elif provider == "Semantic Scholar":

            verified = verify_semantic_source(
                source
            )

        elif provider == "OpenAlex":

            verified = verify_openalex_source(
                source
            )

        else:

            verified = False

        if verified:

            source["verification_attempts"] = ordered

            return source

        for key in (
            "crossref_verification_error",
            "semantic_verification_error",
            "openalex_verification_error",
            "identity_error",
        ):

            if source.get(key):

                verification_errors.append(
                    source[key]
                )

    source["verification_attempts"] = ordered

    source["verification_errors"] = list(
        dict.fromkeys(
            verification_errors
        )
    )

    return False


# ==========================================================================
# EVIDENCE ENRICHMENT
# ==========================================================================

def enrich_from_crossref(source):

    doi = _normalize_doi(
        source.get("doi", "")
    )

    if not doi:
        return source

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
            provider="Crossref",
        )

        item = data.get(
            "message",
            {}
        )

        abstract = _clean_abstract(
            item.get("abstract", "")
        )

        if abstract:

            current = _clean_abstract(
                source.get("abstract", "")
            )

            if len(abstract) > len(current):

                source["abstract"] = abstract

                source["evidence_source"] = (
                    "Crossref abstract"
                )

            _record_evidence_provider(
                source,
                "Crossref",
                abstract,
            )

    except Exception as error:

        source[
            "crossref_enrichment_error"
        ] = str(error)

    return source


def enrich_from_openalex(source):

    doi = _normalize_doi(
        source.get("doi", "")
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
            provider="OpenAlex",
        )

        abstract = _openalex_abstract_text(
            data.get(
                "abstract_inverted_index"
            )
        )

        if abstract:

            current = _clean_abstract(
                source.get("abstract", "")
            )

            if len(abstract) > len(current):

                source["abstract"] = abstract

                source["evidence_source"] = (
                    "OpenAlex abstract"
                )

            _record_evidence_provider(
                source,
                "OpenAlex",
                abstract,
            )

            source["openalex_enriched"] = True

        source["openalex_citation_count"] = (
            data.get(
                "cited_by_count",
                0,
            )
            or 0
        )

        source["openalex_id"] = _clean(
            data.get("id", "")
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
        source.get("doi", "")
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
            "fields": (
                "title,abstract,year,"
                "externalIds,publicationTypes,"
                "citationCount"
            )
        }

        data = _get(
            url,
            params,
            retries=SEMANTIC_RETRIES,
            backoff=SEMANTIC_BACKOFF_SECONDS,
            provider="Semantic Scholar",
        )

        abstract = _clean_abstract(
            data.get("abstract", "")
        )

        if abstract:

            current = _clean_abstract(
                source.get("abstract", "")
            )

            if len(abstract) > len(current):

                source["abstract"] = abstract

                source["evidence_source"] = (
                    "Semantic Scholar abstract"
                )

            _record_evidence_provider(
                source,
                "Semantic Scholar",
                abstract,
            )

        source["citation_count"] = (
            data.get(
                "citationCount",
                source.get(
                    "citation_count",
                    0,
                ),
            )
            or 0
        )

        publication_types = (
            data.get(
                "publicationTypes",
                [],
            )
            or []
        )

        if publication_types:

            existing = set(
                source.get(
                    "publication_types",
                    [],
                )
                or []
            )

            existing.update(
                publication_types
            )

            source["publication_types"] = sorted(
                existing
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
        source.get("abstract", "")
    ):

        return _build_evidence_package(
            source
        )

    source = enrich_from_openalex(
        source
    )

    if _clean_abstract(
        source.get("abstract", "")
    ):

        return _build_evidence_package(
            source
        )

    source = enrich_from_crossref(
        source
    )

    if _clean_abstract(
        source.get("abstract", "")
    ):

        return _build_evidence_package(
            source
        )

    source = enrich_from_semantic(
        source
    )

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
                "   Source: "
                f"{source.get('evidence_source', '')}"
            )

            print(
                "   Providers: "
                + ", ".join(
                    source.get(
                        "evidence_providers",
                        [],
                    )
                )
            )

            print(
                "   Characters: "
                f"{len(source.get('evidence_text', ''))}"
            )

            enriched.append(source)

        else:

            print(
                "❌ No evidence available"
            )

    return enriched


# ==========================================================================
# STUDY DESIGN / EVIDENCE QUALITY
# ==========================================================================

def _classify_study_design(source):

    title = _clean(
        source.get("title", "")
    ).lower()

    publication_types = (
        source.get(
            "publication_types",
            [],
        )
        or []
    )

    publication_types_text = " ".join(
        _clean(value).lower()
        for value in publication_types
    )

    abstract = _clean(
        source.get("abstract", "")
    ).lower()

    text = (
        f"{title} "
        f"{publication_types_text} "
        f"{abstract}"
    )

    if any(
        phrase in text
        for phrase in (
            "systematic review",
            "systematic literature review",
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

        design = "clinical_or_controlled_trial"

    elif any(
        phrase in text
        for phrase in (
            "longitudinal",
            "prospective cohort",
            "retrospective cohort",
            "cohort study",
        )
    ):

        design = "observational_cohort"

    elif (
        "cross-sectional" in text
        or "cross sectional" in text
    ):

        design = "cross_sectional"

    elif (
        "case report" in text
        or "case study" in text
    ):

        design = "case_report_or_case_study"

    else:

        design = "research_article_or_unspecified"

    source["study_design"] = design

    return source


def _assign_evidence_quality(source):

    evidence = _clean(
        source.get(
            "evidence_text",
            "",
        )
    )

    source["evidence_quality"] = (
        "moderate"
        if evidence
        else "none"
    )

    return source


def mark_evidence_verified(sources):

    accepted = []

    for source in sources:

        title = _clean(
            source.get("title", "")
        )

        if source.get(
            "metadata_verified"
        ) is not True:

            print(
                "❌ Rejected unverified source: "
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
                "❌ Rejected metadata-only source: "
                f"{title}"
            )

            continue

        if len(evidence) < MIN_ABSTRACT_CHARACTERS:

            print(
                "❌ Rejected insufficient evidence text: "
                f"{title}"
            )

            continue

        authors = _clean(
            source.get("authors", "")
        )

        year = source.get("year")

        doi = _normalize_doi(
            source.get("doi", "")
        )

        if not authors:

            print(
                "❌ Rejected source without authors: "
                f"{title}"
            )

            continue

        if not year:

            print(
                "❌ Rejected source without publication year: "
                f"{title}"
            )

            continue

        if not doi:

            print(
                "❌ Rejected source without DOI: "
                f"{title}"
            )

            continue

        if not _clean(
            source.get("url", "")
        ):

            source["url"] = (
                f"https://doi.org/{doi}"
            )

        expected_source_id = _generate_source_id(
            doi
        )

        existing_source_id = _clean(
            source.get("source_id", "")
        )

        if (
            existing_source_id
            and existing_source_id
            != expected_source_id
        ):

            print(
                "❌ Rejected source with invalid "
                f"source_id: {title}"
            )

            continue

        source["source_id"] = expected_source_id

        source["doi"] = doi
        source["abstract"] = evidence
        source["evidence_text"] = evidence
        source["evidence_available"] = True
        source["evidence_type"] = "abstract"
        source["evidence_verified"] = True
        source["verified"] = True

        source[
            "verification_level"
        ] = "DOI_METADATA_PLUS_ABSTRACT"

        source[
            "evidence_verification"
        ] = (
            "DOI/publication identity was verified "
            "and a scholarly abstract was retrieved "
            "from an indexed scholarly source."
        )

        _classify_study_design(
            source
        )

        _assign_evidence_quality(
            source
        )

        accepted.append(source)

    return accepted


# ==========================================================================
# SOURCE VALIDATION
# ==========================================================================

def validate_independent_sources(sources):

    unique_dois = {
        _normalize_doi(
            source.get("doi", "")
        )
        for source in sources
        if _normalize_doi(
            source.get("doi", "")
        )
    }

    if len(unique_dois) < MIN_ACCEPTED_SOURCES:

        raise RuntimeError(
            "RESEARCH FAILED: fewer than two "
            "distinct DOI-backed sources remain."
        )

    return {
        "distinct_doi_count": len(unique_dois),
        "independence_basis": (
            "distinct_normalized_dois"
        ),
        "independent_source_count": len(
            unique_dois
        ),
    }


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

        quality_rank = {
            "moderate": 1,
            "none": 0,
        }.get(
            source.get(
                "evidence_quality"
            ),
            0,
        )

        provider_count = len(
            source.get(
                "evidence_providers",
                [],
            )
            or []
        )

        intent_rank = {
            "strong": 3,
            "moderate": 2,
            "weak": 1,
            "mismatch": 0,
        }.get(
            source.get(
                "intent_class",
                "weak",
            ),
            0,
        )

        return (
            intent_rank,
            source.get(
                "relevance_score",
                0,
            ),
            source.get(
                "topic_concept_coverage",
                0,
            ),
            quality_rank,
            provider_count,
            citation_count,
        )

    return sorted(
        sources,
        key=sort_key,
        reverse=True,
    )[:MAX_EVIDENCE_SOURCES]


def validate_source_ids(sources):

    seen_ids = set()
    seen_dois = set()

    for source in sources:

        source_id = _clean(
            source.get("source_id", "")
        )

        doi = _normalize_doi(
            source.get("doi", "")
        )

        if not source_id:

            raise RuntimeError(
                "RESEARCH FAILED: final source "
                "is missing source_id."
            )

        if not doi:

            raise RuntimeError(
                "RESEARCH FAILED: source "
                f"'{source.get('title', '')}' "
                "has no DOI."
            )

        expected_id = _generate_source_id(
            doi
        )

        if source_id != expected_id:

            raise RuntimeError(
                "RESEARCH FAILED: source ID mismatch "
                f"for '{source.get('title', '')}'."
            )

        if source_id in seen_ids:

            raise RuntimeError(
                "RESEARCH FAILED: duplicate "
                f"source_id detected: {source_id}"
            )

        if doi in seen_dois:

            raise RuntimeError(
                "RESEARCH FAILED: duplicate "
                f"DOI detected: {doi}"
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
                    "RESEARCH FAILED: source "
                    f"'{source.get('title', '')}' "
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
                "RESEARCH FAILED: source "
                f"'{source.get('title', '')}' "
                "has insufficient evidence text."
            )

        if source.get(
            "evidence_type"
        ) != "abstract":

            raise RuntimeError(
                "RESEARCH FAILED: source "
                f"'{source.get('title', '')}' "
                "does not contain abstract evidence."
            )

        if not _clean(
            source.get("title", "")
        ):

            raise RuntimeError(
                "RESEARCH FAILED: source has no title."
            )

        if not _clean(
            source.get("authors", "")
        ):

            raise RuntimeError(
                "RESEARCH FAILED: source "
                f"'{source.get('title', '')}' "
                "has no authors."
            )

        if not source.get("year"):

            raise RuntimeError(
                "RESEARCH FAILED: source "
                f"'{source.get('title', '')}' "
                "has no publication year."
            )

        if not _clean(
            source.get("url", "")
        ):

            raise RuntimeError(
                "RESEARCH FAILED: source "
                f"'{source.get('title', '')}' "
                "has no URL."
            )

    return True


def validate_research_package(package):

    if not isinstance(package, dict):

        raise RuntimeError(
            "RESEARCH FAILED: package is not a dictionary."
        )

    if package.get("status") != "VERIFIED":

        raise RuntimeError(
            "RESEARCH FAILED: package status "
            "is not VERIFIED."
        )

    if package.get("verified") is not True:

        raise RuntimeError(
            "RESEARCH FAILED: package verified "
            "flag is not True."
        )

    sources = package.get(
        "sources",
        [],
    )

    if not isinstance(sources, list):

        raise RuntimeError(
            "RESEARCH FAILED: package sources are invalid."
        )

    if len(sources) < MIN_ACCEPTED_SOURCES:

        raise RuntimeError(
            "RESEARCH FAILED: package has fewer "
            "than two sources."
        )

    if package.get(
        "source_count"
    ) != len(sources):

        raise RuntimeError(
            "RESEARCH FAILED: source_count "
            "does not match sources."
        )

    if package.get(
        "evidence_source_count"
    ) != len(sources):

        raise RuntimeError(
            "RESEARCH FAILED: evidence_source_count "
            "does not match sources."
        )

    validate_source_ids(
        sources
    )

    validate_independent_sources(
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
                "RESEARCH FAILED: final source "
                "is not relevant: "
                f"{source.get('title', '')}"
            )

        if source.get(
            "intent_pass"
        ) is not True:

            raise RuntimeError(
                "RESEARCH FAILED: final source "
                "does not satisfy question intent: "
                f"{source.get('title', '')}"
            )

    return True


# ==========================================================================
# MAIN RESEARCH PIPELINE
# ==========================================================================

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

    print(
        f"Topic words: {len(topic.split())}"
    )

    # ------------------------------------------------------------------
    # QUESTION INTENT
    # ------------------------------------------------------------------

    intent_profile = _intent_profile(topic)

    print("=" * 80)
    print("🎯 ANALYZING QUESTION INTENT")
    print("=" * 80)

    print(
        "Detected intents: "
        + (
            ", ".join(
                intent_profile["intents"]
            )
            or "none"
        )
    )

    print(
        "Required mechanism terms:"
    )

    print(
        ", ".join(
            sorted(
                intent_profile[
                    "mechanism_terms"
                ]
            )
        )
        or "none"
    )

    print(
        "Event terms:"
    )

    print(
        ", ".join(
            sorted(
                intent_profile[
                    "event_terms"
                ]
            )
        )
        or "none"
    )

    print(
        "Target terms:"
    )

    print(
        ", ".join(
            sorted(
                intent_profile[
                    "target_terms"
                ]
            )
        )
        or "none"
    )

    print(
        "Topic-drift terms:"
    )

    print(
        ", ".join(
            sorted(
                intent_profile[
                    "negative_terms"
                ]
            )
        )
        or "none"
    )

    # ------------------------------------------------------------------
    # TOPIC VOCABULARY
    # ------------------------------------------------------------------

    print("=" * 80)
    print("🧠 BUILDING RESEARCH VOCABULARY")
    print("=" * 80)

    print(
        "Original terms:"
    )

    print(
        ", ".join(
            sorted(
                _topic_terms(topic)
            )
        )
        or "none"
    )

    print(
        "Expanded scholarly vocabulary:"
    )

    print(
        ", ".join(
            sorted(
                _expanded_topic_terms(topic)
            )
        )
        or "none"
    )

    print(
        "Topic concepts:"
    )

    print(
        ", ".join(
            sorted(
                _topic_concepts(topic)
            )
        )
        or "none"
    )

    scholarly_queries = build_scholarly_queries(
        topic
    )

    print(
        "Scholarly search queries:"
    )

    for query in scholarly_queries:
        print(
            f"   • {query}"
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

    candidates = deduplicate_sources(
        crossref
        + semantic
        + openalex
    )

    print(
        f"Unique candidates: {len(candidates)}"
    )

    if not candidates:

        raise RuntimeError(
            "RESEARCH FAILED: no research "
            "candidates were found."
        )

    # ------------------------------------------------------------------
    # DOI FILTER
    # ------------------------------------------------------------------

    print("=" * 80)

    print(
        "🆔 FILTERING DOI-ELIGIBLE CANDIDATES"
    )

    print("=" * 80)

    doi_candidates = []

    for source in candidates:

        doi = _normalize_doi(
            source.get("doi", "")
        )

        title = _clean(
            source.get("title", "")
        )

        if not doi:

            print(
                "⚠️ REJECTED — NO DOI: "
                f"{title}"
            )

            continue

        source["doi"] = doi

        source["source_id"] = (
            _generate_source_id(doi)
        )

        doi_candidates.append(
            source
        )

    print(
        "DOI-eligible candidates: "
        f"{len(doi_candidates)}"
    )

    if not doi_candidates:

        raise RuntimeError(
            "RESEARCH FAILED: no candidates "
            "with DOI identifiers."
        )

    # ------------------------------------------------------------------
    # RELEVANCE
    # ------------------------------------------------------------------

    relevant = relevance_filter(
        topic,
        doi_candidates,
        label="STRICT TOPIC + QUESTION INTENT FILTER",
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
                "intent_score",
                0,
            ),
            source.get(
                "relevance_score",
                0,
            ),
            source.get(
                "topic_concept_coverage",
                0,
            ),
            len(
                source.get(
                    "evidence_text",
                    "",
                )
            ),
        ),
        reverse=True,
    )[
        :MAX_VERIFICATION_CANDIDATES
    ]

    # ------------------------------------------------------------------
    # IDENTITY VERIFICATION
    # ------------------------------------------------------------------

    print("=" * 80)

    print(
        "🧪 VERIFYING DOI + PUBLICATION IDENTITY"
    )

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

        verified_ok = (
            verify_source_identity(
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
        "DOI/identity-verified sources: "
        f"{len(verified_metadata)}"
    )

    if not verified_metadata:

        raise RuntimeError(
            "RESEARCH FAILED: no DOI-verified "
            "sources remained."
        )

    # ------------------------------------------------------------------
    # EVIDENCE
    # ------------------------------------------------------------------

    verified_metadata = enrich_sources(
        verified_metadata
    )

    evidence_sources = (
        mark_evidence_verified(
            verified_metadata
        )
    )

    print(
        "Evidence-backed sources: "
        f"{len(evidence_sources)}"
    )

    if not evidence_sources:

        raise RuntimeError(
            "RESEARCH FAILED: no evidence-backed "
            "sources remained."
        )

    # ------------------------------------------------------------------
    # FINAL RELEVANCE
    # ------------------------------------------------------------------

    print("=" * 80)

    print(
        "🔍 FINAL EVIDENCE + QUESTION INTENT CHECK"
    )

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
        and source.get(
            "verified"
        ) is True
        and source.get(
            "intent_pass"
        ) is True
    ]

    print(
        "Final relevant evidence sources: "
        f"{len(evidence_sources)}"
    )

    evidence_sources = limit_sources(
        evidence_sources
    )

    print(
        "Sources selected for final package: "
        f"{len(evidence_sources)}"
    )

    if len(evidence_sources) < MIN_ACCEPTED_SOURCES:

        raise RuntimeError(
            f"RESEARCH FAILED: fewer than "
            f"{MIN_ACCEPTED_SOURCES} "
            "evidence-backed relevant "
            "sources remained."
        )

    diversity = (
        validate_independent_sources(
            evidence_sources
        )
    )

    # ------------------------------------------------------------------
    # SOURCE IDS
    # ------------------------------------------------------------------

    print("=" * 80)

    print(
        "🆔 VALIDATING AUTHORITATIVE SOURCE IDs"
    )

    print("=" * 80)

    validate_source_ids(
        evidence_sources
    )

    print(
        "✅ All final sources have valid "
        "stable source_id values."
    )

    # ------------------------------------------------------------------
    # PACKAGE
    # ------------------------------------------------------------------

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

            "expanded_terms": sorted(
                _expanded_topic_terms(topic)
            ),

            "topic_concepts": sorted(
                _topic_concepts(topic)
            ),

            "scholarly_queries": (
                scholarly_queries
            ),

            "question_intents": (
                intent_profile["intents"]
            ),

            "mechanism_terms": sorted(
                intent_profile[
                    "mechanism_terms"
                ]
            ),

            "event_terms": sorted(
                intent_profile[
                    "event_terms"
                ]
            ),

            "target_terms": sorted(
                intent_profile[
                    "target_terms"
                ]
            ),

            "negative_topic_drift_terms": sorted(
                intent_profile[
                    "negative_terms"
                ]
            ),
        },

        "verification_policy": {

            "minimum_sources": (
                MIN_ACCEPTED_SOURCES
            ),

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
                "Semantic Scholar",
                "OpenAlex",
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

            "agriculture_production_drift_protection": True,
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

    print(
        "✅ RESEARCH VERIFIED"
    )

    print("=" * 80)

    print(
        "Evidence-backed relevant sources: "
        f"{len(evidence_sources)}"
    )

    for index, source in enumerate(
        evidence_sources,
        start=1,
    ):

        print(
            f"{index}. {source['title']}"
        )

        print(
            "   Source ID: "
            f"{source['source_id']}"
        )

        print(
            "   DOI: "
            f"{source['doi']}"
        )

        print(
            "   Databases: "
            + ", ".join(
                source.get(
                    "source_databases",
                    [],
                )
            )
        )

        print(
            "   Metadata verification: "
            f"{source.get('metadata_verification_provider', '')}"
        )

        print(
            "   Evidence providers: "
            + ", ".join(
                source.get(
                    "evidence_providers",
                    [],
                )
            )
        )

        print(
            "   Intent: "
            f"{source.get('intent_class', '')}"
        )

        print(
            "   Mechanism matches: "
            f"{source.get('intent_mechanism_matches', [])}"
        )

        print(
            "   Relevance: "
            f"{source.get('relevance_class', '')}"
        )

        print(
            "   Score: "
            f"{source.get('relevance_score', 0)}"
        )

        print(
            "   Concept coverage: "
            f"{source.get('topic_concept_coverage', 0):.1%}"
        )

        print(
            "   Evidence: "
            f"{source.get('evidence_source', '')}"
        )

        print(
            "   Evidence quality: "
            f"{source.get('evidence_quality', '')}"
        )

        print(
            "   Study design: "
            f"{source.get('study_design', '')}"
        )

        print(
            "   Evidence characters: "
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

        print("Usage:")

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

        print(
            "📄 RESEARCH SAVED"
        )

        print("=" * 80)

        print(output)

    except Exception as error:

        print("=" * 80)

        print(
            "❌ RESEARCH FAILED"
        )

        print("=" * 80)

        print(error)

        sys.exit(1)