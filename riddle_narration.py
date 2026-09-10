"""Retention-focused narration polish for narration-led Riddles Shorts."""
from __future__ import annotations
import hashlib
import re

MIN_WORDS = 60
MAX_WORDS = 95
SCENE_WORD_BUDGETS = ((8, 14), (10, 18), (8, 14), (8, 14), (8, 12), (5, 8), (13, 15))

PERSONALITY_GUIDANCE = {
    "mischievous":"Tease the listener, use sly confidence, playful rhetorical turns, and a knowing pause before the trap.",
    "angry":"Sound hilariously impatient with the obvious wrong answer. Use punchy sentences and sharp emphasis, never hostility.",
    "happy":"Sound genuinely delighted and infectious. Use bright wording, upbeat rhythm, and playful excitement.",
    "seductive":"Use smooth, intimate, controlled phrasing and deliberate pauses. Make the mystery feel irresistible, never sexual or explicit.",
    "sick":"Use tired, dry, understated wording with short breaths and low-energy reactions. Keep the puzzle crystal clear.",
    "creepy":"Use quiet, unsettling wording, sparse sentences, and tension before key words. Keep it eerie rather than graphic.",
    "confident":"Use crisp, certain statements and effortless challenge. Sound like you already know the listener will get trapped.",
    "nervous":"Use slightly hesitant, anxious phrasing and quick corrections around the trap. Preserve clarity and momentum.",
    "detective":"Use investigative language, measured observations, and clue-by-clue reasoning without giving away the answer.",
    "sleepy":"Use relaxed, dry, understated phrasing. Let pauses and calm delivery make an ordinary riddle feel strangely interesting.",
    "hyped":"Use energetic verbs, punchy rhythm, excitement, and a stronger countdown. Never sacrifice clarity for speed.",
    "innocent":"Sound sweet and genuinely curious while accidentally leading the listener toward the trap. Avoid childish filler.",
}

REVEAL_STYLES = ("answer_check","quick_payoff","listener_score","confidence_check","clean_reveal","retro_reveal","challenge_reveal","curiosity_reveal")
REVEAL_LINES = {
 "answer_check": ("Last answer: {answer}.","The last answer was {answer}."),
 "quick_payoff": ("Last puzzle: {answer}.","The mystery answer was {answer}."),
 "listener_score": ("Point if you said {answer}.","Got {answer}? Take the point."),
 "confidence_check": ("Be honest: {answer}.","Last time, it was {answer}."),
 "clean_reveal": ("Last riddle answer: {answer}.","The answer we left hanging: {answer}."),
 "retro_reveal": ("Reveal time: {answer}.","One loose end: {answer}."),
 "challenge_reveal": ("Last round: {answer}.","Did you get {answer}?"),
 "curiosity_reveal": ("Remember the last one? {answer}.","That little mystery? {answer}."),
}
BRIDGE_LINES = {s:(a,b) for s,a,b in [
 ("answer_check","New puzzle.","Try this one."),("quick_payoff","Fresh puzzle.","This one changes gears."),("listener_score","Next test.","Your next challenge starts now."),("confidence_check","Reset.","Forget that guess."),("clean_reveal","New puzzle.","Let's switch gears."),("retro_reveal","That's settled.","New puzzle."),("challenge_reveal","Round two.","Try this one."),("curiosity_reveal","New mystery.","This one isn't done yet.") ]}
ENDING_LINES=("Lock in your answer. Subscribe and follow for the reveal in the next Short.","Keep your first guess. Follow and subscribe to find out if you were right in the next Short.","Don't change it now. Subscribe and follow for the answer in the next Short.","Answer locked. Follow and subscribe for the reveal in the next Short.","Got your guess? Subscribe and follow for the answer in the next Short.")

def _words(text): return re.findall(r"\b[\w'-]+\b",str(text or ""))
def _sync_visuals(scene):
    narration=str(scene.get("narration"," ")).strip()
    for visual in scene.get("visuals") or []:
        if isinstance(visual,dict):
            visual["spoken_line"]=narration; visual["visual_focus"]=narration[:180]; visual["visual_action"]="Atmospherically support the spoken beat only; stock media is not a clue and must never reveal the current riddle answer."
    scene["subtitle_text"]=narration

def _variant(topic,number,answer):
    return int.from_bytes(hashlib.sha256(f"{topic}|{number}|{answer}".encode()).digest()[:4],"big") % len(REVEAL_STYLES)
