"""Narration-first Story Shorts generator for the independent second production line."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from . import entertainment as _base

STORY_MIN_WORDS = 80
STORY_MAX_WORDS = 120
STORY_SCENE_WORD_BUDGETS = ((8,18),(7,22),(7,22),(7,22),(7,22),(7,22),(10,28))
STORY_FORMATS = (
    {"name":"rise_from_nothing","direction":"Show the person before success, the obstacle, the decisive attempt, and the consequence. Never turn it into a generic motivational speech."},
    {"name":"one_decision","direction":"Build around one decision that changed the person's direction. Delay the consequence until late in the Short."},
    {"name":"before_they_were_famous","direction":"Start with the ordinary, rejected, broke, unknown, or overlooked version of the person. Delay the famous identity reveal until curiosity is established."},
    {"name":"impossible_odds","direction":"Open with the apparent impossibility, then reveal how the person responded. Keep the human stakes concrete."},
    {"name":"strange_turning_point","direction":"Center the story on an unusual event, coincidence, failure, encounter, or setback that changed the person's life."},
)
GENERIC_OPENERS=re.compile(r"^(?:today|here(?:'s| is)|welcome back|hey guys|guys|listen up|okay guys|alright guys|in this video|today we're)",re.I)
CAPTION_STOP={"the","a","an","and","or","but","so","to","of","in","on","at","for","with","from","was","were","is","are","this","that","it","he","she","they","his","her","their","had","have","has","as","by","not","what","when","who","how","then","just","one","more","because","after","before","into","than","very","would","could","did","do","does","its","their","there","where","which","while","than"}
CAPTION_PRIORITY={"rejected":10,"rejection":10,"failed":10,"failure":10,"broke":10,"poor":9,"unknown":9,"ignored":9,"mocked":10,"accent":10,"foreign":10,"impossible":10,"risk":9,"risky":9,"decision":9,"choice":9,"refused":9,"denied":9,"struggle":9,"struggled":9,"obstacle":9,"chance":8,"opportunity":8,"changed":10,"turning":10,"moment":8,"secret":8,"survived":9,"won":10,"victory":10,"champion":10,"famous":9,"star":9,"dominated":9,"became":8,"finally":8,"against":8,"nothing":9,"dream":7}

def _load_recent_history(limit=30):
    path=Path(__file__).resolve().parent.parent/"story_topic_history.json"
    try:
        rows=json.loads(path.read_text(encoding="utf-8")); return [x for x in rows[-limit:] if isinstance(x,dict)] if isinstance(rows,list) else []
    except Exception:return []

def _format_for(topic,number_hint=0):
    digest=hashlib.sha256(f"{topic}|{number_hint}".encode()).digest(); return STORY_FORMATS[int.from_bytes(digest[:4],"big")%len(STORY_FORMATS)]

def _words(text): return re.findall(r"\b[\w'-]+\b",str(text or ""))

def _content_words(text):
    stop={"the","a","an","and","or","but","so","to","of","in","on","at","for","with","from","was","were","is","are","this","that","it","he","she","they","his","her","their","had","have","has","as","by","not","what","when","who","how","then","just","one","more","because","after","before","into","than","very","would","could","did","do","does"}
    return [w.lower().strip(".,!?;:'\"()[]{}") for w in _words(text) if w.lower() not in stop and len(w)>2]

def _last_sentence(text):
    parts=[x.strip() for x in re.split(r"(?<=[.!?])\s+",str(text or "").strip()) if x.strip()]
    return parts[-1] if parts else str(text or "").strip()

def _first_sentence(text):
    parts=[x.strip() for x in re.split(r"(?<=[.!?])\s+",str(text or "").strip()) if x.strip()]
    return parts[0] if parts else str(text or "").strip()

def _sentence_parts(text):
    """Split narration into spoken sentences for deterministic scene validation."""
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+",str(text or "").strip()) if x.strip()]

def _stem(word):
    word=re.sub(r"[^a-z0-9]","",str(word or "").lower())
    if len(word)<5: return word
    for suffix in ("ingly","edly","ation","ments","ment","ness","less","ing","ers","ies","ied","ed","es","s"):
        if word.endswith(suffix) and len(word)-len(suffix)>=4: return word[:-len(suffix)]
    return word

def _loop_overlap(opening,ending):
    opening_terms={w for w in _content_words(opening) if len(w)>3}
    closing_terms={w for w in _content_words(ending) if len(w)>3}
    exact=opening_terms & closing_terms
    if len(exact)>=2: return sorted(exact)
    stemmed={_stem(w):w for w in closing_terms}
    matches=[]
    for w in opening_terms:
        if _stem(w) in stemmed: matches.append(stemmed[_stem(w)])
    return sorted(set(matches))

def _validate_loop(scenes):
    opening=_first_sentence(str(scenes[0].get("narration","")).strip())
    ending=_last_sentence(str(scenes[-1].get("narration","")).strip())
    if not opening or not ending: raise RuntimeError("Story loop requires opening and ending narration.")
    overlap=_loop_overlap(opening,ending)
    if len(overlap)<2: raise RuntimeError("Story loop seam is too weak: final sentence must echo at least two distinctive opening-hook words.")
    return overlap

def _caption_highlights(narration, scene_index):
    words=_words(narration); candidates=[]
    for position,raw in enumerate(words):
        word=raw.lower().strip(".,!?;:'\"()[]{}")
        if len(word)<4 or word in CAPTION_STOP: continue
        score=CAPTION_PRIORITY.get(word,0)
        if position==0: score+=2
        if position==len(words)-1: score+=1
        if word.isupper(): score+=1
        candidates.append((score,-position,word))
    if not candidates: return []
    candidates.sort(reverse=True); return [candidates[0][2]]

def _visual_role(scene_index, story_format):
    roles=(
        "SCROLL-STOP HOOK: show the most surprising concrete version of the person/situation; if this is before_they_were_famous, prefer early-life/unknown-era identity and delay the famous reveal.",
        "IDENTITY + STAKES: establish who this person was and what they wanted or risked; prefer authentic person media when available.",
        "OBSTACLE: make the rejection, failure, limitation, poverty, criticism, or impossible situation visually concrete; no generic filler.",
        "DECISION/ACTION: show the concrete choice, attempt, work, training, move, encounter, or opportunity that changed the trajectory.",
        "ESCALATION: show a meaningful consequence or second obstacle; use a new visual subject/location rather than repeating a portrait.",
        "TURNING POINT: show the event or achievement that changes the trajectory; prioritize authentic person media or directly relevant context.",
        "PAYOFF: show the recognizable result and emotional resolution; use the strongest identity/payoff visual, then preserve a clean final frame for the spoken loop.",
    )
    return roles[min(scene_index,len(roles)-1)]

def _clean_scenes(scenes, story_format_name=""):
    for index,scene in enumerate(scenes):
        narration=_base._clean(scene.get("narration","")); narration=re.sub(r"^(?:today|welcome back|hey guys|guys),?\s+","",narration,flags=re.I)
        scene["narration"]=narration; scene["subtitle_text"]=narration; scene["visual_dependency"]="none"
        scene["caption_highlights"]=_caption_highlights(narration,index)
        scene["emphasis_word"]=(scene["caption_highlights"] or [""])[0]
        scene["retention_beat"]=("hook" if index==0 else "payoff" if index==6 else "story_progression")
        scene["visual_role"]=_visual_role(index,story_format_name)
        scene["visual_change_priority"]="high" if index in (0,2,4,6) else "medium"
        for visual_index,visual in enumerate(scene.get("visuals") or []):
            if isinstance(visual,dict):
                visual["spoken_line"]=narration; visual["visual_dependency"]="none"; visual["visual_role"]=_visual_role(index,story_format_name)
                visual["visual_priority"]="identity_or_story_critical" if index in (0,1,2,5,6) else "story_support"
                visual["visual_action"]=("Use authentic real-person media when available for identity moments. Otherwise use Pexels/Pixabay footage or photos that directly depict the narrated event, era, occupation, location, or action. Never use generic filler, unrelated people, empty venues, or decorative footage. Shot 2 must advance or reframe the beat rather than duplicate Shot 1." if visual_index==1 else "Use authentic real-person media when available. Otherwise use Pexels/Pixabay footage or photos that concretely establish the narrated beat. Avoid generic portraits, unrelated people, and decorative backgrounds.")
                visual["must_not_show"]=["generic filler","unrelated people","empty stadium or office unless explicitly narrated","decorative cinematic background","duplicate of shot 1"]
    return scenes

def _normalize_story(result,topic):
    if not isinstance(result,dict): raise RuntimeError("Gemini story response was not an object.")
    result["topic"]=_base._clean(topic); scenes=result.get("scene_plan")
    if not isinstance(scenes,list): raise RuntimeError("Gemini story response is missing scene_plan.")
    return result

def _is_gemini_quota_error(error):
    text = str(error or "").lower()
    return (
        "resource_exhausted" in text
        or "quota exceeded" in text
        or "generaterequestsperday" in text
        or "quota_id" in text
        or "rate limit" in text
        or "429" in text
    )


def _validate_story(scenes):
    """Validate the Story Shorts creative contract before expensive TTS/media work."""
    if not isinstance(scenes,list) or len(scenes)!=7:
        raise RuntimeError("Story contract requires exactly 7 scenes.")
    total=0
    for index,scene in enumerate(scenes):
        if not isinstance(scene,dict): raise RuntimeError(f"Story scene {index+1} is not an object.")
        narration=_base._clean(scene.get("narration",""))
        count=len(_words(narration)); total+=count
        low,high=STORY_SCENE_WORD_BUDGETS[index]
        if count<low or count>high:
            raise RuntimeError(f"Story scene {index+1} word count {count} outside {low}-{high}.")
        if index==0 and GENERIC_OPENERS.search(narration):
            raise RuntimeError("Story Scene 1 uses a generic opener; require a curiosity hook.")
        if re.search(r"\b(?:subscribe|follow|like and subscribe|follow us|hit the follow)\b",narration,re.I):
            raise RuntimeError(f"Story scene {index+1} contains a CTA; narration must remain story-only.")
        if index==6 and len(_sentence_parts(narration))<2:
            raise RuntimeError("Story Scene 7 must contain payoff plus a natural loop sentence.")
        visuals=scene.get("visuals")
        if visuals is not None and not isinstance(visuals,list):
            raise RuntimeError(f"Story scene {index+1} visuals must be a list.")
    if total<STORY_MIN_WORDS or total>STORY_MAX_WORDS:
        raise RuntimeError(f"Story narration total {total} words outside {STORY_MIN_WORDS}-{STORY_MAX_WORDS}.")
    _validate_loop(scenes)
    return total

def generate_script(topic,config,research=None,extra_feedback=""):
    from google import genai
    from google.genai import types
    import time
    topic=_base._clean(topic)
    if not topic: raise RuntimeError("Story topic is empty.")
    recent=_load_recent_history(); number_hint=len(recent)+1; story_format=_format_for(topic,number_hint)
    recent_topics=[str(x.get("topic","")).strip() for x in recent if x.get("topic")]; recent_people=[str(x.get("person","")).strip() for x in recent if x.get("person")]
    client=genai.Client(api_key=_base._api_key())
    prompt=f"""STORY SHORTS MODE — RETENTION-FIRST NARRATION + SPOKEN LOOP.
