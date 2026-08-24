"""Story-aware SFX selector.

Prefers real cached SFX downloaded by sfx_assets.py. Uses the original
commercial-safe FAAA/HUH reaction generator for genuinely comedic beats, and
falls back to the existing procedural effects when a real asset is unavailable.
"""
from __future__ import annotations
import os, math, random, struct, wave

SAMPLE_RATE=44100

try:
    from sfx_runtime import prepare_real_sfx
except Exception:
    prepare_real_sfx=None
try:
    from sfx_reactions import ensure_reaction_assets
except Exception:
    ensure_reaction_assets=None


def _clean(text): return " ".join(str(text or "").split()).strip()

def _write_wav(path,samples):
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with wave.open(path,"wb") as wf:
        wf.setnchannels(1);wf.setsampwidth(2);wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(struct.pack("<h",max(-32767,min(32767,int(x)))) for x in samples))

def _env(i,n,a=.015,r=.18):
    t=i/max(1,n);return min(1.0,min(1.0,t/a),min(1.0,(1-t)/r))

def _tone(freq,duration,volume=.5,decay=3,slide=0):
    n=max(1,int(duration*SAMPLE_RATE));out=[];phase=0
    for i in range(n):
        t=i/SAMPLE_RATE;phase+=2*math.pi*max(25,freq+slide*i/max(1,n-1))/SAMPLE_RATE
        out.append(32767*volume*_env(i,n)*math.exp(-decay*t)*math.sin(phase))
    return out

def _noise(duration,volume=.25,decay=5,seed=7):
    rng=random.Random(seed);n=max(1,int(duration*SAMPLE_RATE))
    return [32767*volume*_env(i,n)*math.exp(-decay*i/SAMPLE_RATE)*rng.uniform(-1,1) for i in range(n)]

def _procedural(kind):
    if kind in ("click","tap"): return _tone(1450,.08,.42,25,-500)
    if kind=="pop": return _tone(180,.18,.58,8,520)
    if kind=="impact": return [a+b for a,b in zip(_tone(72,.28,.72,5,-30),_noise(.28,.22,13,13))]
    if kind=="glass_ting": return _tone(2100,.55,.30,4.8,-260)
    if kind=="boing": return _tone(260,.42,.46,2.6,520)
    if kind=="suspense": return _tone(130,.70,.20,1.2,260)
    if kind=="reveal": return _tone(330,.38,.45,5,500)
    if kind=="sparkle":
        parts=[0.0]*int(.45*SAMPLE_RATE)
        for freq,start in [(880,0),(1320,.10),(1760,.20),(2200,.30)]:
            tone=_tone(freq,.22,.18,7,80);off=int(start*SAMPLE_RATE)
            for i,v in enumerate(tone):
                if off+i<len(parts):parts[off+i]+=v
        return parts
    n=int(.42*SAMPLE_RATE);noise=_noise(.42,.20,2.2,11);out=[];phase=0
    for i,x in enumerate(noise):
        p=i/max(1,n-1);phase+=2*math.pi*(180+1050*p)/SAMPLE_RATE
        out.append(x+32767*.11*math.sin(phase)*(p**.8)*(1-p*.15))
    return out

def _fallback(scene,index):
    text=_clean(scene.get("narration","")).lower()
    if index==0:return "pop",180
    if any(x in text for x in ("glass","window","mirror","reflection")):return "glass_ting",220
    if any(x in text for x in ("crack","break","snap","hit","bang")):return "impact",180
    if any(x in text for x in ("suddenly","but then","except","actually","turns out")):return "reveal",180
    if any(x in text for x in ("weird","strange","ridiculous","funny","odd")):return "boing",180
    if any(x in text for x in ("question","wonder","why","how")) and index>=4:return "suspense",250
    if any(x in text for x in ("tiny","little","touch","tap","finger","screen","button")):return "tap",160
    if index in (1,2):return "whoosh",160
    if index==5:return "reveal",180
    if index==6:return "sparkle",120
    return "pop",160

def _is_comedic(scene):
    text=_clean(" ".join(str(scene.get(k,"")) for k in ("narration","spoken_beat","physical_action","visual_prompt"))).lower()
    return any(x in text for x in ("funny","ridiculous","absurd","hilarious","faaa","what?!","wait","no way","insane","bonkers","wild"))

def generate_sfx(script,output_dir):
    scenes=script.get("scene_plan",[]) if isinstance(script,dict) else []
    if len(scenes)!=7: raise RuntimeError("SFX generation requires exactly 7 scenes.")
    os.makedirs(output_dir,exist_ok=True);paths=[];plan=[]
    print("="*80);print("🔊 STORY-AWARE SFX — REAL ASSETS + ORIGINAL REACTIONS");print("="*80)
    real=[]
    if prepare_real_sfx:
        try:
            real=prepare_real_sfx(script)
            print(f"🔊 Real SFX library: {sum(1 for p in real if p)}/{len(real)} scene assets available")
        except Exception as e: print(f"⚠️ Real SFX bootstrap unavailable; using fallback: {e}")
    reactions={}
    if ensure_reaction_assets:
        try: reactions=ensure_reaction_assets()
        except Exception as e: print(f"⚠️ Reaction SFX unavailable: {e}")
    reaction_count=0
    for index,scene in enumerate(scenes):
        kind,at_ms=_fallback(scene,index);source="procedural"
        # Use the original FAAA only for strong comedic moments, max twice.
        if reaction_count<2 and _is_comedic(scene) and reactions.get("faaa"):
            path=reactions["faaa"];kind="faaa";at_ms=170 if index==0 else 240;reaction_count+=1;source="original_reaction"
        elif index<len(real) and real[index] and os.path.exists(real[index]):
            path=real[index];kind=scene.get("sfx_cue",{}).get("category",kind);source="real_library"
            at_ms=scene.get("sfx_cue",{}).get("at_ms",at_ms)
        else:
            path=os.path.join(output_dir,f"scene_{index+1}_{kind}.wav");_write_wav(path,_procedural(kind))
        scene["sfx_cue"]={"enabled":True,"type":kind,"source":source,"at_ms":at_ms,"intensity":"medium" if kind in ("impact","faaa","reveal") else "subtle"}
        paths.append(path);plan.append({"scene":index+1,"type":kind,"source":source,"at_ms":at_ms});print(f"Scene {index+1}: {kind} [{source}] @ {at_ms}ms")
    script["sfx_plan"]=plan
    return paths
