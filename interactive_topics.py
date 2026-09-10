from __future__ import annotations
import json, re, random, math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / "interactive_topic_history.json"
PENDING = ROOT / "pending_riddle.json"
COUNTER = ROOT / "riddle_counter.json"
CANDIDATES = ROOT / "interactive_riddle_candidates.json"

RIDDLES = [
("classic","The more you take, the more you leave behind. What am I?","footsteps"),
("wordplay","What has keys but cannot open locks?","a piano"),
("logic","I speak without a mouth and hear without ears. I have no body, but I come alive with wind. What am I?","an echo"),
("trick","What gets wetter the more it dries?","a towel"),
("observation","What has many teeth but cannot bite?","a comb"),
("classic","What can travel around the world while staying in one corner?","a stamp"),
("logic","What has one eye but cannot see?","a needle"),
("wordplay","What comes once in a minute, twice in a moment, but never in a thousand years?","the letter M"),
("trick","What has hands but cannot clap?","a clock"),
("classic","What goes up but never comes down?","your age"),
("logic","What has cities, forests and rivers but no houses, trees or water?","a map"),
("wordplay","What has a neck but no head?","a bottle"),
("classic","What can fill a room but takes up no space?","light"),
("trick","What belongs to you but other people use it more than you do?","your name"),
("logic","What has to be broken before you can use it?","an egg"),
("observation","What has legs but does not walk?","a table"),
("classic","What can run but never walks, has a mouth but never talks?","a river"),
("wordplay","What begins with T, ends with T and has T in it?","a teapot"),
("logic","What can you catch but not throw?","a cold"),
("trick","What has a thumb and four fingers but is not alive?","a glove"),
("classic","What gets bigger the more you take away from it?","a hole"),
("logic","What can be cracked, made, told and played?","a joke"),
("observation","What has many rings but no fingers?","a telephone"),
("wordplay","What word becomes shorter when you add two letters to it?","short"),
("classic","What has a head, a tail, is brown and has no legs?","a penny"),
("logic","What can you hold without ever touching it?","a conversation"),
("trick","What has one head, one foot and four legs?","a bed"),
("classic","What can you keep after giving it to someone?","your word"),
("logic","What has an endless supply of letters but starts empty?","a mailbox"),
("wordplay","What English word has three consecutive double letters?","bookkeeper"),
]


def _n(x):
    return re.sub(r"[^a-z0-9]+", " ", str(x or "").lower()).strip()


def _tokens(x):
    return {w for w in _n(x).split() if len(w) > 2}


def _load():
    try:
        x = json.loads(HISTORY.read_text(encoding="utf-8"))
        return x if isinstance(x, list) else []
    except Exception:
        return []


def _load_candidates():
    try:
        x = json.loads(CANDIDATES.read_text(encoding="utf-8"))
        return x if isinstance(x, list) else []
    except Exception:
        return []


