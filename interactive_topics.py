from __future__ import annotations
import json,re,random
from pathlib import Path
ROOT=Path(__file__).resolve().parent
HISTORY=ROOT/"interactive_topic_history.json"
TOPICS={"impossible_choices":["Would you press a button that gives you one million dollars but harms a stranger?","Would you erase your happiest memory to forget your worst day?","Would you save your best friend or five strangers?","Would you know the exact day you die if you could?"],"solve_the_mystery":["A locked room, one body, and no way out: who is lying?","Three suspects tell three stories: can you spot the contradiction?","A missing phone, one timestamp, and one impossible clue","A room full of clues, but the smallest detail changes everything"],"psychological_scenarios":["You find a wallet with no ID but enough cash to change your month","Everyone agrees on something you know is false: what do you do?","You can hear one person's thoughts for ten minutes: who do you choose?","You can learn one painful truth about yourself instantly"]}
def _n(x): return re.sub(r"[^a-z0-9]+"," ",str(x or "").lower()).strip()
def _load():
 try:
  x=json.loads(HISTORY.read_text(encoding="utf-8")); return x if isinstance(x,list) else []
 except Exception:return []
def get_next_topic():
 used={_n(x.get("topic","")) for x in _load() if isinstance(x,dict)}
 pool=[(p,t) for p,ts in TOPICS.items() for t in ts if _n(t) not in used]
 if not pool: raise RuntimeError("Interactive topic pool exhausted.")
 return random.choice(pool)
def record_topic(topic,pillar,title="",video_id="",workdir=""):
 rows=_load()
 if _n(topic) not in {_n(x.get("topic","")) for x in rows if isinstance(x,dict)}: rows.append({"topic":topic,"pillar":pillar,"title":title,"video_id":video_id,"workdir":workdir})
 HISTORY.write_text(json.dumps(rows,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
