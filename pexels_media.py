"""Pexels-first media selection: relevant video -> relevant photo -> Pollinations."""
from __future__ import annotations
import json, os, re, time
from pathlib import Path
import requests
PEXELS_API="https://api.pexels.com/v1"; TIMEOUT=45
STOP={"this","that","with","from","your","into","about","just","they","them","their","very","have","will","what","when","where","which","because","while","then","than","like","gets","make","makes","made","thing","things","exact","physical","show","showing","scene","shot","visible","action","state","realistic","cinematic","photo","photograph","video","image","someone","something","person","people","close","camera","natural","looking","moment"}
ACTIONS={"cling","clinging","stick","sticking","pull","pulling","grab","grabbing","hold","holding","touch","touching","rub","rubbing","fall","falling","drop","dropping","jump","jumping","run","running","pour","pouring","spill","spilling","open","opening","close","closing","break","breaking","tear","tearing","bend","bending","shake","shaking","twist","twisting","stretch","stretching","slide","sliding","move","moving","tumble","tumbling","wash","washing","dry","drying","iron","ironing","sew","sewing","wear","wearing","remove","removing","press","pressing","boil","boiling","freeze","freezing","melt","melting","fog","fogging","steam","squeeze","squeezing","crush","crushing","bounce","bouncing","spin","spinning"}
def clean(v,n=500): return " ".join(str(v or "").replace("\n"," ").split()).strip()[:n]
def tokens(v): return {w for w in re.findall(r"[a-z0-9]+",clean(v,1400).lower()) if len(w)>=4 and w not in STOP}
def action_tokens(v): return tokens(v)&ACTIONS
def queries(scene,visual):
    focus=clean(visual.get("visual_focus"),120); action=clean(visual.get("visual_action"),160); spoken=clean(visual.get("spoken_line") or scene.get("narration"),220); prompt=clean(visual.get("image_prompt"),260); out=[]
    for value in (f"{focus} {action}",f"{focus} {spoken}",spoken,prompt):
        words=[]
        for w in re.findall(r"[A-Za-z0-9'-]+",value):
            w=w.lower().strip("'-")
            if len(w)>=4 and w not in STOP and w not in words: words.append(w)
        q=" ".join(words[:8])
        if q and q not in out: out.append(q)
    return out[:3] or ["everyday object close up"]
def score(item,required,actions,kind):
    if kind=="video": text=" ".join([clean(item.get("url"),400),clean(item.get("image"),300),clean(item.get("video_pictures"),300)])
    else:
        src=item.get("src") or {}; text=" ".join([clean(item.get("alt"),500),clean(item.get("url"),300),clean(src.get("portrait"),300) if isinstance(src,dict) else ""])
    rt=tokens(text); s=len(required&rt)*2.0
    if kind=="video":
        d=float(item.get("duration") or 0); w=int(item.get("width") or 0); h=int(item.get("height") or 0)
        if 2<=d<=20:s+=2
        if h>w:s+=2
        elif w and h:s+=.5
        s+=len(actions&rt)*2.5
    else:
        src=item.get("src") or {}
        if isinstance(src,dict) and src.get("portrait"):s+=2
        if int(item.get("height") or 0)>=int(item.get("width") or 0):s+=1
    return s
def headers():
    key=os.environ.get("PEXELS_API_KEY","").strip(); return {"Authorization":key,"User-Agent":"Mint-YT-Factory/PexelsMedia/2.0"} if key else None
def search(endpoint,q,params):
    h=headers()
    if not h:return []
    r=requests.get(f"{PEXELS_API}/{endpoint}",headers=h,params={"query":q,"per_page":20,**params},timeout=TIMEOUT)
    if r.status_code!=200: print(f"⚠️ Pexels {endpoint}: HTTP {r.status_code}"); return []
    d=r.json(); return d.get("videos",[]) if endpoint=="videos/search" else d.get("photos",[])
def download(url,path):
    try:
        r=requests.get(url,headers={"User-Agent":"Mint-YT-Factory/PexelsMedia/2.0"},timeout=120,stream=True); r.raise_for_status(); Path(path).parent.mkdir(parents=True,exist_ok=True)
        with open(path,"wb") as f:
            for chunk in r.iter_content(1024*1024):
                if chunk:f.write(chunk)
        return os.path.getsize(path)>10000
    except Exception as e:
        print(f"⚠️ Pexels download failed: {e}");
        try: os.remove(path)
        except OSError: pass
        return False
