"""Entertainment-first storyboard generator for Mint-YT-Factory."""
from __future__ import annotations

import json
import os
import re
import time
import uuid

from google import genai
from google.genai import types

MODEL_NAME = "gemini-flash-lite-latest"
FALLBACK_MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"
SCENE_COUNT = 7
VISUALS_PER_SCENE = 2
SCENE_DURATIONS = [3, 5, 7, 7, 8, 8, 7]
MAX_ATTEMPTS = 4

CAMERAS = {"close_up", "medium", "wide", "macro", "top_down", "side", "aerial", "orbit"}
ANIMATIONS = {"zoom_in", "zoom_out", "pan_left", "pan_right", "rotate", "parallax", "highlight", "hold"}
PURPOSES = {"hook", "question", "explanation", "example", "mindblowing_fact", "ending"}
TONES = {"curious", "tense", "calm", "awe", "playful", "urgent", "satisfied"}
RETENTION = {"open_loop", "escalation", "payoff", "reframe", "curiosity_gap", "pattern_break", "emotional_release", "closure"}
TRANSITIONS = {"hard_cut", "whip_pan", "match_cut", "dissolve", "none"}
MUSIC_CUES = {"intro", "build", "swell", "drop", "fade_out", "none"}
IMAGE_STYLES = {"cinematic_photograph", "macro_photography", "realistic_3d_render"}

def _clean(value): return re.sub(r"\s+", " ", str(value or "")).strip()
def _safe_int(value, default=0):
    try: return int(value)
    except (TypeError, ValueError): return default
def _words(text): return re.findall(r"\b[\w'-]+\b", _clean(text))
def _api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if not key: raise RuntimeError("GEMINI_API_KEY environment variable is missing.")
    return key

SYSTEM_PROMPT = r"""
You are the entertainment writer and visual director for Wonder Minute.
Create ONE highly engaging 35–45 second YouTube Short about the supplied topic.

RESEARCH IS OFF. Do not cite sources or write like a textbook. Use ordinary knowledge only when needed for coherence. Never invent precise statistics, studies, quotes or fake evidence.

VOICE: conversational, playful, curious, slightly quirky and confident. Short punchy sentences. Sound like a clever human storyteller. Use vivid everyday comparisons. Explain technical ideas through what a person can see, touch or imagine in ordinary life.

NEVER USE: "Did you know", "Have you ever wondered", "Today we're going to", "In this video", lecture language, lists, countdowns, Top 5, generic filler.

STORY ARC:
1) 0–3s: immediate weird behavior or surprising claim. No warm-up.
2) 3–8s: deepen the mystery.
3) 8–15s: simple explanation.
4) 15–22s: concrete demonstration/example.
5) 22–30s: reframe what the viewer thought was happening.
6) 30–38s: strongest twist/payoff.
7) 38–45s: satisfying ending, then ONE new curiosity topic as the final sentence only.

The current story must feel complete before the continuation sentence. The continuation topic must not appear in the title, description, or Scenes 1–6.

SCENE 7 HARD RULE: Scene 7 must contain ONLY the payoff/ending of the CURRENT topic plus the final continuation sentence. Do not introduce a second fact, second mystery, unrelated object, new animal, new invention, or a mini-story before the continuation sentence.

NATURAL CONTINUATION BRIDGE: Gemini itself must write the final bridge sentence. Do NOT use a reusable template, fixed phrase, canned transition, or repeated sentence pattern. The bridge should grow naturally out of the current story and make the viewer curious about the next topic. The exact next_short.topic must appear once in that final sentence. NEVER start it with "And next", "Then comes", "Coming next", "Stay tuned", "Part 2", "Have you ever wondered", "Ever wondered", "Wonder why", "Curious why", "Why do", "Why does", "How do", "How does", "What makes", or another generic question opener.

IMPORTANT FORMAT: Scene 7 must contain two spoken sentences: a satisfying payoff sentence, followed by the natural continuation bridge sentence. If Gemini accidentally combines them into one sentence, the pipeline may safely insert the sentence boundary immediately before the final-topic clause; it must never replace the bridge with a canned template.

VISUAL DIRECTOR RULE: Every image must literally depict the exact physical beat being spoken. Illustrate the action, not the general topic. If narration describes an invisible phenomenon, use a truthful visible physical proxy. Never use random people, generic laboratories, microscopes, diagrams, arrows, equations, glowing particles, abstract science art, generic blue backgrounds, concept art, text, labels, logos, UI or watermarks unless narration explicitly requires them.

TWO SHOTS PER SCENE: Shot 1 establishes the exact moment. Shot 2 advances it by changing physical state, action, viewpoint, comparison, reaction or revealed detail. Never duplicate Shot 1.

EVERY VISUAL MUST RETURN: spoken_line, visual_focus, visual_action, must_show, must_not_show, image_prompt. image_prompt must be 25–45 words, literal, concrete, realistic and physically plausible.

REALISM: Prefer cinematic photography or macro photography. Use realistic 3D only when necessary. Natural materials, believable scale, realistic reflections, shadows and physics. No illustration look.

MOTION: Hooks can use strong motion. Explanations use controlled push-ins. Demonstrations use pans that follow the action. Payoffs use a punchy reveal. Do not make every shot a zoom.

Return ONLY JSON matching the supplied schema.
"""

