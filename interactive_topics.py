"""Topic and durable sequence state for Story Shorts."""
from __future__ import annotations
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / "story_topic_history.json"
PENDING = ROOT / "pending_story.json"
COUNTER = ROOT / "story_counter.json"
CANDIDATES = ROOT / "story_candidates.json"

SEED_STORIES = [
    ("rise_from_nothing", "Thomas Edison", "The inventor whose laboratory burned down and who started again"),
    ("before_they_were_famous", "J.K. Rowling", "The difficult period before Harry Potter changed her career"),
    ("impossible_odds", "Arunima Sinha", "The athlete who rebuilt her life and climbed Mount Everest"),
    ("one_decision", "A.P.J. Abdul Kalam", "The journey from Rameswaram to India's space and missile programs"),
    ("rise_from_nothing", "Colonel Harland Sanders", "The late-life reinvention behind a global chicken business"),
    ("before_they_were_famous", "Walt Disney", "The failures and setbacks before the Disney empire"),
    ("one_decision", "Michael Jordan", "The rejection that helped shape a legendary basketball career"),
    ("impossible_odds", "Milkha Singh", "The traumatic childhood and extraordinary athletic journey of the Flying Sikh"),
    ("strange_turning_point", "Steve Jobs", "How leaving Apple became part of the story of his return"),
    ("rise_from_nothing", "Dhirubhai Ambani", "The modest beginnings behind a famous Indian business story"),
    ("impossible_odds", "Stephen Hawking", "How a devastating diagnosis changed the life of a future physicist"),
    ("before_they_were_famous", "Oprah Winfrey", "The difficult early years before television fame"),
]


def _n(x): return re.sub(r"[^a-z0-9]+", " ", str(x or "").lower()).strip()
def _tokens(x): return {w for w in _n(x).split() if len(w) > 2}

def _load(path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except Exception: return default

def _save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def _load_history(): return _load(HISTORY, [])

def _performance_by_format():
    rows = _load(ROOT / "analytics" / "story_videos.json", [])
    groups = {}
    for row in rows:
        if not isinstance(row, dict): continue
        latest = row.get("latest") or {}
        vals = tuple(float(latest.get(k, 0) or 0) for k in ("views", "average_view_percentage", "shares", "comments"))
        if not any(vals): continue
        groups.setdefault(str(row.get("pillar") or "story"), []).append(vals)
    return {k: {"views":sum(x[0] for x in v)/len(v), "retention":sum(x[1] for x in v)/len(v), "shares":sum(x[2] for x in v)/len(v), "comments":sum(x[3] for x in v)/len(v)} for k,v in groups.items()}

def _novelty_penalty(person, premise, recent):
    score = 0.0
    p_tokens, s_tokens = _tokens(person), _tokens(premise)
    for row in recent[-15:]:
        old_person, old_premise = _tokens(row.get("person", "")), _tokens(row.get("topic", ""))
        if p_tokens and old_person and len(p_tokens & old_person) / max(1, len(p_tokens | old_person)) >= .5: score += 40
        if s_tokens and old_premise:
            overlap = len(s_tokens & old_premise) / max(1, len(s_tokens | old_premise))
            score += 18 if overlap >= .45 else 8 if overlap >= .30 else 0
    return score

def _generate_candidates(count=10):
    try:
        from google import genai
        from google.genai import types
        from generate_script.entertainment import MODEL_NAME, _api_key
        client = genai.Client(api_key=_api_key())
        recent = _load_history()[-20:]
        people = [str(x.get("person", "")) for x in recent if x.get("person")]
        prompt = f"""Generate {count} fresh YouTube Shorts story ideas about REAL, recognizable people.
Mix these formats: rise_from_nothing, one_decision, before_they_were_famous, impossible_odds, strange_turning_point.
Prefer a mix of Indian and international people from science, sport, business, entertainment, exploration, arts and history.
Each idea needs one strong human hook and a concrete obstacle, failure, decision, or turning point.
Use only broadly established facts. Do not invent quotes, dialogue, private thoughts, dates, achievements, causes, or disputed anecdotes.
Return JSON array only with: format, person, premise, hook, key_facts. key_facts must contain 3-5 short factual anchors.
Avoid politics, sexual content, medical advice, and sensational claims.
RECENT PEOPLE TO AVOID:\n{chr(10).join('- '+x for x in people[-15:]) or '- none'}"""
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt, config=types.GenerateContentConfig(response_mime_type="application/json", temperature=1.0))
        data = json.loads(getattr(response, "text", "") or "[]")
        if not isinstance(data, list): return []
        existing = {_n(x.get("person", "")) for x in recent if isinstance(x, dict)}
        out=[]
        for item in data:
            if not isinstance(item, dict): continue
            person,premise=str(item.get("person", "")).strip(),str(item.get("premise", "")).strip()
            facts=item.get("key_facts") or []
            if not person or not premise or _n(person) in existing or not isinstance(facts,list) or len(facts)<3: continue
            out.append({"format":str(item.get("format","strange_turning_point")).strip().lower(),"person":person,"premise":premise,"hook":str(item.get("hook","")).strip(),"key_facts":[str(x).strip() for x in facts[:5] if str(x).strip()],"source":"gemini_original"})
        return out
    except Exception as exc:
        print(f"⚠️ Original Story topic generation unavailable: {exc}")
        return []

