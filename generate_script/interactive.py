"""Riddles Shorts generator with its own ending contract."""
from __future__ import annotations
from . import entertainment as _base

def _feedback(extra=""):
    return ("RIDDLES SHORTS ONLY. This is not a Publish Shorts explainer. "
            "Do not require a topic continuation bridge or current-riddle payoff. "
            "A previous riddle answer may be revealed, but the NEW answer must remain locked. "
            "The ending must explicitly promise that the NEW answer will be revealed in the next Riddle Short. "
            "Narration length is flexible and must never be forced into the Publish Shorts 90-135 word contract. "
            + str(extra or ""))

def generate_script(topic,config,research=None,extra_feedback=""):
    from google import genai
    from google.genai import types
    import time
    topic=_base._clean(topic)
    if not topic: raise RuntimeError("Riddle topic is empty.")
    client=genai.Client(api_key=_base._api_key())
    prompt=f"""RIDDLES SHORTS MODE.
CURRENT RIDDLE: {topic}
Create exactly 7 scenes. Return the normal production JSON schema.
{_feedback(extra_feedback)}
Visual rule: never show the NEW answer while asking the riddle or during countdown.
"""
    last_error=None
    attempts=0
    while attempts<_base.MAX_ATTEMPTS:
        try:
            retry=f"\nFix previous error: {last_error}" if last_error else ""
            response=client.models.generate_content(model=_base.MODEL_NAME,contents=prompt+retry,
                config=types.GenerateContentConfig(system_instruction=_base.SYSTEM_PROMPT,response_mime_type="application/json",
                response_json_schema=_base._build_schema(),temperature=0.85))
            raw=getattr(response,"text",None)
            if not raw: raise RuntimeError("Gemini returned an empty riddle script.")
            data=_base._parse(raw)
            data.setdefault("next_short",{"topic":"riddle answer reveal","teaser":"answer reveal"})
            original_boundary=_base._ensure_scene7_boundary
            original_bridge=_base._validate_natural_bridge
            _base._ensure_scene7_boundary=lambda narration,next_topic:_base._clean(narration)
            _base._validate_natural_bridge=lambda narration,next_topic:"riddle continuation"
            try:
                result=_base._normalize(data,topic,enforce_word_contract=False)
            finally:
                _base._ensure_scene7_boundary=original_boundary
                _base._validate_natural_bridge=original_bridge
            scenes=result.get("scene_plan") or []
            if len(scenes)!=7: raise RuntimeError("Riddle script must contain exactly 7 scenes.")
            total=sum(len(_base._words(s.get("narration",""))) for s in scenes)
            if not 20<=total<=260: raise RuntimeError(f"Riddle narration length {total} outside flexible 20-260 range.")
            print(f"🧩 Riddles Shorts narration validated: {total} words")
            return result
        except Exception as e:
            last_error=f"{type(e).__name__}: {e}";attempts+=1
            if attempts<_base.MAX_ATTEMPTS:
                print(f"⚠️ Riddle script attempt {attempts} rejected: {last_error}");time.sleep(2)
    raise RuntimeError(f"RIDDLE SCRIPT GENERATION FAILED after bounded retries. Last error: {last_error}")