def pick_video(results,required,actions):
    for item in sorted(results,key=lambda x:score(x,required,actions,"video"),reverse=True):
        s=score(item,required,actions,"video")
        if s<7:continue
        files=item.get("video_files") or []; candidates=[]
        for vf in files:
            link=vf.get("link"); w=int(vf.get("width") or 0); h=int(vf.get("height") or 0)
            if link and w and h:candidates.append(((2 if h>=w else 0)+(2 if str(vf.get("quality","")).lower()=="hd" else 0),w*h,link))
        if candidates:return {"video":max(candidates)[2],"page":item.get("url",""),"photographer":(item.get("user") or {}).get("name",""),"score":s}
    return None
def pick_photo(results,required,actions):
    for item in sorted(results,key=lambda x:score(x,required,actions,"photo"),reverse=True):
        s=score(item,required,actions,"photo")
        if s<5.5:continue
        src=item.get("src") or {}; link=src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
        if link:return {"photo":link,"page":item.get("url",""),"photographer":item.get("photographer","") or "","score":s}
    return None
def credit(path,kind,page,photographer):
    with open(path,"w",encoding="utf-8") as f:json.dump({"type":kind,"page":page,"photographer":photographer,"provider":"Pexels"},f,ensure_ascii=False,indent=2)
def fallback(gim,scene,visual,path,width,height,seed,si,vi):
    prompt=gim.build_prompt(scene,visual,{},scene_index=si,visual_index=vi,correction="Pexels had no sufficiently relevant video or photo. Generate the exact literal physical moment described by the spoken beat.")
    return gim._save_image(gim.generate_image(prompt,width,height,seed),path,width,height)
def generate_media(script,output_dir,config,gim):
    scenes=script.get("scene_plan") or []; cfg=config.get("image",{}) if isinstance(config,dict) else {}; width=int(cfg.get("width",2160)); height=int(cfg.get("height",3840)); base=int(time.time()); os.makedirs(output_dir,exist_ok=True); available=bool(headers()); used=False; groups=[]; credits=[]
    print("="*80); print("📚 PEXELS-FIRST STORY MEDIA v2"); print(f"Pexels API: {'AVAILABLE' if available else 'NOT CONFIGURED'}"); print("Rule: literal spoken beat > generic relevance"); print("Provider order: Pexels video → Pexels photo → Pollinations FLUX"); print("="*80)
    for si,scene in enumerate(scenes,1):
        paths=[]; visuals=scene.get("visuals") or []
        for vi,visual in enumerate(visuals[:2],1):
            spoken=clean(visual.get("spoken_line") or scene.get("narration")); required=tokens(" ".join([clean(visual.get("visual_focus")),clean(visual.get("visual_action")),clean(visual.get("must_show")),spoken])); acts=action_tokens(" ".join([clean(visual.get("visual_action")),spoken])); qs=queries(scene,visual); stem=f"scene_{si:02d}_shot_{vi:02d}"
            print(f"🎬 Scene {si}/7 Shot {vi}/2 | {spoken}"); selected=None
            if available:
                try:
                    for q in qs:
                        selected=pick_video(search("videos/search",q,{"orientation":"portrait","size":"medium"}),required,acts)
                        if selected:break
                    if selected:
                        path=os.path.join(output_dir,stem+".mp4")
                        if download(selected["video"],path):credit(os.path.join(output_dir,stem+".credit.json"),"video",selected["page"],selected["photographer"]); credits.append({**selected,"scene":si,"shot":vi}); paths.append(path); used=True; print(f"🎞️ Pexels VIDEO selected | score={selected['score']:.1f}"); continue
                    for q in qs:
                        selected=pick_photo(search("search",q,{"orientation":"portrait","size":"large"}),required,acts)
                        if selected:break
                    if selected:
                        path=os.path.join(output_dir,stem+".jpg")
                        if download(selected["photo"],path):credit(os.path.join(output_dir,stem+".credit.json"),"photo",selected["page"],selected["photographer"]); credits.append({**selected,"scene":si,"shot":vi}); paths.append(path); used=True; print(f"🖼️ Pexels PHOTO selected | score={selected['score']:.1f}"); continue
                except Exception as e: print(f"⚠️ Pexels lookup failed: {e}")
            path=os.path.join(output_dir,stem+".png"); paths.append(fallback(gim,scene,visual,path,width,height,base+si*100+vi,si,vi)); print("🧠 Pollinations FLUX fallback selected")
        if len(paths)!=2:raise RuntimeError(f"Scene {si} did not produce exactly 2 media assets.")
        groups.append(paths)
    script["_pexels_used"]=used; script["_pexels_credits"]=credits; script["_media_provider_order"]=["pexels_video","pexels_photo","pollinations"]
    with open(os.path.join(output_dir,"media_manifest.json"),"w",encoding="utf-8") as f:json.dump({"provider_order":["pexels_video","pexels_photo","pollinations"],"pexels_used":used,"credits":credits},f,ensure_ascii=False,indent=2)
    print(f"✅ Media complete: {sum(map(len,groups))} assets | Pexels used: {used}"); return groups
