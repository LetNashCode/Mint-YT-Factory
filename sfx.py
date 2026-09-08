"""Narration-aware, fun SFX director for Mint-YT-Factory.

SFX are selected from the *meaning and beat* of each scene rather than literal
keyword matches. Voice remains dominant, effects are short and restrained, and
Scene 7 is reserved for the clean continuation teaser.
"""
from __future__ import annotations
import hashlib, math, os, random, re, struct, wave
from sfx_assets import ensure_sfx_assets

SAMPLE_RATE = 44100
DEFAULT_SCENE_DURATIONS = (3, 5, 7, 7, 8, 8, 7)
DEFAULTS = ("pop", "boing", "reveal", "bruh", "glitch", "whoosh", "none")

# Ordered by intent. A literal word such as "crack" no longer automatically
# produces an impact: context has to indicate surprise/impact.
RULES = [
 ("record_scratch", ("but here's", "but here is", "wait", "hold on", "actually", "turns out", "except")),
 ("crowd_gasp", ("no way", "can't believe", "cannot believe", "insane", "shocking", "unexpected")),
 ("dramatic_reveal", ("the answer", "the secret", "here's why", "here is why", "the weird part", "the truth", "mystery")),
 ("cartoon_boing", ("weird", "quirky", "odd", "pruney", "bouncy", "squishy", "funny")),
 ("windows_error", ("doesn't make sense", "does not make sense", "impossible", "wrong", "confusing")),
 ("sad_trombone", ("oops", "failed", "bad news", "unfortunately")),
 ("airhorn", ("finally", "big reveal", "there it is", "winner")),
]

def _clean(x): return " ".join(str(x or "").split()).lower().strip()

def _text(scene):
    return _clean(" ".join(str(scene.get(k,"")) for k in ("narration","spoken_beat","physical_action","visual_action")))

def _duration(scene,index):
    try: return max(.2,float(scene.get("duration_seconds",scene.get("duration"))))
    except Exception: return float(DEFAULT_SCENE_DURATIONS[index])

def _beat(scene,duration):
    text=_text(scene); words=re.findall(r"\b[\w'-]+\b",text)
    if not words:return max(.2,duration*.62)
    triggers=("but here's","wait","actually","turns out","here's why","the answer","finally","suddenly","no way","weird part")
    positions=[len(re.findall(r"\b[\w'-]+\b",text[:text.find(t)])) for t in triggers if t in text]
    ratio=min(positions)/max(1,len(words)) if positions else .62
    return max(.20,min(duration-.20,duration*max(.22,min(.84,ratio))))

def _category(scene,index):
    text=_text(scene)
    cue=scene.get("sfx_cue")
    if isinstance(cue,dict) and cue.get("category") and cue.get("category") not in ("none","auto"): return str(cue["category"])
    for category, phrases in RULES:
        if any(p in text for p in phrases): return category
    # Scene-position rhythm is intentionally subtle, not a random loud meme.
    return DEFAULTS[index]

def _procedural(kind):
    def env(i,n,a=.025,r=.25):
        t=i/max(1,n); return min(1.,t/max(.001,a),(1-t)/max(.001,r))
    def tone(freq,dur,vol=.3,decay=5,slide=0):
        n=max(1,int(dur*SAMPLE_RATE)); phase=0.; out=[]
        for i in range(n):
            phase += 2*math.pi*max(30,freq+slide*i/max(1,n-1))/SAMPLE_RATE
            out.append(32767*vol*env(i,n)*math.exp(-decay*i/SAMPLE_RATE)*math.sin(phase))
        return out
    def noise(dur,vol=.12,decay=7,seed=17):
        rng=random.Random(seed); n=max(1,int(dur*SAMPLE_RATE))
        return [32767*vol*env(i,n)*math.exp(-decay*i/SAMPLE_RATE)*rng.uniform(-1,1) for i in range(n)]
    if kind=="pop": return tone(720,.11,.22,18,220)
    if kind=="boing": return tone(180,.30,.25,5,600)
    if kind=="reveal": return tone(260,.38,.22,3,650)
    if kind=="whoosh": return noise(.30,.16,5,41)
    if kind=="glitch": return noise(.16,.18,14,73)
    if kind=="record_scratch": return noise(.22,.22,12,33)
    if kind=="crowd_gasp": return noise(.28,.16,5,61)
    if kind=="windows_error": return [*tone(780,.08,.18,10),*([0]*int(.05*SAMPLE_RATE)),*tone(620,.12,.20,9)]
    if kind=="sad_trombone": return tone(330,.48,.20,3,-170)
    if kind=="airhorn": return tone(440,.28,.22,2,20)
    if kind=="dramatic_reveal": return tone(210,.42,.22,2,800)
    return [0.0]*int(.05*SAMPLE_RATE)

def _write_wav(path,samples):
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with wave.open(path,"wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(struct.pack("<h",max(-32767,min(32767,int(x)))) for x in samples))

def generate_sfx(script,output_dir):
    scenes=script.get("scene_plan",[]) if isinstance(script,dict) else []
    if len(scenes)!=7: raise RuntimeError("SFX generation requires exactly 7 scenes.")
    os.makedirs(output_dir,exist_ok=True)
    library=ensure_sfx_assets(); paths=[]; plan=[]
    print("="*80); print("🎭 NARRATION-AWARE FUN SFX DIRECTOR"); print("="*80)
    for i,scene in enumerate(scenes):
        if i==6:
            path=os.path.join(output_dir,"scene_7_continuation_silent.wav")
            if not os.path.exists(path): _write_wav(path,[0.0]*int(.05*SAMPLE_RATE))
            cue={"enabled":False,"type":"none","category":"none","source":"disabled_for_continuation","at_ms":0,"intensity":"none","voice_priority":"absolute"}
        else:
            category=_category(scene,i); duration=_duration(scene,i); at=int(_beat(scene,duration)*1000)
            candidates=library.get(category,[]); path=None; source="procedural_meme_stinger"
            if candidates:
                digest=hashlib.sha1(f"{script.get('topic','')}:{i}:{category}".encode()).hexdigest(); path=candidates[int(digest[:8],16)%len(candidates)]; source="local_meme_clip"
            if not path:
                path=os.path.join(output_dir,f"scene_{i+1}_{category}.wav"); _write_wav(path,_procedural(category))
            # Keep reactions short enough that speech is always dominant.
            cue={"enabled":True,"type":category,"category":category,"source":source,"at_ms":at,"timing":"narration_semantic_beat","meme_only":True,"intensity":"low" if category in ("pop","whoosh","glitch","boing") else "medium","voice_priority":"absolute"}
        scene["sfx_cue"]=cue; paths.append(path); plan.append({"scene":i+1,**cue})
        print(f"Scene {i+1}: {cue['category']} [{cue['source']}] @ {cue['at_ms']}ms")
    script["sfx_plan"]=plan; script["sfx_mode"]="narration_aware_fun"
    return paths

def prepare_real_sfx(script):
    # Keep compatibility with callers that expect a seven-item list.
    library=ensure_sfx_assets(); result=[]
    for i,scene in enumerate(script.get("scene_plan",[])):
        if i==6: result.append(None); continue
        category=_category(scene,i); candidates=library.get(category,[])
        result.append(candidates[0] if candidates else None)
    return result