def _save_candidates(rows):
    CANDIDATES.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _performance_by_pillar():
    try:
        rows = json.loads((ROOT / "analytics" / "interactive_videos.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    groups = {}
    for row in rows if isinstance(rows, list) else []:
        latest = row.get("latest") or {}
        views = float(latest.get("views", 0) or 0)
        retention = float(latest.get("average_view_percentage", 0) or 0)
        shares = float(latest.get("shares", 0) or 0)
        comments = float(latest.get("comments", 0) or 0)
        engagement = float(latest.get("engagement_rate", 0) or 0)
        if views <= 0 and retention <= 0 and shares <= 0 and comments <= 0:
            continue
        pillar = row.get("pillar", "classic")
        groups.setdefault(pillar, []).append({"views": views, "retention": retention, "shares": shares, "comments": comments, "engagement": engagement})
    out = {}
    for pillar, vals in groups.items():
        out[pillar] = {
            "views": sum(x["views"] for x in vals) / len(vals),
            "retention": sum(x["retention"] for x in vals) / len(vals),
            "shares": sum(x["shares"] for x in vals) / len(vals),
            "comments": sum(x["comments"] for x in vals) / len(vals),
            "engagement": sum(x["engagement"] for x in vals) / len(vals),
        }
    return out


def _performance_by_topic():
    """Return historical performance for the exact riddle/question when available."""
    try:
        rows = json.loads((ROOT / "analytics" / "interactive_videos.json").read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        key = _n(row.get("topic", ""))
        if not key:
            continue
        latest = row.get("latest") or {}
        out[key] = {
            "views": float(latest.get("views", 0) or 0),
            "retention": float(latest.get("average_view_percentage", 0) or 0),
            "comments": float(latest.get("comments", 0) or 0),
            "shares": float(latest.get("shares", 0) or 0),
            "engagement": float(latest.get("engagement_rate", 0) or 0),
        }
    return out


def _novelty_penalty(question, answer, recent_rows):
    """Penalize conceptual repetition, not just exact duplicate wording."""
    q_tokens = _tokens(question)
    a_tokens = _tokens(answer)
    penalty = 0.0
    for row in recent_rows[-12:]:
        if not isinstance(row, dict):
            continue
        old_q = _tokens(row.get("topic", ""))
        old_a = _tokens(row.get("answer", ""))
        if q_tokens and old_q:
            overlap = len(q_tokens & old_q) / max(1, len(q_tokens | old_q))
            if overlap >= 0.45:
                penalty += 18.0
            elif overlap >= 0.30:
                penalty += 8.0
        if a_tokens and old_a:
            answer_overlap = len(a_tokens & old_a) / max(1, len(a_tokens | old_a))
            if answer_overlap >= 0.50:
                penalty += 15.0
            elif answer_overlap >= 0.30:
                penalty += 6.0
    return penalty


def _creative_score(pillar, question, answer, performance, topic_performance=None, recent_rows=None, source="original"):
    q = str(question).lower()
    score = 0.0
    score += min(len(question), 115) / 115 * 14
    score += 8 if "?" in question else 0
    score += 7 if any(w in q for w in ("what", "which", "why", "can", "how")) else 0
    score += 6 if any(w in q for w in ("really", "actually", "secret", "never", "only", "without")) else 0
    score += 5 if len(str(answer).split()) <= 4 else 2
    score += 5 if any(w in q for w in ("but", "without", "never", "more", "less", "one", "two")) else 0

    p = performance.get(pillar)
    if p:
        score += min(p["retention"] / 100, 1.5) * 18
        score += math.log1p(p["views"]) * 0.7
        score += math.log1p(p["shares"]) * 1.8
        score += math.log1p(p["comments"]) * 1.2
        score += min(p["engagement"], 10) * 1.0

    exact = (topic_performance or {}).get(_n(question))
    if exact:
        if exact["retention"]:
            score += max(-16.0, min(12.0, (exact["retention"] - 50.0) * 0.45))
        if exact["comments"] or exact["shares"]:
            score += math.log1p(exact["comments"]) * 2.0 + math.log1p(exact["shares"]) * 2.5
        score -= 30.0

    score -= _novelty_penalty(question, answer, recent_rows or [])

    # Generated originals are the primary creative engine. Legacy seeds remain a
    # safety net, but should lose to a genuinely fresh generated candidate.
    if source == "seed":
        score -= 12.0
    return round(score, 3)


def _generate_original_candidates(count=12):
    try:
        from google import genai
        from google.genai import types
        from generate_script.entertainment import MODEL_NAME, _api_key
        client = genai.Client(api_key=_api_key())
        recent = _load()[-20:]
        recent_questions = [str(x.get("topic", "")) for x in recent if isinstance(x, dict) and x.get("topic")]
        recent_answers = [str(x.get("answer", "")) for x in recent[-12:] if isinstance(x, dict) and x.get("answer")]
        prompt = f"""Create {count} genuinely ORIGINAL short-form riddles for a YouTube Shorts channel.
These must feel unlike one another and unlike common internet riddle templates.
Do NOT paraphrase famous riddles or the usual piano, towel, echo, age, map, comb, clock, bottle, egg, hole, river, stamp, name, glove, or bed riddles.
Do NOT create ten versions of the same mechanic with different objects.
Use a wide mix of spoken mechanics: double meaning, causal misdirection, category shift, temporal ambiguity, false assumption, lateral logic, expectation reversal, language ambiguity, tiny real-world mystery, or counterintuitive definition.
Prefer different answer domains across the batch: household object, sound, behavior, place, action, word, system, everyday phenomenon, etc.
Each must have exactly one defensible answer and be solvable from spoken words alone.
Return JSON only as an array with keys: pillar, question, answer, hook, difficulty, mechanic, answer_domain.
Allowed pillar values: classic, wordplay, logic, trick, observation.
Never require visual clues, image inspection, screen text, or recognizable stock footage.
Avoid unsafe, political, sexual or medical topics.

RECENT QUESTIONS TO AVOID OR MOVE FAR AWAY FROM:
{chr(10).join('- ' + x for x in recent_questions[-15:]) or '- none'}
RECENT ANSWERS TO AVOID REUSING:
{', '.join(recent_answers[-12:]) or 'none'}
"""
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=1.0),
        )
        data = json.loads(getattr(response, "text", "") or "[]")
        if not isinstance(data, list):
            return []
        used = {_n(x.get("topic", "")) for x in _load() if isinstance(x, dict)}
        existing = {_n(q) for _, q, _ in RIDDLES}
        fresh = []
        batch_questions = []
        batch_answers = []
        for item in data:
            if not isinstance(item, dict):
                continue
            q, a = str(item.get("question", "")).strip(), str(item.get("answer", "")).strip()
            if not q or not a or _n(q) in used or _n(q) in existing:
                continue
            if len(q) < 15 or len(q) > 180 or len(a) > 80:
                continue
            # Reject near-duplicates inside the newly generated batch.
            if any(len(_tokens(q) & _tokens(old)) / max(1, len(_tokens(q) | _tokens(old))) >= 0.42 for old in batch_questions):
                continue
            if any(len(_tokens(a) & _tokens(old)) / max(1, len(_tokens(a) | _tokens(old))) >= 0.70 for old in batch_answers):
                continue
            batch_questions.append(q)
            batch_answers.append(a)
            fresh.append({
                "pillar": str(item.get("pillar", "logic")).strip().lower(),
                "question": q,
                "answer": a,
                "hook": str(item.get("hook", "")).strip(),
                "difficulty": str(item.get("difficulty", "medium")).strip().lower(),
                "mechanic": str(item.get("mechanic", "")).strip().lower(),
                "answer_domain": str(item.get("answer_domain", "")).strip().lower(),
                "source": "gemini_original",
            })
        return fresh
    except Exception as exc:
        print(f"⚠️ Original riddle generation unavailable: {exc}")
        return []


def _ensure_candidate_pool():
    rows = _load_candidates()
    used = {_n(x.get("topic", "")) for x in _load() if isinstance(x, dict)}
    rows = [x for x in rows if isinstance(x, dict) and _n(x.get("question", "")) not in used]
    if len(rows) < 8:
        rows.extend(_generate_original_candidates(12))
    seen = set(); clean = []
    for row in rows:
        q = _n(row.get("question", ""))
        if not q or q in seen or q in used:
            continue
        seen.add(q); clean.append(row)
    _save_candidates(clean[-100:])
    return clean


def get_next_topic():
    rows = _load()
    used_q = {_n(x.get("topic", "")) for x in rows if isinstance(x, dict)}
    performance = _performance_by_pillar()
    topic_performance = _performance_by_topic()
    candidates = _ensure_candidate_pool()
    recent_pillars = [str(x.get("pillar", "")) for x in rows[-4:] if isinstance(x, dict)]

    pool = []
    for item in candidates:
        q, a = str(item.get("question", "")).strip(), str(item.get("answer", "")).strip()
        if q and a and _n(q) not in used_q:
            pillar = str(item.get("pillar", "logic")).strip().lower()
            source = str(item.get("source", "original"))
            score = _creative_score(pillar, q, a, performance, topic_performance, rows, source)
            score -= recent_pillars.count(pillar) * 5.0
            pool.append((pillar, q, a, round(score, 3), source, item.get("mechanic", ""), item.get("answer_domain", "")))

    # Seeds are retained only as a fallback for a temporarily empty generated pool.
    if not pool:
        for pillar, q, a in RIDDLES:
            if _n(q) not in used_q:
                score = _creative_score(pillar, q, a, performance, topic_performance, rows, "seed")
                score -= recent_pillars.count(pillar) * 5.0
                pool.append((pillar, q, a, round(score, 3), "seed", "legacy", "legacy"))

    if not pool:
        raise RuntimeError("Riddle candidate pool exhausted. Generate new original riddles before publishing.")

    pool.sort(key=lambda x: x[3], reverse=True)
    # Prefer fresh generated candidates. Among them, use weighted exploration rather
    # than always choosing #1 so the channel continues testing different concepts.
    shortlist = pool[:min(8, len(pool))]
    weights = [max(0.15, (len(shortlist) - i) ** 1.45) for i in range(len(shortlist))]
    chosen = random.choices(shortlist, weights=weights, k=1)[0]
    print("🧠 Riddle creative selection:", json.dumps({
        "selected_pillar": chosen[0], "source": chosen[4], "score": chosen[3],
        "mechanic": chosen[5], "answer_domain": chosen[6],
        "recent_pillars": recent_pillars,
        "shortlist": [{"pillar": x[0], "score": x[3], "source": x[4], "mechanic": x[5], "answer_domain": x[6]} for x in shortlist]
    }, ensure_ascii=False))
    return chosen[0], chosen[1], chosen[2]


def record_topic(topic, pillar, title="", video_id="", workdir="", answer=""):
    rows = _load()
    nq = _n(topic)
    if nq in {_n(x.get("topic", "")) for x in rows if isinstance(x, dict)}:
        return
    rows.append({"topic": topic, "answer": answer, "pillar": pillar, "title": title,
                 "video_id": video_id, "workdir": workdir})
    HISTORY.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def get_pending_riddle():
    try:
        x = json.loads(PENDING.read_text(encoding="utf-8"))
        return x if isinstance(x, dict) and x.get("topic") and x.get("answer") and x.get("number") else None
    except Exception:
        return None


def save_pending_riddle(pillar, topic, answer, number):
    PENDING.write_text(json.dumps({"pillar": pillar, "topic": topic, "answer": answer,
                                   "number": number}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def next_riddle_number():
    pending = get_pending_riddle()
    if pending:
        return int(pending["number"]) + 1
    last = 0
    for row in _load():
        if isinstance(row, dict):
            m = re.search(r"Riddle\s*#\s*(\d+)", str(row.get("title", "")), re.I)
            if m:
                last = max(last, int(m.group(1)))
    return last + 1
