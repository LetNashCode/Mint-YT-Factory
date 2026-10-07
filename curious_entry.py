from __future__ import annotations
import json, os, re
from google import genai
from google.genai import types

TOPIC_PROMPT = """You are the topic director for Mint Fever Curious Shorts.
Audience: United States.
Choose one familiar American everyday saying, habit, object, tradition, childhood rule, or phrase that people recognize but rarely know the story behind.
Turn the origin, history, practical reason, psychology, or surprising explanation into an entertaining mini-story.
Avoid India-specific topics, generic facts, lists, politics, medical advice, celebrities, fearbait, conspiracy, and obscure trivia.
Return JSON only: {"topic":"..."}.
Previously covered:
"""

def clean(x):
    return re.sub(r"\s+", " ", str(x or "")).strip()

_GENAI_CLIENT = None

def client():
    global _GENAI_CLIENT
    key=os.environ.get("GEMINI_API_KEY","").strip()
    if not key: raise RuntimeError("GEMINI_API_KEY is missing.")
    if _GENAI_CLIENT is None:
        _GENAI_CLIENT = genai.Client(api_key=key)
    return _GENAI_CLIENT

def reset_client():
    global _GENAI_CLIENT
    old = _GENAI_CLIENT
    _GENAI_CLIENT = None
    if old is not None:
        try:
            old.close()
        except Exception:
            pass

def previous():
    import topics
    prefix=getattr(topics,"_PENDING_PREFIX","__PENDING__")
    return [str(x) for x in topics._read_used() if not str(x).startswith(prefix)][-80:]

def get_curious_topic():
    import topics
    old=previous()
    last=None
    for attempt in range(1,13):
        try:
            response=client().models.generate_content(
                model="gemini-flash-lite-latest",
                contents=TOPIC_PROMPT + ("\n".join(old) or "none"),
                config=types.GenerateContentConfig(temperature=0.95,response_mime_type="application/json"),
            )
            data=json.loads(response.text)
            topic=clean(data.get("topic"))
            if topic and len(topic.split()) <= 9 and topics.validate_topic_for_pipeline(topic,used=old,check_duplicate=True):
                print("CURIOUS TOPIC:",topic,flush=True)
                return topic
            old.append(topic)
        except Exception as exc:
            last=exc
            message=str(exc).lower()
            if "client has been closed" in message or "client is closed" in message:
                reset_client()
                print(f"⚠️ Curious Gemini client was closed; recreated client (attempt {attempt}/12)",flush=True)
                continue
            if any(code in message for code in ("429","500","502","503","504","timeout")):
                reset_client()
                print(f"⚠️ Curious topic Gemini transient failure; retrying (attempt {attempt}/12): {type(exc).__name__}: {exc}",flush=True)
                continue
            raise
    raise RuntimeError(f"No Curious Short topic passed novelty gate after 12 attempts: {last}")
    raise RuntimeError("No Curious Short topic passed novelty gate after 12 attempts.")

SCRIPT_PROMPT = """You write Mint Fever Curious Shorts for a United States audience.
Create one entertaining 35-44 second mini-mystery about the CURRENT TOPIC.
The viewer should recognize it immediately, wonder why it exists, hear an entertaining story behind it, and finish with a satisfying reveal.
Structure: familiar cold open, weird contradiction, curiosity gap, story, escalation, explanation, memorable payoff.
Sound like a clever friend, not a documentary or teacher. Use natural American English, concrete situations, playful observations, second person, rhetorical questions, and surprise.
Never use Did you know, Today we're going to, In this video, According to scientists, In conclusion, Here's the answer, Wikipedia-style chronology, generic filler, a second topic, or a future-video teaser.
Narration must work without visuals.
Return JSON with title,tags,category,hook_type,story_format,payoff_type,voice_style,scene_plan,next_short.
Use exactly 7 scenes. Each scene needs scene,narration,purpose,retention_purpose,emotional_tone,visuals,subtitle_text.
Each visual needs spoken_line,visual_focus,visual_action,must_show,must_not_show,camera,animation,zoom_strength,motion_intensity,visual_complexity,image_style,lighting,color_palette,image_prompt,visual_impact.
CURRENT TOPIC:
"""

