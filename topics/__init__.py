"""Entertainment-first everyday-curiosity topic engine."""
from __future__ import annotations
import json, os, re, time
from pathlib import Path
from google import genai
from google.genai import types
from topic_history import find_duplicate, is_new_topic, published_topics

_ROOT=Path(__file__).resolve().parent.parent
_USED_TOPICS_PATH=_ROOT/"used_topics.json"
_PENDING_PREFIX="__MINT_PENDING_NEXT_TOPIC__::"
_RETIRED_TOPIC_KEYS={"why do onions make you cry","why onions make you cry"}
MODEL="gemini-flash-lite-latest"

_BANNED=("permafrost","tundra","tectonic","geological","geology","quantum","particle physics","astrophysics","cosmology","black hole","neutron star","supernova","dark matter","dark energy","subduction","plate boundary","ice wedge","brine pocket","crystal lattice","electromagnetic field","entropy","thermodynamics","microcrack","gravitational wave","neutrino","gene expression","chromosome","mitochondria","atmospheric circulation","ocean current","radiative forcing","fracture mechanics","thermal cracks","material fatigue","periglacial","seismic","magnetohydrodynamic","fluid dynamics","cryogenic","crystallography","geophysical","cell tower","cellular positioning","gps positioning","rf positioning","triangulation","trilateration")
_FORBIDDEN=("the science of","the physics of","the biology of","the history of","the neuroscience of","study of","mechanism of","top 5","top 10","facts about","interesting facts","did you know","benefits of","importance of","complete guide","ultimate guide","what is","what are")
_SIGNALS=("phone","battery","charger","charging","screen","wifi","wi-fi","headphone","earbuds","voice","recording","speaker","fan","mirror","shower","toothpaste","orange juice","onion","popcorn","milk","coffee","tea","food","taste","smell","spicy","mosquito","sneeze","hiccup","yawn","sleep","alarm","dream","skin","water","ice","cold","hot","sweat","hair","clothes","static","shock","door","window","glass","soap","bubble","bread","egg","rice","salt","sugar","fridge","freezer","car","traffic","seatbelt","tire","keyboard","computer","laptop","remote","light","shadow","rain","umbrella","pillow","blanket","shoe","echo","sound","nose","mouth","teeth","tears","breath","blink","goosebumps","fingers","hands","laundry","oven","stove","microwave","toaster","candle","towel","sink","tap","socks","float","floats","soda","kettle","boil","boiling","steam","hiss","pitch","whistle","can","pasta","spaghetti","noodle","noodles","banana","bananas","garlic","toast","cheese","butter","potato","potatoes","apple","apples","dough","yeast","meat","chocolate","ice cream","cereal","jam","honey","ketchup","mustard","plate","pan","pot","knife","fork","spoon","bowl","mug","straw","lid","zipper","shoelace","shirt","jeans","sock","sponge","brush","comb","razor","drain","toilet","shampoo","deodorant","perfume","paint","rust","metal","wood","plastic","rubber","magnet","coin","key","lock","hinge","wheel","brake","engine","seat","road","bus","train","airplane","helmet","ball","bounce","break","snap","crack","bruise","green","sink","stick","melt","burn","rise","pop","fog","squeak","stale","spill","drip","leak")

_FALLBACK_TOPICS=("Why do receipts fade", "Why do shoelaces come undone", "Why does toast pop up", "Why do bubbles shimmer", "Why does popcorn pop", "Why do wet towels smell", "Why does soap get slippery", "Why do windows collect drops", "Why does bread go stale", "Why do bananas brown", "Why does rice stick together", "Why does pasta foam", "Why does cheese melt", "Why does butter soften", "Why do socks disappear", "Why do clothes cling", "Why does static make hair rise", "Why do zippers get stuck", "Why do keys jingle", "Why do coins smell", "Why does wood creak", "Why does plastic crackle", "Why do doors squeak", "Why do hinges squeak", "Why does glass fog up", "Why do mirrors streak", "Why does a kettle whistle", "Why does steam fog glasses", "Why does water bead", "Why do ice cubes float", "Why does soda fizz", "Why does a straw whistle", "Why do balloons stick", "Why does rubber smell", "Why does metal feel cold", "Why does a shadow move", "Why does rain smell", "Why do puddles disappear", "Why do umbrellas flip", "Why do pillows flatten", "Why do blankets cling", "Why do shoes squeak", "Why does a tire lose air", "Why do brakes squeal", "Why does a car windshield fog", "Why do seatbelts lock", "Why does a remote need pointing", "Why does a keyboard click", "Why do headphones tangle", "Why does a phone vibrate", "Why does a screen attract fingerprints", "Why do chargers get warm", "Why does a fan wobble", "Why does a microwave hum", "Why does an oven smell", "Why does a toaster smell", "Why do candles flicker", "Why does a flame lean", "Why do paper clips stick", "Why does tape lose stickiness", "Why does a sponge expand", "Why does a brush shed", "Why do combs collect hair", "Why does shampoo foam", "Why does toothpaste foam", "Why do tears taste salty", "Why do fingers wrinkle", "Why do goosebumps appear", "Why do we blink", "Why does a sneeze happen", "Why do hiccups happen", "Why does a yawn spread", "Why does cold air hurt", "Why does hot food smell stronger", "Why does coffee smell stronger hot", "Why does chocolate melt quickly", "Why does honey crystallize", "Why does jam get sticky", "Why does ketchup resist pouring", "Why does mustard stain", "Why does an apple brown", "Why does garlic smell linger", "Why does toast smell good", "Why does dough rise", "Why does bread crack", "Why does an egg shell crack", "Why does a spoon feel colder", "Why does a plate get hot", "Why does a mug leave a ring", "Why does a sink drain slowly", "Why does a tap drip", "Why does a toilet swirl", "Why does shampoo smell linger", "Why does perfume spread", "Why does rust form", "Why does paint peel", "Why does a lock jam", "Why does a zipper catch")