def _build_schema():
    visual={"type":"object","properties":{"segment":{"type":"integer"},"duration":{"type":"integer"},"spoken_line":{"type":"string"},"visual_focus":{"type":"string"},"visual_action":{"type":"string"},"must_show":{"type":"array","items":{"type":"string"}},"must_not_show":{"type":"array","items":{"type":"string"}},"camera":{"type":"string"},"animation":{"type":"string"},"zoom_strength":{"type":"string"},"motion_intensity":{"type":"string"},"visual_complexity":{"type":"string"},"image_style":{"type":"string"},"lighting":{"type":"string"},"color_palette":{"type":"string"},"overlay":{"type":"object","properties":{"type":{"type":"string"},"description":{"type":"string"}},"required":["type","description"]},"image_prompt":{"type":"string"},"visual_impact":{"type":"integer"}},"required":["segment","duration","spoken_line","visual_focus","visual_action","must_show","must_not_show","camera","animation","zoom_strength","motion_intensity","visual_complexity","image_style","lighting","color_palette","overlay","image_prompt","visual_impact"]}
    scene={"type":"object","properties":{"scene":{"type":"integer"},"purpose":{"type":"string"},"retention_purpose":{"type":"string"},"narration":{"type":"string"},"source_ids":{"type":"array","items":{"type":"string"}},"subtitle_text":{"type":"string"},"caption_highlights":{"type":"array","items":{"type":"object","properties":{"word":{"type":"string"},"emphasis":{"type":"string"}},"required":["word","emphasis"]}},"subtitle_style":{"type":"string"},"emphasis_word":{"type":"string"},"duration":{"type":"integer"},"pause_after_ms":{"type":"integer"},"emotional_tone":{"type":"string"},"visual_priority":{"type":"string"},"transition":{"type":"string"},"sfx_cue":{"type":"object","properties":{"term":{"type":"string"},"at_ms":{"type":"integer"}},"required":["term","at_ms"]},"music_cue":{"type":"string"},"confidence":{"type":"string"},"visuals":{"type":"array","items":visual}},"required":["scene","purpose","retention_purpose","narration","source_ids","subtitle_text","caption_highlights","subtitle_style","emphasis_word","duration","pause_after_ms","emotional_tone","visual_priority","transition","sfx_cue","music_cue","confidence","visuals"]}
    return {"type":"object","properties":{"title":{"type":"string"},"description":{"type":"string"},"tags":{"type":"array","items":{"type":"string"}},"category":{"type":"string"},"thumbnail_prompt":{"type":"string"},"voice_style":{"type":"object","properties":{"tone":{"type":"string"},"pace":{"type":"string"},"pitch":{"type":"string"}},"required":["tone","pace","pitch"]},"music":{"type":"object","properties":{"search":{"type":"string"},"arc":{"type":"string"}},"required":["search","arc"]},"visual_identity":{"type":"object","properties":{"style":{"type":"string"},"palette":{"type":"string"},"mood_arc":{"type":"string"}},"required":["style","palette","mood_arc"]},"visual_continuity":{"type":"object","properties":{"recurring_subjects":{"type":"array","items":{"type":"object","properties":{"name":{"type":"string"},"type":{"type":"string"},"appearance":{"type":"string"},"continuity":{"type":"string"}},"required":["name","type","appearance","continuity"]}},"recurring_objects":{"type":"array","items":{"type":"string"}},"recurring_environment":{"type":"string"},"continuity_rules":{"type":"array","items":{"type":"string"}}},"required":["recurring_subjects","recurring_objects","recurring_environment","continuity_rules"]},"retention_self_check":{"type":"object","properties":{"weakest_scene":{"type":"integer"},"reason":{"type":"string"}},"required":["weakest_scene","reason"]},"next_short":{"type":"object","properties":{"topic":{"type":"string"},"teaser":{"type":"string"},"why_viewers_should_return":{"type":"string"},"subscription_cta":{"type":"string"}},"required":["topic","teaser","why_viewers_should_return","subscription_cta"]},"scene_plan":{"type":"array","items":scene}},"required":["title","description","tags","category","thumbnail_prompt","voice_style","music","visual_identity","visual_continuity","retention_self_check","next_short","scene_plan"]}

