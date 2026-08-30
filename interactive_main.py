"""Independent Interactive Mystery pipeline. Does not modify main.py or production_entry.py."""
from __future__ import annotations
import json,os,time,yaml
from interactive_topics import get_next_topic,record_topic
from interactive_analytics import record as record_analytics,build_comparison
from generate_script import generate_script
from tts import synthesize_script
from stock_media_resilient import generate_media
from music import download_music
from sfx import generate_sfx
from assemble import assemble_video
from upload_youtube import upload_video
from validate_video import validate_final_video
def load_config():
 with open("config.yaml",encoding="utf-8") as f:return yaml.safe_load(f)
def save(x,p):
 os.makedirs(os.path.dirname(p),exist_ok=True)
 with open(p,"w",encoding="utf-8") as f:json.dump(x,f,indent=2,ensure_ascii=False)
def run(dry_run=False):
 config=load_config(); pillar,topic=get_next_topic()
 print("🧩 INTERACTIVE MYSTERY |",pillar,"|",topic)
 feedback=f"""INTERACTIVE MYSTERY UNIVERSE. PILLAR: {pillar}. Write an entertaining 7-scene interactive Short, not a science explainer. Open with a concrete dilemma, clue, or psychological situation. Make the viewer choose or solve before the payoff. Use tension, reversals, specific details, and natural spoken English. Ask one genuine viewer question near the end. No generic like/subscribe CTA. Scene 7 must have a satisfying payoff and no continuation teaser."""
 script=generate_script(topic,config,None,extra_feedback=feedback); script["topic"]=topic; script["interactive_pillar"]=pillar
 script["engagement"]={"comment":"What would YOU choose? Explain below 👇" if pillar!="solve_the_mystery" else "What was your solution? Drop it below 👇"}
 workdir=os.path.join("output","interactive",str(int(time.time()))); os.makedirs(workdir,exist_ok=True); save(script,os.path.join(workdir,"script.json"))
 if dry_run: print("✅ INTERACTIVE DRY RUN COMPLETE"); return
 audio=synthesize_script(script,config,os.path.join(workdir,"audio")); visuals=generate_media(script,os.path.join(workdir,"visuals"),config); sfx=generate_sfx(script,os.path.join(workdir,"sfx")); music=download_music(script,os.path.join(workdir,"music"))
 final=os.path.join(workdir,"final.mp4"); assemble_video(script,audio,visuals,music,sfx,config,final)
 q=validate_final_video(final,expected_bitrate_mbps=100.0); save(q,os.path.join(workdir,"validation.json"))
 if not q.get("ok"): raise RuntimeError("Interactive final video validation failed.")
 title=str(script.get("title") or topic)[:100]; desc=f"Can YOU figure this out? {topic}\n\n#Mystery #Psychology #Shorts"
 result=upload_video(final,title,desc,config,engagement_comment=script["engagement"]["comment"]); vid=str((result or {}).get("video_id") or (result or {}).get("id") or "")
 record_topic(topic,pillar,title,vid,workdir)
 if vid: record_analytics(vid,topic,pillar,title,workdir)
 print("📊 Comparison:",json.dumps(build_comparison(),ensure_ascii=False))
if __name__=="__main__":
 import argparse
 p=argparse.ArgumentParser(); p.add_argument("--dry-run",action="store_true"); run(p.parse_args().dry_run)
