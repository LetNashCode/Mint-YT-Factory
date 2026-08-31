"""Persistent published-topic history with stronger idea-level duplicate guards."""
from __future__ import annotations
import difflib, json, re, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_HISTORY_PATH = _ROOT / "analytics" / "topic_history.json"
_STOPWORDS={"why","how","what","does","do","did","is","are","the","a","an","your","you","my","in","on","at","to","of","for","with","when","and","or","so","get","gets","make","makes","feel","feels"}
_ALIAS={"cellphone":"phone","mobile":"phone","mobiles":"phone","screens":"screen","chargers":"charger","cables":"cable","onions":"onion","eyes":"eye","cubes":"cube","candles":"candle","mirrors":"mirror","windows":"window","bubbles":"bubble","bags":"bag","earbuds":"earbud"}

def normalize_topic(value):
    words=re.findall(r"[a-z0-9]+",str(value or "").lower())
    return " ".join(_ALIAS.get(w,w) for w in words)

def _tokens(value):
    return {w for w in normalize_topic(value).split() if len(w)>2 and w not in _STOPWORDS}

def _core(value):
    return _tokens(value)

def _similarity(a,b):
    ak,bk=normalize_topic(a),normalize_topic(b)
    if not ak or not bk:return 0.0
    if ak==bk:return 1.0
    ta,tb=_tokens(a),_tokens(b)
    j=len(ta&tb)/len(ta|tb) if ta or tb else 0.0
    seq=difflib.SequenceMatcher(None,ak,bk).ratio()
    contain=1.0 if ta and (ta<=tb or tb<=ta) else 0.0
    return max(j,seq,contain)

def _same_subject(a,b):
    ta,tb=_core(a),_core(b)
    shared=ta&tb
    # A shared concrete subject is treated as an idea collision when either topic is short.
    return bool(shared) and (len(ta)<=4 or len(tb)<=4)

def _load():
    try:
        data=json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data,list) else []
    except Exception:return []

def _save(items):
    _HISTORY_PATH.parent.mkdir(parents=True,exist_ok=True)
    tmp=_HISTORY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(items,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    tmp.replace(_HISTORY_PATH)

def find_duplicate(topic,threshold=0.70):
    clean=" ".join(str(topic or "").split()).strip()
    for item in _load():
        existing=str(item.get("topic",""))
        score=_similarity(clean,existing)
        if score>=threshold or _same_subject(clean,existing):
            reason="same_subject" if _same_subject(clean,existing) and score<threshold else "similarity"
            return {"topic":existing,"score":round(score,3),"status":item.get("status","published"),"reason":reason}
    return None

def find_duplicate_in(topic,topics,threshold=0.70):
    clean=" ".join(str(topic or "").split()).strip()
    for existing in topics:
        existing=str(existing or "")
        score=_similarity(clean,existing)
        if score>=threshold or _same_subject(clean,existing):
            return {"topic":existing,"score":round(score,3),"reason":"same_subject" if _same_subject(clean,existing) and score<threshold else "similarity"}
    return None

def is_new_topic(topic,threshold=0.70):
    return find_duplicate(topic,threshold) is None

def record_topic(topic,title="",video_id="",workdir="",status="published"):
    clean=" ".join(str(topic or "").split()).strip()
    if not clean:raise RuntimeError("Cannot record an empty topic.")
    items=_load()
    duplicate=find_duplicate_in(clean,[x.get("topic","") for x in items])
    if duplicate:
        print(f"📚 Topic history already contains: {duplicate['topic']} ({duplicate['reason']}, {duplicate['score']})")
        return False
    items.append({"topic":clean,"normalized":normalize_topic(clean),"title":str(title or "").strip(),"video_id":str(video_id or "").strip(),"workdir":str(workdir or "").strip(),"status":status,"recorded_at":int(time.time())})
    _save(items);print(f"📚 Topic history recorded: {clean}");return True

def published_topics():
    return [str(x.get("topic","")) for x in _load() if x.get("topic")]
