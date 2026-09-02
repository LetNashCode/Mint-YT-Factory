from __future__ import annotations
import json,re,random
from pathlib import Path
ROOT=Path(__file__).resolve().parent
HISTORY=ROOT/"interactive_topic_history.json"
RIDDLES=[
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
]
def _n(x): return re.sub(r"[^a-z0-9]+"," ",str(x or "").lower()).strip()
def _load():
 try:
  x=json.loads(HISTORY.read_text(encoding="utf-8")); return x if isinstance(x,list) else []
 except Exception:return []
def get_next_topic():
 rows=_load(); used_q={_n(x.get("topic","")) for x in rows if isinstance(x,dict)}; used_a={_n(x.get("answer","")) for x in rows if isinstance(x,dict)}
 pool=[(p,q,a) for p,q,a in RIDDLES if _n(q) not in used_q and _n(a) not in used_a]
 if not pool: raise RuntimeError("Riddle pool exhausted. Add new unique riddles before publishing.")
 pillar,question,answer=random.choice(pool)
 return pillar,question,answer
def record_topic(topic,pillar,title="",video_id="",workdir="",answer=""):
 rows=_load(); nq=_n(topic); na=_n(answer)
 if nq in {_n(x.get("topic","")) for x in rows if isinstance(x,dict)}: return
 if na and na in {_n(x.get("answer","")) for x in rows if isinstance(x,dict)}: return
 rows.append({"topic":topic,"answer":answer,"pillar":pillar,"title":title,"video_id":video_id,"workdir":workdir})
 HISTORY.write_text(json.dumps(rows,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