def validate(script):
    scenes=script.get("scene_plan") or []
    if len(scenes)!=7: raise RuntimeError("Curious Short requires exactly 7 scenes")
    narration=" ".join(clean(s.get("narration")) for s in scenes)
    words=len(re.findall(r"\b[\w'-]+\b",narration))
    if words < 95 or words > 155: raise RuntimeError(f"Curious narration word count {words} outside 95-155")
    low=narration.lower()
    for phrase in ("did you know","today we're going to","in this video","according to scientists","in conclusion","here's the answer"):
        if phrase in low: raise RuntimeError("Lecture phrase detected: "+phrase)
    if len(clean(scenes[0].get("narration")).split()) < 8: raise RuntimeError("Weak familiar cold open")
    if any(x in clean(scenes[-1].get("narration")).lower() for x in ("next video","next short","stay tuned","part 2","coming next")):
        raise RuntimeError("Future-video teaser in ending")
    print("CURIOUS STORY GATE PASSED | words=",words,flush=True)

def _research_topic(topic):
    """Use Google Search grounding in a separate pass; keep final JSON generation structured."""
    try:
        response=client().models.generate_content(
            model="gemini-flash-lite-latest",
            contents=(
                "Research the CURRENT TOPIC for a short factual story. "
                "Return concise factual notes: origin or reason, key mechanism, "
                "one surprising but well-supported detail, and useful source context. "
                "Do not write narration or a second topic. CURRENT TOPIC: " + topic
            ),
            config=types.GenerateContentConfig(
                temperature=0.2,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        return clean(getattr(response, "text", ""))[:7000]
    except Exception as exc:
        print(f"Curious research grounding unavailable; continuing without it: {type(exc).__name__}: {exc}",flush=True)
        return ""

def generate_curious_script(topic,config,research=None,extra_feedback=""):
    research = clean(research) or _research_topic(topic)
    prompt=SCRIPT_PROMPT+topic
    if research:
        prompt+="\n\nVERIFIED RESEARCH NOTES — use only facts supported by these notes:\n"+research
    if extra_feedback: prompt+="\nRETRY:\n"+clean(extra_feedback)
    last=None
    for attempt in range(1,6):
        try:
            response=client().models.generate_content(
                model="gemini-flash-lite-latest",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.85,
                    response_mime_type="application/json",
                ),
            )
            script=json.loads(response.text)
            script["topic"]=topic
            script.setdefault("next_short",{})
            validate(script)
            return script
        except Exception as exc:
            last=exc
            print(f"Curious script attempt {attempt}/5 failed: {exc}",flush=True)
            prompt+="\nRetry: make it more entertaining and story-driven without adding a second topic."
    raise RuntimeError(f"Could not generate Curious Short: {last}")

def main_entry():
    import main, tts_bridge
    main.get_next_topic=get_curious_topic
    main.generate_script=generate_curious_script

    def curious_lock(script,current_topic,locked_topic=None,stale_topics=None):
        script["topic"]=current_topic
        script.setdefault("next_short",{})
        if locked_topic: script["next_short"]["topic"]=locked_topic
        for scene in script.get("scene_plan") or []:
            scene["subtitle_text"]=clean(scene.get("narration"))
        print("Curious ending lock: current-topic payoff only; no future-topic bridge",flush=True)
        return script,clean((script.get("next_short") or {}).get("topic"))
    main.lock_next_topic=curious_lock

    os.environ.update({"MINT_TTS_PROVIDER":"kokoro","MINT_KOKORO_VOICE":"af_heart","MINT_KOKORO_LANG":"a","MINT_EDGE_TTS_FALLBACK":"0"})

    original_load=main.load_config
    def load_config(*args,**kwargs):
        config=original_load(*args,**kwargs)
        config["channel"]={"name":"Mint Fever","niche":"Curious everyday stories","tone":["curious","playful","entertaining","cinematic","quirky"],"audience":"United States","language":"English","reading_level":"Grade 6-8"}
        config["voice"]={"provider":"kokoro","voice_name":"af_heart","kokoro_lang":"a","edge_voice":"en-US-GuyNeural","speed":1.0,"tone":"curious, playful storyteller"}
        config["branding"]={"channel_name":"Mint Fever","ending_text":"Follow for more.","ending_text_enabled":True,"ending_text_in_narration":False,"overlay_branding":False,"watermark":False}
        return config
    main.load_config=load_config
    # Keep Curious narration below the workflow's 43.9s maximum after the fixed TTS tail.
    tts_bridge.MAX_FINAL_NARRATION_SECONDS = 43.50
    tts_bridge.patch(main)
    print("MINT FEVER CURIOUS SHORT | US audience | Kokoro af_heart single-pass",flush=True)
    main.run(dry_run=False)

if __name__=="__main__":
    main_entry()
