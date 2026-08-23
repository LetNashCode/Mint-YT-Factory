"""Robust word timing for Mint-YT-Factory.

Whisper remains the timing authority. When Whisper cannot align the TTS audio
reliably, we fail over to deterministic script timing instead of killing the
whole video build. This is preferable to publishing a video with no captions.
"""
from __future__ import annotations
import json,os,re
import whisper
WHISPER_MODEL_NAME="tiny.en"; WHISPER_RETRY_MODEL_NAME="base.en"; _model=None; _retry_model=None
_WORD_RE=re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")
def _get_model(name=WHISPER_MODEL_NAME):
    global _model,_retry_model
    if name==WHISPER_RETRY_MODEL_NAME:
        if _retry_model is None: print(f"🎙️ Loading Whisper retry model: {name}"); _retry_model=whisper.load_model(name); print(f"✅ Whisper retry model ready: {name}")
        return _retry_model
    if _model is None: print(f"🎙️ Loading Whisper model: {name}"); _model=whisper.load_model(name); print(f"✅ Whisper model ready: {name}")
    return _model
def _clean_word(v):return re.sub(r"[^a-z0-9'’-]+","",str(v or "").lower()).strip()
def _load_expected_words(audio_path):
    try:
        run_dir=os.path.dirname(os.path.dirname(os.path.abspath(audio_path))); p=os.path.join(run_dir,"script.json")
        with open(p,"r",encoding="utf-8") as h:s=json.load(h)
        text=" ".join(str(x.get("narration","") ) for x in s.get("scene_plan",[]) if isinstance(x,dict)); return _WORD_RE.findall(text)
    except Exception:return []
def _extract_whisper_words(result):
    out=[]
    for seg in result.get("segments",[]) or []:
        ss=max(0.,float(seg.get("start",0.))); se=max(ss+.05,float(seg.get("end",ss+.05)))
        for item in seg.get("words") or []:
            if not isinstance(item,dict):continue
            word=str(item.get("word","")).strip()
            if not word:continue
            try:
                st=max(ss,float(item.get("start",ss))); en=min(se,max(st+.04,float(item.get("end",st+.04))))
                out.append({"word":word,"start":st,"end":en})
            except Exception:continue
    return sorted(out,key=lambda x:(x["start"],x["end"]))
def _finalize_words(words):
    out=[];prev=0.
    for x in words:
        st=max(0.,float(x["start"]));en=max(st+.04,float(x["end"]));
        if st<prev:st=prev;en=max(st+.04,en)
        out.append({"word":str(x["word"]).strip(),"start":st,"end":en});prev=en
    return out
def _alignment(expected,observed):
    if not observed:return [],0.
    if not expected:return _finalize_words(observed),1.
    n,m=len(expected),len(observed);dp=[[0]*(m+1) for _ in range(n+1)]
    for i in range(n):
        a=_clean_word(expected[i])
        for j in range(m):
            b=_clean_word(observed[j]["word"]);match=3 if a==b else(-.5 if len(a)>=4 and len(b)>=4 and a[:4]==b[:4] else -2)
            dp[i+1][j+1]=max(dp[i][j+1]-1,dp[i+1][j]-1,dp[i][j]+match)
    pairs=[];i,j=n,m
    while i and j:
        a=_clean_word(expected[i-1]);b=_clean_word(observed[j-1]["word"]);match=3 if a==b else(-.5 if len(a)>=4 and len(b)>=4 and a[:4]==b[:4] else -2);score=dp[i][j]
        if score==dp[i-1][j-1]+match:
            if a==b or(len(a)>=4 and len(b)>=4 and a[:4]==b[:4]):pairs.append((i-1,j-1))
            i-=1;j-=1
        elif score==dp[i-1][j]-1:i-=1
        else:j-=1
    pairs.reverse();mapped=[{"word":expected[a],"start":observed[b]["start"],"end":observed[b]["end"]} for a,b in pairs]
    return _finalize_words(mapped),len(mapped)/float(max(1,n))
def _transcribe(model,audio_path,strong=False):
    # Do NOT feed the entire expected script as initial_prompt. It can bias Whisper
    # into hallucinating/rejecting expressive neural TTS and was the main cause of
    # the 2% alignment seen in production.
    return model.transcribe(audio_path,language="en",task="transcribe",word_timestamps=True,fp16=False,temperature=0,best_of=3 if strong else 1,beam_size=5 if strong else 1,condition_on_previous_text=False,compression_ratio_threshold=2.8,logprob_threshold=-1.2,no_speech_threshold=0.35,initial_prompt=None,verbose=False)
def _proportional_words(expected,duration):
    if not expected:return []
    # Deterministic fallback: allocate time by character weight, with a small
    # punctuation pause effect. This keeps every caption on screen and in order.
    weights=[]
    for w in expected:
        weights.append(max(1.0,len(re.sub(r"[^A-Za-z]","",w))*0.82 + (0.8 if w[-1:] in ".!?" else 0)))
    total=sum(weights) or 1.;cursor=0.;out=[]
    for w,weight in zip(expected,weights):
        span=duration*weight/total;st=cursor;en=min(duration,st+span);out.append({"word":w,"start":st,"end":max(st+.05,en)});cursor=en
    return _finalize_words(out)
def transcribe(audio_path):
    print("🎙️ Starting WORD-ACCURATE Whisper caption timing");print(f"   Model: {WHISPER_MODEL_NAME} → retry: {WHISPER_RETRY_MODEL_NAME}");print(f"   Audio: {audio_path}");print("   Word timestamps: ENABLED")
    expected=_load_expected_words(audio_path)
    result=_transcribe(_get_model(),audio_path,False);observed=_extract_whisper_words(result);words,coverage=_alignment(expected,observed);print(f"🔎 Whisper alignment pass 1: {len(words)}/{len(expected)} words ({coverage:.0%})")
    if coverage<.85:
        print("⚠️ Whisper coverage below 85%; retrying with base.en + clean decoding")
        result=_transcribe(_get_model(WHISPER_RETRY_MODEL_NAME),audio_path,True);observed=_extract_whisper_words(result);words,coverage=_alignment(expected,observed);print(f"🔎 Whisper alignment pass 2: {len(words)}/{len(expected)} words ({coverage:.0%})")
    if coverage>=.70 and words:
        if coverage<.85:print(f"⚠️ Caption alignment coverage: {coverage:.0%}; using matched Whisper timings only")
        print(f"✅ Word-accurate caption timing complete: {len(words)} matched words");return words
    # Never crash the production render because a neural TTS voice defeats Whisper.
    # If Whisper returned some trustworthy matches, preserve them; otherwise use
    # deterministic timing for the script so the video still completes.
    try:
        import wave,contextlib
        with contextlib.closing(wave.open(audio_path,"rb")) as wf:duration=wf.getnframes()/float(wf.getframerate())
    except Exception:
        try:
            from moviepy.editor import AudioFileClip
            clip=AudioFileClip(audio_path);duration=float(clip.duration);clip.close()
        except Exception:duration=36.
    print(f"⚠️ Whisper alignment unreliable ({coverage:.0%}). Falling back to deterministic word timing for {duration:.2f}s.")
    fallback=_proportional_words(expected,duration)
    if not fallback:raise RuntimeError("Caption timing produced no words.")
    print(f"✅ Caption fallback complete: {len(fallback)} script words timed across {duration:.2f}s")
    print("⚠️ Timing source: deterministic script timing because Whisper coverage was unusable")
    return fallback
