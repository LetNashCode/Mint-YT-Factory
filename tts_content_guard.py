"""Hard verification that generated Publish Shorts audio contains the full script."""
from __future__ import annotations
import contextlib, json, re, traceback, wave
from pathlib import Path
import torch
import whisper
from whisper.audio import SAMPLE_RATE, N_SAMPLES, log_mel_spectrogram, pad_or_trim
from whisper.decoding import DecodingOptions

MODEL_NAME="base.en"
RETRY_MODEL_NAME="tiny.en"
MIN_COVERAGE=0.90
MIN_SCENE_COVERAGE=0.80
MAX_MISSING_RUN=7
DECODE_WINDOW_SECONDS=30.0
DECODE_OVERLAP_SECONDS=2.0
_model=None
_retry_model=None
_WORD_RE=re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")


def _get_model(name):
    global _model,_retry_model
    if name==RETRY_MODEL_NAME:
        if _retry_model is None: _retry_model=whisper.load_model(name)
        return _retry_model
    if _model is None: _model=whisper.load_model(name)
    return _model


def _expected(script_path):
    data=json.loads(Path(script_path).read_text(encoding="utf-8")); scenes=data.get("scene_plan") or []
    return [[w.lower() for w in _WORD_RE.findall(str(s.get("narration") or ""))] for s in scenes if isinstance(s,dict)]


def _decode_window(model,audio,start_sample,end_sample):
    segment=pad_or_trim(audio[start_sample:end_sample],N_SAMPLES)
    mel=log_mel_spectrogram(segment,model.dims.n_mels)
    options=DecodingOptions(language="en",task="transcribe",temperature=0.0,beam_size=1,best_of=None,without_timestamps=True,fp16=False,suppress_tokens="-1")
    result=model.decode(mel.to(model.device),options)
    return str(getattr(result,"text","") or "").strip()


def _direct_decode(model,audio_path):
    audio=whisper.load_audio(str(audio_path)); total=len(audio)
    if total<=0: return ""
    window=int(DECODE_WINDOW_SECONDS*SAMPLE_RATE); overlap=int(DECODE_OVERLAP_SECONDS*SAMPLE_RATE); step=max(1,window-overlap)
    texts=[]; start=0
    while start<total:
        end=min(total,start+window); text=_decode_window(model,audio,start,end)
        if text: texts.append(text)
        if end>=total: break
        start+=step
    return " ".join(texts).strip()


def _observed_text(text): return [w.lower() for w in _WORD_RE.findall(str(text or ""))]


def _norm(word):
    word=re.sub(r"[^a-z0-9]+","",str(word).lower())
    if word.endswith("'s"): word=word[:-2]
    return word


def _align(expected,observed):
    """Return LCS word indexes without the previous backtracking boundary bug."""
    n,m=len(expected),len(observed)
    if not n or not m: return set()
    prev=[0]*(m+1)
    rows=[]
    for i in range(n):
        cur=[0]*(m+1); a=_norm(expected[i])
        for j in range(m):
            b=_norm(observed[j])
            if a and a==b: cur[j+1]=prev[j]+1
            else: cur[j+1]=max(prev[j+1],cur[j])
        rows.append(cur); prev=cur
    matched=set(); i,j=n,m
    while i>0 and j>0:
        if _norm(expected[i-1]) and _norm(expected[i-1])==_norm(observed[j-1]) and rows[i-1][j-1]+1==rows[i-1][j-1]+1 and rows[i][j]==rows[i-1][j-1]+1:
            matched.add(i-1); i-=1; j-=1
        elif rows[i-1][j]>=rows[i][j-1]: i-=1
        else: j-=1
    return matched


def verify_narration(audio_path:str,script_path:str,*,log_prefix="🎙️"):
    scenes=_expected(script_path); expected=[w for scene in scenes for w in scene]
    if not expected: raise RuntimeError("Narration content gate: script contains no expected words.")
    best=set(); observed_count=0; best_model=None
    for name in (MODEL_NAME,RETRY_MODEL_NAME):
        try:
            transcript=_direct_decode(_get_model(name),audio_path); observed=_observed_text(transcript); matched=_align(expected,observed)
            if len(matched)>len(best): best,observed_count,best_model=matched,len(observed),name
            coverage=len(matched)/max(1,len(expected)); print(f"{log_prefix} Whisper {name}: observed={len(observed)} words | matched={len(matched)} ({coverage:.0%})")
            if coverage>=MIN_COVERAGE: break
        except Exception as exc:
            print(f"⚠️ Narration content check {name} failed: {type(exc).__name__}: {exc}"); traceback.print_exc()
    missing=[i for i in range(len(expected)) if i not in best]; longest_run=0; current=0
    for i in range(len(expected)):
        if i in best: current=0
        else: current+=1; longest_run=max(longest_run,current)
    scene_results=[]; cursor=0
    for number,scene_words in enumerate(scenes,1):
        hits=sum(1 for i in range(cursor,cursor+len(scene_words)) if i in best); coverage=hits/max(1,len(scene_words))
        scene_results.append({"scene":number,"expected_words":len(scene_words),"matched_words":hits,"coverage":round(coverage,4)}); cursor+=len(scene_words)
    coverage=len(best)/max(1,len(expected)); bad_scenes=[x for x in scene_results if x["coverage"]<MIN_SCENE_COVERAGE]; passed=coverage>=MIN_COVERAGE and longest_run<=MAX_MISSING_RUN and not bad_scenes
    print(f"{log_prefix} CONTENT CHECK: {len(best)}/{len(expected)} words matched ({coverage:.0%}) | longest missing run={longest_run} | model={best_model or 'none'}")
    for item in scene_results: print(f"   Scene {item['scene']}: {item['matched_words']}/{item['expected_words']} ({item['coverage']:.0%})")
    if not passed:
        missing_words=" ".join(expected[i] for i in missing[:20])
        raise RuntimeError(f"Narration content verification failed: coverage={coverage:.1%}, longest_missing_run={longest_run}, bad_scenes={[x['scene'] for x in bad_scenes]}, missing_sample={missing_words!r}")
    return {"passed":True,"coverage":coverage,"longest_missing_run":longest_run,"scene_results":scene_results,"observed_words":observed_count,"model":best_model}
