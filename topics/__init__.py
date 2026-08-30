"""Entertainment-first everyday-curiosity topic engine."""
from __future__ import annotations
import json, os, re, time
from pathlib import Path
from google import genai
from google.genai import types
from topic_history import is_new_topic, published_topics

_ROOT=Path(__file__).resolve().parent.parent
_USED_TOPICS_PATH=_ROOT/"used_topics.json"
_PENDING_PREFIX="__MINT_PENDING_NEXT_TOPIC__::"
MODEL="gemini-flash-lite-latest"

_BANNED=("permafrost","tundra","tectonic","geological","geology","quantum","particle physics","astrophysics","cosmology","black hole","neutron star","supernova","dark matter","dark energy","subduction","plate boundary","ice wedge","brine pocket","crystal lattice","electromagnetic field","entropy","thermodynamics","microcrack","gravitational wave","neutrino","gene expression","chromosome","mitochondria","atmospheric circulation","ocean current","radiative forcing","fracture mechanics","thermal cracks","material fatigue","periglacial","seismic","magnetohydrodynamic","fluid dynamics","cryogenic","crystallography","geophysical","cell tower","cellular positioning","gps positioning","rf positioning","triangulation","trilateration")
_FORBIDDEN=("the science of","the physics of","the biology of","the history of","the neuroscience of","study of","mechanism of","top 5","top 10","facts about","interesting facts","did you know","benefits of","importance of","complete guide","ultimate guide","what is","what are")
_SIGNALS=("phone","battery","charger","charging","screen","wifi","wi-fi","headphone","earbuds","voice","recording","speaker","fan","mirror","shower","toothpaste","orange juice","onion","popcorn","milk","coffee","tea","food","taste","smell","spicy","mosquito","sneeze","hiccup","yawn","sleep","alarm","dream","skin","water","ice","cold","hot","sweat","hair","clothes","static","shock","door","window","glass","soap","bubble","bread","egg","rice","salt","sugar","fridge","freezer","car","traffic","seatbelt","tire","keyboard","computer","laptop","remote","light","shadow","rain","umbrella","pillow","blanket","shoe","paper","pen","bag","bottle","cup","echo","sound","nose","mouth","teeth","tears","breath","blink","goosebumps","fingers","hands","laundry","oven","stove","microwave","toaster","candle","towel","sink","tap","socks","float","floats","soda","kettle","boil","boiling","steam","hiss","pitch","whistle","can","pasta","spaghetti","noodle","noodles","banana","bananas","garlic","toast","cheese","butter","potato","potatoes","apple","apples","dough","yeast","meat","chocolate","ice cream","cereal","jam","honey","ketchup","mustard","plate","pan","pot","knife","fork","spoon","bowl","mug","straw","lid","zipper","shoelace","shirt","jeans","sock","sponge","brush","comb","razor","drain","toilet","shampoo","deodorant","perfume","paint","rust","metal","wood","plastic","rubber","magnet","coin","key","lock","hinge","wheel","brake","engine","seat","road","bus","train","airplane","helmet","ball","bounce","break","snap","crack","bruise","green","sink","stick","melt","burn","rise","pop","fog","squeak","stale","spill","drip","leak")

_PROMPT="""You create topics for a highly entertaining YouTube Shorts channel.
CHANNEL PROMISE: Things ordinary people experience all the time but almost never stop to ask why.
Choose ONE NEW familiar, visually interesting everyday mystery. The viewer should instantly recognise it and think: Wait... why DOES that happen?
Science is the explanation, NEVER the packaging. Reject academic subjects, generic facts, lists, countdowns, medical advice, politics, conspiracy, fearbait, broad subjects, and anything difficult to show.
The topic will be spoken aloud as a final teaser in a 45-second Short. Keep it VERY short: 3 to 7 words total.
IMPORTANT: Generate an original topic from your own reasoning. Do NOT copy, reuse, or select a topic from examples, fallback lists, or previous topics.
Return ONLY one short curiosity question. No quotes, numbering, explanation, or question mark.
Previous topics:
{previous}"""

def _clean_topic(value):
    text=str(value or "").strip(); text=re.sub(r"```(?:text|json)?","",text,flags=re.I).strip(); text=text.replace('"',"").replace("'","")
    text=re.sub(r"^(topic|next topic|next_short|next short)\s*:\s*","",text,flags=re.I); text=re.sub(r"^\s*\d+[.)\-:]\s*","",text)
    return " ".join(text.split()).rstrip(".!? ").strip()

def _key(value): return " ".join(re.sub(r"[^a-z0-9]+"," ",_clean_topic(value).lower()).split())

