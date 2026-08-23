"""Production media QC for Pexels-first selection."""
from __future__ import annotations
import io,json,os,re,subprocess,tempfile

def _image_preview(path):
    from PIL import Image
    p=str(path)
    if p.lower().endswith((".jpg",".jpeg",".png",".webp")):
        with Image.open(p) as im:
            im=im.convert("RGB"); im.thumbnail((640,640)); out=io.BytesIO(); im.save(out,format="JPEG",quality=82,optimize=True); return out.getvalue()
    if not p.lower().endswith((".mp4",".mov",".webm",".m4v")): return None
    tmp=[]
    try:
        probe=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",p],capture_output=True,text=True,timeout=15); duration=float((probe.stdout or "0").strip() or 0)
        if duration<=0:return None
        frames=[]
        for fraction in (.2,.5,.8):
            fd,fp=tempfile.mkstemp(suffix=".jpg"); os.close(fd); tmp.append(fp); target=max(0,min(duration-.05,duration*fraction))
            subprocess.run(["ffmpeg","-y","-loglevel","error","-ss",str(target),"-i",p,"-frames:v","1","-vf","scale=480:-2",fp],capture_output=True,timeout=30)
            if os.path.isfile(fp) and os.path.getsize(fp)>1000: frames.append(Image.open(fp).convert("RGB").copy())
        if not frames:return None
        width=sum(x.width for x in frames); height=max(x.height for x in frames); sheet=Image.new("RGB",(width,height),"white"); x=0
        for im in frames:sheet.paste(im,(x,0)); x+=im.width
        out=io.BytesIO(); sheet.save(out,format="JPEG",quality=78,optimize=True); return out.getvalue()
    except Exception as exc: print(f"⚠️ Media preview failed: {exc}"); return None
    finally:
        for fp in tmp:
            try:os.remove(fp)
            except OSError:pass

def _parse_json(text):
    text=str(text or "").strip(); text=re.sub(r"^```(?:json)?","",text,flags=re.I).strip(); text=re.sub(r"```$","",text).strip()
    try:return json.loads(text)
    except Exception:
        m=re.search(r"\[[\s\S]*\]",text)
        if m:
            try:return json.loads(m.group(0))
            except Exception:pass
    return None

def _current_story_beat(scene,visual,si):
    spoken=str(visual.get("spoken_line") or scene.get("narration") or "").strip()
    if si==7: spoken=re.split(r"\b(?:and\s+next|next\s+(?:video|short|topic)|coming\s+next)\s*:\s*",spoken,maxsplit=1,flags=re.I)[0].strip()
    return spoken

def _batch_media_qc(script,groups):
    try:
        from google import genai
        from google.genai import types
    except Exception:return []
    key=os.environ.get("GEMINI_API_KEY")
    if not key:return []
    parts=[]; labels=[]; idx=0; scenes=script.get("scene_plan") or []
    for si,paths in enumerate(groups,1):
        scene=scenes[si-1] if si-1<len(scenes) else {}; visuals=scene.get("visuals") or []
        for vi,path in enumerate(paths,1):
            idx+=1; labels.append({"index":idx,"scene":si,"shot":vi,"path":path})
            preview=_image_preview(path)
            if not preview:continue
            visual=visuals[vi-1] if vi-1<len(visuals) else {}; spoken=_current_story_beat(scene,visual,si); focus=str(visual.get("visual_focus") or ""); action=str(visual.get("visual_action") or ""); must=str(visual.get("must_show") or "")
            parts.append(types.Part.from_bytes(data=preview,mime_type="image/jpeg")); parts.append(types.Part.from_text(text=f"MEDIA {idx} — Scene {si}, Shot {vi}\nCURRENT STORY BEAT: {spoken}\nFOCUS: {focus}\nACTION: {action}\nMUST SHOW: {must}"))
    if not parts:return labels
    instruction="""Strict visual QC for a YouTube Short. PASS only if the asset literally shows the current-story beat: correct object, physical state/action and relevant setting. FAIL generic stock, keyword-only matches, unrelated people, scenery, abstract graphics, symbolic science imagery or wrong object/action. Scene 7: ignore any And next teaser and judge only the current story payoff. Return ONLY JSON array [{\"index\":1,\"pass\":true,\"score\":9,\"reason\":\"short reason\"}]."""
    try:
        client=genai.Client(api_key=key); response=client.models.generate_content(model="gemini-flash-lite-latest",contents=parts+[instruction],config=types.GenerateContentConfig(temperature=0)); result=_parse_json(getattr(response,"text","") or "")
        if not isinstance(result,list):return labels
        by={int(x.get("index")):x for x in result if isinstance(x,dict) and str(x.get("index","")).isdigit()}; failed=[]
        for item in labels:
            v=by.get(item["index"],{}); passed=bool(v.get("pass")) and int(v.get("score",0) or 0)>=8; print(f"🔎 MEDIA QC Scene {item['scene']} Shot {item['shot']}: {'PASS' if passed else 'FAIL'} — {v.get('reason','no confident match')}")
            if not passed:failed.append(item)
        return failed
    except Exception as exc: print(f"⚠️ Media QC unavailable; retaining selected assets: {exc}"); return []