SUBJECT: {topic}
STORY FORMAT: {story_format['name']}
FORMAT DIRECTION: {story_format['direction']}

Create exactly 7 scenes for a vertical YouTube Short about this person.
The story must stand on narration alone. Real-person photos/footage may be used for key identity or historical moments when available; supporting Pexels/Pixabay stock footage/images are atmosphere and context only. Viewers must never need a particular image, face, map, screenshot, or caption to understand the story.
TARGET: 80-120 spoken words. Aim for 95-110 words. Naturally paced. Every line must move the story forward.
SCENE BANDS: 1=8-18, 2=7-22, 3=7-22, 4=7-22, 5=7-22, 6=7-22, 7=10-28.

RETENTION ARCHITECTURE — CRITICAL:
- Scene 1 first 1-2 seconds must be a scroll-stopping contradiction, risk, rejection, mystery, or surprising claim. Do NOT open with the subject as a biography introduction.
- Make the first sentence short, concrete, and memorable. Prefer 2-4 distinctive content words that can be echoed naturally at the end.
- For BEFORE_THE_FAME stories, delay the famous identity reveal until curiosity is established.
- Scene 2 creates the curiosity gap and establishes stakes.
- Scene 3 makes the obstacle/rejection/failure concrete.
- Scene 4 shows a decision or action.
- Scene 5 escalates with a consequence, second setback, or higher stake. Do not merely restate Scene 3.
- Scene 6 delivers the turning point and starts the payoff.
- Scene 7 MUST contain EXACTLY TWO short spoken sentences: first sentence = emotional payoff/result; second sentence = natural loop callback. The second sentence must echo at least TWO distinctive content words from Scene 1's FIRST sentence. Do not make Scene 7 one long sentence joined by commas or semicolons.
- Every scene must add a new piece of information or change the viewer's understanding. No filler, generic inspiration, or repeated biography facts.
- Build a clear visual opportunity into each scene: person, era, location, occupation, object, action, or event that a stock search can actually depict.

