import re

# Mint-YT-Factory hardening shim. Keeps existing pipeline files intact while
# adding deterministic guards before their public gates are used.


def _terms(text):
    return set(re.findall(r"[a-z0-9]+", str(text or "").lower()))


def _content_terms(text):
    stop = {
        "why","what","how","when","where","who","does","do","did","can","could","would","should","will",
        "is","are","was","were","be","been","being","the","a","an","and","or","of","to","in","on",
        "for","with","from","about","into","through","during","as","at","by","your","you","we","our",
        "they","their","it","its","this","that","these","those","very","really","actually","often","usually",
        "sometimes","people","human","humans","thing","things","right","good","fresh","new","common","everyday",
    }
    return {w for w in _terms(text) if len(w) >= 3 and w not in stop}


def _topic_identity(topic):
    text = str(topic or "").strip().lower()
    m = re.match(r"^(?:why|how)\s+(?:does|do|can|is|are)\s+(.+?)\s+(?:smell|smells|sound|sounds|feel|feels|taste|tastes|get|gets|look|looks|appear|appears|seem|seems|turn|turns)\b", text)
    if m:
        subject = m.group(1)
    else:
        m = re.match(r"^(?:why|how)\s+(.+?)\s+(?:smell|smells|sound|sounds|feel|feels|taste|tastes)\b", text)
        subject = m.group(1) if m else text

    subject_terms = _content_terms(subject)
    phenomenon = set()

    if re.search(r"\b(smell|smells|odor|odour|aroma|aromas|fragrance)\b", text):
        phenomenon.update({"smell","smells","odor","odour","aroma","aromas","fragrance"})
    if re.search(r"\b(sound|sounds|noise|noises|echo|echoes|acoustic)\b", text):
        phenomenon.update({"sound","sounds","noise","noises","echo","echoes","acoustic"})
    if re.search(r"\b(feel|feels|feeling|cold|colder|temperature|sensation)\b", text):
        phenomenon.update({"feel","feels","feeling","cold","colder","temperature","sensation"})
    if re.search(r"\b(taste|tastes|flavor|flavour|flavors|flavours)\b", text):
        phenomenon.update({"taste","tastes","flavor","flavour","flavors","flavours"})

    return subject_terms, phenomenon


def _source_matches(topic, source):
    subject_terms, phenomenon_terms = _topic_identity(topic)
    if not subject_terms or not phenomenon_terms:
        return True
    title = str(source.get("title", ""))
    evidence = str(source.get("evidence_text", "") or source.get("abstract", ""))
    combined = f"{title} {evidence}".lower()
    subject_hit = any(re.search(r"\b" + re.escape(t) + r"(?:s|es|ing|ed)?\b", combined) for t in subject_terms)
    phenomenon_hit = any(re.search(r"\b" + re.escape(t) + r"(?:s|es|ing|ed)?\b", combined) for t in phenomenon_terms)
    return subject_hit and phenomenon_hit


# Patch research.py after import.
try:
    import research

    _old_extract_subject = research._extract_subject

    def _extract_subject(topic):
        text = research._clean(topic).lower()
        m = re.match(r"^(?:why|how)\s+(?:does|do|can|is|are)\s+(.+?)\s+(?:smell|smells|sound|sounds|feel|feels|taste|tastes|get|gets|look|looks|appear|appears|seem|seems|turn|turns)\b", text)
        if m:
            left = [x for x in research._tokens(m.group(1)) if x not in {"fresh","good","right","different","cold","hot","new"}]
            if left:
                return [" ".join(left), *left]
        return _old_extract_subject(topic)

    research._extract_subject = _extract_subject

    _old_score_source = research._score_source

    def _score_source(topic, source):
        result = _old_score_source(topic, source)
        if not _source_matches(topic, source):
            result["scientific_score"] = 0
            result["relevance_score"] = 0
            result["relevance_class"] = "weak"
            result["scientific_relevance_pass"] = False
            result["concept_coverage_pass"] = False
            result["intent_pass"] = False
            result.setdefault("rejection_reasons", []).append("current_topic_identity_mismatch")
        return result

    research._score_source = _score_source
except Exception:
    pass


# Patch generate_script so next_short is constrained at generation/validation time
# and the final script cannot silently drift to a different subject.
try:
    import generate_script

    _old_build_system_prompt = generate_script.build_system_prompt
    def build_system_prompt():
        return _old_build_system_prompt().rstrip() + r"""

============================================================
NEXT SHORT TOPIC FORMAT — HARD REQUIREMENT
============================================================

next_short.topic MUST be a complete curiosity question.

It MUST begin with one of:
Why does
Why do
Why is
Why are
Why can
How does
How do
How is
How are
How can

GOOD:
Why does fresh laundry odor boost retail spending in second-hand stores
Why does ice sometimes crack loudly
Why do wet clothes feel colder in moving air

BAD:
how fresh laundry odor boosts retail spending in second-hand stores
fresh laundry odor and retail spending
the effect of fresh laundry odor on retail spending

Return the topic as the question itself, without a question mark.
"""
    generate_script.build_system_prompt = build_system_prompt

    _old_build_user_prompt = generate_script.build_user_prompt
    def build_user_prompt(topic, config, research):
        return _old_build_user_prompt(topic, config, research) + r"""

============================================================
NEXT SHORT QUESTION SHAPE — HARD REQUIREMENT
============================================================

next_short.topic MUST be a complete observable question.

Allowed starts only:
Why does / Why do / Why is / Why are / Why can /
How does / How do / How is / How are / How can

Do NOT output a noun phrase or an incomplete "how ..." phrase.
"""
    generate_script.build_user_prompt = build_user_prompt

    _original_module = getattr(generate_script, "_original", None)

    if _original_module is not None:
        _old_normalize_next_short = _original_module._normalize_next_short

        def _normalize_next_short(script):
            _old_normalize_next_short(script)
            topic = str(script["next_short"]["topic"]).strip()
            if not re.match(r"^(why does|why do|why is|why are|why can|how does|how do|how is|how are|how can)\s+.+", topic, re.I):
                raise RuntimeError(
                    "next_short.topic must be a complete observable question starting with "
                    "Why does/Why do/Why is/Why are/Why can/How does/How do/How is/How are/How can."
                )
            script["next_short"]["topic"] = topic.rstrip("?!.").strip()

        _original_module._normalize_next_short = _normalize_next_short

        _old_validate_script = _original_module.validate_script

        def validate_script(script, verified_research):
            result = _old_validate_script(script, verified_research)
            topic = str(verified_research.get("topic", "") or "")
            subject_terms, phenomenon_terms = _topic_identity(topic)
            narrative = " ".join(str(s.get("narration", "")) for s in script.get("scene_plan", []) if isinstance(s, dict))
            title = str(script.get("title", ""))
            description = str(script.get("description", ""))
            if subject_terms:
                narrative_subject = any(t in _terms(narrative) for t in subject_terms)
                metadata_subject = any(t in _terms(f"{title} {description}") for t in subject_terms)
                if not narrative_subject or not metadata_subject:
                    raise RuntimeError("CURRENT TOPIC DRIFT: generated narration/title/description do not identify the current topic's concrete subject.")
            if phenomenon_terms and not any(t in _terms(narrative) for t in phenomenon_terms):
                raise RuntimeError("CURRENT TOPIC DRIFT: generated narration does not contain the current observable phenomenon.")
            return result

        _original_module.validate_script = validate_script
        generate_script._normalize_next_short = _normalize_next_short
        generate_script.validate_script = validate_script
except Exception:
    pass
