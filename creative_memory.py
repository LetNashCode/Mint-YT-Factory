"""Creative memory and originality gates for Publish Shorts."""
from __future__ import annotations

import difflib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REGISTRY = ROOT / "analytics" / "videos.json"
HISTORY = ROOT / "analytics" / "topic_history.json"

STOP = {
    "the","a","an","and","or","but","with","from","into","your","you","that","this",
    "why","what","when","where","how","does","do","did","is","are","to","of","for",
    "it","its","they","their","have","has","will","can","could","would","just","really",
    "actually","ever","there","here","then","than","about","once","now","something",
}

def _load(path, default):
    try:
        data=json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
        return data
    except Exception:
        return default

def _norm(text):
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))

def _tokens(text):
    return {x for x in _norm(text).split() if len(x) > 2 and x not in STOP}

def _similar(a,b):
    na,nb=_norm(a),_norm(b)
    if not na or not nb: return 0.0
    ta,tb=_tokens(a),_tokens(b)
    j=len(ta&tb)/len(ta|tb) if ta|tb else 0.0
    seq=difflib.SequenceMatcher(None,na,nb).ratio()
    return max(j,seq)

def _records():
    data=_load(REGISTRY,[])
    return [x for x in data if isinstance(x,dict)]

def _script(record):
    workdir=str(record.get("workdir") or "").strip()
    if not workdir: return {}
    p=Path(workdir)/"script.json"
    return _load(p,{}) if p.exists() else {}

def _hook(record):
    stored=str(record.get("hook_text") or "").strip()
    if stored:
        return stored
    script=_script(record)
    scenes=script.get("scene_plan") or []
    return str((scenes[0] if scenes else {}).get("narration") or "").strip()

def _topic(record):
    return str(record.get("topic") or _script(record).get("topic") or "").strip()

def _recent(limit=40):
    rows=[]
    for record in reversed(_records()):
        hook=_hook(record)
        topic=_topic(record)
        if hook or topic:
            rows.append({
                "topic":topic,
                "hook":hook,
                "hook_type":str(record.get("hook_type") or _script(record).get("hook_type") or "").strip(),
                "payoff_type":str(record.get("payoff_type") or _script(record).get("payoff_type") or "").strip(),
                "tease_type":str(record.get("tease_type") or _script(record).get("tease_type") or "").strip(),
            })
        if len(rows)>=limit: break
    return rows

def hook_is_unique(hook, recent=None):
    hook=str(hook or "").strip()
    if not hook: return False, "empty_hook"
    rows=recent if recent is not None else _recent()
    meaningful=[x for x in _norm(hook).split() if x not in STOP]
    first6=" ".join(meaningful[:6])
    for row in rows:
        old=str(row.get("hook") or "")
        old_words=[x for x in _norm(old).split() if x not in STOP]
        old6=" ".join(old_words[:6])
        if first6 and old6 and first6 == old6:
            return False, "same_first_six_meaningful_words"
        if _similar(hook,old) >= 0.78:
            return False, "near_duplicate_hook"
    return True, "unique"

def topic_is_novel(topic, recent=None):
    topic=str(topic or "").strip()
    if not topic: return False, "empty_topic"
    rows=recent if recent is not None else _recent()
    for row in rows:
        old=str(row.get("topic") or "")
        if _similar(topic,old) >= 0.70:
            return False, "near_duplicate_topic"
    # Also consult durable topic history, which can outlive the analytics registry.
    for row in _load(HISTORY,[]):
        if isinstance(row,dict):
            old=str(row.get("topic") or "")
            if _similar(topic,old) >= 0.70:
                return False, "historical_duplicate_topic"
    return True, "novel"

def choose_tease_type(current_topic, next_topic, recent=None):
    styles=[
        "curiosity_connection","unexpected_consequence","pattern_connection",
        "challenge","observation_prompt","hidden_connection","unanswered_question",
        "contrast","everyday_reveal","mystery_escalation",
    ]
    rows=recent if recent is not None else _recent()
    used=Counter(str(x.get("tease_type") or "") for x in rows[:10])
    seed=sum(ord(c) for c in str(current_topic)+"|"+str(next_topic))
    ordered=sorted(styles,key=lambda x:(used.get(x,0),(seed+sum(map(ord,x)))%len(styles)))
    return ordered[0]

def build_generation_context(limit=24):
    rows=_recent(limit)
    if not rows:
        return "No prior creative memory is available yet. Make the hook and story mechanism genuinely original."
    lines=[
        "RECENT CREATIVE MEMORY — DO NOT COPY:",
        "These are examples of recent hooks/topics and are supplied only to prevent repetition.",
        "Do not reuse their wording, opening structure, underlying fact, or story angle.",
    ]
    for row in rows:
        if row["topic"] or row["hook"]:
            lines.append(
                f"- TOPIC: {row['topic']} | HOOK TYPE: {row['hook_type'] or 'unknown'} | "
                f"PAYOFF: {row['payoff_type'] or 'unknown'} | TEASE: {row['tease_type'] or 'unknown'} | "
                f"HOOK: {row['hook'][:220]}"
            )
    # Give the writer a useful view of mechanism saturation.
    hook_counts=Counter(x["hook_type"] for x in rows if x["hook_type"])
    tease_counts=Counter(x["tease_type"] for x in rows if x["tease_type"])
    if hook_counts:
        lines.append("RECENT HOOK MECHANISM COUNTS: "+", ".join(f"{k}={v}" for k,v in hook_counts.most_common()))
    if tease_counts:
        lines.append("RECENT TEASE MECHANISM COUNTS: "+", ".join(f"{k}={v}" for k,v in tease_counts.most_common()))
    return "\n".join(lines)

def validate_candidate(topic, script):
    recent=_recent()
    ok_topic,topic_reason=topic_is_novel(topic,recent)
    scenes=script.get("scene_plan") or []
    hook=str((scenes[0] if scenes else {}).get("narration") or "")
    ok_hook,hook_reason=hook_is_unique(hook,recent)
    return {
        "ok": ok_topic and ok_hook,
        "topic_ok": ok_topic,
        "topic_reason": topic_reason,
        "hook_ok": ok_hook,
        "hook_reason": hook_reason,
    }
