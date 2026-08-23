"""Entertainment-first topic queue with persistent, semantic duplicate protection."""
from __future__ import annotations
import json, os, re, tempfile
from google import genai
from google.genai import types

MODEL_NAME="gemini-flash-lite-latest"
USED_TOPICS_PATH="used_topics.json"
NEXT_TOPIC_PATH="next_topic.json"
MAX_TOPIC_WORDS=12
MAX_TOPIC_CHARACTERS=300
SEMANTIC_HISTORY_LIMIT=300

SYSTEM_PROMPT="""
You are the viral topic strategist for Wonder Minute, an entertaining YouTube Shorts channel built around strange things people notice in daily life.
Generate ONE topic with strong visual and storytelling potential. The viewer reaction should be: "Wait, why does THAT happen?"
Prefer familiar everyday experiences, weird physical behavior, surprising animal behavior, strange sounds/sights/textures/reactions, objects behaving unexpectedly, and simple mysteries that can be shown literally. The topic must have ONE central mystery and support a 35–45 second story.
Avoid academic titles, generic facts, lists/top 5/countdowns, broad subjects, medical advice, politics, conspiracy theories, fearbait, and topics difficult to visualize.
Return ONLY one question, no quotes, no numbering, no explanation.
"""


def _clean_topic(value):
    text=str(value or "").strip()
    text=re.sub(r"```(?:text|json)?","",text,flags=re.I)
    text=text.replace('"',"").replace("'","")
    text=re.sub(r"^(topic|next topic|next_short|next short)\s*:\s*", "", text, flags=re.I)
    text=re.sub(r"^\s*\d+[.)\-:]\s*", "", text)
    return " ".join(text.split()).rstrip(".!? ").strip()


def _key(topic):
    return re.sub(r"[^a-z0-9]+"," ",_clean_topic(topic).lower()).strip()


def _topic_records(items):
    out=[]
    for item in items if isinstance(items,list) else []:
        if not isinstance(item,str) or item.startswith("__MINT_PENDING_NEXT_TOPIC__::"):
            continue
        if item.startswith("__MINT_ANALYTICS__::"):
            try:
                obj=json.loads(item.split("::",1)[1])
                item=obj.get("topic") or item
            except Exception:
                continue
        topic=_clean_topic(item)
        if topic: out.append(topic)
    return out


def _load_json(path,fallback):
    if not os.path.exists(path): return fallback
    try:
        with open(path,"r",encoding="utf-8") as h: return json.load(h)
    except Exception: return fallback