VISUAL DIRECTION FIELDS:
For every visual object, provide a concrete visual_focus, visual_action, must_show and must_not_show. The visual must be useful even without captions. Shot 1 establishes the beat; Shot 2 advances/reframes it. Never request generic cinematic filler. Never use empty stadiums, random offices, unrelated horses, generic business people, or decorative landscapes unless the narration explicitly makes them relevant.

CAPTION DIRECTION:
Provide caption_highlights and emphasis_word for each scene. Highlights must be words that are actually spoken in that scene. Prefer high-impact words such as rejection, accent, broke, impossible, decision, failed, changed, champion, or the story's most concrete equivalent. Do not highlight articles, pronouns, filler, or random nouns just because they are available.

WORD-BUDGET RULE — CRITICAL:
- Write the complete story first, then make it concise.
- Prefer 95-110 words total.
- Never exceed 120 words.
- Do not add filler merely to increase word count.
- Before returning JSON, internally count every narration word. The seven scene narrations together MUST be between 80 and 120 words.
- If under 80, add one concise factual story detail that advances the story; never add motivational filler.

LOOP STORY RULE — CRITICAL:
- Scene 1's FIRST spoken sentence is the opening hook.
- Scene 7's FINAL SPOKEN SENTENCE must naturally call back to that FIRST SENTENCE.
- Echo at least TWO distinctive words from that opening sentence in the final sentence. Natural grammatical variants are acceptable.
- Do not simply repeat the entire hook verbatim.
- Do not say "watch again," "replay," "loop," "back to the beginning," or anything that exposes the editing trick.
- Do not use a next-topic teaser.
- Do NOT include a subscribe/follow CTA anywhere in the narration. The story ends on the loop sentence.

