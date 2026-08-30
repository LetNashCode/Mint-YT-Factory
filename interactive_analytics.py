from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PATH=ROOT/"analytics"/"interactive_videos.json"
REPORT=ROOT/"analytics"/"interactive_comparison.json"
def _load(p,d):
 try:return json.loads(p.read_text(encoding="utf-8"))
 except Exception:return d
def _write(p,x): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def record(video_id,topic,pillar,title,workdir=""):
 rows=_load(PATH,[]); rows=rows if isinstance(rows,list) else []; rows.append({"video_id":video_id,"topic":topic,"pillar":pillar,"title":title,"workdir":workdir}); _write(PATH,rows)
def build_comparison():
 current=_load(ROOT/"analytics"/"videos.json",[]); interactive=_load(PATH,[]); groups={"curiosity_explainers":current if isinstance(current,list) else []}
 for x in interactive if isinstance(interactive,list) else []: groups.setdefault(x.get("pillar","interactive"),[]).append(x)
 out={}
 for k,rows in groups.items():
  latest=[x.get("latest",{}) for x in rows if isinstance(x,dict)]
  n=len(latest); out[k]={"videos":n,"avg_views":round(sum(float(x.get("views",0) or 0) for x in latest)/n,2) if n else 0,"avg_comments":round(sum(float(x.get("comments",0) or 0) for x in latest)/n,2) if n else 0,"avg_shares":round(sum(float(x.get("shares",0) or 0) for x in latest)/n,2) if n else 0}
 _write(REPORT,out); return out
