"""Sequential engagement experiments for Mint-YT-Factory Shorts.

The factory tests one engagement mechanic at a time, records the mechanic on
published videos, and learns from comment/share rates. Pinning is not attempted
because the standard YouTube Data API does not expose a supported pin endpoint.
"""
from __future__ import annotations
import json, math, re
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parent; REGISTRY_PATH=ROOT/'analytics'/'videos.json'
EXPERIMENTS=['prediction','choice','challenge','disagreement','next_experiment','curiosity']

def _load(path:Path,default:Any)->Any:
    try:return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def _clean_topic(topic:str)->str:return re.sub(r'\s+',' ',str(topic or '').strip()).rstrip('?.!')
def _topic_object(topic:str)->str:return re.sub(r'^why\s+(do|does|is|are|can)\s+','',_clean_topic(topic),flags=re.I)[:100]
def _records()->list[dict]:
    data=_load(REGISTRY_PATH,[]);return data if isinstance(data,list) else []
def _rate(record:dict,metric:str)->float:
    latest=record.get('latest',{}) or {};views=max(1,int(latest.get('views',0) or 0));return float(latest.get(metric,0) or 0)/views*100.0

def _published_experiments()->list[str]:return [str(r.get('engagement_experiment')) for r in _records() if r.get('engagement_experiment') in EXPERIMENTS]

def _learned_winner()->str|None:
    grouped:dict[str,list[tuple[float,int]]]={}
    for record in _records():
        exp=record.get('engagement_experiment');latest=record.get('latest',{}) or {};views=int(latest.get('views',0) or 0)
        if exp not in EXPERIMENTS or views<100:continue
        score=_rate(record,'comments')*.65+_rate(record,'shares')*.35;grouped.setdefault(exp,[]).append((score,views))
    eligible=[]
    for exp,vals in grouped.items():
        if len(vals)>=2:
            weighted=sum(score*math.sqrt(max(views,1)) for score,views in vals)/sum(math.sqrt(max(views,1)) for _,views in vals);eligible.append((weighted,exp))
    return max(eligible)[1] if eligible else None

def choose_experiment()->tuple[str,str]:
    published=_published_experiments();completed=len(published);winner=_learned_winner()
    if completed<len(EXPERIMENTS):
        experiment=EXPERIMENTS[completed];phase=f'baseline_test_{completed+1}_of_{len(EXPERIMENTS)}'
    elif winner:
        cycle=completed-len(EXPERIMENTS)
        if cycle%6==5:
            experiment=EXPERIMENTS[(cycle//6)%len(EXPERIMENTS)];phase='exploration_recheck'
        else:experiment=winner;phase='learned_winner'
    else:
        experiment=EXPERIMENTS[completed%len(EXPERIMENTS)];phase='rotation_until_enough_data'
    return experiment,phase

def build_engagement_package(topic:str,experiment:str)->dict[str,str]:
    obj=_topic_object(topic)
    if experiment=='prediction':spoken=f'Quick guess: would {obj} happen more or less than you expect?';comment=f'Before watching again: what was your guess about {obj}? 👇';share='Send this to someone who would guess wrong.'
    elif experiment=='choice':spoken='Pick one before I reveal it: A or B?';comment=f'Your vote: A or B for {obj}? 👇';share='Send this to someone who will confidently pick the wrong one.'
    elif experiment=='challenge':spoken='Try this yourself and see if your result matches.';comment=f'If you test {obj}, tell me what happened. 👇';share='Send this to someone who should try the experiment.'
    elif experiment=='disagreement':spoken='But would you actually call that what I just called it?';comment=f'Would you describe {obj} the same way, or differently? 👇';share='Send this to the person who will argue about this.'
    elif experiment=='next_experiment':spoken='What should we test next?';comment='What everyday mystery should we test next? 👇';share='Send this to someone with a weird everyday question.'
    else:spoken='And that leaves one more weird question.';comment=f'What do you think the next mystery about {obj} is? 👇';share='Send this to someone who loves weird everyday facts.'
    return {'spoken_prompt':spoken,'comment':comment,'share_prompt':share}

def assign(topic:str)->dict[str,str]:
    experiment,phase=choose_experiment();package=build_engagement_package(topic,experiment);return {'experiment':experiment,'phase':phase,**package}

def summarize()->dict[str,Any]:
    by:dict[str,list[dict[str,float]]]={}
    for r in _records():
        exp=r.get('engagement_experiment');latest=r.get('latest',{}) or {};views=int(latest.get('views',0) or 0)
        if exp not in EXPERIMENTS or views<=0:continue
        by.setdefault(exp,[]).append({'comments_rate':_rate(r,'comments'),'shares_rate':_rate(r,'shares'),'views':views})
    return {exp:{'videos':len(rows),'avg_comment_rate':round(sum(x['comments_rate'] for x in rows)/len(rows),4),'avg_share_rate':round(sum(x['shares_rate'] for x in rows)/len(rows),4),'avg_views':round(sum(x['views'] for x in rows)/len(rows),1)} for exp,rows in by.items()}
