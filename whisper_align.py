"""TTS-locked word timing for Mint-YT-Factory.

The final narration audio is authoritative. Whisper is used only to locate
reliable word anchors; the exact script text remains authoritative for captions.
"""
from __future__ import annotations
import contextlib, json, os, re, wave
import whisper

WHISPER_MODEL_NAME = "base.en"
WHISPER_RETRY_MODEL_NAME = "tiny.en"
_model = None
_retry_model = None
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")

def _get_model(name=WHISPER_MODEL_NAME):
    global _model, _retry_model
    if name == WHISPER_RETRY_MODEL_NAME:
        if _retry_model is None: _retry_model = whisper.load_model(name)
        return _retry_model
    if _model is None: _model = whisper.load_model(name)
    return _model

def _load_expected_words(audio_path):
    run_dir = os.path.dirname(os.path.dirname(os.path.abspath(audio_path)))
    script_path = os.path.join(run_dir, "script.json")
    try:
        with open(script_path, "r", encoding="utf-8") as f: script = json.load(f)
        text = " ".join(str(s.get("narration", "")) for s in script.get("scene_plan", []) if isinstance(s, dict))
        return _WORD_RE.findall(text)
    except Exception as error:
        print(f"⚠️ Could not load expected narration words: {error}")
        return []

def _audio_duration(path):
    try:
        with contextlib.closing(wave.open(path, "rb")) as w: return w.getnframes()/float(w.getframerate())
    except Exception:
        try:
            from moviepy.editor import AudioFileClip
            c=AudioFileClip(path); d=float(c.duration); c.close(); return d
        except Exception: return 36.0

def _transcribe(model, path, strong=False):
    return model.transcribe(path, language="en", task="transcribe", word_timestamps=True, fp16=False, temperature=0, best_of=3 if strong else 1, beam_size=5 if strong else 1, condition_on_previous_text=False, compression_ratio_threshold=2.8, logprob_threshold=-1.2, no_speech_threshold=0.35, initial_prompt=None, verbose=False)

def _observed(result):
    out=[]
    for seg in result.get("segments",[]) or []:
        ss=max(0.,float(seg.get("start",0))); se=max(ss+.05,float(seg.get("end",ss+.05)))
        for item in seg.get("words") or []:
            w=str(item.get("word","")).strip()
            if not w: continue
            try:
                st=max(ss,float(item.get("start",ss))); en=min(se,max(st+.04,float(item.get("end",st+.04))))
                out.append({"word":w,"start":st,"end":en})
            except Exception: pass
    return sorted(out,key=lambda x:(x["start"],x["end"]))

def _clean(w): return re.sub(r"[^a-z0-9'’-]+","",str(w or "").lower())

def _alignment(expected, observed):
    if not expected or not observed: return [],0.
    n,m=len(expected),len(observed); gap=-1; mismatch=-5; match=8
    dp=[[0]*(m+1) for _ in range(n+1)]
    for i in range(n):
        for j in range(m):
            same=_clean(expected[i])==_clean(observed[j]["word"]); score=match if same else mismatch
            dp[i+1][j+1]=max(dp[i][j+1]+gap,dp[i+1][j]+gap,dp[i][j]+score)
    pairs=[]; i,j=n,m
    while i and j:
        a=_clean(expected[i-1]); b=_clean(observed[j-1]["word"]); score=match if a==b else mismatch
        if dp[i][j]==dp[i-1][j-1]+score:
            if a==b: pairs.append((i-1,j-1))
            i-=1; j-=1
        elif dp[i][j]==dp[i-1][j]+gap: i-=1
        else: j-=1
    pairs.reverse()
    anchors=[{"expected_index":a,"word":expected[a],"start":observed[b]["start"],"end":observed[b]["end"]} for a,b in pairs]
    return anchors,len(anchors)/float(max(1,n))

def _word_weight(w):
    letters=len(re.sub(r"[^A-Za-z]","",w)); return max(1.,letters*.78+(0.55 if str(w).endswith((".","!","?")) else 0))

def _fill_gap(expected,left,right,left_time,right_time,out):
    if right<=left: return
    right_time=max(left_time,right_time); indexes=list(range(left,right)); weights=[_word_weight(expected[i]) for i in indexes]; total=sum(weights) or 1.; cursor=left_time; available=max(.025,right_time-left_time)
    for i,weight in zip(indexes,weights):
        span=max(.025,available*weight/total)
        out.append({"expected_index":i,"word":expected[i],"start":cursor,"end":min(right_time,cursor+span)}); cursor+=span

def _reconstruct(expected,anchors,duration):
    if not expected:return []
    if not anchors:
        out=[]; _fill_gap(expected,0,len(expected),0.,duration,out); return _finalize(out,duration)
    anchors=sorted(anchors,key=lambda x:x["expected_index"]); out=[]; first=anchors[0]
    _fill_gap(expected,0,first["expected_index"],0.,first["start"],out); out.append(first.copy())
    for a,b in zip(anchors,anchors[1:]):
        _fill_gap(expected,a["expected_index"]+1,b["expected_index"],a["end"],b["start"],out); out.append(b.copy())
    last=anchors[-1]; _fill_gap(expected,last["expected_index"]+1,len(expected),last["end"],duration,out); return _finalize(out,duration)

def _finalize(words,duration):
    ordered=sorted(words,key=lambda x:x.get("expected_index",0)); out=[]; previous=0.
    for index,item in enumerate(ordered):
        start=max(previous,min(duration,float(item["start"])))
        if index+1<len(ordered):
            # The next Whisper start is the caption boundary. Whisper end
            # timestamps are intentionally ignored because they frequently
            # arrive before the acoustic tail of the same spoken word.
            boundary=max(start+.025,min(duration,float(ordered[index+1]["start"])))
            end=boundary
        else:
            end=min(duration,max(start+.025,float(item["end"])))
        if start>=duration: start=max(0.,duration-.025); end=duration
        out.append({"word":str(item["word"]).strip(),"start":start,"end":max(start+.025,min(duration,end))}); previous=out[-1]["end"]
    return out

def transcribe(audio_path):
    expected=_load_expected_words(audio_path); duration=_audio_duration(audio_path)
    if not expected: raise RuntimeError("Caption timing could not load narration text from script.json.")
    best=[]; coverage=0.
    for name,strong in ((WHISPER_MODEL_NAME,True),(WHISPER_RETRY_MODEL_NAME,False)):
        try:
            anchors,cov=_alignment(expected,_observed(_transcribe(_get_model(name),audio_path,strong)))
            if cov>coverage: best,coverage=anchors,cov
            if cov>=.90: break
        except Exception as error: print(f"⚠️ Whisper {name} failed: {type(error).__name__}: {error}")
    timeline=_reconstruct(expected,best,duration)
    if len(timeline)!=len(expected): raise RuntimeError(f"Caption reconstruction failed: expected {len(expected)} words, got {len(timeline)}")
    print(f"✅ TTS-locked captions: {len(timeline)} exact script words; Whisper anchor coverage {coverage:.0%}; final audio {duration:.2f}s")
    return timeline
