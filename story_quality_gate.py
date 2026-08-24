"""Final hard gate for narration/visual coherence before TTS and Pexels."""
from __future__ import annotations
import re

MAX_ATTEMPTS = 4
MIN_STORY_WORDS = 80
MAX_STORY_WORDS = 112

ABSTRACT_BEATS = (
    "plotting chemical warfare", "chemical warfare", "plotting", "secret code",
    "secret world", "underground world", "reveals its secret", "reveals the secret",
    "molecules dance", "atoms dance", "physics dances", "physics plays",
    "nature plays", "kitchen symphony", "becomes an orchestra", "plays an orchestra",
    "tiny workers", "invisible machine", "invisible machines", "magic happens",
    "the magic happens", "gets angry", "gets confused", "has a conversation",
    "is having a conversation", "tells a story", "tells us", "wins the battle",
    "loses the battle", "fights the", "comes alive", "searching for moisture",
    "desperate panic", "chemical invader", "secret", "invader",
)

# Only reject these when they are used as VISUAL actions. Ordinary narration can
# naturally contain words such as "wins", "climb", or "fights" without making
# the visual contract abstract.
ABSTRACT_VISUAL_SINGLE_WORDS = {
    "whispers", "dances", "thinks", "decides", "communicates", "remembers",
    "plotting", "reveals", "invades", "imagines", "wonders",
}

CTA_WORDS = (
    "subscribe", "follow for", "like and subscribe", "smash that", "comment below",
    "link in bio", "click the link", "watch next", "watch why", "watch how",
    "part 2", "stay tuned", "don't miss", "hit subscribe", "decode why",
)
FUTURE_MARKERS = (
    "another question", "one more question", "one more thing", "that makes you wonder",
    "that makes you ask", "speaking of", "on a related note", "coming next",
    "next topic", "next short", "next video", "then comes",
)

PHYSICAL_ACTIONS = {
    "cut","cuts","slice","slices","chop","chops","dice","dices","peel","peels",
    "pour","pours","boil","boils","bubble","bubbles","rise","rises","fall","falls",
    "drop","drops","melt","melts","freeze","freezes","crack","cracks","stick","sticks",
    "rub","rubs","squeeze","squeezes","spin","spins","roll","rolls","shake","shakes",
    "open","opens","close","closes","expand","expands","shrink","shrinks","change","changes",
    "drip","drips","flow","flows","rush","rushes","escape","escapes","hit","hits","touch","touches",
    "land","lands","bounce","bounces","bend","bends","break","breaks","tear","tears","burn","burns",
    "glow","glows","flash","flashes","move","moves","turn","turns","form","forms","collapse","collapses",
    "spread","spreads","dry","dries","wet","wets","mix","mixes","react","reacts","release","releases",
    "released","reach","reaches","reached","fill","fills","filled","irritate","irritates","sting","stings",
    "blink","blinks","blinked","swell","swells","water","waters","stream","streams","flowing","running",
    "pouring","cutting","slicing","chopping","opening","closing","rising","falling","floating","appearing",
    "forming","changing","visible","shown","shows","showing","close-up","closeup","wetness","liquid",
    "droplets","droplet","steam","smoke","foam","teardrop","teardrops","red","watery","swollen","cracked",
    "broken","hot","cold","cloudy","mist","misting","spray","sprays","leak","leaks","climb","climbs",
    "fight","fights","win","wins","lose","loses","hold","holds","push","pushes","pull","pulls",
}

def _words(text):
    return re.findall(r"\b[\w'-]+\b", str(text or "").lower())

def _clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()

def _hits(text, phrases):
    low = _clean(text).lower()
    return [p for p in phrases if p in low]

def _abstract_visual_word_hits(text):
    return sorted(set(_words(text)) & ABSTRACT_VISUAL_SINGLE_WORDS)

def _physical_action(text):
    low = _clean(text).lower()
    return any(re.search(rf"\b{re.escape(x)}\b", low) for x in PHYSICAL_ACTIONS)