def _parse(text):
    text=_clean(text)
    if text.startswith("```"):
        text=re.sub(r"^```(?:json)?","",text,flags=re.I).strip(); text=re.sub(r"```$","",text).strip()
    return json.loads(text)

def _content_tokens(text):
    stop={"that","this","with","from","your","they","them","then","than","into","when","where","what","which","because","while","just","really","very","have","will","does","doesn","there","their","about","like","more","only","still","even","gets","make","makes","made","over","under","also","actually","strange","weird","thing","things","little","sudden","suddenly","part","time","way","water","you","are","the","and","but","for","not","its","it's","can","how","why","now","watch","ever"}
    return {w.lower() for w in re.findall(r"[a-z0-9]+",_clean(text).lower()) if len(w)>=4 and w not in stop}

def _sentence_parts(text): return [s.strip() for s in re.split(r"(?<=[.!?])\s+",_clean(text)) if s.strip()]
def _normalise_phrase(text): return re.sub(r"[^a-z0-9]+"," ",_clean(text).lower()).strip()

def _ensure_scene7_boundary(text,next_topic):
    """Guarantee payoff + bridge sentence without inventing bridge wording."""
    text=_clean(text)
    topic_key=_normalise_phrase(next_topic)
    if not text or not topic_key: return text
    sentences=_sentence_parts(text)
    if len(sentences)>=2:
        return text
    norm=_normalise_phrase(text)
    pos=norm.find(topic_key)
    if pos<=0: return text
    # Work from the actual text and find the start of the topic phrase.
    match=re.search(re.escape(next_topic),text,re.I)
    if not match:
        # Fall back to a punctuation-insensitive whitespace match.
        words=re.escape(_clean(next_topic)).replace(r"\ ",r"\\s+")
        match=re.search(words,text,re.I)
    if not match: return text
    prefix=text[:match.start()].rstrip(" ,;:-–—")
    suffix=text[match.start():].strip()
    # Prefer a natural clause boundary immediately before the topic.
    candidates=list(re.finditer(r"\s+(?:and|but|so|because|while|which|that)\s+",prefix,re.I))
    if candidates:
        cut=candidates[-1]
        left=prefix[:cut.start()].rstrip(" ,;:-–—")
        bridge_prefix=prefix[cut.end():].strip(" ,;:-–—")
        if left and bridge_prefix:
            return f"{left}. {bridge_prefix} {suffix}".strip()
    commas=list(re.finditer(r"[,;:]\s+",prefix))
    if commas:
        cut=commas[-1]
        left=prefix[:cut.start()].strip()
        bridge_prefix=prefix[cut.end():].strip()
        if left and bridge_prefix:
            return f"{left}. {bridge_prefix} {suffix}".strip()
    # Last-resort structural repair: preserve Gemini's words and only add the boundary.
    return f"{prefix}. {suffix}".strip()