def _atomic_write(path,data):
    directory=os.path.dirname(os.path.abspath(path)) or "."
    fd,tmp=tempfile.mkstemp(prefix=".mint_topic_",suffix=".tmp",dir=directory,text=True)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as h:
            json.dump(data,h,indent=2,ensure_ascii=False); h.write("\n"); h.flush(); os.fsync(h.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except OSError: pass


def _used(): return _load_json(USED_TOPICS_PATH,[])


def _pending():
    data=_load_json(NEXT_TOPIC_PATH,{})
    return _clean_topic(data.get("topic")) if isinstance(data,dict) else _clean_topic(data)


def _similar(topic,used):
    a=set(_key(topic).split())
    if not a: return True
    stop={"why","does","do","your","you","the","a","an","is","are","to","in","on","of","and","when","how","what"}
    a-=stop
    for previous in _topic_records(used):
        b=set(_key(previous).split())-stop
        if not b: continue
        j=len(a&b)/max(1,len(a|b))
        containment=len(a&b)/max(1,min(len(a),len(b)))
        if j>=0.55 or containment>=0.75: return True
    return False


def _semantic_duplicate(client,topic,used):
    history=_topic_records(used)[-SEMANTIC_HISTORY_LIMIT:]
    if not history: return False
    compact="\n".join(f"{i+1}. {x}" for i,x in enumerate(history))
    prompt=f"""
You are the final duplicate-topic gate for a YouTube Shorts channel.

CANDIDATE:
{topic}

PUBLISHED OR USED TOPICS:
{compact}

Reject the candidate if it covers the SAME underlying curiosity, object + phenomenon,
or cause/effect question as any previous topic, even if worded differently.
Examples of duplicates: "Why do phone screens attract dust" vs "Why does dust stick to your phone screen"; "Why do onions make you cry" vs "Why do cut onions make your eyes water".
Do NOT reject merely because two topics share a broad category such as phones, food, water, or animals.
Return ONLY JSON: {{"duplicate":true/false,"match_index":0,"reason":"brief"}}
"""
    try:
        r=client.models.generate_content(model=MODEL_NAME,contents=prompt,config=types.GenerateContentConfig(temperature=0))
        text=re.sub(r"^```(?:json)?|```$","",str(getattr(r,"text","") or "").strip(),flags=re.I).strip()
        obj=json.loads(text)
        dup=bool(obj.get("duplicate"))
        if dup: print(f"🚫 Semantic topic duplicate: {obj.get('reason','previous topic is too similar')}")
        return dup
    except Exception as exc:
        print(f"⚠️ Semantic topic gate unavailable: {exc}")
        return False


def _save_pending(topic):
    topic=_clean_topic(topic)
    if not topic or len(topic)>MAX_TOPIC_CHARACTERS: return False
    if _similar(topic,_used()): return False
    _atomic_write(NEXT_TOPIC_PATH,{"topic":topic})
    return _pending()==topic


def _generate_new_topic():
    key=os.environ.get("GEMINI_API_KEY")
    if not key: raise RuntimeError("GEMINI_API_KEY environment variable is missing.")
    client=genai.Client(api_key=key)
    used=_used(); history=_topic_records(used)
    recent="\n".join(f"- {x}" for x in history[-SEMANTIC_HISTORY_LIMIT:]) or "(none)"
    prompt=f"""
Generate one highly clickable Wonder Minute Short topic.
Previously used topics:
{recent}
The new topic must be substantially different in subject AND underlying phenomenon from every previous topic.
Do not make a reworded version of an old topic.
Maximum {MAX_TOPIC_WORDS} words.
"""
    response=client.models.generate_content(model=MODEL_NAME,contents=prompt,config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT,temperature=1.0))
    topic=_clean_topic(getattr(response,"text",""))
    if not topic: raise RuntimeError("Gemini returned an empty topic.")
    if len(topic.split())>MAX_TOPIC_WORDS: raise RuntimeError("Generated topic is too long.")
    if _similar(topic,used): raise RuntimeError("Generated topic is too similar to a previous topic.")
    if _semantic_duplicate(client,topic,used): raise RuntimeError("Generated topic failed semantic duplicate check.")
    return topic


def get_next_topic():
    pending=_pending()
    if pending and not _similar(pending,_used()):
        print(f"🎯 QUEUED TOPIC: {pending}"); return pending
    if pending:
        print("⚠️ Queued topic is now a duplicate; discarding it.")
        try: os.remove(NEXT_TOPIC_PATH)
        except OSError: pass
    for attempt in range(1,11):
        try:
            topic=_generate_new_topic()
            if _save_pending(topic):
                print(f"📌 NEW TOPIC QUEUED: {topic}"); return topic
        except Exception as error:
            print(f"⚠️ Topic attempt {attempt}/10 failed: {error}")
    raise RuntimeError("Could not generate a unique entertainment-first topic.")


def save_next_short(next_short):
    topic=_clean_topic(next_short)
    if not topic or _similar(topic,_used()): return False
    return _save_pending(topic)


def commit_topic(topic):
    topic=_clean_topic(topic)
    if not topic: raise RuntimeError("Cannot commit an empty topic.")
    used=_used()
    if not any(_key(item)==_key(topic) for item in _topic_records(used)):
        used.append(topic)
        _atomic_write(USED_TOPICS_PATH,used[-500:])
    pending=_pending()
    if pending and _key(pending)==_key(topic):
        try: os.remove(NEXT_TOPIC_PATH)
        except OSError: pass
    return True


def clear_next_topic():
    try: os.remove(NEXT_TOPIC_PATH)
    except OSError: pass
    return True
