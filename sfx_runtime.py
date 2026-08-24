"""Runtime real-SFX selection for Mint-YT-Factory."""
from pathlib import Path
import hashlib
from sfx_assets import ensure_sfx_assets

KEYWORDS={
 "whoosh": ["move","rush","sweep","fly","pass","zoom","transition","suddenly"],
 "impact": ["hit","crash","slam","shock","reveal","twist","boom","bang","impact"],
 "interface": ["phone","screen","click","tap","button","digital","computer"],
 "magic": ["magic","spark","sparkle","strange","mysterious","weird","glow"],
 "correct": ["correct","right","answer","true","actually","fact"],
 "spin": ["spin","turn","twist","rotate","swirl"],
 "misc": ["funny","quirky","odd","crazy","tiny","pop","comedy"],
}

def _category_for_scene(scene):
 text=" ".join(str(scene.get(k,"")) for k in ("narration","visual_prompt","spoken_beat","physical_action")).lower()
 scores={k:sum(text.count(w) for w in words) for k,words in KEYWORDS.items()}
 best=max(scores,key=scores.get)
 return best if scores[best] else "whoosh"

def select_sfx(script, library):
 result=[]
 for index,scene in enumerate(script.get("scene_plan",[])):
  category=_category_for_scene(scene)
  paths=library.get(category,[])
  if not paths:
   result.append(None);continue
  digest=hashlib.sha1(f"{script.get('topic','')}:{index}:{category}".encode()).hexdigest()
  result.append(paths[int(digest[:8],16)%len(paths)])
  scene["sfx_cue"]={"enabled":True,"category":category,"at_ms":180 if index==0 else 220}
 return result

def prepare_real_sfx(script):
 library=ensure_sfx_assets()
 return select_sfx(script,library)
