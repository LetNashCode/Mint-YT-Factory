from __future__ import annotations
import json, re, random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / "interactive_topic_history.json"
PENDING = ROOT / "pending_riddle.json"
COUNTER = ROOT / "riddle_counter.json"

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

def _load():
    try:
        x = json.loads(HISTORY.read_text(encoding="utf-8"))
        return x if isinstance(x, list) else []
    except Exception:
        return []

def get_next_topic():
    rows = _load()
    used_q = {_n(x.get("topic", "")) for x in rows if isinstance(x, dict)}
    pool = [(p, q, a) for p, q, a in RIDDLES if _n(q) not in used_q]
    if not pool:
        raise RuntimeError("Riddle pool exhausted. Add new unique riddles before publishing.")
    return random.choice(pool)

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
    try:
        n = int(json.loads(COUNTER.read_text(encoding="utf-8")).get("last", 0)) + 1
    except Exception:
        n = 1
    COUNTER.write_text(json.dumps({"last": n}, indent=2) + "\n", encoding="utf-8")
    return n