def _is_everyday_topic(value):
    text=_clean_topic(value).lower()
    if not text or any(x in text for x in _BANNED) or any(x in text for x in _FORBIDDEN): return False
    if not re.match(r"^(why|how)\s+.+",text): return False
    words=re.findall(r"\b[\w'-]+\b",text)
    if not 3<=len(words)<=7:return False
    if any(x in text for x in (" and why "," and how "," or why "," or how ")):return False
    tokens=set(words)
    for signal in _SIGNALS:
        if " " in signal:
            if signal in text:return True
        elif signal in tokens or signal+"s" in tokens or (signal.endswith("s") and signal[:-1] in tokens):return True
    return False

def _read_used():
    try:
        if not _USED_TOPICS_PATH.exists():return []
        data=json.loads(_USED_TOPICS_PATH.read_text(encoding="utf-8")); return [str(x) for x in data] if isinstance(data,list) else []
    except Exception:return []

def _write_used(items):
    tmp=_USED_TOPICS_PATH.with_suffix(".tmp"); tmp.write_text(json.dumps(items,indent=2,ensure_ascii=False)+"\n",encoding="utf-8"); tmp.replace(_USED_TOPICS_PATH)

def _consume_pending():
    items=_read_used(); pending=""; clean=[]
    for item in items:
        if item.startswith(_PENDING_PREFIX):
            if not pending:pending=_clean_topic(item[len(_PENDING_PREFIX):])
        else:clean.append(item)
    if pending:
        _write_used(clean); print("🔗 CONTINUING FROM PREVIOUS SHORT"); print(f"Next topic: {pending}")
    return pending

def _generate_topic(used):
    key=os.environ.get("GEMINI_API_KEY")
    if not key:raise RuntimeError("GEMINI_API_KEY is missing.")
    client=genai.Client(api_key=key); prompt=_PROMPT.format(previous="\n".join(used[-100:]))
    for attempt in range(1,11):
        try:
            response=client.models.generate_content(model=MODEL,contents=prompt,config=types.GenerateContentConfig(temperature=1.1))
            candidate=_clean_topic(getattr(response,"text","")); print(f"🧠 Topic attempt {attempt}/10: {candidate}")
            if not _is_everyday_topic(candidate):print("⚠️ Rejected: not a valid short everyday curiosity.");continue
            if any(_key(candidate)==_key(x) for x in used) or not is_new_topic(candidate):print("⚠️ Rejected: duplicate or near-duplicate topic.");continue
            return candidate
        except Exception as error:
            print(f"⚠️ Topic attempt failed: {error}")
            if attempt<10:time.sleep(min(2*attempt,8))
    raise RuntimeError("Gemini could not generate a valid new short everyday-curiosity topic after 10 attempts; no static topic fallback is permitted.")

def get_next_topic():
    pending=_consume_pending()
    if pending and _is_everyday_topic(pending) and is_new_topic(pending):return pending
    if pending:print(f"⚠️ Discarding already-covered or stale continuation topic: {pending}")
    used=[x for x in _read_used() if not x.startswith(_PENDING_PREFIX)] + published_topics()
    return _generate_topic(used)

def save_next_short(next_short):
    topic=_clean_topic(next_short); items=[x for x in _read_used() if not x.startswith(_PENDING_PREFIX)]
    if not _is_everyday_topic(topic):raise RuntimeError(f"Refusing to queue invalid continuation topic: {topic}")
    if any(_key(topic)==_key(x) for x in items) or not is_new_topic(topic):raise RuntimeError(f"Refusing to queue duplicate or near-duplicate continuation topic: {topic}")
    items.append(_PENDING_PREFIX+topic); _write_used(items); print(f"🔗 Exact next-video topic: {topic}"); return topic

def commit_topic(topic):
    topic=_clean_topic(topic); items=_read_used(); key=_key(topic); pending=[x for x in items if x.startswith(_PENDING_PREFIX)]; committed=[x for x in items if not x.startswith(_PENDING_PREFIX)]
    if not any(_key(x)==key for x in committed):committed.append(topic)
    _write_used(committed+pending); print(f"📌 Committed topic: {topic}"); return True

def validate_topic_for_pipeline(topic,used=None,check_duplicate=True):
    if not _is_everyday_topic(topic):return False
    if check_duplicate:
        pool=list(used) if used is not None else _read_used()
        if any(_key(topic)==_key(x) for x in pool if not x.startswith(_PENDING_PREFIX)):return False
        if not is_new_topic(topic):return False
    return True