FACTUALITY:
- This is a factual story about a real person. Do not invent dialogue, private thoughts, dates, locations, achievements, causes, or dramatic details.
- Do not use quotation marks unless the quote is widely established and you are confident it is authentic; paraphrase whenever possible.
- If a famous anecdote is disputed, omit it.
- Do not exaggerate overnight success or claim one event caused an entire career unless genuinely supported.
- Prefer concrete, broadly established facts over trivia.

STYLE:
- Cinematic, conversational, emotionally engaging, concise.
- Sound like someone telling a friend an unbelievable true story, not reading Wikipedia.
- Use short sentences, contrast, curiosity gaps, and specific stakes.
- No welcome back, today's story, today we're talking about, in this video, or generic motivational filler.
- Do not say wait until the end or similar empty retention bait.
- Do not mention stock footage or visuals in narration.
- Do not make the story dependent on captions.

RECENT PEOPLE — avoid repeating them:
{chr(10).join('- '+x for x in recent_people[-15:]) or '- none'}
RECENT STORY SUBJECTS — avoid repeating or closely mirroring:
{chr(10).join('- '+x for x in recent_topics[-15:]) or '- none'}

Return the normal production JSON schema. Put the person's name in the topic/title metadata where appropriate, but keep the narration story-first.
{extra_feedback}"""
    last_error=None; story_attempts=max(int(getattr(_base,"MAX_ATTEMPTS",3)),8)
    for attempt in range(story_attempts):
        try:
            retry=""
            if last_error:
                retry=f"\nRETRY {attempt+1}: Rewrite ONLY the parts necessary to fix the validation error while preserving the strongest factual beats. TARGET 95-110 WORDS TOTAL; HARD LIMIT 80-120. Scene 1 must be a hard curiosity hook, not a biography opener. Scene 7 MUST be EXACTLY TWO spoken sentences: payoff first, loop callback second. The second sentence MUST echo TWO distinctive content words from Scene 1's FIRST sentence. Scene 7 must contain NO subscribe/follow CTA. Keep every scene within its stated word band. If the previous error is a scene word-count error, shorten or redistribute wording instead of adding filler. Previous error: {last_error}"
            response=client.models.generate_content(model=_base.MODEL_NAME,contents=prompt+retry,config=types.GenerateContentConfig(system_instruction=_base.SYSTEM_PROMPT,response_mime_type="application/json",response_json_schema=_base._build_schema(),temperature=.55))
            raw=getattr(response,"text",None)
            if not raw: raise RuntimeError("Gemini returned an empty story script.")
            result=_normalize_story(_base._parse(raw),topic)
            scenes=_clean_scenes(result.get("scene_plan") or [],story_format["name"]); _validate_story(scenes)
            result["scene_plan"]=scenes
            result["story_format"]=story_format["name"]; result["story_format_direction"]=story_format["direction"]; result["story_visual_mode"]="real_person_plus_atmosphere_v2"; result["story_factuality_policy"]="real-person-facts-no-invented-dialogue"; result["story_word_target"]={"min":STORY_MIN_WORDS,"max":STORY_MAX_WORDS}; result["story_loop_mode"]="spoken_hook_callback_v6_exact_two_sentences_no_cta"; result["story_retention_mode"]="hook_gap_obstacle_decision_escalation_payoff_v1"; result["story_visual_change_mode"]="beat_specific_14_shots_v1"; result["visual_dependency"]="none"
            total=sum(len(_words(s.get("narration",""))) for s in scenes); print(f"📖 Story Shorts narration validated: {total} words | format={story_format['name']} | retention=ON | loop=ON | CTA=OFF"); return result
        except Exception as exc:
            last_error=f"{type(exc).__name__}: {exc}"
            if _is_gemini_quota_error(exc):
                print("🛑 Gemini project/day quota exhausted — deferring Story Shorts generation without consuming the reserved subject.")
                raise RuntimeError(f"{STORY_GEMINI_QUOTA_DEFERRED}: Gemini project/day quota is exhausted; Story Shorts will resume on the next successful run.") from exc
            if attempt+1<story_attempts: print(f"⚠️ Story script attempt {attempt+1} rejected: {last_error}"); time.sleep(2)
    raise RuntimeError(f"STORY SCRIPT GENERATION FAILED after bounded retries. Last error: {last_error}")
