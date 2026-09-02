"""Self-learning decision engine for Mint-YT-Factory."""
from __future__ import annotations
import json,math
from collections import defaultdict
import re
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parent; ANALYTICS_DIR=ROOT/'analytics'; PLAYBOOK_PATH=ANALYTICS_DIR/'playbook.json'; USED_TOPICS_PATH=ROOT/'used_topics.json'
EXPLOITATION=.70; ADJACENT_EXPLORATION=.20; WILD_EXPLORATION=.10

def _load(path:Path,default:Any)->Any:
    try:return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception:return default

def _write(path:Path,data:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8'); tmp.replace(path)

def _norm_topic(value:str)->str:return ' '.join(str(value or '').lower().strip().replace('?','').split())
def _performance(record:dict)->float:
    latest=record.get('latest',{}) or {}; views=max(0,int(latest.get('views',0))); likes=max(0,int(latest.get('likes',0))); comments=max(0,int(latest.get('comments',0))); subs=max(0,int(latest.get('subscribers_gained',0))); retention=float(latest.get('average_view_percentage',0) or 0)
    return .35*math.log1p(views)+.20*retention+.10*(likes/max(views,1)*1000)+.10*(comments/max(views,1)*1000)+.25*(subs/max(views,1)*100000)

def _pattern_features(topic:str)->dict:
    text=str(topic or '').lower()
    words=re.findall(r"[a-z0-9]+",text)
    return {
        'topic_category': next((x for x in ('technology','food','clothing','home','body','car','weather','sound','kitchen','everyday') if x in text), 'everyday'),
        'hook_type': 'why_question' if text.startswith('why') else ('how_question' if text.startswith('how') else 'curiosity'),
        'topic_length': 'short' if len(words)<=5 else ('medium' if len(words)<=7 else 'long'),
    }

def _topic_similarity(a:str,b:str)->float:
    sa,sb=set(_norm_topic(a).split()),set(_norm_topic(b).split())
    return len(sa&sb)/len(sa|sb) if sa and sb else 0.0

def build_playbook(records:list[dict])->dict:
    scored=[(_performance(r),r) for r in records if isinstance(r,dict) and r.get('video_id') and isinstance(r.get('latest',{}),dict)]
    scored.sort(key=lambda x:x[0],reverse=True); count=len(scored); top_n=max(3,min(10,math.ceil(count*.25))) if count else 0; winners=[r for _,r in scored[:top_n]]; losers=[r for _,r in scored[-top_n:]] if count>=4 else []
    def pattern_rows(items):
        out=defaultdict(list)
        for r in items:
            enriched={**_pattern_features(r.get('topic','')), **r}
            for key in ('topic_category','hook_type','story_structure','visual_style','music_type','voice','topic_length'):
                value=str(enriched.get(key,'')).strip()
                if value: out[f'{key}:{value}'].append(_performance(r))
        return out
    def ranked(rows):return [{"pattern":k,"score":round(sum(v)/len(v),3),"sample_size":len(v)} for k,v in sorted(rows.items(),key=lambda kv:sum(kv[1])/len(kv[1]),reverse=True)]
    topics=[_norm_topic(r.get('topic','')) for r in records if r.get('topic')]
    has_live_metrics=any(int((r.get('latest',{}) or {}).get('views',0))>0 or float((r.get('latest',{}) or {}).get('average_view_percentage',0) or 0)>0 for r in records)
    return {'generated_at':datetime.now(timezone.utc).isoformat(),'video_count':len(records),'learning_ready':len(records)>=3 and has_live_metrics,'metrics_available':has_live_metrics,'objective':'maximize sustainable views and subscriber growth while preserving originality','strategy':{'exploitation':EXPLOITATION,'adjacent_exploration':ADJACENT_EXPLORATION,'wild_exploration':WILD_EXPLORATION},'winning_patterns':ranked(pattern_rows(winners))[:20] if has_live_metrics else [],'weak_patterns':ranked(pattern_rows(losers))[:20] if has_live_metrics else [],'winning_topics':[r.get('topic','') for r in winners if r.get('topic')][:10] if has_live_metrics else [],'avoid_topics':[r.get('topic','') for r in losers if r.get('topic')][:10] if has_live_metrics else [],'used_topic_count':len(set(topics)),'rules':['Learn patterns, never copy winning topics literally.','Prefer concrete everyday mysteries with an immediate curiosity gap.','Favor entertaining demonstrations and playful explanations over lectures.','Use subscriber conversion and retention, not views alone, as growth signals.','Keep 20% of topics adjacent experiments and 10% genuinely new experiments.','Reject exact repeats and near-duplicate topics before generation.']}

def score_candidate_topic(topic:str, playbook:dict|None=None)->dict:
    pb=playbook or get_playbook(); features=_pattern_features(topic); wins=pb.get('winning_patterns',[]) if isinstance(pb,dict) else []; weak=pb.get('weak_patterns',[]) if isinstance(pb,dict) else []
    score=0.0; reasons=[]
    for row in wins:
        pat=str(row.get('pattern',''))
        for k,v in features.items():
            if pat==f"{k}:{v}": score+=float(row.get('score',0))*max(1,int(row.get('sample_size',1))); reasons.append('winner '+pat)
    for row in weak:
        pat=str(row.get('pattern',''))
        for k,v in features.items():
            if pat==f"{k}:{v}": score-=abs(float(row.get('score',0)))*max(1,int(row.get('sample_size',1))); reasons.append('weak '+pat)
    return {'topic':topic,'score':round(score,3),'features':features,'reasons':reasons[:8]}

def refresh_playbook()->dict:
    records=_load(ANALYTICS_DIR/'videos.json',[]); records=records if isinstance(records,list) else []
    current=_load(PLAYBOOK_PATH,{})
    playbook=build_playbook(records)
    if records and not playbook['metrics_available'] and isinstance(current,dict) and current.get('metrics_available'):
        current['generated_at']=datetime.now(timezone.utc).isoformat(); current['video_count']=len(records); current['metrics_stale']=True; playbook=current
    _write(PLAYBOOK_PATH,playbook); print(f"🧠 Learning engine: {'READY' if playbook.get('learning_ready') else 'WARMING UP'}"); print(f"🧠 Playbook saved: {PLAYBOOK_PATH}"); return playbook

def get_playbook()->dict:
    data=_load(PLAYBOOK_PATH,{})
    return data if isinstance(data,dict) else {}

def get_used_topics()->list[str]:
    raw=_load(USED_TOPICS_PATH,[]); result=[]
    if not isinstance(raw,list):return result
    for item in raw:
        if isinstance(item,str) and not item.startswith('__MINT_ANALYTICS__::'):result.append(item)
        elif isinstance(item,dict) and item.get('topic'):result.append(str(item['topic']))
    return result

def topic_is_duplicate(topic:str,threshold:float=.62)->bool:
    candidate=_norm_topic(topic)
    return bool(candidate) and any(_topic_similarity(candidate,old)>=threshold for old in get_used_topics()) or not bool(candidate)

if __name__=='__main__':refresh_playbook()