def _sanitize_scene7(scene7, earlier_scenes):
    text=_clean(scene7.get("narration")); text=re.sub(r"\s+([.!?,])",r"\1",text)
    sentences=_sentence_parts(text)
    if not sentences: return text
    current_tokens=set()
    for scene in earlier_scenes: current_tokens |= _content_tokens(scene.get("narration",""))
    bad_intro=re.compile(r"^(now watch|speaking of|and now|meanwhile|another weird|here's another|here is another)\b",re.I)
    kept=[]
    for i,sentence in enumerate(sentences):
        # Scene 7's final sentence is the authored continuation bridge. Never
        # remove it merely because its vocabulary differs from the current topic.
        if i==len(sentences)-1:
            kept.append(sentence); continue
        if bad_intro.search(sentence): continue
        tokens=_content_tokens(sentence)
        if len(tokens)>=4 and not (tokens & current_tokens): continue
        kept.append(sentence)
    return _clean(" ".join(kept))

def _bridge_is_canned(sentence):
    banned=(r"^(?:and\s+)?next\b",r"^then\s+comes\b",r"^coming\s+next\b",r"^in\s+the\s+next\s+(?:video|short)\b",r"^stay\s+tuned\b",r"^part\s+2\b",r"^have\s+you\s+ever\s+wondered\b",r"^ever\s+wondered\b",r"^wonder\s+why\b",r"^curious\s+(?:why|how|what)\b",r"^why\s+(?:do|does|is|are)\b",r"^how\s+(?:do|does|is|are)\b",r"^what\s+(?:makes|happens|causes)\b")
    return any(re.search(p,sentence,re.I) for p in banned)

def _validate_natural_bridge(scene7_narration,next_topic):
    sentences=_sentence_parts(scene7_narration)
    if len(sentences)<2: raise RuntimeError("Scene 7 must contain a payoff followed by a natural continuation bridge.")
    key=_normalise_phrase(next_topic); matches=[s for s in sentences if key and key in _normalise_phrase(s)]
    if len(matches)!=1: raise RuntimeError("The exact next topic must appear exactly once in Scene 7.")
    bridge=matches[0]
    if sentences[-1]!=bridge: raise RuntimeError("The continuation topic must be in Scene 7's final sentence.")
    if _bridge_is_canned(bridge): raise RuntimeError(f"Canned continuation bridge rejected: {bridge}")
    if len(_words(bridge))<4 or len(_words(bridge))>30: raise RuntimeError("Natural continuation bridge is too short or too long.")
    return bridge

