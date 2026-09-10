"""Narration-first Riddles Shorts generator with anti-repetition controls."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from . import entertainment as _base

# One episode-level contract for the whole Riddles pipeline. Scene bands are
# intentionally flexible; the total word budget is the real pacing gate.
MIN_WORDS=50; MAX_WORDS=85
SCENE_WORD_BUDGETS=((4,18),(7,20),(5,16),(5,16),(5,12),(3,8),(12,26))
CREATIVE_PROFILES=(
 {"name":"cold_open_challenge","hook":"Open with a provocative claim or challenge before stating the riddle.","flow":"challenge -> question -> obvious answer -> contradiction -> commitment -> countdown -> CTA"},
 {"name":"tiny_story","hook":"Begin with a tiny everyday situation that naturally creates the puzzle.","flow":"micro-scenario -> question -> first interpretation -> twist -> commitment -> countdown -> CTA"},
 {"name":"false_confidence","hook":"Make the listener confidently expect one answer, then verbally break that assumption.","flow":"confident setup -> question -> obvious answer -> assumption break -> commitment -> countdown -> CTA"},
 {"name":"word_ambush","hook":"Make one ordinary word or phrase carry the hidden twist; do not rely on visual clues.","flow":"intriguing phrase -> question -> literal reading -> alternate meaning -> commitment -> countdown -> CTA"},
 {"name":"impossible_choice","hook":"Frame the puzzle as a choice between two tempting interpretations before revealing the trap.","flow":"choice -> question -> option A -> option B / reversal -> commitment -> countdown -> CTA"},
 {"name":"reverse_logic","hook":"Lead from a strange consequence backward toward the riddle instead of using a standard setup.","flow":"strange consequence -> question -> expected logic -> reversal -> commitment -> countdown -> CTA"},
 {"name":"listener_test","hook":"Talk directly to the listener as if testing a quick mental reflex, without generic filler.","flow":"direct test -> question -> instinct -> trap -> commitment -> countdown -> CTA"},
 {"name":"mini_mystery","hook":"Treat the riddle like a tiny mystery with one missing piece, not like a classic riddle recital.","flow":"mystery -> question -> clue interpretation -> reveal of the trap -> commitment -> countdown -> CTA"},
)
GENERIC_OPENERS=re.compile(r"^(?:today(?:'s| is)? riddle|here(?:'s| is) (?:today(?:'s)? )?riddle|welcome back|hey guys|guys|listen up|okay guys|alright guys)",re.I)

def _feedback(extra=""):
 return ("RIDDLES SHORTS ONLY. This is an audio/narration-led puzzle, not a visual puzzle. The viewer must be able to solve the riddle with the phone face-down; stock visuals are atmosphere only and must never carry a required clue. Do not require a visual clue, visual inspection, on-screen text, or an object in the footage to solve the NEW riddle. A previous riddle answer may be revealed, but the NEW answer must remain locked. The ending must ask viewers to subscribe and follow for the NEW answer in the next Short; never say tomorrow, next day, or imply a fixed schedule. " + f"Target {MIN_WORDS}-{MAX_WORDS} total spoken words, with flexible scene pacing bands. Every sentence must earn its place. Every episode must feel like a different mini-game, not a synonym rewrite of the previous episode. "+str(extra or ""))

def _load_recent_history(limit=20):
 path=Path(__file__).resolve().parent.parent/"interactive_topic_history.json"
 try:
  rows=json.loads(path.read_text(encoding="utf-8")); return [x for x in rows[-limit:] if isinstance(x,dict)] if isinstance(rows,list) else []
 except Exception:return []
def _profile_for(topic,number_hint=0):
 digest=hashlib.sha256(f"{topic}|{number_hint}".encode()).digest(); return CREATIVE_PROFILES[int.from_bytes(digest[:4],"big")%len(CREATIVE_PROFILES)]
def _normalized_words(text):return re.findall(r"[a-z0-9']+",str(text or "").lower())
def _validate_internal_novelty(scenes):
 all_text=" ".join(str(s.get("narration","") ) for s in scenes if isinstance(s,dict))
 if GENERIC_OPENERS.search(all_text):raise RuntimeError("Riddle script contains a banned generic opener.")
 grams={}
 for index,scene in enumerate(scenes):
  words=_normalized_words(scene.get("narration",""))
  for i in range(max(0,len(words)-3)):
   gram=tuple(words[i:i+4])
   if len(set(gram))<2:continue
   grams.setdefault(gram,set()).add(index)
 if [g for g,v in grams.items() if len(v)>=2]:raise RuntimeError("Riddle narration repeats a 4-word phrase across scenes; regenerate with a different structure.")
 if sum(str(s.get("narration","")).count("?") for s in scenes)>2:raise RuntimeError("Riddle contains too many repeated question beats.")

def _remove_next_topic_leak(scenes,next_topic):
 """Remove an obvious future-topic sentence from Scenes 1-6 without weakening the hard boundary guard."""
 key=_base._clean(next_topic).lower()
 if not key:return False
 key_norm=re.sub(r"[^a-z0-9]+"," ",key).strip()
 future=re.compile(r"\b(next|coming|later|after this|afterwards|up next|following|future|we(?:'ll| will) see|you(?:'ll| will) see|stay tuned|part 2|next short|next video|tomorrow)\b",re.I)
 changed=False
 for scene in scenes[:6]:
  text=_base._clean(scene.get("narration","")); sentences=[s.strip() for s in re.split(r"(?<=[.!?])\s+",text) if s.strip()]
  kept=[]; removed=False
  for sentence in sentences:
   sentence_norm=re.sub(r"[^a-z0-9]+"," ",sentence.lower()).strip()
   if key_norm and key_norm in sentence_norm and (future.search(sentence) or len(sentences)>1):
    removed=True; changed=True; continue
   kept.append(sentence)
  if removed:
   repaired=_base._clean(" ".join(kept))
   if repaired:
    scene["narration"]=repaired; scene["subtitle_text"]=repaired
   else:return False
 return changed

def generate_script(topic,config,research=None,extra_feedback=""):
 from google import genai
 from google.genai import types
 import time
 try: from riddle_personality import choose_personality
 except Exception: choose_personality=None
 topic=_base._clean(topic)
 if not topic:raise RuntimeError("Riddle topic is empty.")
 recent=_load_recent_history(); number_hint=len(recent)+1; profile=_profile_for(topic,number_hint)
 recent_topics=[str(x.get("topic","")).strip() for x in recent if x.get("topic")]; recent_answers=[str(x.get("answer","")).strip() for x in recent[-10:] if x.get("answer")]
 personality=choose_personality(topic,"",number_hint) if choose_personality else {"name":"dynamic","direction":"Use a distinctive conversational performance without changing the riddle's logic.","speed":1.0}
 client=genai.Client(api_key=_base._api_key()); recent_block="\n".join(f"- {x}" for x in recent_topics[-12:]) or "- none available"; answer_block=", ".join(recent_answers[-8:]) or "none available"
 prompt=f"""RIDDLES SHORTS MODE — NARRATION FIRST.