def _validate(script, topic):
    errors=[]
    scenes=script.get("scene_plan") or []
    if len(scenes)!=7:
        return [f"expected 7 scenes, got {len(scenes)}"]

    next_topic=_clean((script.get("next_short") or {}).get("topic"))
    if not next_topic:
        errors.append("next_short.topic is empty")

    total_words=0
    for si,scene in enumerate(scenes,1):
        narration=_clean(scene.get("narration"))
        total_words += len(_words(narration))
        if not narration:
            errors.append(f"Scene {si}: empty narration")
            continue
        if _hits(narration,CTA_WORDS):
            errors.append(f"Scene {si}: CTA/marketing language inside narration")
        if si<7 and _hits(narration,FUTURE_MARKERS):
            errors.append(f"Scene {si}: future-topic transition leaked into story")
        abstract=_hits(narration,ABSTRACT_BEATS)
        if abstract:
            errors.append(f"Scene {si}: non-literal narration: {', '.join(abstract[:4])}")

        visuals=scene.get("visuals") or []
        if len(visuals)!=2:
            errors.append(f"Scene {si}: exactly 2 visuals required")
            continue

        previous_focus=""
        for vi,visual in enumerate(visuals,1):
            focus=_clean(visual.get("visual_focus"))
            action=_clean(visual.get("visual_action"))
            prompt=_clean(visual.get("image_prompt"))
            spoken=_clean(visual.get("spoken_line"))
            combined=" ".join((focus,action,prompt))
            label=f"Scene {si} Shot {vi}"

            if len(prompt.split())<8:
                errors.append(f"{label}: image prompt too vague")
            if len(prompt.split())>60:
                errors.append(f"{label}: image prompt too long")
            if not focus or not action:
                errors.append(f"{label}: missing concrete focus/action")

            abstract_visual=_hits(combined,ABSTRACT_BEATS)
            if abstract_visual:
                errors.append(f"{label}: non-literal visual wording: {', '.join(abstract_visual[:4])}")
            word_hits=_abstract_visual_word_hits(combined)
            if word_hits:
                errors.append(f"{label}: abstract visual action: {', '.join(word_hits)}")
            if _hits(combined,CTA_WORDS):
                errors.append(f"{label}: CTA text in visual contract")
            if not _physical_action(combined):
                errors.append(f"{label}: no searchable physical action/state")

            if spoken:
                narration_words=set(_words(narration))
                spoken_words={w for w in _words(spoken) if len(w)>=4}
                overlap=len(spoken_words & narration_words)/max(1,len(spoken_words))
                if overlap<0.35:
                    errors.append(f"{label}: spoken_line does not map to narration")

            if vi==2 and previous_focus and focus.lower()==previous_focus.lower():
                errors.append(f"{label}: Shot 2 duplicates Shot 1 focus")
            previous_focus=focus

    if total_words<MIN_STORY_WORDS or total_words>MAX_STORY_WORDS:
        errors.append(f"story word count {total_words} outside {MIN_STORY_WORDS}–{MAX_STORY_WORDS}")
    return errors

def patch_story_generation(main):
    original=main.generate_script
    if getattr(original,"_mint_final_story_gate",False):
        return

    def generate_script(topic,config,research=None,extra_feedback=""):
        last_error=""
        for attempt in range(1,MAX_ATTEMPTS+1):
            feedback=(extra_feedback or "") + """

FINAL MINT VISUAL RULES — NON-NEGOTIABLE:
Every narration beat must describe a literal, observable physical event. Avoid metaphorical visual language such as plotting, chemical warfare, dancing molecules, invisible workers, secret worlds, or magic. If an idea is invisible, describe its visible physical consequence instead.
Do not put Subscribe, Follow, CTA, or a different future mystery inside the story.
Every visual needs a concrete subject, a searchable physical action OR clearly visible physical state, and context.
Shot 2 must physically advance Shot 1 rather than repeating the same view.
Aim for 88–105 words, but do not pad. A coherent 80–112 word story is valid because TTS duration is authoritative.
Do not use a future-topic tease inside the generated draft; the production system adds the locked continuation after the gate.
"""
            if last_error:
                feedback += f"""

THE PREVIOUS DRAFT FAILED THIS HARD GATE:
{last_error}
Rewrite the entire story and fix every listed problem. Keep the explanation fun, conversational, concrete, and easy to visualize.
"""
            script=original(topic,config,research,extra_feedback=feedback)
            errors=_validate(script,topic)
            if not errors:
                print(f"🛡️ Final story/visual gate: PASS (attempt {attempt})")
                return script
            last_error=" | ".join(errors[:8])
            print(f"🛡️ Final story/visual gate: FAIL (attempt {attempt}/{MAX_ATTEMPTS}) — {last_error}")

        raise RuntimeError(f"Final story/visual quality gate failed after {MAX_ATTEMPTS} attempts: {last_error}")

    generate_script._mint_final_story_gate=True
    main.generate_script=generate_script