def _clean_topic(value):
    text=str(value or "").strip(); text=re.sub(r"```(?:text|json)?","",text,flags=re.I).strip(); text=text.replace('"',"").replace("'","")
    text=re.sub(r"^(topic|next topic|next_short|next short)\s*:\s*","",text,flags=re.I); text=re.sub(r"^\s*\d+[.)\-:]\s*","",text)
    return " ".join(text.split()).rstrip(".!? ").strip()

def _key(value): return " ".join(re.sub(r"[^a-z0-9]+"," ",_clean_topic(value).lower()).split())

def _is_everyday_topic(value):
    text=_clean_topic(value).lower()
    if _key(text) in _RETIRED_TOPIC_KEYS: return False
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

def _pending_topics(items=None):
    items = _read_used() if items is None else list(items)
    pending=[]; seen=set()
    for x in items:
        if not isinstance(x, str) or not x.startswith(_PENDING_PREFIX): continue
        topic=_clean_topic(x[len(_PENDING_PREFIX):]); key=_key(topic)
        if topic and key and key not in seen: pending.append(topic); seen.add(key)
    return pending

def _repair_pending_state(items=None):
    raw=_read_used() if items is None else list(items); pending=_pending_topics(raw)
    if len(pending)<=1:return pending[0] if pending else ""
    authoritative=pending[-1]; committed=[x for x in raw if not (isinstance(x,str) and x.startswith(_PENDING_PREFIX))]
    _write_used(committed+[_PENDING_PREFIX+authoritative]); print(f"🛠️ Repaired multiple pending continuations; keeping: {authoritative}"); return authoritative

def _consume_pending():
    pending_topics=_pending_topics(); pending=pending_topics[0] if pending_topics else ""
    if pending: print("🔗 CONTINUING FROM PREVIOUS SHORT"); print(f"Next topic: {pending}")
    return pending

def _candidate_is_new(candidate, used):
    if not _is_everyday_topic(candidate): return False
    pool=list(used or [])+published_topics()
    if any(_key(candidate)==_key(x) for x in pool): return False
    return is_new_topic(candidate, threshold=0.82)