def _replace_failed(script,groups,failed,output_dir,gim,round_no):
    scenes=script.get("scene_plan") or []
    for item in failed:
        si,vi=item["scene"],item["shot"]; scene=scenes[si-1]; visual=(scene.get("visuals") or [])[vi-1]; old=groups[si-1][vi-1]; original=visual.get("spoken_line"); visual["spoken_line"]=_current_story_beat(scene,visual,si)
        correction="VISUAL QC REJECTED THE PREVIOUS IMAGE. Show ONLY the exact physical moment. Main object fills most of the frame. Use simple macro/tabletop product photography. No abstract effects, metaphors, random people, diagrams or unrelated scenery."
        prompt=gim.build_prompt(scene,visual,{},scene_index=si,visual_index=vi,correction=correction); data=gim.generate_image(prompt,2160,3840,900000+round_no*10000+si*100+vi); new=os.path.join(output_dir,f"scene_{si:02d}_shot_{vi:02d}_qc{round_no}.png"); saved=gim._save_image(data,new,2160,3840); visual["spoken_line"]=original; groups[si-1][vi-1]=saved
        try:os.remove(old)
        except OSError:pass
        try:os.remove(os.path.splitext(old)[0]+".credit.json")
        except OSError:pass
        print(f"🧠 Pollinations replacement: Scene {si} Shot {vi} | round={round_no} | {saved}")

def _assert_complete(groups):
    if len(groups)!=7:raise RuntimeError(f"Media contract failed: expected 7 scene groups, found {len(groups)}.")
    for si,paths in enumerate(groups,1):
        if len(paths)!=2:raise RuntimeError(f"Media contract failed: Scene {si} has {len(paths)} paths.")
        if any(not os.path.exists(p) for p in paths):raise RuntimeError(f"Media contract failed: Scene {si} has missing assets.")

def patch_media_selection(media):
    original_generate=media.generate_media
    if getattr(original_generate,"_mint_media_qc",False):return
    def generate_media(script,output_dir,config,gim):
        groups=original_generate(script,output_dir,config,gim); _assert_complete(groups)
        # Three bounded rounds prevent infinite Actions runs while giving FLUX
        # enough chances to replace poor stock selections with literal images.
        for round_no in (1,2,3):
            failed=_batch_media_qc(script,groups)
            if not failed:break
            print(f"⚠️ MEDIA QC ROUND {round_no}: replacing {len(failed)} failed assets")
            _replace_failed(script,groups,failed,output_dir,gim,round_no); _assert_complete(groups)
        else:
            remaining=_batch_media_qc(script,groups)
            if remaining:print(f"⚠️ MEDIA QC exhausted 3 rounds; retaining best available replacements for {len(remaining)} assets.")
        with open(os.path.join(output_dir,"media_manifest.json"),"w",encoding="utf-8") as h:json.dump({"provider_order":["pexels_video","pexels_photo","pollinations"],"qc_rounds":3},h,indent=2)
        print(f"🎞️ Media final: {sum(map(len,groups))} assets"); return groups
    generate_media._mint_media_qc=True; media.generate_media=generate_media; print("🧠 Media QC: current-story verification + 3 bounded replacement rounds ENABLED")
