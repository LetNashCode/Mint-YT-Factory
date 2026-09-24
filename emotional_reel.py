import json,os,random,re,subprocess,time
from pathlib import Path
import requests,yaml
from google import genai
from google.genai import types
from music import download_music
from upload_youtube import upload_video
from social_publish import publish_social_reels
OUT=Path('output/emotional_reel');OUT.mkdir(parents=True,exist_ok=True);N=9;SEC=6
def ai(p):
 k=os.getenv('GEMINI_API_KEY','');
 if not k: raise RuntimeError('GEMINI_API_KEY is required')
 r=genai.Client(api_key=k).models.generate_content(model=os.getenv('EMOTIONAL_REEL_MODEL','gemini-flash-lite-latest'),contents=p,config=types.GenerateContentConfig(temperature=.7,response_mime_type='application/json'))
 return json.loads(str(r.text).replace('```json','').replace('```','').strip())
def search(q):
 out=[]; pk=os.getenv('PEXELS_API_KEY',''); xb=os.getenv('PIXABAY_API_KEY','')
 if pk:
  r=requests.get('https://api.pexels.com/videos/search',params={'query':q,'orientation':'portrait','per_page':12},headers={'Authorization':pk},timeout=25)
  if r.ok:
   for v in r.json().get('videos',[]):
    fs=[x for x in v.get('video_files',[]) if x.get('link')]; fs.sort(key=lambda x:-float(x.get('width') or 0))
    if fs: out.append((f"pexels:{v.get('id')}",fs[0]['link']))
 if xb:
  r=requests.get('https://pixabay.com/api/videos/',params={'key':xb,'q':q,'video_type':'film','per_page':12},timeout=25)
  if r.ok:
   for v in r.json().get('hits',[]):
    fs=sorted((v.get('videos') or {}).values(),key=lambda x:-float(x.get('width') or 0))
    if fs and fs[0].get('url'): out.append((f"pixabay:{v.get('id')}",fs[0]['url']))
 return out
def run(c,msg):
 if subprocess.run(c,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE).returncode: raise RuntimeError(msg)
def main():
 p='''Create an original 54-second cinematic emotional text Reel. Style: intimate reflective quote video, direct-to-viewer writing, quiet recognition of hidden pressure, escalation, turning point, relief, memorable close. Do not copy creators or wording. No medical claims, diagnosis, crisis language, emojis, or cliche "you are not alone". Return JSON: title,description,hashtags,scenes. Exactly 9 scenes. Each scene has text (4-12 words) and search (concrete visible stock-video query). Scene 1 is a 4-8 word hook. Scene 9 is the closing thought. Text must fit 1-2 short lines and be readable in 3-5 seconds.'''
 d=ai(p); scenes=d.get('scenes')
 if not isinstance(scenes,list) or len(scenes)!=N: raise RuntimeError('Need exactly 9 scenes')
 (OUT/'script.json').write_text(json.dumps(d,indent=2,ensure_ascii=False),encoding='utf-8'); used=set(); rendered=[]
 for i,s in enumerate(scenes,1):
  cand=[x for x in search(s['search']) if x[0] not in used]
  if not cand: raise RuntimeError(f'No stock VIDEO for scene {i}')
  sid,url=random.choice(cand[:8]); used.add(sid); raw=OUT/f'raw_{i}.mp4'; out=OUT/f'scene_{i}.mp4'; txt=OUT/f'text_{i}.txt'
  with requests.get(url,stream=True,timeout=(15,60)) as r:
   r.raise_for_status(); f=open(raw,'wb'); [f.write(b) for b in r.iter_content(1024*1024) if b]; f.close()
  words=str(s['text']).split(); text=(' '.join(words[:len(words)//2])+'\\n'+' '.join(words[len(words)//2:])) if len(words)>7 else str(s['text']); txt.write_text(text,encoding='utf-8')
  vf="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,eq=brightness=-0.03:saturation=0.90,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf:textfile='"+str(txt)+"':fontcolor=white:fontsize=56:line_spacing=10:x=(w-text_w)/2:y=h*0.61-text_h/2:shadowcolor=black@0.55:shadowx=1:shadowy=2"
  run(['ffmpeg','-y','-hide_banner','-loglevel','error','-stream_loop','-1','-i',str(raw),'-t',str(SEC),'-vf',vf,'-an','-r','30','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p',str(out)],f'Scene {i} failed'); rendered.append(out)
 manifest=OUT/'concat.txt';manifest.write_text('\n'.join("file '"+p.as_posix()+"'" for p in rendered),encoding='utf-8'); silent=OUT/'silent.mp4'
 run(['ffmpeg','-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(manifest),'-c','copy',str(silent)],'Concat failed')
 music=download_music(d,str(OUT));
 if not music: raise RuntimeError('No music in assets/music')
 final=OUT/'final.mp4';run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(silent),'-stream_loop','-1','-i',str(music),'-filter_complex','[1:a]volume=0.28,afade=t=in:st=0:d=1.2,afade=t=out:st=51:d=3[a]','-map','0:v:0','-map','[a]','-t','54','-c:v','copy','-c:a','aac','-b:a','160k','-movflags','+faststart',str(final)],'Music mix failed')
 cfg=yaml.safe_load(Path('config.yaml').read_text());cfg.setdefault('seo',{})['hashtags']=d.get('hashtags',[]);cfg.setdefault('upload',{})['privacy_status']=os.getenv('EMOTIONAL_REEL_PRIVACY','public')
 yt=upload_video(str(final),d['title'],d['description'],cfg,engagement_comment=scenes[-1]['text']);social=publish_social_reels(str(final),d['title'],d['description'],cfg,str(OUT))
 (OUT/'publish_state.json').write_text(json.dumps({'status':'uploaded','video_id':yt,'social':social,'created_at':int(time.time())},indent=2),encoding='utf-8');print('EMOTIONAL_REEL_PUBLISHED',yt);print(json.dumps(social,indent=2))
if __name__=='__main__': main()