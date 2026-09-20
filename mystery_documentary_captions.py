"""Burn Whisper-timed documentary subtitles with keyword emphasis."""
from __future__ import annotations
import argparse, json, re, subprocess
from pathlib import Path
import whisper

def atime(value):
    cs=max(0,int(round(float(value)*100))); h,cs=divmod(cs,360000); m,cs=divmod(cs,6000); s,cs=divmod(cs,100); return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
def esc(value): return str(value).replace('\\','\\\\').replace('{','\\{').replace('}','\\}')
def main():
    p=argparse.ArgumentParser(); p.add_argument('--input',required=True); p.add_argument('--output',required=True); p.add_argument('--keywords',required=True); a=p.parse_args()
    source=Path(a.input); output=Path(a.output); wav=output.with_suffix('.wav'); ass=output.with_suffix('.ass')
    subprocess.run(['ffmpeg','-y','-i',str(source),'-vn','-ac','1','-ar','16000',str(wav)],check=True)
    data=json.loads(Path(a.keywords).read_text(encoding='utf-8'))
    keyword_list=data.get('highlighted_keywords',[]) if isinstance(data,dict) else data
    words={re.sub(r'[^a-z0-9]+','',str(item).lower()) for item in keyword_list}
    result=whisper.load_model('base.en').transcribe(str(wav),language='en',word_timestamps=True,fp16=False,verbose=False)
    events=[]
    for seg in result.get('segments',[]):
        for word in seg.get('words',[]):
            text=str(word.get('word','')).strip()
            if not text: continue
            key=re.sub(r'[^a-z0-9]+','',text.lower()) in words
            body='{\\\\c&H66CCFF&\\b1}'+esc(text)+'{\\\\c&HFFFFFF&\\b0}' if key else esc(text)
            events.append((float(word.get('start',seg.get('start',0))),float(word.get('end',seg.get('end',0.2))),body))
    header='''[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Documentary,Arial,46,&H00FFFFFF,&H00FFFFFF,&H00101010,&H99000000,0,0,0,0,100,100,0,0,1,3,1,2,80,80,70,1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n'''
    ass.write_text(header+'\n'.join(f'Dialogue: 0,{atime(s)},{atime(max(e,s+0.15))},Documentary,,0,0,0,,{t}' for s,e,t in events)+'\n',encoding='utf-8')
    subprocess.run(['ffmpeg','-y','-i',str(source),'-vf',f'ass={ass}','-c:a','copy',str(output)],check=True)
    wav.unlink(missing_ok=True); ass.unlink(missing_ok=True); print(f'MYSTERY_DOCUMENTARY_CAPTIONS_OUTPUT={output}')
if __name__=='__main__': main()
