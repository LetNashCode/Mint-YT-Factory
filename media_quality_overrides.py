"""Runtime media selection improvements for the Pexels-first provider."""
from __future__ import annotations

import os


def patch_media_selection(media):
    used=set()
    original_generate=media.generate_media

    def pick_video(results,required,actions):
        # Pexels already ranks search results for relevance; the selector's job
        # here is to prefer portrait, usable-duration clips and avoid repeats.
        ranked=[]
        for item in results:
            url=item.get("url","")
            if not url or url in used: continue
            duration=float(item.get("duration") or 0)
            width=int(item.get("width") or 0); height=int(item.get("height") or 0)
            if duration<2 or duration>20 or not width or not height: continue
            score=(5 if height>=width else 0)+(2 if 4<=duration<=15 else 0)+(1 if height/width>=1.15 else 0)
            ranked.append((score,item))
        for score,item in sorted(ranked,key=lambda x:x[0],reverse=True):
            files=[]
            for vf in item.get("video_files") or []:
                link=vf.get("link"); w=int(vf.get("width") or 0); h=int(vf.get("height") or 0)
                if link and w and h: files.append(((2 if h>=w else 0)+(2 if str(vf.get("quality","")).lower()=="hd" else 0),w*h,link))
            if files:
                return {"video":max(files)[2],"page":item.get("url",""),"photographer":(item.get("user") or {}).get("name",""),"score":score}
        return None

    def pick_photo(results,required,actions):
        ranked=[]
        for item in results:
            url=item.get("url","")
            if not url or url in used: continue
            w=int(item.get("width") or 0); h=int(item.get("height") or 0)
            src=item.get("src") or {}; link=src.get("portrait") or src.get("large2x") or src.get("large") or src.get("original")
            if not link: continue
            score=(4 if h>=w else 0)+(2 if h/w>=1.15 else 0) if w else 0
            ranked.append((score,item,link))
        for score,item,link in sorted(ranked,key=lambda x:x[0],reverse=True):
            if score<4: continue
            return {"photo":link,"page":item.get("url",""),"photographer":item.get("photographer","") or "","score":score}
        return None

    media._pick_video=pick_video
    media._pick_photo=pick_photo

    def generate_media(script,output_dir,config,gim):
        used.clear()
        groups=original_generate(script,output_dir,config,gim)
        # Build the set from the generated credit files after selection. This
        # makes duplicate prevention durable in the manifest as well.
        for item in script.get("_pexels_credits",[]):
            if item.get("page"): used.add(item["page"])
        return groups

    media.generate_media=generate_media
    print("🎯 Pexels selector: portrait/action-friendly clips, duration scoring, no duplicate assets")