CURRENT RIDDLE: {topic}

CREATIVE PROFILE: {profile['name']}
Hook direction: {profile['hook']}
Story flow: {profile['flow']}

PERSONALITY FOR THIS EPISODE: {personality['name']}
PERFORMANCE DIRECTION: {personality['direction']}
Write the actual spoken wording so the personality is audible even before TTS processing. This is not merely a metadata label. Change sentence rhythm, word choice, reactions, punctuation, pauses and conversational attitude to fit the personality. Do NOT exaggerate into a cartoon unless the personality naturally calls for it. Keep every clue precise and solvable. Never let personality wording reveal the NEW answer.

Create exactly 7 scenes. Return the normal production JSON schema.
The Short must work as a spoken mini-game. Stock media is only mood/context and must never be needed to solve the riddle.
Target {MIN_WORDS}-{MAX_WORDS} total spoken words. Aim roughly 18-25 seconds at a natural energetic pace. Do not pad.
SCENE BANDS: Scene 1 4-18 words; Scene 2 7-20; Scene 3 5-16; Scene 4 5-16; Scene 5 5-12; Scene 6 3-8 with conversational 3…2…1; Scene 7 12-26 and MUST preserve a short answer gap plus subscribe/follow CTA for the answer in the next Short.
IMPORTANT: Scene 7 may be longer than the other scenes because it owns the retention CTA. Never reject a good script merely because Scene 7 needs 20-26 words.
MECHANIC DIVERSITY: Rotate wording traps, double meanings, lateral logic, expectation reversals, misconception traps, causal misdirection, category shifts, temporal ambiguity, and psychological assumptions. Do not default to the same mechanic.
LANGUAGE DIVERSITY: Avoid the repeated pattern "Can you solve this? ... Most people think ... But ... Lock in your answer ... Three, two, one." Use personality-specific sentence shapes and rhythm.
RECENT TOPICS — avoid conceptual neighbors:
{recent_block}
RECENT ANSWERS — avoid repeated answer domains:
{answer_block}
Do not paraphrase recent riddles. Keep clues spoken-only. Do not reveal, spell out, strongly hint at, or explain the NEW answer.
Avoid generic filler and greetings. Do not use visual-dependent clues.
{_feedback(extra_feedback)}
"""
 last_error=None; attempts=0
 while attempts<_base.MAX_ATTEMPTS:
  try:
   retry=f"\nFix previous error: {last_error}. Change wording AND structural approach while preserving the selected personality. Keep total spoken words between {MIN_WORDS} and {MAX_WORDS}." if last_error else ""
   response=client.models.generate_content(model=_base.MODEL_NAME,contents=prompt+retry,config=types.GenerateContentConfig(system_instruction=_base.SYSTEM_PROMPT,response_mime_type="application/json",response_json_schema=_base._build_schema(),temperature=0.95))
   raw=getattr(response,"text",None)
   if not raw:raise RuntimeError("Gemini returned an empty riddle script.")
   data=_base._parse(raw); data.setdefault("next_short",{"topic":"riddle answer reveal","teaser":"answer reveal"})
   original_boundary=_base._ensure_scene7_boundary; original_bridge=_base._validate_natural_bridge; _base._ensure_scene7_boundary=lambda narration,next_topic:_base._clean(narration); _base._validate_natural_bridge=lambda narration,next_topic:"riddle continuation"
   try: result=_base._normalize(data,topic,enforce_word_contract=False)
   finally: _base._ensure_scene7_boundary=original_boundary; _base._validate_natural_bridge=original_bridge
   scenes=result.get("scene_plan") or []
   if len(scenes)!=7:raise RuntimeError("Riddle script must contain exactly 7 scenes.")
   total=sum(len(_base._words(s.get("narration",""))) for s in scenes)
   if not MIN_WORDS<=total<=MAX_WORDS:raise RuntimeError(f"Riddle narration length {total} outside optimized {MIN_WORDS}-{MAX_WORDS} range.")
   for index,(low,high) in enumerate(SCENE_WORD_BUDGETS):
    count=len(_base._words(scenes[index].get("narration","")))
    if count<low or count>high:raise RuntimeError(f"Riddle Scene {index+1} has {count} words; expected {low}-{high} for pacing.")
   previous_answer=""; previous_number=None
   m=re.search(r'Reveal Riddle #(\d+) answer naturally: "([^"]+)"',str(extra_feedback or ""),re.I)
   if m:
    previous_number=int(m.group(1)); previous_answer=_base._clean(m.group(2)); first=scenes[0]; first_narration=_base._clean(first.get("narration",""))
    if previous_answer.lower() not in first_narration.lower(): first["narration"]=_base._clean(f"Last answer: {previous_answer}. Did you get it? "+first_narration)
    if previous_answer.lower() not in _base._clean(scenes[0].get("narration","")).lower():raise RuntimeError(f"Previous riddle answer must be revealed in Scene 1: {previous_answer!r}")
    total=sum(len(_base._words(s.get("narration",""))) for s in scenes)
    if total>MAX_WORDS:raise RuntimeError(f"Riddle narration length {total} outside optimized {MIN_WORDS}-{MAX_WORDS} range after reveal insertion.")
   next_topic=_base._clean((result.get("next_short") or {}).get("topic"))
   if _remove_next_topic_leak(scenes,next_topic):
    total=sum(len(_base._words(s.get("narration",""))) for s in scenes)
   next_key=re.sub(r"[^a-z0-9 ]"," ",next_topic.lower()).strip()
   for scene in scenes[:6]:
    if next_key and next_key in re.sub(r"[^a-z0-9 ]"," ",scene["narration"].lower()):raise RuntimeError("Next topic appeared before Scene 7.")
   if not MIN_WORDS<=total<=MAX_WORDS:raise RuntimeError(f"Riddle narration length {total} outside optimized {MIN_WORDS}-{MAX_WORDS} range after continuation cleanup.")
   _validate_internal_novelty(scenes)
   result["riddle_creative_profile"]=profile["name"]; result["riddle_mechanic_policy"]="rotating_mechanic"; result["riddle_novelty_guard"]="internal_phrase_and_structure"; result["riddle_recent_topic_context"]=recent_topics[-12:]
   result["riddle_personality"]=dict(personality); result["riddle_personality_name"]=personality["name"]; result["riddle_personality_direction"]=personality["direction"]; result["riddle_personality_version"]="v2_prompt_and_tts"
   print(f"🧩 Riddles Shorts narration validated: {total} words | profile={profile['name']} | personality={personality['name']} | personality_prompt=ACTIVE | novelty_guard=PASS"+(f" | Riddle #{previous_number} answer revealed in Scene 1" if previous_answer else ""))
   return result
  except Exception as e:
   last_error=f"{type(e).__name__}: {e}"; attempts+=1
   if attempts<_base.MAX_ATTEMPTS:print(f"⚠️ Riddle script attempt {attempts} rejected: {last_error}"); time.sleep(2)
 raise RuntimeError(f"RIDDLE SCRIPT GENERATION FAILED after bounded retries. Last error: {last_error}")
