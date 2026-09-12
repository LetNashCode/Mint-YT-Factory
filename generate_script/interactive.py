"""Narration-first Story Shorts generator for the independent second production line."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from . import entertainment as _base

STORY_MIN_WORDS = 80
STORY_MAX_WORDS = 125
# Keep scene bands flexible enough for natural storytelling. The total-word
# contract is the primary pacing guard; Scene 7 is intentionally larger so the
# payoff, CTA, and spoken loop seam can all survive.
STORY_SCENE_WORD_BUDGETS = ((6,20),(7,20),(7,20),(7,20),(7,20),(7,20),(12,30))
STORY_FORMATS = (
    {"name":"rise_from_nothing","direction":"Show the person before success, the obstacle, the decisive attempt, and the consequence. Never turn it into a generic motivational speech."},
    {"name":"one_decision","direction":"Build around one decision that changed the person's direction. Delay the consequence until late in the Short."},
    {"name":"before_they_were_famous","direction":"Start with the ordinary, rejected, broke, unknown, or overlooked version of the person. Reveal the famous identity after curiosity is established."},
    {"name":"impossible_odds","direction":"Open with the apparent impossibility, then reveal how the person responded. Keep the human stakes concrete."},
    {"name":"strange_turning_point","direction":"Center the story on an unusual event, coincidence, failure, encounter, or setback that changed the person's life."},
)
GENERIC_OPENERS=re.compile(r"^(?:today|here(?:'s| is)|welcome back|hey guys|guys|listen up|okay guys|alright guys)",re.I)


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


def _ensure_story7_cta(text):
    """Insert a short CTA before the authored loop sentence when Gemini omits it."""
    text=_base._clean(text)
    if re.search(r"\bsubscribe\b",text,re.I) and re.search(r"\bfollow\b",text,re.I):
        return text
    sentences=[x.strip() for x in re.split(r"(?<=[.!?])\s+",text) if x.strip()]
    if not sentences:
        return "Subscribe and follow for more remarkable stories."
    cta="Subscribe and follow for more remarkable stories."
    if len(sentences)>=2:
        return " ".join(sentences[:-1]+[cta,sentences[-1]])
    return f"{cta} {sentences[0]}"


def _validate_loop(scenes):
    """Require a spoken loop seam while allowing the CTA immediately before it."""
    opening=str(scenes[0].get("narration","")).strip()
    ending=str(scenes[-1].get("narration","")).strip()
    if not opening or not ending: raise RuntimeError("Story loop requires opening and ending narration.")
    opening_terms=set(_content_words(_last_sentence(opening)))
    closing_terms=set(_content_words(_last_sentence(ending)))
    overlap=opening_terms & closing_terms
    if len(overlap)<2:
        raise RuntimeError("Story loop seam is too weak: final sentence must echo at least two distinctive opening-hook words.")
    final_sentences=[x.strip() for x in re.split(r"(?<=[.!?])\s+",ending) if x.strip()]
    cta_present=any(re.search(r"\bsubscribe\b",s,re.I) and re.search(r"\bfollow\b",s,re.I) for s in final_sentences[:-1])
    if not cta_present:
        raise RuntimeError("Story Scene 7 CTA must come before the final loop sentence.")
    return sorted(overlap)


def _validate_story(scenes):
    if len(scenes)!=7: raise RuntimeError("Story script must contain exactly 7 scenes.")
    total=sum(len(_words(s.get("narration",""))) for s in scenes)
    if not STORY_MIN_WORDS<=total<=STORY_MAX_WORDS: raise RuntimeError(f"Story narration length {total} outside {STORY_MIN_WORDS}-{STORY_MAX_WORDS} words.")
    for i,(low,high) in enumerate(STORY_SCENE_WORD_BUDGETS):
        count=len(_words(scenes[i].get("narration","")))
        if count<low or count>high: raise RuntimeError(f"Story Scene {i+1} has {count} words; expected {low}-{high}.")
    all_text=" ".join(str(s.get("narration","")) for s in scenes)
    if GENERIC_OPENERS.search(all_text): raise RuntimeError("Story script contains a generic social-media opener.")
    final=scenes[-1].get("narration","")
    if not re.search(r"\bsubscribe\b",final,re.I) or not re.search(r"\bfollow\b",final,re.I):
        raise RuntimeError("Story Scene 7 must contain subscribe and follow CTA.")
    loop_terms=_validate_loop(scenes)
    print(f"🔁 Story loop seam validated: opening/ending echo={', '.join(loop_terms[:5])}")


def _clean_scenes(scenes):
    for i,scene in enumerate(scenes):
        narration=_base._clean(scene.get("narration","")); narration=re.sub(r"^(?:today|welcome back|hey guys|guys),?\s+","",narration,flags=re.I)
        if i==6: narration=_ensure_story7_cta(narration)
        scene["narration"]=narration; scene["subtitle_text"]=narration; scene["visual_dependency"]="none"
        for visual in scene.get("visuals") or []:
            if isinstance(visual,dict):
                visual["spoken_line"]=narration; visual["visual_action"]="Use a real-person photo or footage for key identity moments when available; otherwise use relevant atmosphere/context stock footage."; visual["visual_dependency"]="none"
    return scenes


def _normalize_story(result,topic):
    """Story-specific normalization; deliberately bypasses Publish-only continuation logic."""
    if not isinstance(result,dict): raise RuntimeError("Gemini story response was not an object.")
    result["topic"]=_base._clean(topic)
    scenes=result.get("scene_plan")
    if not isinstance(scenes,list): raise RuntimeError("Gemini story response is missing scene_plan.")
    return result


def generate_script(topic,config,research=None,extra_feedback=""):
    from google import genai
    from google.genai import types
    import time
    topic=_base._clean(topic)
    if not topic: raise RuntimeError("Story topic is empty.")
    recent=_load_recent_history(); number_hint=len(recent)+1; story_format=_format_for(topic,number_hint)
    recent_topics=[str(x.get("topic","")).strip() for x in recent if x.get("topic")]; recent_people=[str(x.get("person","")).strip() for x in recent if x.get("person")]
    client=genai.Client(api_key=_base._api_key())
    prompt=f"""STORY SHORTS MODE — NARRATION FIRST + LOOP STORY.
