"""Quality controls layered onto the existing Mint-YT-Factory pipeline."""
from __future__ import annotations
import inspect
import re

FILLER={"the","a","an","and","or","but","so","because","that","this","these","those","your","you","yourself","is","are","was","were","be","been","being","to","of","in","on","at","for","from","with","into","over","under","it","its","they","them","their","there","here","just","really","very","then","than","when","where","what","why","how","do","does","did","can","could","will","would","should","has","have","had","as","like","about","one","two","three","some","any","even","also","still"}
MIN_STORY_WORDS=100
MAX_STORY_WORDS=145
MAX_REGEN_ATTEMPTS=3
TECHNICAL_TERMS={"molecule","molecules","electron","electrons","proton","protons","neutron","neutrons","quantum","thermodynamics","electromagnetic","electromagnetism","coefficient","equilibrium","density","molecular","microscopic","microscope","wavelength","frequency","entropy","kinetic","potential","inertia","viscosity","polarity","covalent","ionic","charge","charges","particles","particle","mechanism","phenomenon","oscillation","pressure","buoyancy"}
FUTURE_MARKERS=re.compile(r"\b(?:speaking of|on a related note|that makes you wonder|that makes you ask|another question|one more question|one more thing|which raises|which brings up|that brings us to|related question|then comes|coming next|next topic|next short|next video|stay tuned|part 2)\b",re.I)
QUESTION_START=re.compile(r"^(?:why|how|what|when|where)\b",re.I)
MYSTERY_CLAUSE=re.compile(r"\b(?:why|how)\s+([^.!?]{8,100})",re.I)

def _words(text): return re.findall(r"\b[\w'-]+\b",str(text or ""))
def _meaningful(text):
    out=[]; filler={x.lower() for x in FILLER}
    for w in _words(text):
        key=w.lower().strip(".,!?;:'\"()[]")
        if len(key)>=4 and key not in filler and key not in {x.lower() for x in out}: out.append(w)
    return out

def _topic_tokens(topic): return {w.lower() for w in _meaningful(topic) if len(w)>=4}
def _split_sentences(text): return [x.strip() for x in re.split(r"(?<=[.!?])\s+",str(text or "").strip()) if x.strip()]
def _word_total(script): return sum(len(_words(scene.get("narration",""))) for scene in script.get("scene_plan",[]))
def _story_text(script): return " ".join(str(scene.get("narration","")).strip() for scene in script.get("scene_plan",[]))

def _story_topic_vocabulary(topic,script):
    vocab=_topic_tokens(topic); counts={}
    for scene in (script.get("scene_plan") or [])[:6]:
        for w in set(x.lower() for x in _meaningful(scene.get("narration",""))): counts[w]=counts.get(w,0)+1
    for w,n in counts.items():
        if n>=2:vocab.add(w)
    return vocab

def _mystery_clause_is_unrelated(sentence,story_vocab):
    for match in MYSTERY_CLAUSE.finditer(sentence):
        words=[w.lower() for w in _meaningful(match.group(1))]
        if not words:continue
        unknown=[w for w in words if w not in story_vocab]
        if len(unknown)>=2:return True,match.group(0).strip()
    return False,""

def _find_visual_problems(script):
    problems=[]
    for index,scene in enumerate(script.get("scene_plan") or [],1):
        narration_tokens=set(w.lower() for w in _meaningful(scene.get("narration","")))
        for vi,visual in enumerate(scene.get("visuals") or [],1):
            spoken=str(visual.get("spoken_line") or "").strip()
            if not spoken:continue
            visual_tokens=set(w.lower() for w in _meaningful(spoken))
            if visual_tokens and narration_tokens:
                overlap=len(visual_tokens & narration_tokens)/max(1,len(visual_tokens))
                if overlap<0.45:
                    problems.append(f"Scene {index} Shot {vi} visual beat does not match its narration: {spoken}");continue
            prompt=" ".join(str(visual.get(k) or "") for k in ("visual_focus","visual_action","image_prompt"))
            bad,_=_mystery_clause_is_unrelated(prompt,narration_tokens)
            if bad:problems.append(f"Scene {index} Shot {vi} visual contract contains a side mystery: {prompt[:180]}")
    return problems

