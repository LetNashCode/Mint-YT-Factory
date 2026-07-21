import os
import shutil

from moviepy.config import change_settings

_im=shutil.which("convert") or shutil.which("magick")
if _im:
    change_settings({"IMAGEMAGICK_BINARY":_im})

from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ColorClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
    afx,
)

FONT="DejaVu-Sans-Bold"

def _fit(c,size):
    w,h=size
    c=c.resize(height=h) if c.h/c.w<h/w else c.resize(width=w)
    return c.crop(x_center=c.w/2,y_center=c.h/2,width=w,height=h)

def _caption(text,duration,size):
    w,h=size
    words=text.upper().split()
    step=max(1,len(words))
    seg=duration/step
    clips=[]
    t=0
    for word in words:
        clips.append(
            TextClip(word,font=FONT,fontsize=82,color="white",
                     stroke_color="black",stroke_width=4)
            .set_position(("center",h*0.78))
            .set_start(t)
            .set_duration(seg)
        )
        t+=seg
    return clips

def assemble_video(script,audio_paths,visual_paths,config,out_path):
    size=tuple(config["video"]["resolution"])
    narration=AudioFileClip(audio_paths[0])
    total=narration.duration
    scenes=script["scene_plan"]
    seg=total/max(1,len(scenes))
    clips=[]
    for i,scene in enumerate(scenes):
        vp=visual_paths[i] if i<len(visual_paths) else None
        if vp and os.path.exists(vp):
            base=VideoFileClip(vp).without_audio()
            if base.duration<seg:
                base=base.loop(duration=seg)
            else:
                base=base.subclip(0,seg)
            base=_fit(base,size)
        else:
            base=ColorClip(size,color=(15,15,15)).set_duration(seg)
        comp=CompositeVideoClip([base,*_caption(scene["text"],seg,size)],size=size).set_duration(seg)
        clips.append(comp)
    final=concatenate_videoclips(clips,method="compose").set_audio(narration)
    music=config["video"].get("background_music")
    if music and os.path.exists(music):
        bg=AudioFileClip(music).fx(afx.audio_loop,duration=final.duration).volumex(0.08)
        final=final.set_audio(CompositeAudioClip([final.audio,bg]))
    os.makedirs(os.path.dirname(out_path),exist_ok=True)
    final.write_videofile(out_path,fps=30,codec="libx264",audio_codec="aac",preset="medium",threads=4)
