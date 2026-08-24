"""Story-aware SFX selector.

Guarantees one FAAA reaction per Short and places effects at meaningful
narrative beats instead of using a fixed offset for every scene.
"""
from __future__ import annotations
import os, math, random, struct, wave, re

SAMPLE_RATE=44100
DEFAULT_SCENE_DURATIONS=(3,5,7,7,8,8,7)

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
    return _noise(.42,.20,2.2,11)

def _fallback(scene,index):
    text=_clean(scene.get("narration","")).lower()
    if index==0:return "pop",120
    if any(x in text for x in ("glass","window","mirror","reflection")):return "glass_ting",180
    if any(x in text for x in ("crack","break","snap","hit","bang")):return "impact",120
    if any(x in text for x in ("suddenly","but then","except","actually","turns out")):return "reveal",120
    if any(x in text for x in ("weird","strange","ridiculous","funny","odd")):return "boing",120
    if any(x in text for x in ("question","wonder","why","how")) and index>=4:return "suspense",160
    if any(x in text for x in ("tiny","little","touch","tap","finger","screen","button")):return "tap",100
    if index in (1,2):return "whoosh",120
    if index==5:return "reveal",120
    if index==6:return "sparkle",100
    return "pop",120

def _is_comedic(scene):
    text=_clean(" ".join(str(scene.get(k,"")) for k in ("narration","spoken_beat","physical_action","visual_prompt"))).lower()
    return any(x in text for x in ("funny","ridiculous","absurd","hilarious","faaa","what?!","wait","no way","insane","bonkers","wild","seriously"))

def _scene_strength(scene,index):
    text=_clean(" ".join(str(scene.get(k,"")) for k in ("narration","spoken_beat","physical_action","visual_prompt"))).lower()
    score=index*0.05
    for phrase,weight in (("suddenly",5),("but then",5),("turns out",5),("actually",4),("wait",5),("what",3),("no way",6),("insane",5),("weird",3),("ridiculous",4),("finally",3),("the truth",5)):
        if phrase in text: score+=weight
    if _is_comedic(scene): score+=5
    if index==0: score-=4
    return score

def _pick_faaa_scene(scenes):
    ranked=sorted(range(len(scenes)),key=lambda i:_scene_strength(scenes[i],i),reverse=True)
    return ranked[0] if ranked else min(3,len(scenes)-1)

def _scene_duration(scene,index):
    value=scene.get("duration_seconds",scene.get("duration",None)) if isinstance(scene,dict) else None
    try:
        value=float(value)
        if value>0:return value
    except Exception: pass
    return float(DEFAULT_SCENE_DURATIONS[min(index,len(DEFAULT_SCENE_DURATIONS)-1)])

def _beat_position(scene,duration):
    """Return milliseconds for the strongest spoken/comedic beat."""
    narration=_clean(scene.get("narration","")).lower()
    words=re.findall(r"\b[\w'-]+\b",narration)
    if not words:return int(max(.15,min(duration*.65,duration-.25))*1000)
    triggers=("wait","what","no way","seriously","suddenly","but then","turns out","actually","insane","ridiculous","weird","truth","finally","faaa")
    positions=[]
    for trigger in triggers:
        pos=narration.find(trigger)
        if pos>=0:
            positions.append(len(re.findall(r"\b[\w'-]+\b",narration[:pos])))
    match=min(positions) if positions else None
    if match is None:
        ratio=.72
    else:
        ratio=match/max(1,len(words))
        ratio=max(.28,min(.86,ratio))
    return int(max(.15,min(duration-.25,duration*ratio))*1000)

def generate_sfx(script,output_dir):
    scenes=script.get("scene_plan",[]) if isinstance(script,dict) else []
    if len(scenes)!=7: raise RuntimeError("SFX generation requires exactly 7 scenes.")
    os.makedirs(output_dir,exist_ok=True);paths=[];plan=[]
    print("="*80);print("🔊 STORY-AWARE SFX — NARRATIVE PLACEMENT + MANDATORY FAAA");print("="*80)
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

    faaa_scene=_pick_faaa_scene(scenes)
    print(f"😂 FAAA mandatory scene: {faaa_scene+1}")
    for index,scene in enumerate(scenes):
        kind,at_ms=_fallback(scene,index);source="procedural"
        if index==faaa_scene and reactions.get("faaa"):
            path=reactions["faaa"];kind="faaa";source="original_reaction"
            at_ms=_beat_position(scene,_scene_duration(scene,index))
        elif index<len(real) and real[index] and os.path.exists(real[index]):
            path=real[index];kind=scene.get("sfx_cue",{}).get("category",kind) if isinstance(scene.get("sfx_cue"),dict) else kind;source="real_library"
            # Never trust the old fixed 180/220ms offsets from the real-SFX
            # selector. Only an explicitly marked manual cue may override the
            # narration-beat timing.
            cue=scene.get("sfx_cue",{}) if isinstance(scene.get("sfx_cue"),dict) else {}
            explicit=cue.get("at_ms") if cue.get("manual") is True else None
            at_ms=int(explicit) if isinstance(explicit,(int,float)) else _beat_position(scene,_scene_duration(scene,index))
        else:
            path=os.path.join(output_dir,f"scene_{index+1}_{kind}.wav");_write_wav(path,_procedural(kind))
            at_ms=_beat_position(scene,_scene_duration(scene,index))
        cue={"enabled":True,"type":kind,"source":source,"at_ms":int(at_ms),"timing":"narration_beat","intensity":"medium" if kind in ("impact","faaa","reveal") else "subtle"}
        scene["sfx_cue"]=cue
        paths.append(path);plan.append({"scene":index+1,"type":kind,"source":source,"at_ms":int(at_ms),"timing":"narration_beat"})
        print(f"Scene {index+1}: {kind} [{source}] @ {int(at_ms)}ms (narration beat)")
    if not any(x["type"]=="faaa" and x["source"]=="original_reaction" for x in plan):
        raise RuntimeError("FAAA generation failed: every Short must contain one FAAA reaction.")
    script["sfx_plan"]=plan
    script["faaa_required"]=True
    return paths