def _reveal_line(number,answer,variant):
    style=REVEAL_STYLES[variant%len(REVEAL_STYLES)]; lines=REVEAL_LINES[style]; return lines[(variant//len(REVEAL_STYLES))%len(lines)].format(answer=answer),style
def _bridge_line(variant,style): return BRIDGE_LINES[style][(variant//2)%2]
def _ending_line(variant): return ENDING_LINES[variant%len(ENDING_LINES)]
def _replace_canned_ending(text):
    out=str(text or "").strip()
    for pattern in (r"(?:the answer to riddle\s*#?\d+\s*(?:will be|comes|is).*?$)",r"(?:answer.*?next riddle short.*?$)",r"(?:answer.*?next short.*?$)",r"(?:subscribe.*?next short.*?$)",r"(?:follow.*?next short.*?$)"): out=re.sub(pattern,"",out,flags=re.I)
    return out.strip()
def _remove_visual_dependency(text):
    out=str(text or "")
    for p,r in {r"\blook at this\b":"listen to this",r"\blook closely\b":"listen closely",r"\blook carefully\b":"listen carefully",r"\bwhat do you see\b":"what do you think",r"\bin this picture\b":"in this riddle",r"\bon screen\b":"in the question",r"\bwatch this\b":"hear this"}.items(): out=re.sub(p,r,out,flags=re.I)
    return out
def _trim_low_value_filler(text):
    out=str(text or "").strip(); filler=re.compile(r"\b(?:okay|alright|so|basically|well|guys|come on|listen up),?\s+",re.I)
    for _ in range(2):
        new=filler.sub("",out,count=1).strip()
        if new==out: break
        out=new
    return out
def _compact_scene(scene): scene["narration"]=_trim_low_value_filler(_remove_visual_dependency(scene.get("narration","")))

def _fit_scene1(text, max_words=14):
    """Keep the previous-answer reveal while preserving a compact new-riddle hook."""
    text=_trim_low_value_filler(text)
    words=_words(text)
    if len(words)<=max_words:
        return text
    sentences=[s.strip() for s in re.split(r"(?<=[.!?])\s+",text) if s.strip()]
    if not sentences:
        return " ".join(words[:max_words]).rstrip(" ,;:-") + "."
    kept=[]; total=0
    for sentence in sentences:
        n=len(_words(sentence))
        if not kept or total+n<=max_words:
            kept.append(sentence); total+=n
        if total>=max_words:
            break
    result=" ".join(kept).strip()
    if len(_words(result))<=max_words:
        return result
    return " ".join(_words(result)[:max_words]).rstrip(" ,;:-") + "."

def polish_riddle_script(script,previous,number):
    scenes=script.get("scene_plan") or []
    if len(scenes)!=7: raise RuntimeError("Riddle script must contain exactly 7 scenes before narration polish.")
    variant=_variant(str(script.get("topic","")),number,str((previous or {}).get("answer","")))
    personality=dict(script.get("riddle_personality") or {})
    personality_name=str(personality.get("name") or script.get("riddle_personality_name") or "").strip().lower()
    for scene in scenes: _compact_scene(scene)
    reveal_style="none"
    if previous:
        answer=str(previous.get("answer","")).strip(); previous_number=int(previous.get("number",number-1))
        if answer:
            first=scenes[0]; existing=str(first.get("narration","")).strip()
            existing=re.sub(rf"^(?:before today.?s challenge,?\s*)?(?:here.?s|here is|the answer to)?\s*riddle\s*#?{previous_number}[^.?!]*[.?!]\s*","",existing,flags=re.I)
            reveal,reveal_style=_reveal_line(previous_number+1,answer,variant)
            bridge=_bridge_line(variant,reveal_style)
            # The old implementation prepended a full reveal + full bridge + full
            # Gemini hook, which could inflate Scene 1 to 20-30 words and then fail
            # the pacing gate. Build the combined hook first, then fit it to Scene 1.
            first["narration"]=_fit_scene1(f"{reveal} {bridge} {existing}", max_words=SCENE_WORD_BUDGETS[0][1])
            first["purpose"]="hook"; first["retention_purpose"]="pattern_break_and_payoff"
    scenes[4]["narration"]=_trim_low_value_filler(scenes[4].get("narration",""))
    if not re.search(r"\b(first answer|first guess|lock|commit|pick|choose|guess)\b",scenes[4]["narration"],re.I): scenes[4]["narration"]="Lock in your first answer. Don't change it."
    scenes[4]["retention_purpose"]="forced_commitment"
    pressure=_trim_low_value_filler(scenes[5].get("narration","")); pressure=re.sub(r"\b(?:10|9|8|7|6|5|4|3|2|1)(?:\s*,?\s*(?:10|9|8|7|6|5|4|3|2|1)){2,}\b","Final guess. Three… two… one.",pressure,count=1)
    if not re.search(r"three[.… ]+two[.… ]+one|3[.… ]*2[.… ]*1",pressure,re.I): pressure="Final guess. Three… two… one."
    scenes[5]["narration"]=pressure; scenes[5]["retention_purpose"]="countdown_pressure"
    last=scenes[-1]; text=_replace_canned_ending(last.get("narration","")); text=text.rstrip(" .!?"); ending=_ending_line(variant+2); last["narration"]=f"{text}. {ending}" if text else ending; last["purpose"]="ending"; last["retention_purpose"]="answer_loop_subscribe_follow"
    for scene in scenes: _compact_scene(scene); _sync_visuals(scene)
    total=sum(len(_words(s.get("narration",""))) for s in scenes)
    if total<MIN_WORDS or total>MAX_WORDS: raise RuntimeError(f"Riddle narration length {total} outside optimized {MIN_WORDS}-{MAX_WORDS} range.")
    for index,(low,high) in enumerate(SCENE_WORD_BUDGETS):
        count=len(_words(scenes[index].get("narration","")))
        if count<low or count>high: raise RuntimeError(f"Riddle Scene {index+1} has {count} words; expected {low}-{high} for pacing.")
    script["riddle_narration_version"]="retention_v8_compact_reveal"; script["riddle_reveal_style"]=reveal_style; script["riddle_reveal_variant"]=variant; script["riddle_personality_name"]=personality_name or "dynamic"; script["riddle_personality_guidance"]=PERSONALITY_GUIDANCE.get(personality_name,""); script["riddle_word_target"]={"min":MIN_WORDS,"max":MAX_WORDS}; script["riddle_scene_word_budgets"]=[list(x) for x in SCENE_WORD_BUDGETS]; script["estimated_narration_seconds"]=round(total/3.2,1); script["visual_dependency"]="none"
    return script