SUBJECT: {topic}
STORY FORMAT: {story_format['name']}
FORMAT DIRECTION: {story_format['direction']}

Create exactly 7 scenes for a vertical YouTube Short about this person.
The story must stand on narration alone. Real-person photos/footage may be used for key identity or historical moments when available; supporting stock footage/images are atmosphere and context only. Viewers must never need a particular image, face, object, map, screenshot, or on-screen text to understand the story.
TARGET: {STORY_MIN_WORDS}-{STORY_MAX_WORDS} spoken words, naturally paced for roughly 32-44 seconds. Do not pad the story just to hit a number. Every line must move the story forward.
SCENE BANDS: 1={STORY_SCENE_WORD_BUDGETS[0][0]}-{STORY_SCENE_WORD_BUDGETS[0][1]}, 2={STORY_SCENE_WORD_BUDGETS[1][0]}-{STORY_SCENE_WORD_BUDGETS[1][1]}, 3={STORY_SCENE_WORD_BUDGETS[2][0]}-{STORY_SCENE_WORD_BUDGETS[2][1]}, 4={STORY_SCENE_WORD_BUDGETS[3][0]}-{STORY_SCENE_WORD_BUDGETS[3][1]}, 5={STORY_SCENE_WORD_BUDGETS[4][0]}-{STORY_SCENE_WORD_BUDGETS[4][1]}, 6={STORY_SCENE_WORD_BUDGETS[5][0]}-{STORY_SCENE_WORD_BUDGETS[5][1]}, 7={STORY_SCENE_WORD_BUDGETS[6][0]}-{STORY_SCENE_WORD_BUDGETS[6][1]}.

LOOP STORY RULE — CRITICAL:
- The Short must feel satisfying when played once AND when it immediately restarts.
- Scene 1 must open with a distinctive hook containing 2-4 memorable content words or a short phrase that can be echoed later.
- Scenes 2-6 tell the complete factual story and build to the payoff.
- Scene 7 must contain the concise subscribe/follow CTA BEFORE the final loop sentence.
- The FINAL SPOKEN SENTENCE of Scene 7 must naturally call back to the opening hook so that, when the video restarts, Scene 1 feels like the continuation of that final thought.
- Echo at least TWO distinctive words from the opening hook in the final sentence. Do not simply repeat the entire hook verbatim.
- Do not say "watch again," "replay," "loop," "back to the beginning," or anything that exposes the editing trick.
- Do not use a next-topic teaser.
- The loop must be created through narration/story wording, not captions or visuals.

