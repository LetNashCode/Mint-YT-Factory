"""Persistent published-topic history for Mint-YT-Factory."""
from __future__ import annotations

import difflib
import json
import re
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_HISTORY_PATH = _ROOT / "analytics" / "topic_history.json"
_STOPWORDS = {"why","how","what","does","do","did","is","are","the","a","an","your","you","my","in","on","at","to","of","for","with","when","and","or","so"}

def normalize_topic(value):
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))

def _tokens(value):
    return {w for w in normalize_topic(value).split() if len(w) > 2 and w not in _STOPWORDS}

def _similarity(a, b):
    ak, bk = normalize_topic(a), normalize_topic(b)
    if not ak or not bk: return 0.0
    if ak == bk: return 1.0
    ta, tb = _tokens(a), _tokens(b)
    jaccard = len(ta & tb) / len(ta | tb) if ta or tb else 0.0
    sequence = difflib.SequenceMatcher(None, ak, bk).ratio()
    containment = 1.0 if ta and (ta <= tb or tb <= ta) else 0.0
    return max(jaccard, sequence, containment)

def _load():
    try:
        data = json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []

def _save(items):
    _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _HISTORY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(_HISTORY_PATH)

def find_duplicate(topic, threshold=0.82):
    for item in _load():
        existing = str(item.get("topic", ""))
        score = _similarity(topic, existing)
        if score >= threshold:
            return {"topic": existing, "score": round(score, 3), "status": item.get("status", "published")}
    return None

def is_new_topic(topic, threshold=0.82):
    return find_duplicate(topic, threshold) is None

def record_topic(topic, title="", video_id="", workdir="", status="published"):
    clean = " ".join(str(topic or "").split()).strip()
    if not clean: raise RuntimeError("Cannot record an empty topic.")
    duplicate = find_duplicate(clean)
    if duplicate:
        print(f"📚 Topic history already contains: {duplicate['topic']} ({duplicate['score']})")
        return False
    items = _load()
    items.append({
        "topic": clean,
        "normalized": normalize_topic(clean),
        "title": str(title or "").strip(),
        "video_id": str(video_id or "").strip(),
        "workdir": str(workdir or "").strip(),
        "status": status,
        "recorded_at": int(time.time()),
    })
    _save(items)
    print(f"📚 Topic history recorded: {clean}")
    return True

def published_topics():
    return [str(item.get("topic", "")) for item in _load() if item.get("topic")]
