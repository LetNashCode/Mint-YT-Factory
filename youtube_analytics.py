"""YouTube performance collector + self-learning data source for Mint-YT-Factory."""
from __future__ import annotations
import argparse,json,os
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT=Path(__file__).resolve().parent; ANALYTICS_DIR=ROOT/'analytics'; REGISTRY_PATH=ANALYTICS_DIR/'videos.json'; SUMMARY_PATH=ANALYTICS_DIR/'summary.json'; USED_TOPICS_PATH=ROOT/'used_topics.json'; ANALYTICS_MARKER='__MINT_ANALYTICS__::'

def _utc_now(): return datetime.now(timezone.utc).isoformat()
def _load(path,default):
    try: return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except Exception: return default
def _write(path,data):
    ANALYTICS_DIR.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8'); tmp.replace(path)
def _credentials():
    raw=os.environ.get('YOUTUBE_TOKEN_JSON')
    if not raw: raise RuntimeError('YOUTUBE_TOKEN_JSON is missing.')
    return Credentials.from_authorized_user_info(json.loads(raw))
def _youtube_service(): return build('youtube','v3',credentials=_credentials(),cache_discovery=False)

def _read_registry_markers():
    raw=_load(USED_TOPICS_PATH,[]); out=[]
    if not isinstance(raw,list): return out
    for item in raw:
        if isinstance(item,str) and item.startswith(ANALYTICS_MARKER):
            try:
                record=json.loads(item[len(ANALYTICS_MARKER):]);
                if isinstance(record,dict) and record.get('video_id'): out.append(record)
            except Exception: pass
    return out

def _persist_registry_marker(record):
    raw=_load(USED_TOPICS_PATH,[]); raw=raw if isinstance(raw,list) else []; vid=str(record.get('video_id',''))
    if not vid: return
    for item in raw:
        if isinstance(item,str) and item.startswith(ANALYTICS_MARKER):
            try:
                if json.loads(item[len(ANALYTICS_MARKER):]).get('video_id')==vid: return
            except Exception: pass
    raw.append(ANALYTICS_MARKER+json.dumps(record,ensure_ascii=False,separators=(',',':')))
    tmp=USED_TOPICS_PATH.with_suffix('.tmp'); tmp.write_text(json.dumps(raw,indent=2,ensure_ascii=False)+'\n',encoding='utf-8'); tmp.replace(USED_TOPICS_PATH)

def fetch_video_stats(video_ids):
    if not video_ids: return {}
    yt=_youtube_service(); result={}
    for start in range(0,len(video_ids),50):
        batch=[x for x in video_ids[start:start+50] if x]; response=yt.videos().list(part='snippet,statistics,contentDetails',id=','.join(batch),maxResults=50).execute()
        for item in response.get('items',[]):
            stats=item.get('statistics',{}); snippet=item.get('snippet',{})
            result[item['id']]={'title':snippet.get('title',''),'published_at':snippet.get('publishedAt'),'views':int(stats.get('viewCount',0)),'likes':int(stats.get('likeCount',0)),'comments':int(stats.get('commentCount',0)),'duration':item.get('contentDetails',{}).get('duration')}
    return result

def fetch_analytics_metrics(video_ids):
    """Best-effort retention/subscriber metrics. Requires yt-analytics.readonly."""
    if not video_ids: return {}
    try:
        yt=build('youtubeAnalytics','v2',credentials=_credentials(),cache_discovery=False); out={}
        for vid in video_ids:
            try:
                response=yt.reports().query(ids='channel==MINE',startDate='2000-01-01',endDate=datetime.now(timezone.utc).date().isoformat(),metrics='views,likes,comments,shares,averageViewDuration,averageViewPercentage,subscribersGained,subscribersLost,estimatedMinutesWatched',dimensions='video',filters=f'video=={vid}').execute()
                rows=response.get('rows',[])
                if rows:
                    row=rows[0]; out[vid]={'analytics_views':int(row[1] or 0),'analytics_likes':int(row[2] or 0),'analytics_comments':int(row[3] or 0),'shares':int(row[4] or 0),'average_view_duration':float(row[5] or 0),'average_view_percentage':float(row[6] or 0),'subscribers_gained':int(row[7] or 0),'subscribers_lost':int(row[8] or 0),'estimated_minutes_watched':float(row[9] or 0)}
            except Exception as exc: print(f'⚠️ Analytics metrics unavailable for {vid}: {exc}')
        return out
    except Exception as exc:
        print(f'⚠️ YouTube Analytics API scope unavailable; using Data API metrics only: {exc}')
        return {}

