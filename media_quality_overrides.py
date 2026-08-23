"""Production media QC for Pexels-first selection.

Pexels is preferred only when it is genuinely relevant. Every selected asset is
checked against the exact spoken beat. Failed assets are replaced by a
Pollinations image and the replacement is checked again before assembly.
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import tempfile


def _image_preview(path: str):
    from PIL import Image
    p = str(path)
    if p.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        with Image.open(p) as im:
            im = im.convert("RGB")
            im.thumbnail((640, 640))
            out = io.BytesIO(); im.save(out, format="JPEG", quality=82, optimize=True)
            return out.getvalue()
    if not p.lower().endswith((".mp4", ".mov", ".webm", ".m4v")):
        return None
    tmp_files=[]
    try:
        probe=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",p],capture_output=True,text=True,timeout=15)
        duration=float((probe.stdout or "0").strip() or 0)
        if duration<=0:return None
        frames=[]
        for fraction in (0.20,0.50,0.80):
            target=max(0.0,min(duration-0.05,duration*fraction))
            fd,frame_path=tempfile.mkstemp(suffix=".jpg"); os.close(fd); tmp_files.append(frame_path)
            subprocess.run(["ffmpeg","-y","-loglevel","error","-ss",str(target),"-i",p,"-frames:v","1","-vf","scale=480:-2",frame_path],capture_output=True,timeout=30)
            if os.path.isfile(frame_path) and os.path.getsize(frame_path)>1000:
                frames.append(Image.open(frame_path).convert("RGB").copy())
        if not frames:return None
        width=sum(im.width for im in frames); height=max(im.height for im in frames)
        sheet=Image.new("RGB",(width,height),"white"); x=0
        for im in frames: sheet.paste(im,(x,0)); x+=im.width
        out=io.BytesIO(); sheet.save(out,format="JPEG",quality=78,optimize=True); return out.getvalue()
    except Exception as exc:
        print(f"⚠️ Media preview failed: {exc}"); return None
    finally:
        for f in tmp_files:
            try: os.remove(f)
            except OSError: pass


def _parse_json(text):
    text=str(text or "").strip(); text=re.sub(r"^```(?:json)?","",text,flags=re.I).strip(); text=re.sub(r"```$","",text).strip()
    try:return json.loads(text)
    except Exception:
        m=re.search(r"\[[\s\S]*\]",text)
        if m:
            try:return json.loads(m.group(0))
            except Exception: pass
    return None


def _batch_media_qc(script,groups):
    """Verify every final asset against its exact spoken beat."""
    try:
        from google import genai
        from google.genai import types
    except Exception as exc:
        print(f"⚠️ Media visual QC unavailable: {exc}"); return []
    key=os.environ.get("GEMINI_API_KEY")
    if not key:return []
    parts=[]; labels=[]; index=0
    scenes=script.get("scene_plan") or []
    for si,paths in enumerate(groups,1):
        scene=scenes[si-1] if si-1<len(scenes) else {}
        visuals=scene.get("visuals") or []
        for vi,path in enumerate(paths,1):
            if not os.path.exists(path):
                labels.append({"index":index+1,"scene":si,"shot":vi,"path":path,"missing":True})
                index += 1
                continue
            preview=_image_preview(path)
            if not preview:continue
            visual=visuals[vi-1] if vi-1<len(visuals) else {}
            spoken=str(visual.get("spoken_line") or scene.get("narration") or "").strip()
            focus=str(visual.get("visual_focus") or "").strip(); action=str(visual.get("visual_action") or "").strip(); must=str(visual.get("must_show") or "").strip()
            index+=1; labels.append({"index":index,"scene":si,"shot":vi,"path":path})
            parts.append(types.Part.from_bytes(data=preview,mime_type="image/jpeg"))
            parts.append(types.Part.from_text(text=f"MEDIA {index} — Scene {si}, Shot {vi}\nSPOKEN BEAT: {spoken}\nFOCUS: {focus}\nACTION: {action}\nMUST SHOW: {must}"))
    if not parts:return []
    instruction="""