def _find_story_problems(script,topic):
    scenes=script.get("scene_plan") or []; problems=[]; story_vocab=_story_topic_vocabulary(topic,script)
    for index,scene in enumerate(scenes,1):
        narration=str(scene.get("narration","")).strip()
        for sentence in _split_sentences(narration):
            if FUTURE_MARKERS.search(sentence):
                problems.append(f"Scene {index} contains future-topic language: {sentence}");break
            if QUESTION_START.search(sentence) and sentence.rstrip().endswith("?") and len(_meaningful(sentence))>=4:
                content={w.lower() for w in _meaningful(sentence)}
                if story_vocab and not (content & story_vocab):
                    problems.append(f"Scene {index} contains an unrelated question: {sentence}");break
            bad,clause=_mystery_clause_is_unrelated(sentence,story_vocab)
            if bad:
                problems.append(f"Scene {index} contains a hidden side mystery: {clause}");break
    all_words=[w.lower().strip(".,!?;:'\"()[]") for w in _words(_story_text(script))]; jargon=[w for w in all_words if w in TECHNICAL_TERMS]
    if len(jargon)>=6:problems.append(f"Too much technical jargon ({len(jargon)} terms)")
    lecture_patterns=(r"according to scientists",r"the scientific explanation",r"in scientific terms",r"the definition of",r"this phenomenon occurs because",r"the reason is that",r"from a physics perspective",r"in conclusion",r"therefore,")
    story=_story_text(script).lower()
    for pattern in lecture_patterns:
        if re.search(pattern,story,re.I):problems.append(f"Lecture-style wording: {pattern}")
    first=str(scenes[0].get("narration","")) if scenes else ""
    if re.match(r"^(?:today|in this video|did you know|have you ever wondered)",first.strip(),re.I):problems.append("Generic hook opening")
    problems.extend(_find_visual_problems(script));return problems