def _ensure_pool():
    rows=_load(CANDIDATES,[]); history=_load_history(); used={_n(x.get("person","")) for x in history if isinstance(x,dict)}
    rows=[x for x in rows if isinstance(x,dict) and _n(x.get("person","")) not in used]
    if len(rows)<5: rows.extend(_generate_candidates(10))
    seen=set(); clean=[]
    for row in rows:
        key=_n(row.get("person",""))
        if not key or key in seen or key in used: continue
        seen.add(key); clean.append(row)
    _save(CANDIDATES,clean[-100:]); return clean

def get_next_topic():
    history=_load_history(); performance=_performance_by_format(); pool=_ensure_pool(); recent_formats=[str(x.get("pillar","")) for x in history[-4:] if isinstance(x,dict)]; scored=[]
    for item in pool:
        person,premise=str(item.get("person","")),str(item.get("premise","")); fmt=str(item.get("format","strange_turning_point")).lower()
        if not person or not premise: continue
        score=20+min(len(premise),160)/160*15
        score+=8 if any(w in premise.lower() for w in ("failed","rejected","lost","almost","before","unexpected","burned","survived")) else 0
        score-=recent_formats.count(fmt)*6; score-=_novelty_penalty(person,premise,history)
        perf=performance.get(fmt)
        if perf: score+=min(perf["retention"]/100,1.5)*16+math.log1p(perf["views"])*.6+math.log1p(perf["shares"])*1.5+math.log1p(perf["comments"])
        scored.append((score,fmt,person,premise,item))
    if not scored:
        used={_n(x.get("person","")) for x in history if isinstance(x,dict)}
        for fmt,person,premise in SEED_STORIES:
            if _n(person) not in used: scored.append((10,fmt,person,premise,{"format":fmt,"person":person,"premise":premise,"source":"seed","key_facts":[]}))
    if not scored: raise RuntimeError("Story candidate pool is empty; no unused story subjects are available.")
    scored.sort(key=lambda x:(-x[0],x[2])); _,fmt,person,premise,_=scored[0]
    _save(CANDIDATES,[x for x in pool if _n(x.get("person",""))!=_n(person)])
    return fmt, f"{person}: {premise}", person

def record_topic(topic,pillar,title,video_id,workdir,person=""):
    rows=_load_history(); rows.append({"topic":topic,"pillar":pillar,"person":person,"title":title,"video_id":video_id,"workdir":workdir}); _save(HISTORY,rows[-200:])

def next_story_number():
    data=_load(COUNTER,{}); number=int(data.get("number",0) or 0)+1; _save(COUNTER,{"number":number}); return number

def get_pending_story():
    data=_load(PENDING,{})
    return data if isinstance(data,dict) and data else None

def save_pending_story(pillar,topic,person,number): _save(PENDING,{"pillar":pillar,"topic":topic,"person":person,"number":number})