def _normalize(script,topic):
    if not isinstance(script,dict): raise RuntimeError("Gemini returned a non-object script.")
    scenes=script.get("scene_plan")
    if not isinstance(scenes,list) or len(scenes)!=SCENE_COUNT: raise RuntimeError(f"Expected exactly {SCENE_COUNT} scenes.")
    script["topic"]=topic; script["title"]=_clean(script.get("title"))[:70] or topic[:70]; script["description"]=f"Explore the strange everyday mystery behind {topic}."; script["tags"]=[_clean(x).lstrip("#") for x in script.get("tags",[]) if _clean(x)][:12]; script["category"]=_clean(script.get("category")) or "science"; script["thumbnail_prompt"]=_clean(script.get("thumbnail_prompt"))[:500]
    next_short=script.get("next_short") or {}; next_topic=_clean(next_short.get("topic"));
    if not next_topic: raise RuntimeError("Gemini did not provide next_short.topic.")
    next_teaser=_clean(next_short.get("teaser"));
    if not next_teaser: raise RuntimeError("Gemini did not provide next_short.teaser.")
    script["next_short"]={"topic":next_topic[:300],"teaser":next_teaser[:220],"why_viewers_should_return":_clean(next_short.get("why_viewers_should_return"))[:220] or next_topic,"subscription_cta":_clean(next_short.get("subscription_cta"))[:160] or "Follow for another weird little mystery."}
    identity=script.get("visual_identity") or {}; script["visual_identity"]={"style":_clean(identity.get("style")) or "cinematic realistic storytelling, tactile detail, believable real-world photography","palette":_clean(identity.get("palette")) or "natural colors, crisp highlights, believable contrast","mood_arc":_clean(identity.get("mood_arc")) or "curiosity, playful tension, surprise, satisfying payoff"}
    continuity=script.get("visual_continuity") or {}; subjects=[]
    for item in continuity.get("recurring_subjects",[])[:6]:
        if isinstance(item,dict) and _clean(item.get("name")) and _clean(item.get("appearance")): subjects.append({"name":_clean(item.get("name")),"type":_clean(item.get("type")),"appearance":_clean(item.get("appearance")),"continuity":_clean(item.get("continuity")) or "keep appearance consistent whenever visible"})
    script["visual_continuity"]={"recurring_subjects":subjects,"recurring_objects":[_clean(x)[:200] for x in continuity.get("recurring_objects",[])[:8] if _clean(x)],"recurring_environment":_clean(continuity.get("recurring_environment"))[:500],"continuity_rules":[_clean(x)[:250] for x in continuity.get("continuity_rules",[])[:8] if _clean(x)]}
    banned_openings=("did you know","have you ever wondered","today we're going to","in this video")
    for i,scene in enumerate(scenes):
        if not isinstance(scene,dict): raise RuntimeError(f"Scene {i+1} is invalid.")
        scene["scene"]=i+1; scene["duration"]=SCENE_DURATIONS[i]; narration=_clean(scene.get("narration"))
        if not narration: raise RuntimeError(f"Scene {i+1} narration is empty.")
        if i==0 and narration.lower().startswith(banned_openings): raise RuntimeError("Hook uses a forbidden generic opening.")
        scene["narration"]=narration; scene["subtitle_text"]=narration; scene["source_ids"]=[]; scene["pause_after_ms"]=max(0,min(500,_safe_int(scene.get("pause_after_ms"),0))); scene["purpose"]=_clean(scene.get("purpose")) if _clean(scene.get("purpose")) in PURPOSES else ("hook" if i==0 else "ending" if i==6 else "explanation"); scene["retention_purpose"]=_clean(scene.get("retention_purpose")) if _clean(scene.get("retention_purpose")) in RETENTION else ("open_loop" if i<2 else "payoff" if i>=5 else "escalation"); scene["subtitle_style"]=_clean(scene.get("subtitle_style")) or "dynamic"; scene["emphasis_word"]=_clean(scene.get("emphasis_word")) or (_words(narration)[0] if _words(narration) else ""); scene["emotional_tone"]=_clean(scene.get("emotional_tone")) if _clean(scene.get("emotional_tone")) in TONES else ("urgent" if i==0 else "satisfied" if i==6 else "curious"); scene["visual_priority"]=_clean(scene.get("visual_priority")) or "primary"; scene["transition"]=_clean(scene.get("transition")) if _clean(scene.get("transition")) in TRANSITIONS else ("hard_cut" if i in (0,1,5) else "match_cut"); scene["music_cue"]=_clean(scene.get("music_cue")) if _clean(scene.get("music_cue")) in MUSIC_CUES else ("intro" if i==0 else "drop" if i==5 else "fade_out" if i==6 else "build"); scene["confidence"]=_clean(scene.get("confidence")) or "high"; scene["sfx_cue"]=scene.get("sfx_cue") if isinstance(scene.get("sfx_cue"),dict) else {"term":"","at_ms":0}
        visuals=scene.get("visuals")
        if not isinstance(visuals,list) or len(visuals)!=VISUALS_PER_SCENE: raise RuntimeError(f"Scene {i+1} must contain exactly 2 visuals.")
        durations=[scene["duration"]//2,scene["duration"]-scene["duration"]//2]
        for j,visual in enumerate(visuals):
            if not isinstance(visual,dict): raise RuntimeError(f"Scene {i+1} visual {j+1} is invalid.")
            visual["segment"]=j+1; visual["duration"]=durations[j]; visual["spoken_line"]=_clean(visual.get("spoken_line")) or narration; visual["visual_focus"]=_clean(visual.get("visual_focus")) or topic; visual["visual_action"]=_clean(visual.get("visual_action")) or "show the exact physical action described in the spoken line"; visual["must_show"]=[_clean(x)[:100] for x in visual.get("must_show",[]) if _clean(x)][:6] or [visual["visual_focus"],visual["visual_action"]]; visual["must_not_show"]=[_clean(x)[:100] for x in visual.get("must_not_show",[]) if _clean(x)][:8]; visual["camera"]=_clean(visual.get("camera")) if _clean(visual.get("camera")) in CAMERAS else ("close_up" if j==0 else "macro"); visual["animation"]=_clean(visual.get("animation")) if _clean(visual.get("animation")) in ANIMATIONS else (["zoom_in","pan_right","highlight","parallax"][i%4] if j==0 else ["pan_left","zoom_out","highlight","rotate"][i%4]); visual["zoom_strength"]=_clean(visual.get("zoom_strength")) or ("strong" if i==0 else "medium"); visual["motion_intensity"]=_clean(visual.get("motion_intensity")) or ("high" if i in (0,5) else "medium"); visual["visual_complexity"]=_clean(visual.get("visual_complexity")) or "focused"; visual["image_style"]=_clean(visual.get("image_style")) if _clean(visual.get("image_style")) in IMAGE_STYLES else ("macro_photography" if visual["camera"] in {"close_up","macro"} else "cinematic_photograph"); visual["lighting"]=_clean(visual.get("lighting")) or "natural believable lighting with realistic reflections and shadows"; visual["color_palette"]=_clean(visual.get("color_palette")) or script["visual_identity"]["palette"]; visual["overlay"]=visual.get("overlay") if isinstance(visual.get("overlay"),dict) else {"type":"none","description":""}; visual["visual_impact"]=max(1,min(10,_safe_int(visual.get("visual_impact"),8))); prompt_text=_clean(visual.get("image_prompt")); visual["image_prompt"]=(prompt_text or f"Realistic cinematic scene showing {visual['visual_action']} with {visual['visual_focus']} clearly visible.")[:900]
    scene7=scenes[6]
    scene7["narration"]=_ensure_scene7_boundary(scene7.get("narration"),next_topic)
    scene7["narration"]=_sanitize_scene7(scene7,scenes[:6])
    if not scene7["narration"]: raise RuntimeError("Scene 7 lost its current-topic payoff during continuation sanitization.")
    bridge=_validate_natural_bridge(scene7["narration"],next_topic); scene7["subtitle_text"]=scene7["narration"]; script["next_short"]["teaser"]=bridge
    next_key=re.sub(r"[^a-z0-9 ]"," ",next_topic.lower()).strip()
    for scene in scenes[:6]:
        if next_key and next_key in re.sub(r"[^a-z0-9 ]"," ",scene["narration"].lower()): raise RuntimeError("Next topic appeared before Scene 7.")
    total_words=sum(len(_words(scene["narration"])) for scene in scenes)
    if total_words<90 or total_words>135: raise RuntimeError(f"Narration length is {total_words} words; target is 90–135 words including continuation.")
    for visual in scene7.get("visuals",[]):
        if isinstance(visual,dict) and not _clean(visual.get("spoken_line")): visual["spoken_line"]=scene7["narration"]
    script["retention_self_check"]=script.get("retention_self_check") or {"weakest_scene":4,"reason":"Every scene advances the mystery."}; script["publishing"]={"research_verified":False,"research_sources_require_verification":False,"citations_ready":False,"claim_verification_required":False,"captions_match_narration":True,"semantic_image_prompts":True,"fourteen_visuals_required":True,"entertainment_first":True,"visual_relevance_constraints":True}; script["generated_at"]=int(time.time()); script["video_id"]=f"{re.sub(r'[^a-z0-9]+','-',script['title'].lower()).strip('-')[:40]}-{uuid.uuid4().hex[:8]}"; script["image_generation"]={"seed":int(time.time()),"style_lock":"realistic cinematic photography, natural materials, physically plausible lighting, no illustration look"}
    return script

def _is_quota_error(error_text):
    value=_clean(error_text).lower()
    return any(x in value for x in ("429","resource_exhausted","quota exceeded","rate limit","insufficient quota"))

def _generate_with_qwen(prompt,topic,last_error=None):
    """Free Hugging Face model fallback for GitHub Actions when Gemini quota is exhausted."""
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch
    print(f"🛟 Gemini unavailable — using free fallback: {FALLBACK_MODEL_NAME}")
    tokenizer=AutoTokenizer.from_pretrained(FALLBACK_MODEL_NAME)
    model=AutoModelForCausalLM.from_pretrained(FALLBACK_MODEL_NAME,torch_dtype=torch.float32,low_cpu_mem_usage=True)
    user_prompt=prompt+(f"\\n\\nFIX THE PREVIOUS ERROR: {last_error}" if last_error else "")
    messages=[{"role":"system","content":SYSTEM_PROMPT+"\\nReturn ONLY valid JSON matching the requested schema."},{"role":"user","content":user_prompt}]
    rendered=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
    inputs=tokenizer(rendered,return_tensors="pt")
    with torch.inference_mode():
        output=model.generate(**inputs,max_new_tokens=6000,do_sample=True,temperature=0.8,top_p=0.9,pad_token_id=tokenizer.eos_token_id)
    generated=output[0][inputs["input_ids"].shape[1]:]
    text=tokenizer.decode(generated,skip_special_tokens=True)
    if not _clean(text): raise RuntimeError("Qwen returned an empty response.")
    return _normalize(_parse(text),topic)

def generate_script(topic,config,research=None,extra_feedback=""):
    topic=_clean(topic)
    if not topic: raise RuntimeError("Topic is empty.")
    client=genai.Client(api_key=_api_key()); feedback="\n\nPRIOR FEEDBACK:\n"+_clean(extra_feedback) if extra_feedback else ""
    prompt=f"""
CURRENT TOPIC:
{topic}

Create exactly 7 scenes totaling about 45 seconds, durations 3, 5, 7, 7, 8, 8, 7.
Write 90–135 spoken words total INCLUDING the final continuation sentence.
Keep sentences short enough for natural TTS.

Make the opening instantly visual and surprising. Make the middle feel like a tiny story, not a lecture. Use a concrete everyday demonstration. Give a clear payoff before the final continuation sentence.

DESCRIPTION: write only about the current topic. Never mention the next topic.

NEXT SHORT: invent one specific curiosity topic. It must appear only in the final sentence of Scene 7 and nowhere else. Scene 7 must NOT introduce any unrelated fact before that sentence.
The final sentence should be the only bridge to the next Short.

IMPORTANT FINAL BRIDGE: Write the final bridge sentence yourself. Do not use a fixed template or repeat a stock transition. The exact next_short.topic must appear once in that sentence. Make the wording feel like a natural continuation of the current story, not an announcement of the next video.

VISUALS: every one of the 14 shots must represent a specific spoken beat. Return spoken_line, visual_focus, visual_action, must_show and must_not_show. The image_prompt must literally show the action. For invisible/microscopic phenomena, describe an honest visible physical proxy rather than an impossible camera view. No generic topic images and no unrelated filler.
{feedback}
"""
    last_error=None
    for attempt in range(1,MAX_ATTEMPTS+1):
        try:
            retry=f"\n\nFIX THE PREVIOUS VALIDATION ERROR:\n{last_error}" if last_error else ""
            response=client.models.generate_content(model=MODEL_NAME,contents=prompt+retry,config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT,response_mime_type="application/json",response_json_schema=_build_schema(),temperature=0.95))
            text=getattr(response,"text",None)
            if not text: raise RuntimeError("Gemini returned an empty response.")
            return _normalize(_parse(text),topic)
        except Exception as error:
            last_error=f"{type(error).__name__}: {error}"
            if attempt<MAX_ATTEMPTS: time.sleep(3*attempt)
    if last_error and _is_quota_error(last_error):
        try:
            return _generate_with_qwen(prompt,topic,last_error)
        except Exception as fallback_error:
            raise RuntimeError(f"SCRIPT GENERATION FAILED. Gemini error: {last_error} | Qwen fallback error: {type(fallback_error).__name__}: {fallback_error}") from fallback_error
    raise RuntimeError(f"SCRIPT GENERATION FAILED. Last error: {last_error}")