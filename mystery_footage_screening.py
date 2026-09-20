"""Screen mystery footage for provenance, real-incident signals, and usability."""
from __future__ import annotations
import json, os, subprocess, tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests
from google import genai
from google.genai import types

ROOT=Path(__file__).resolve().parent; CATALOG=ROOT/'mystery_footage_catalog.json'; MODEL_NAME='gemini-flash-lite-latest'
TRUE={'1','true','yes'}; MIN_BYTES=10000; MAX_BYTES=300*1024*1024

def enabled(name, default=False): return os.getenv(name,str(default).lower()).lower() in TRUE
def run(cmd): return subprocess.run(cmd,check=True,capture_output=True,text=True).stdout.strip()
def download(url,dest):
    r=requests.get(url,timeout=120,stream=True,headers={'User-Agent':'Mint-YT-Factory/1.0 footage-screening'}); r.raise_for_status(); total=0
    with dest.open('wb') as f:
        for chunk in r.iter_content(1024*1024):
            if chunk:
                total+=len(chunk)
                if total>MAX_BYTES: raise RuntimeError('source exceeds screening size limit')
                f.write(chunk)
    if total<MIN_BYTES: raise RuntimeError('downloaded file is too small')
def probe(path):
    data=json.loads(run(['ffprobe','-v','error','-show_entries','format=duration,size:stream=width,height,codec_type','-of','json',str(path)])); fmt=data.get('format',{}); v=next((s for s in data.get('streams',[]) if s.get('codec_type')=='video'),None)
    if not v: raise RuntimeError('no video stream found')
    duration=float(fmt.get('duration') or 0); w=int(v.get('width') or 0); h=int(v.get('height') or 0)
    if duration<90: raise RuntimeError(f'rejected short-form source: {duration:.1f}s; minimum 90s')
    if h>w: raise RuntimeError(f'rejected portrait source: {w}x{h}')
    return {'duration_seconds':round(duration,2),'width':w,'height':h,'size_bytes':int(float(fmt.get('size') or path.stat().st_size))}
def frames(source,directory):
    directory.mkdir(parents=True,exist_ok=True); run(['ffmpeg','-y','-i',str(source),'-vf','fps=1/8,scale=768:-2','-frames:v','8','-q:v','4',str(directory/'frame-%02d.jpg')]); return [p.read_bytes() for p in sorted(directory.glob('frame-*.jpg'))]
def assess(candidate,images):
    key=os.getenv('GEMINI_API_KEY','').strip()
    if not key or not images: return {'hook_score':0,'story_score':0,'usable_visuals':False,'real_incident_supported':False,'screening_status':'manual-review-required','screening_notes':'Gemini unavailable; manual provenance review required.'}
    prompt=f'''Assess this candidate for a factual mystery documentary. Return JSON only with integer hook_score and story_score (0-10), usable_visuals boolean, real_incident_supported boolean, and screening_notes. Require evidence of a real-world incident, CCTV/surveillance capture, or explicitly documented found footage. Do NOT treat a title, dramatic appearance, or uploader claim as proof. Reject fiction, films, reenactments, compilations, commentary, podcasts, Shorts, Reels, TikToks, and videos whose authenticity cannot be supported by the supplied metadata and frames. Clearly state uncertainty. Title: {candidate.get('title')} Description: {candidate.get('footage_description')} Source: {candidate.get('source_url')}'''
    with genai.Client(api_key=key) as client:
        response=client.models.generate_content(model=MODEL_NAME,contents=[prompt]+[types.Part.from_bytes(data=x,mime_type='image/jpeg') for x in images],config=types.GenerateContentConfig(response_mime_type='application/json',temperature=0.2))
    try: result=json.loads(response.text)
    except Exception: result={}
    clamp=lambda x:max(0,min(10,int(x or 0)))
    return {'hook_score':clamp(result.get('hook_score')),'story_score':clamp(result.get('story_score')),'usable_visuals':bool(result.get('usable_visuals')),'real_incident_supported':bool(result.get('real_incident_supported')),'screening_status':'gemini-reviewed','screening_notes':str(result.get('screening_notes',''))[:1200]}
def screen(item):
    url=item.get('video_url') or item.get('direct_download_url')
    if not url: raise RuntimeError('candidate has no video URL')
    with tempfile.TemporaryDirectory(prefix='mystery-screen-') as t:
        p=Path(t); source=p/'source'; download(url,source); tech=probe(source); assessment=assess(item,frames(source,p/'frames'))
    out=dict(item); out['screening']={**tech,**assessment,'screened_at':datetime.now(timezone.utc).isoformat()}; s=out['screening']; minimum=int(os.getenv('MYSTERY_FOOTAGE_MIN_STORY_SCORE','6'))
    s['eligible']=bool(s['screening_status']=='gemini-reviewed' and s['real_incident_supported'] is True and s['usable_visuals'] is True and s['hook_score']>=minimum and s['story_score']>=minimum)
    return out
def main():
    data=json.loads(CATALOG.read_text(encoding='utf-8')); changed=False
    for i,item in enumerate(data.setdefault('items',[])):
        if item.get('screening',{}).get('eligible') is True: continue
        try: data['items'][i]=screen(item); changed=True; print(f"Screened {item.get('id')}: eligible={data['items'][i]['screening']['eligible']}")
        except Exception as e: data['items'][i]['screening']={'eligible':False,'screening_status':'failed','screening_notes':str(e)[:1200],'screened_at':datetime.now(timezone.utc).isoformat()}; changed=True; print(f'Screening failed for {item.get("id")}: {e}')
    if changed: CATALOG.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
if __name__=='__main__': main()