def record_upload(video_id,topic,title,workdir='',production_metadata=None):
    metadata=production_metadata if isinstance(production_metadata,dict) else {}
    record={'video_id':video_id,'topic':str(topic or '').strip(),'title':str(title or '').strip(),'workdir':str(workdir or '').strip(),'published_at':_utc_now(),**metadata}
    records=_load(REGISTRY_PATH,[]); records=records if isinstance(records,list) else []
    existing=next((x for x in records if isinstance(x,dict) and x.get('video_id')==video_id),None)
    if existing:
        existing.update({k:v for k,v in record.items() if v not in ('',None,{})})
    else:
        records.append({**record,'latest':{'views':0,'likes':0,'comments':0,'shares':0,'average_view_duration':0,'average_view_percentage':0,'subscribers_gained':0,'subscribers_lost':0},'snapshots':[]})
    _write(REGISTRY_PATH,records); _persist_registry_marker(record); print(f'📊 Analytics registry: recorded {video_id}')

def _engagement_rate(v,l,c): return round(((l+c)/v)*100,4) if v>0 else 0.0

def _materialize_records():
    files=_load(REGISTRY_PATH,[]); files=files if isinstance(files,list) else []; by_id={str(x.get('video_id')):x for x in files if isinstance(x,dict) and x.get('video_id')}
    for marker in _read_registry_markers():
        vid=str(marker['video_id'])
        if vid not in by_id: by_id[vid]={**marker,'latest':{},'snapshots':[]}
        else: by_id[vid].update({k:v for k,v in marker.items() if v})
    return list(by_id.values())

def refresh_registry():
    records=_materialize_records()
    if not records:
        summary={'generated_at':_utc_now(),'video_count':0,'optimization_ready':False,'reason':'Need at least 3 published videos before optimizing content.','totals':{},'averages':{},'top_videos':[],'topic_performance':[]}; _write(REGISTRY_PATH,[]); _write(SUMMARY_PATH,summary); return summary
    ids=[str(x['video_id']) for x in records]; basic=fetch_video_stats(ids); advanced=fetch_analytics_metrics(ids); now=_utc_now()
    for r in records:
        vid=str(r['video_id']); cur=basic.get(vid)
        if not cur: continue
        r['title']=cur.get('title') or r.get('title',''); r['published_at']=cur.get('published_at') or r.get('published_at')
        latest={'views':int(cur.get('views',0)),'likes':int(cur.get('likes',0)),'comments':int(cur.get('comments',0)),'engagement_rate':_engagement_rate(int(cur.get('views',0)),int(cur.get('likes',0)),int(cur.get('comments',0))),'checked_at':now}
        latest.update(advanced.get(vid,{})); r['latest']=latest; snaps=r.get('snapshots',[]); snaps=snaps if isinstance(snaps,list) else []; snaps.append(latest); r['snapshots']=snaps[-60:]
    _write(REGISTRY_PATH,records)
    total_views=sum(int(x.get('latest',{}).get('views',0)) for x in records); total_likes=sum(int(x.get('latest',{}).get('likes',0)) for x in records); total_comments=sum(int(x.get('latest',{}).get('comments',0)) for x in records); count=len(records)
    avg={k:round(sum(float(x.get('latest',{}).get(k,0)) for x in records)/count,2) for k in ('views','likes','comments','average_view_percentage','subscribers_gained','shares')}
    ranked=sorted(records,key=lambda x:int(x.get('latest',{}).get('views',0)),reverse=True)
    rows=[]
    for r in ranked:
        x=r.get('latest',{}); rows.append({'topic':r.get('topic',''),'video_id':r.get('video_id'),'title':r.get('title',''),'views':int(x.get('views',0)),'likes':int(x.get('likes',0)),'comments':int(x.get('comments',0)),'shares':int(x.get('shares',0)),'average_view_duration':float(x.get('average_view_duration',0)),'average_view_percentage':float(x.get('average_view_percentage',0)),'subscribers_gained':int(x.get('subscribers_gained',0)),'subscribers_lost':int(x.get('subscribers_lost',0)),'engagement_rate':float(x.get('engagement_rate',0))})
    summary={'generated_at':now,'video_count':count,'optimization_ready':count>=3,'reason':'' if count>=3 else 'Need at least 3 published videos before optimizing content.','totals':{'views':total_views,'likes':total_likes,'comments':total_comments},'averages':avg,'top_videos':rows[:10],'topic_performance':rows[:50],'optimization_rules':['Learn patterns, never copy winning topics literally.','Optimize for retention and subscriber conversion as well as views.','Prefer strong curiosity gaps and concrete everyday mysteries.','Keep experiments so the model does not overfit to one topic.'] if count>=3 else []}
    _write(SUMMARY_PATH,summary); print(f'📊 Tracked videos: {count}'); print(f'📊 Total views: {total_views:,}'); print(f'🧠 Optimization ready: {"YES" if count>=3 else "NO"}')
    return summary

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--refresh',action='store_true'); args=parser.parse_args()
    if not args.refresh: parser.error('Use --refresh')
    refresh_registry()
if __name__=='__main__': main()