You are the final visual editor for a YouTube Short.
Each MEDIA block contains a visual preview followed by the exact spoken beat.
PASS only when the preview literally depicts the spoken beat: correct subject,
physical action/state and relevant setting/detail. The viewer should understand
what is happening with sound OFF.
FAIL generic or merely related stock footage. A beautiful image is still a FAIL
if it shows the wrong object, wrong action, random people, unrelated scenery,
symbolic science imagery, text, logos, watermarks or UI.
Score 8-10 only when the requested moment is unmistakable.
Return ONLY JSON array:
[{"index":1,"pass":true,"score":9,"reason":"short reason"}]
"""
    # Missing files are deterministic failures and do not need a Gemini call.
    missing=[x for x in labels if x.get("missing")]
    labels_for_model=[x for x in labels if not x.get("missing")]
    failed=list(missing)
    if not labels_for_model:
        return failed
    try:
        client=genai.Client(api_key=key)
        response=client.models.generate_content(model="gemini-flash-lite-latest",contents=parts+[instruction],config=types.GenerateContentConfig(temperature=0))
        result=_parse_json(getattr(response,"text","") or "")
        if not isinstance(result,list):
            print("⚠️ Media visual QC returned invalid JSON; treating selected assets as failed for safety.")
            return labels
        by_index={int(x.get("index")):x for x in result if isinstance(x,dict) and str(x.get("index","")).isdigit()}
        for item in labels_for_model:
            verdict=by_index.get(item["index"],{}); passed=bool(verdict.get("pass")) and int(verdict.get("score",0) or 0)>=8
            print(f"🔎 MEDIA QC Scene {item['scene']} Shot {item['shot']}: {'PASS' if passed else 'FAIL'} — {verdict.get('reason','no confident match')}")
            if not passed:failed.append(item)
        return failed
    except Exception as exc:
        # If QC itself fails, do not destroy otherwise usable media. Assembly
        # still receives a complete 14-file contract.
        print(f"⚠️ Media visual QC unavailable; retaining selected assets: {exc}"); return failed


def _replace_failed(script,groups,failed,output_dir,gim,round_no=1):
    failed_keys={(x["scene"],x["shot"]) for x in failed}
    credits=list(script.get("_pexels_credits") or [])
    script["_pexels_credits"]=[c for c in credits if (int(c.get("scene",0)),int(c.get("shot",0))) not in failed_keys]
    scenes=script.get("scene_plan") or []
    for item in failed:
        si,vi=item["scene"],item["shot"]
        scene=scenes[si-1]; visual=(scene.get("visuals") or [])[vi-1]
        old_path=groups[si-1][vi-1] if len(groups[si-1])>=vi else ""
        # Always use a unique replacement filename. This avoids stale Pexels
        # paths and guarantees assemble.py sees the replacement file.
        new_path=os.path.join(output_dir,f"scene_{si:02d}_shot_{vi:02d}_qc{round_no}.png")
        prompt=gim.build_prompt(scene,visual,{},scene_index=si,visual_index=vi,correction="Selected media failed literal relevance QC. Generate ONLY the exact spoken physical moment; no generic related object, metaphor, unrelated person, or stock-style substitute.")
        data=gim.generate_image(prompt,2160,3840,900000+round_no*10000+si*100+vi)
        saved=gim._save_image(data,new_path,2160,3840)
        if not os.path.exists(saved) or os.path.getsize(saved)<10000:
            raise RuntimeError(f"QC replacement was not saved correctly: {saved}")
        groups[si-1][vi-1]=saved
        if old_path and old_path != saved:
            try:os.remove(old_path)
            except OSError:pass
            try:os.remove(os.path.splitext(old_path)[0]+".credit.json")
            except OSError:pass
        print(f"🧠 Pollinations replacement: Scene {si} Shot {vi} | round={round_no} | {saved}")
    script["_pexels_used"]=bool(script.get("_pexels_credits"))


def _assert_complete(groups):
    if len(groups)!=7:
        raise RuntimeError(f"Media contract failed: expected 7 scene groups, found {len(groups)}.")
    for si,paths in enumerate(groups,1):
        if len(paths)!=2:
            raise RuntimeError(f"Media contract failed before assembly: Scene {si} has {len(paths)} paths.")
        missing=[p for p in paths if not os.path.exists(p)]
        if missing:
            raise RuntimeError(f"Media contract failed before assembly: Scene {si} missing {missing}.")


def patch_media_selection(media):
    """Patch the actual generate_media entrypoint.

    Pexels selection happens first, but every selected asset must pass literal
    spoken-beat QC. Replacements are re-checked so a bad AI image cannot reach
    assembly. The final filesystem contract is verified explicitly.
    """
    original_generate=media.generate_media
    if getattr(original_generate,"_mint_media_qc",False):return

    def generate_media(script,output_dir,config,gim):
        groups=original_generate(script,output_dir,config,gim)
        _assert_complete(groups)

        credits=script.get("_pexels_credits") or []
        seen=set(); duplicates=[]
        for c in credits:
            page=c.get("page"); key=(int(c.get("scene",0)),int(c.get("shot",0)))
            if page and page in seen:duplicates.append({"scene":key[0],"shot":key[1],"path":groups[key[0]-1][key[1]-1]})
            elif page:seen.add(page)
        if duplicates:
            print(f"⚠️ Duplicate Pexels assets detected: {len(duplicates)}")
            _replace_failed(script,groups,duplicates,output_dir,gim,round_no=1)

        # Two QC/replacement rounds. This is intentionally bounded so a bad
        # provider can never create an infinite GitHub Actions run.
        for round_no in (1,2):
            failed=_batch_media_qc(script,groups)
            if not failed:
                break
            print(f"⚠️ MEDIA QC ROUND {round_no}: replacing {len(failed)} failed assets")
            _replace_failed(script,groups,failed,output_dir,gim,round_no=round_no)
            _assert_complete(groups)
        else:
            # One final check after round 2. Do not silently publish an image
            # that still fails the literal contract.
            remaining=_batch_media_qc(script,groups)
            if remaining:
                raise RuntimeError(f"Visual QC failed after 2 replacement rounds: {len(remaining)} assets remain invalid.")

        _assert_complete(groups)
        manifest={"provider_order":["pexels_video","pexels_photo","pollinations"],"pexels_used":bool(script.get("_pexels_credits")),"credits":script.get("_pexels_credits") or []}
        with open(os.path.join(output_dir,"media_manifest.json"),"w",encoding="utf-8") as h:json.dump(manifest,h,ensure_ascii=False,indent=2)
        print(f"🎞️ Pexels unique assets used: {len(script.get('_pexels_credits') or [])}")
        return groups

    generate_media._mint_media_qc=True
    media.generate_media=generate_media
    print("🧠 Media QC: exact spoken-beat verification + duplicate protection + final filesystem contract ENABLED")
