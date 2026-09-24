import json,os,random,re,subprocess,time
from pathlib import Path
import requests,yaml
from google import genai
from google.genai import types
from music import download_music
from tts import synthesize_narration
from upload_youtube import upload_video
from social_publish import publish_social_reels
from moviepy.editor import VideoFileClip, CompositeVideoClip
from whisper_align import transcribe
import assemble as caption_style

OUT=Path('output/emotional_reel');OUT.mkdir(parents=True,exist_ok=True);N=9;SEC=6
RESUME_STATE=OUT/'resume_state.json'

def _file_sha256(path):
 import hashlib
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
 return h.hexdigest()

def _load_pending_resume():
 if not RESUME_STATE.exists(): return None
 try:
  state=json.loads(RESUME_STATE.read_text(encoding='utf-8'))
  if state.get('status')!='pending_upload': return None
  final=Path(state.get('final_path',''))
  if not final.exists() or final.stat().st_size<4096: return None
  return state
 except Exception as error:
  print(f'⚠️ Emotional Reel resume state ignored: {type(error).__name__}: {error}',flush=True)
  return None

def _write_resume_state(state):
 RESUME_STATE.write_text(json.dumps(state,indent=2,ensure_ascii=False),encoding='utf-8')

def _resume_and_upload(state):
 print('♻️ RESUMING EXISTING RENDER — skipping generation and re-encoding',flush=True)
 final=Path(state['final_path'])
 probe=subprocess.run(['ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=codec_name,duration','-of','json',str(final)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 if probe.returncode:
  raise RuntimeError(f'Resumed Emotional Reel audio probe failed: {probe.stderr.strip()}')
 streams=json.loads(probe.stdout).get('streams') or []
 if not streams or float(streams[0].get('duration') or 0)<5.0:
  raise RuntimeError('Cached Emotional Reel has no usable audio; refusing to upload it.')
 final_hash=_file_sha256(final)
 if state.get('final_sha256') and state['final_sha256']!=final_hash:
  raise RuntimeError('Cached Emotional Reel hash does not match resume state; refusing to reuse it.')
 cfg=yaml.safe_load(Path('config.yaml').read_text())
 cfg['seo']['hashtags']=state.get('hashtags',[])
 cfg.setdefault('upload',{})['privacy_status']=os.getenv('EMOTIONAL_REEL_PRIVACY','public')
 yt=upload_video(str(final),state['title'],state['description'],cfg,engagement_comment=state.get('engagement_comment',''))
 social=publish_social_reels(str(final),state['title'],state['description'],cfg,str(OUT))
 state.update({'status':'uploaded','video_id':yt,'social':social,'uploaded_at':int(time.time())})
 _write_resume_state(state)
 print(f'♻️ RESUMED RENDER PUBLISHED | video_id={yt}',flush=True)
 print(json.dumps(social,indent=2))

def _is_quota_error(error):
 text=str(error or '').lower()
 return any(x in text for x in ('resource_exhausted','quota exceeded','generaterequestsperday','quota_id','rate limit','429'))
def _is_retryable_gemini_error(error):
 if _is_quota_error(error): return False
 text=str(error or '').lower()
 return any(x in text for x in ('client has been closed','cannot send a request','503','unavailable','high demand','deadline exceeded','timeout','temporarily','connection reset','connection aborted'))
def ai(p):
 k=os.getenv('GEMINI_API_KEY','')
 if not k: raise RuntimeError('GEMINI_API_KEY is required')
 model=os.getenv('EMOTIONAL_REEL_MODEL','gemini-flash-lite-latest')
 last=None
 for attempt in range(1,5):
  client=None
  try:
   client=genai.Client(api_key=k)
   r=client.models.generate_content(
    model=model,
    contents=p,
    config=types.GenerateContentConfig(
     temperature=.7,
     response_mime_type='application/json',
    ),
   )
   text=str(r.text or '').replace(chr(96)*3+'json','').replace(chr(96)*3,'').strip()
   if not text: raise RuntimeError('Gemini returned an empty response')
   return json.loads(text)
  except Exception as error:
   last=error
   if _is_quota_error(error):
    raise RuntimeError('GEMINI_QUOTA_DEFERRED: Gemini project/day quota is exhausted; emotional reel generation will resume on the next successful run.') from error
   if attempt>=4 or not _is_retryable_gemini_error(error):
    raise
   delay=min(20,2**attempt)
   print(f'⚠️ Gemini transient failure ({attempt}/4): {error}; retrying in {delay}s')
   time.sleep(delay)
 raise RuntimeError(f'Gemini generation failed: {last}')

def search(q):
 out=[];pk=os.getenv('PEXELS_API_KEY','');xb=os.getenv('PIXABAY_API_KEY','')
 if pk:
  r=requests.get('https://api.pexels.com/videos/search',params={'query':q,'orientation':'portrait','per_page':12},headers={'Authorization':pk},timeout=25)
  if r.ok:
   for v in r.json().get('videos',[]):
    fs=[x for x in v.get('video_files',[]) if x.get('link')];fs.sort(key=lambda x:-float(x.get('width') or 0))
    if fs:out.append((f"pexels:{v.get('id')}",fs[0]['link']))
 if xb:
  r=requests.get('https://pixabay.com/api/videos/',params={'key':xb,'q':q,'video_type':'film','per_page':12},timeout=25)
  if r.ok:
   for v in r.json().get('hits',[]):
    fs=sorted((v.get('videos') or {}).values(),key=lambda x:-float(x.get('width') or 0))
    if fs and fs[0].get('url'):out.append((f"pixabay:{v.get('id')}",fs[0]['url']))
 return out

def run(c,msg):
 p=subprocess.run(c,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 if p.returncode:
  cmd=' '.join(str(x) for x in c)
  err=(p.stderr or '').strip()
  print(f'\\n❌ {msg}\\nCommand: {cmd}\\nReturn code: {p.returncode}\\nFFmpeg stderr:\\n{err[-12000:]}',flush=True)
  raise RuntimeError(f'{msg}: {err[-1200:] or "ffmpeg returned a non-zero exit code"}')
 return p.stdout.strip()

def _word_count(text):
 return len(re.findall(r"\b[\w'-]+\b",str(text or '')))

def main():
 resume=_load_pending_resume()
 if resume:
  _resume_and_upload(resume)
  return

 p='''Create an original 54-second cinematic emotional Reel. Use intimate reflective quote-video pacing, but do not copy any creator or wording. The viewer should feel directly addressed. Build: immediate recognition, hidden pressure, escalation, turning point, relief, memorable close. No medical claims, diagnosis, crisis language, emojis, or "you are not alone" cliche.
Return JSON with title, description, hashtags and exactly 9 scenes.
Each scene has text (4-12 words) for the screen, narration (12-18 natural spoken words) that expands the same thought, and search (concrete visible stock-video query).
Scene 1 text is a 4-8 word hook. Scene 9 is a memorable closing thought.
Total narration should be about 120-145 words. Narration must flow as ONE continuous story, not nine disconnected quotes.
IMPORTANT: Every narration word you generate is production-critical. Do not omit, summarize, truncate, rewrite, compact, or otherwise remove any narration content after this JSON is accepted. The exact concatenated scene narration is the script that must be spoken in full.'''

 d=None;scenes=None;narration=''
 for attempt in range(1,9):
  candidate=ai(p);candidate_scenes=candidate.get('scenes')
  if not isinstance(candidate_scenes,list) or len(candidate_scenes)!=N:
   print(f'⚠️ Emotional Reel script attempt {attempt}/8 rejected: need exactly {N} scenes',flush=True);continue
  candidate_narration=' '.join(str(s.get('narration','')).strip() for s in candidate_scenes).strip()
  word_count=_word_count(candidate_narration)
  scene_counts=[_word_count(s.get('narration','')) for s in candidate_scenes]
  if 120 <= word_count <= 145 and all(12 <= n <= 18 for n in scene_counts):
   d,scenes,narration=candidate,candidate_scenes,candidate_narration
   print(f'✅ Complete narration script accepted: {word_count} words | scene counts={scene_counts}',flush=True)
   break
  print(f'⚠️ Emotional Reel script attempt {attempt}/8 rejected: total={word_count} words, scene counts={scene_counts}; requiring 120-145 total and 12-18 per scene',flush=True)

 if d is None:
  raise RuntimeError('Could not generate a valid full-length Emotional Reel narration after 8 bounded attempts. No narration was compacted or dropped.')

 (OUT/'script.json').write_text(json.dumps(d,indent=2,ensure_ascii=False),encoding='utf-8')
 (OUT/'narration.txt').write_text(narration,encoding='utf-8')
 used=set();rendered=[]
 for i,s in enumerate(scenes,1):
  cand=[x for x in search(s['search']) if x[0] not in used]
  if not cand:raise RuntimeError(f'No stock VIDEO for scene {i}')
  sid,url=random.choice(cand[:8]);used.add(sid);raw=OUT/f'raw_{i}.mp4';out=OUT/f'scene_{i}.mp4';txt=OUT/f'text_{i}.txt'
  with requests.get(url,stream=True,timeout=(15,60)) as r:
   r.raise_for_status()
   with open(raw,'wb') as f:
    for b in r.iter_content(1024*1024):
     if b:f.write(b)
  words=str(s['text']).split();text=(' '.join(words[:len(words)//2])+'\n'+' '.join(words[len(words)//2:])) if len(words)>7 else str(s['text']);txt.write_text(text,encoding='utf-8')
  vf="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,eq=brightness=-0.03:saturation=0.90"
  run(['ffmpeg','-y','-hide_banner','-loglevel','error','-stream_loop','-1','-i',str(raw),'-t',str(SEC),'-vf',vf,'-an','-r','30','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p',str(out)],f'Scene {i} failed');rendered.append(out)

 manifest=OUT/'concat.txt'
 for i,p in enumerate(rendered,1):
  if not p.exists() or p.stat().st_size < 4096:
   raise RuntimeError(f'Scene {i} output is missing or suspiciously small: {p}')
  probe=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=codec_name,width,height,pix_fmt,r_frame_rate','-show_entries','format=duration,size','-of','json',str(p)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  if probe.returncode:
   raise RuntimeError(f'Scene {i} is not a valid video: {p}\\nffprobe: {probe.stderr.strip()}')
  try:
   info=json.loads(probe.stdout); stream=(info.get('streams') or [])[0]; duration=float((info.get('format') or {}).get('duration') or 0); size=int((info.get('format') or {}).get('size') or 0)
  except Exception as e:
   raise RuntimeError(f'Scene {i} ffprobe returned invalid JSON: {e}')
  if not stream or stream.get('codec_name')!='h264' or int(stream.get('width') or 0)!=1080 or int(stream.get('height') or 0)!=1920 or duration < SEC-0.15 or size < 4096:
   raise RuntimeError(f'Scene {i} has unexpected media properties: {probe.stdout}')
  print(f'✅ Scene {i} validated: {duration:.2f}s {stream.get("codec_name")} {stream.get("width")}x{stream.get("height")} {stream.get("pix_fmt")}',flush=True)

 manifest.write_text('\n'.join("file '"+p.resolve().as_posix().replace("'","'\\\\''")+"'" for p in rendered)+'\n',encoding='utf-8')
 print(f'🎬 Concatenating {len(rendered)} validated scenes',flush=True)
 print(manifest.read_text(encoding='utf-8'),flush=True)
 silent=OUT/'silent.mp4'
 try:
  run(['ffmpeg','-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(manifest),'-c','copy','-movflags','+faststart',str(silent)],'Concat stream-copy failed')
 except RuntimeError as first_error:
  print(f'⚠️ Stream-copy concat failed; retrying with normalized re-encode: {first_error}',flush=True)
  run(['ffmpeg','-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(manifest),'-an','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-r','30','-movflags','+faststart',str(silent)],'Concat re-encode failed')
 if not silent.exists() or silent.stat().st_size < 4096:
  raise RuntimeError(f'Concat produced no usable output: {silent}')
 print(f'✅ Silent reel assembled: {silent.stat().st_size} bytes',flush=True)

 cfg=yaml.safe_load(Path('config.yaml').read_text());cfg['voice']=dict(cfg.get('voice') or {});cfg['voice'].update({'provider':'kokoro','voice_name':os.getenv('EMOTIONAL_REEL_KOKORO_VOICE','am_echo'),'kokoro_lang':'a','speed':float(os.getenv('EMOTIONAL_REEL_KOKORO_SPEED','0.92'))})
 os.environ['MINT_TTS_PROVIDER']='kokoro'
 narration_audio=OUT/'narration.mp3'
 # Use the full 54-second reel as the hard narration budget. TTS may speed up
 # the complete script, but it must never truncate or drop its ending.
 synthesize_narration(narration,cfg,str(narration_audio),target_duration=53.5)

 music=download_music(d,str(OUT))
 if not music:raise RuntimeError('No music in assets/music')
 final=OUT/'final.mp4'

 probe=subprocess.run(['ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=codec_name,duration,sample_rate','-of','json',str(narration_audio)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 if probe.returncode:
  raise RuntimeError(f'Voice narration ffprobe failed: {probe.stderr.strip()}')
 try:
  audio_info=json.loads(probe.stdout); audio_stream=(audio_info.get('streams') or [])[0]; voice_duration=float(audio_stream.get('duration') or 0)
 except Exception as e:
  raise RuntimeError(f'Voice narration probe returned invalid data: {e}')
 if not audio_stream or voice_duration < 5.0:
  raise RuntimeError(f'Voice narration missing or too short: {probe.stdout}')
 if voice_duration > 53.5:
  raise RuntimeError(f'Complete narration is {voice_duration:.2f}s after speed adaptation, which exceeds the 53.5s audio budget. Refusing to truncate the script.')
 print(f'🎙️ VOICE NARRATION VERIFIED | provider=Kokoro-82M | voice={cfg["voice"].get("voice_name")} | duration={voice_duration:.2f}s | COMPLETE_SCRIPT_PRESERVED=YES',flush=True)

 print('🌈 BUILDING EMOTIONAL REEL CAPTIONS — SHARED MINT STYLE',flush=True)
 words=transcribe(str(narration_audio))
 if not words:
  raise RuntimeError('Whisper returned no usable narration timings for Emotional Reel captions')
 video=VideoFileClip(str(silent),audio=False); captioned=None; caption_clips=[]
 try:
  frame_size=(int(video.w),int(video.h)); total_duration=min(54.0,float(video.duration))
  scene_ranges=[{'start':i*SEC,'end':min((i+1)*SEC,total_duration),'scene':{'caption_highlights':[],'emphasis_word':''}} for i in range(N)]
  phrases=caption_style._build_caption_phrases(words)
  for phrase_index,phrase in enumerate(phrases):
   scene_index=caption_style._get_scene_index_for_time(scene_ranges,phrase['start'])
   scene=scene_ranges[scene_index]['scene']
   fontsize,color=caption_style._caption_style(scene_index,scene,phrase,phrase_index)
   position=caption_style.caption_position(frame_size)
   text_clip=caption_style._make_caption_clip(phrase['text'],fontsize,color,frame_size).set_start(phrase['start']).set_duration(phrase['duration']).set_position(position)
   shadow_clip=caption_style._make_caption_shadow(phrase['text'],fontsize,frame_size).set_start(phrase['start']).set_duration(phrase['duration']).set_position(('center',position[1]+caption_style.CAPTION_SHADOW_OFFSET)).set_opacity(caption_style.CAPTION_SHADOW_OPACITY)
   caption_clips.extend([shadow_clip,text_clip])
  captioned=CompositeVideoClip([video]+caption_clips,size=frame_size).set_duration(total_duration)
  captioned_path=OUT/'captioned.mp4'
  captioned.write_videofile(str(captioned_path),fps=30,codec='libx264',audio=False,preset='fast',bitrate='8M',verbose=False,logger=None)
 finally:
  if captioned is not None:
   try: captioned.close()
   except Exception: pass
  try: video.close()
  except Exception: pass
  for clip in caption_clips:
   try: clip.close()
   except Exception: pass

 mix='[1:a]volume=0.12,afade=t=in:st=0:d=1.2,afade=t=out:st=51:d=3[m];[2:a]volume=1.0[n];[m][n]amix=inputs=2:duration=longest:dropout_transition=0,aresample=async=1:first_pts=0[mixout]'
 run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(captioned_path),'-stream_loop','-1','-i',str(music),'-i',str(narration_audio),'-filter_complex',mix,'-map','0:v:0','-map','[mixout]','-t','54','-c:v','copy','-c:a','aac','-b:a','192k','-ac','2','-movflags','+faststart',str(final)],'Music and narration mix failed')
 if not final.exists() or final.stat().st_size < 4096:
  raise RuntimeError(f'Final Emotional Reel was not created by FFmpeg: {final}')
 final_probe=subprocess.run(['ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=codec_name,duration','-of','json',str(final)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 if final_probe.returncode:
  raise RuntimeError(f'Final Emotional Reel audio probe failed: {final_probe.stderr.strip()}')
 final_audio=json.loads(final_probe.stdout).get('streams') or []
 final_audio_duration=float(final_audio[0].get('duration') or 0) if final_audio else 0.0
 if not final_audio or final_audio_duration < 5.0:
  raise RuntimeError('Final Emotional Reel has no usable audio track; upload blocked.')
 if final_audio_duration + 0.25 < voice_duration:
  raise RuntimeError(f'Final mix is shorter than the complete narration ({final_audio_duration:.2f}s final vs {voice_duration:.2f}s voice); upload blocked to prevent narration truncation.')
 print(f'✅ FINAL REEL AUDIO VERIFIED | complete voice narration + music | duration={final_audio_duration:.2f}s | COMPLETE_SCRIPT_PRESERVED=YES',flush=True)

 final_sha256=_file_sha256(final)
 resume_state={'status':'pending_upload','final_path':str(final),'final_sha256':final_sha256,'cache_key':f'emotional-reel-final-v2-{final_sha256[:32]}','title':d['title'],'description':d['description'],'hashtags':d.get('hashtags',[]),'engagement_comment':scenes[-1]['text'],'voice':cfg['voice'],'created_at':int(time.time()),'narration_word_count':_word_count(narration),'complete_script_preserved':True}
 _write_resume_state(resume_state)
 print(f'💾 RENDER CHECKPOINT SAVED | sha256={final_sha256[:16]} | cache_key={resume_state["cache_key"]}',flush=True)
 cfg['seo']['hashtags']=d.get('hashtags',[]);cfg.setdefault('upload',{})['privacy_status']=os.getenv('EMOTIONAL_REEL_PRIVACY','public')
 try:
  yt=upload_video(str(final),d['title'],d['description'],cfg,engagement_comment=scenes[-1]['text'])
  social=publish_social_reels(str(final),d['title'],d['description'],cfg,str(OUT))
 except Exception:
  print('⚠️ Upload failed AFTER render checkpoint. The next run will reuse final.mp4.',flush=True)
  raise
 resume_state.update({'status':'uploaded','video_id':yt,'social':social,'uploaded_at':int(time.time())})
 _write_resume_state(resume_state)
 print('EMOTIONAL_REEL_PUBLISHED',yt);print(json.dumps(social,indent=2))

if __name__=='__main__':main()