def _deterministic_fallback(used):
    start=(int(time.time())//60) % len(_FALLBACK_TOPICS)
    for offset in range(len(_FALLBACK_TOPICS)):
        candidate=_clean_topic(_FALLBACK_TOPICS[(start+offset)%len(_FALLBACK_TOPICS)])
        if _candidate_is_new(candidate, used):
            print(f"🛟 Topic fallback selected: {candidate}")
            return candidate
    raise RuntimeError("Topic engine exhausted its deterministic fallback pool; manual topic maintenance is required.")

def _generate_topic(used):
    key=os.environ.get("GEMINI_API_KEY")
    if not key: return _deterministic_fallback(used)
    client=genai.Client(api_key=key); prompt=_PROMPT.format(previous="\n".join(used[-30:]) or "(none)")
    for attempt in range(1,11):
        try:
            response=client.models.generate_content(model=MODEL,contents=prompt,config=types.GenerateContentConfig(temperature=1.1))
            candidate=_clean_topic(getattr(response,"text","")); print(f"🧠 Topic attempt {attempt}/10: {candidate}")
            if not _candidate_is_new(candidate, used): print("⚠️ Rejected: invalid, duplicate, or near-duplicate topic."); continue
            return candidate
        except Exception as error:
            print(f"⚠️ Topic attempt failed: {error}")
            if attempt<10:time.sleep(min(2*attempt,8))
    print("⚠️ Gemini topic generation exhausted 10 attempts; switching to deterministic unused-topic fallback.")
    return _deterministic_fallback(used)

def get_next_topic():
    items=_read_used(); pending=_repair_pending_state(items) or _consume_pending()
    if pending and _is_everyday_topic(pending): return pending
    if pending:
        print(f"⚠️ Discarding invalid continuation topic: {pending}")
        items=[x for x in items if not (isinstance(x,str) and x.startswith(_PENDING_PREFIX))]; _write_used(items)
    used=[_clean_topic(x[len(_PENDING_PREFIX):]) if isinstance(x,str) and x.startswith(_PENDING_PREFIX) else x for x in _read_used()]
    used+=published_topics(); return _generate_topic(used)

def reserve_next_short(next_short,current_topic=""):
    topic=_clean_topic(next_short); raw_items=_read_used(); current_key=_key(current_topic)
    existing_pending=_pending_topics(raw_items); foreign_pending=next((x for x in existing_pending if _key(x)!=current_key),"")
    if foreign_pending: raise RuntimeError(f"Cannot reserve a new continuation while one is pending: {foreign_pending}")
    committed=[x for x in raw_items if not (isinstance(x,str) and x.startswith(_PENDING_PREFIX))]; used=[current_topic]; used.extend(committed)
    if not validate_topic_for_pipeline(topic,used=used,check_duplicate=True):
        topic=_generate_topic(used); print(f"🛠️ Repaired and reserved continuation topic: {topic}")
    if existing_pending and all(_key(x)==current_key for x in existing_pending):
        _write_used(committed); print(f"🔓 Consumed current pending topic before reserving next: {current_topic}")
    return save_next_short(topic)

def save_next_short(next_short):
    topic=_clean_topic(next_short); raw_items=_read_used(); existing_pending=_pending_topics(raw_items)
    items=[x for x in raw_items if not x.startswith(_PENDING_PREFIX)]
    if not _is_everyday_topic(topic):raise RuntimeError(f"Refusing to queue invalid continuation topic: {topic}")
    history_duplicate=find_duplicate(topic,threshold=0.82); pending_duplicate=any(_key(topic)==_key(x) for x in existing_pending)
    if existing_pending and pending_duplicate:
        print(f"🔗 Pending continuation already matches requested topic: {existing_pending[0]}")
        return existing_pending[0]
    if existing_pending:
        # A resumed Publish Shorts run has already consumed the current pending topic
        # logically, but its artifact is restored without calling get_next_topic().
        # Replace exactly one stale pending reservation with the newly reserved topic.
        # Normal fresh runs reach this function with no pending reservation, so this
        # does not weaken the ordinary duplicate/concurrency guard.
        if len(existing_pending) == 1:
            old_pending = existing_pending[0]
            print(f"🔓 Replacing consumed pending continuation: {old_pending} → {topic}")
            items.append(_PENDING_PREFIX+topic); _write_used(items); return topic
        raise RuntimeError(f"Refusing to replace multiple pending continuation topics: {existing_pending}")
    if any(_key(topic)==_key(x) for x in items) or history_duplicate:raise RuntimeError(f"Refusing to queue duplicate or near-duplicate continuation topic: {topic}")
    items.append(_PENDING_PREFIX+topic); _write_used(items); print(f"🔗 Exact next-video topic: {topic}"); return topic

def commit_topic(topic):
    topic=_clean_topic(topic); items=_read_used(); key=_key(topic); committed=[x for x in items if not (isinstance(x,str) and x.startswith(_PENDING_PREFIX))]
    if not any(_key(x)==key for x in committed):committed.append(topic)
    pending=_repair_pending_state(items)
    if pending and _key(pending)==key:pending=""
    _write_used(committed+([_PENDING_PREFIX+pending] if pending else [])); print(f"📌 Committed topic: {topic}"); return True

def validate_topic_for_pipeline(topic,used=None,check_duplicate=True):
    if not _is_everyday_topic(topic):return False
    if check_duplicate:
        pool=list(used) if used is not None else _read_used(); normalized_pool=[_clean_topic(x[len(_PENDING_PREFIX):]) if isinstance(x,str) and x.startswith(_PENDING_PREFIX) else x for x in pool]
        if any(_key(topic)==_key(x) for x in normalized_pool):return False
        if not is_new_topic(topic,threshold=0.82):return False
    return True

_PROMPT="""You create topics for a highly entertaining YouTube Shorts channel.
CHANNEL PROMISE: Things ordinary people experience all the time but almost never stop to ask why.
Choose ONE NEW familiar, visually interesting everyday mystery. The viewer should instantly recognise it and think: Wait... why DOES that happen?
Science is the explanation, NEVER the packaging. Reject academic subjects, generic facts, lists, countdowns, medical advice, politics, conspiracy, fearbait, broad subjects, and anything difficult to show.
The topic will be spoken aloud as a final teaser in a 45-second Short. Keep it VERY short: 3 to 7 words total.
IMPORTANT: Generate an original topic from your own reasoning. Do NOT copy, reuse, or select a topic from examples, fallback lists, or previous topics.
Return ONLY one short curiosity question. No quotes, numbering, explanation, or question mark.
Previously covered topics are ONLY an exclusion list. Do not use them as inspiration and do not stay in their subject areas. Deliberately choose a different everyday category such as home, clothing, food, objects, sounds, weather, body reactions, travel, or technology. A shared object word alone does not make a topic invalid; only avoid the same curiosity or near-rewording.
Previously covered topics:
{previous}"""