IMPORTANT CTA RULE:
- Scene 7 MUST contain both the words "subscribe" and "follow".
- Put that CTA in a short sentence BEFORE the final loop sentence.
- The final loop sentence is NOT the CTA; it is the story's natural closing thought.
- Do not place the CTA after the loop sentence.

STORY ARC:
- Scene 1: hard hook. Start inside the most surprising moment or contradiction. Do not start with the person's name as a biography introduction unless the name itself creates curiosity. Make the hook distinctive enough to echo in Scene 7.
- Scene 2: establish who the person was and what was at stake.
- Scene 3: introduce the obstacle, rejection, failure, or impossible situation.
- Scene 4: show the decision, action, encounter, or attempt that changed the trajectory.
- Scene 5: escalate. Give one concrete consequence or setback before the payoff.
- Scene 6: reveal the turning point and what it led to. Avoid a generic motivational lecture.
- Scene 7: give the emotional payoff, place a short natural subscribe/follow CTA, then end on a single loop-closing sentence that echoes the opening hook.

FACTUALITY:
- This is a factual story about a real person. Do not invent dialogue, private thoughts, dates, locations, achievements, causes, or dramatic details.
- Do not use quotation marks unless the quote is widely established and you are confident it is authentic; paraphrase instead whenever possible.
- If a famous anecdote is disputed, omit it rather than presenting it as fact.
- Do not exaggerate overnight success or claim one event caused an entire career unless genuinely supported.
- Prefer concrete, broadly established facts over trivia.

STYLE:
- Cinematic, conversational, emotionally engaging, concise.
- Sound like someone telling a friend an unbelievable true story, not reading Wikipedia.
- Use short sentences, contrast, curiosity gaps, and specific stakes.
- No welcome back, today's story, today we're talking about, in this video, or generic motivational filler.
- Do not say wait until the end or similar empty retention bait.
- Do not mention stock footage or visuals.
- Do not make the story dependent on captions.
- Keep the final loop sentence short and natural; it should feel like the story's final thought, not an instruction to the editor.

RECENT PEOPLE — avoid repeating them:
{chr(10).join('- '+x for x in recent_people[-15:]) or '- none'}
RECENT STORY SUBJECTS — avoid repeating or closely mirroring:
{chr(10).join('- '+x for x in recent_topics[-15:]) or '- none'}

Return the normal production JSON schema. Put the person's name in the topic/title metadata where appropriate, but keep the narration story-first.
{extra_feedback}"""
    last_error=None
    for attempt in range(_base.MAX_ATTEMPTS):
        try:
            retry=f"\nFix this validation error without changing the subject. Preserve the complete story and keep the CTA before the final loop sentence: {last_error}" if last_error else ""
            response=client.models.generate_content(model=_base.MODEL_NAME,contents=prompt+retry,config=types.GenerateContentConfig(system_instruction=_base.SYSTEM_PROMPT,response_mime_type="application/json",response_json_schema=_base._build_schema(),temperature=.9))
            raw=getattr(response,"text",None)
            if not raw: raise RuntimeError("Gemini returned an empty story script.")
            result=_normalize_story(_base._parse(raw),topic)
            scenes=_clean_scenes(result.get("scene_plan") or []); _validate_story(scenes); result["scene_plan"]=scenes
            result["story_format"]=story_format["name"]; result["story_format_direction"]=story_format["direction"]; result["story_visual_mode"]="real_person_plus_atmosphere_v1"; result["story_factuality_policy"]="real-person-facts-no-invented-dialogue"; result["story_word_target"]={"min":STORY_MIN_WORDS,"max":STORY_MAX_WORDS}; result["story_loop_mode"]="spoken_hook_callback_v2"; result["visual_dependency"]="none"
            total=sum(len(_words(s.get("narration",""))) for s in scenes); print(f"📖 Story Shorts narration validated: {total} words | format={story_format['name']} | loop=ON | CTA=SAFE"); return result
        except Exception as exc:
            last_error=f"{type(exc).__name__}: {exc}"
            if attempt+1<_base.MAX_ATTEMPTS: print(f"⚠️ Story script attempt {attempt+1} rejected: {last_error}"); time.sleep(2)
    raise RuntimeError(f"STORY SCRIPT GENERATION FAILED after bounded retries. Last error: {last_error}")
