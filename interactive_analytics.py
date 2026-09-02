from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PATH=ROOT/"analytics"/"interactive_videos.json"
REPORT=ROOT/"analytics"/"interactive_comparison.json"

def _load(p,d):
    try:return json.loads(p.read_text(encoding="utf-8"))
    except Exception:return d
def _write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def record(video_id,topic,pillar,title,workdir=""):
    rows=_load(PATH,[]);rows=rows if isinstance(rows,list) else []
    if not any(isinstance(x,dict) and x.get("video_id")==video_id for x in rows):
        rows.append({"video_id":video_id,"topic":topic,"pillar":pillar,"title":title,"workdir":workdir,"latest":{}})
    _write(PATH,rows)
def build_comparison():
    current=_load(ROOT/"analytics"/"videos.json",[])
    interactive=_load(PATH,[])
    groups={"publish_shorts":current if isinstance(current,list) else []}
    for x in interactive if isinstance(interactive,list) else []:groups.setdefault(x.get("pillar","riddles"),[]).append(x)
    out={}
    for k,rows in groups.items():
        metrics=[x.get("latest",{}) for x in rows if isinstance(x,dict)]
        n=len(rows)
        def avg(name):return round(sum(float(m.get(name,0) or 0) for m in metrics)/len(metrics),2) if metrics else 0
        out[k]={"videos":n,"avg_views":avg("views"),"avg_comments":avg("comments"),"avg_shares":avg("shares"),"avg_likes":avg("likes")}
    _write(REPORT,out);return out