def _refresh_highlights(script):
    for index,scene in enumerate(script.get("scene_plan") or []):
        words=_meaningful(scene.get("narration",""));chosen=words[:3]
        if index in (0,5,6) and len(words)>=3:chosen=[words[0],words[len(words)//2],words[-1]]
        scene["caption_highlights"]=[{"word":w,"emphasis":"strong"} for w in chosen]
        if chosen:scene["emphasis_word"]=chosen[0]

def _add_visual_contract_fields(script):
    for scene in script.get("scene_plan") or []:
        narration=str(scene.get("narration","")).strip()
        for vi,visual in enumerate(scene.get("visuals") or []):
            prompt=str(visual.get("image_prompt","")).strip();visual.setdefault("spoken_line",narration);visual.setdefault("visual_focus",prompt[:180] or narration[:180]);visual.setdefault("visual_action",prompt[:220] or narration[:220]);visual.setdefault("must_show",_meaningful(prompt)[:6] or _meaningful(narration)[:6]);visual["story_beat"]="establish" if vi==0 else "advance"
            if vi==1:visual["advance_rule"]="show a changed physical state, reaction, closer detail, or consequence; do not repeat shot 1"

def _sanitize_final_scene(script):
    scenes=script.get("scene_plan") or []
    if not scenes:return
    scene=scenes[-1];text=str(scene.get("narration","")).strip()
    if not text:return
    text=re.split(r"\b(?:and\s+next\s*:|next\s+(?:video|short|topic)\s*:|coming\s+next\b|stay\s+tuned\b|part\s*2\b)",text,maxsplit=1,flags=re.I)[0].strip();text=re.split(r"\s+(?:which|and\s+that)\s+(?:is\s+)?(?:also\s+)?why\b",text,maxsplit=1,flags=re.I)[0].strip();text=re.split(r"\s+(?:and\s+that'?s\s+why|which\s+means)\b",text,maxsplit=1,flags=re.I)[0].strip()
    if text:scene["narration"]=text.rstrip(".!? ")+".";scene["subtitle_text"]=scene["narration"]

def _call_original(original,topic,config,research,feedback):
    try:
        params=inspect.signature(original).parameters
        if "extra_feedback" in params or any(p.kind==inspect.Parameter.VAR_KEYWORD for p in params.values()):return original(topic,config,research,extra_feedback=feedback)
    except (TypeError,ValueError):pass
    return original(topic,config,research)

def patch_story_quality(main):
    original=main.generate_script
    def generate_script(topic,config,research=None,extra_feedback=""):
        last_reason=""
        for attempt in range(1,MAX_REGEN_ATTEMPTS+1):
            feedback=(extra_feedback or "") + """

MINT SCRIPT QUALITY CONTRACT — FOLLOW THIS ON EVERY DRAFT
- Write one self-contained everyday mystery, not a mini lesson.
- The current topic is the ONLY subject of all 7 scenes until the production system appends the locked continuation topic.
- Do not introduce a second mystery, animal, object, state, comparison target, or question that is not needed to explain the current topic.
- Scene 1 must create an immediate 'wait, why does THAT happen?' reaction without a generic YouTube intro.
- Escalate the SAME mystery across Scenes 2–6. Each scene adds a new observation, demonstration, reveal, or consequence.
- Scene 7 must finish the CURRENT story. The production system alone owns the continuation teaser.
- Never write a hidden side mystery such as 'see why frozen bubbles look like foggy marbles' before the continuation teaser.
- Every visual's spoken_line must be a literal excerpt or tight paraphrase of that scene's narration. Never invent a new visual story inside the visual contract.
- Keep the same concrete subject across the story. If the topic is a kettle, do not switch to generic pots, soda glasses, soap bubbles, torches, marbles, frozen bubbles, or other objects unless the narration explicitly requires that comparison.
- Explain the mechanism in plain spoken language. Prefer funny comparisons, personification, vivid verbs, and ordinary situations over scientific terminology.
- Use technical vocabulary only when it materially improves the explanation, and immediately translate it into normal language.
- The payoff must answer the original mystery with an 'ohhh' realization.
- Do not write 'speaking of...', 'another question...', 'that makes you wonder...', 'then comes...' or similar transitions inside the story body.
- A causal sentence such as 'When bubbles rise into the cooler water, they collapse' is valid story narration and MUST NOT be rejected as an unrelated question.
"""
            if last_reason:feedback+=f"\nPrevious draft failed quality gate: {last_reason}. Rewrite the ENTIRE story; do not patch one sentence."
            script=_call_original(original,topic,config,research,feedback);_sanitize_final_scene(script);total=_word_total(script);problems=_find_story_problems(script,topic)
            print(f"🧮 Story length: {total} words (soft production range {MIN_STORY_WORDS}-{MAX_STORY_WORDS}; TTS duration is authoritative)")
            if problems:
                last_reason="; ".join(problems[:3]);print(f"🚫 Story quality gate failed: {last_reason}")
                if attempt<MAX_REGEN_ATTEMPTS:continue
                raise RuntimeError(f"Story failed quality gate after {MAX_REGEN_ATTEMPTS} attempts: {last_reason}")
            if MIN_STORY_WORDS<=total<=MAX_STORY_WORDS:_refresh_highlights(script);_add_visual_contract_fields(script);return script
            last_reason=f"story length {total} outside soft range {MIN_STORY_WORDS}-{MAX_STORY_WORDS}";print(f"⚠️ Story length outside soft range: {last_reason}")
            if attempt==MAX_REGEN_ATTEMPTS:
                print("⚠️ Accepting final draft; real TTS duration will decide production viability.");_refresh_highlights(script);_add_visual_contract_fields(script);return script
        raise RuntimeError("Unreachable story generation state")
    main.generate_script=generate_script

def patch_visual_diversity(generate_media_module):
    generate_media_module.MEDIA_DIVERSITY_REQUIRED=True;print("🎞️ Media diversity: duplicate stock assets prohibited")
