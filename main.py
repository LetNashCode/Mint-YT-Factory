"""Mint-YT-Factory production pipeline."""
from __future__ import annotations
import argparse, json, os, re, time, yaml
from topics import get_next_topic, save_next_short, commit_topic, validate_topic_for_pipeline, _generate_topic, _read_used, _PENDING_PREFIX, reserve_next_short
from generate_script import generate_script
from tts import synthesize_script
from stock_media_resilient import generate_media
from music import download_music
from sfx import generate_sfx
from assemble import assemble_video
from upload_youtube import upload_video
from pathlib import Path
from social_publish import publish_social_reels
from validate_video import validate_final_video
from learning_context import load_learning_context
from learning_engine import refresh_playbook, get_playbook, score_candidate_topic, select_creative_strategy
from topic_history import record_topic

CONTINUATION_MANIFEST = "continuation_state.json"
EXPECTED_UPLOAD_BITRATE_MBPS = 100.0
MIN_UPLOAD_BITRATE_MBPS = 80.0
EXPECTED_UPLOAD_RESOLUTION = (2160, 3840)
EXPECTED_UPLOAD_FPS = 60
MAX_SCRIPT_ATTEMPTS = 4
MAX_TRANSIENT_GEMINI_RETRIES = 8


def load_config():
    with open("config.yaml", "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict): raise RuntimeError("config.yaml is invalid.")
    return config

def save_json(data, path):
    directory = os.path.dirname(path)
    if directory: os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle: json.dump(data, handle, indent=2, ensure_ascii=False)

def _normalise_topic_text(value): return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
def _word_count(value): return len(re.findall(r"\b[\w'-]+\b", str(value or "")))
def _split_sentences(text): return [p.strip() for p in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if p.strip()]
_BANNED_BRIDGE_PATTERNS=(r"^(?:and\s+)?next\b",r"^then\s+comes\b",r"^coming\s+next\b",r"^up\s+next\b",r"^stay\s+tuned\b",r"^part\s+2\b",r"^have\s+you\s+ever\s+wondered\b",r"^ever\s+wondered\b",r"^wonder\s+why\b",r"^curious\s+(?:why|how|what)\b")
def _is_canned_bridge(sentence): return any(re.search(pattern,str(sentence or "").strip(),re.I) for pattern in _BANNED_BRIDGE_PATTERNS)
def _content_words(value):
    stop={"why","what","when","where","how","does","do","did","is","are","the","and","that","this","with","from","into","your","about"}
    return {w for w in re.findall(r"[a-z0-9]+",str(value or "").lower()) if len(w)>=4 and w not in stop}
def _bridge_matches_topic(bridge,topic): return bool(_content_words(topic)&_content_words(bridge)) if _content_words(topic) else True

def _generate_natural_bridge(current_topic,next_topic):
    """Create a varied spoken handoff; rotate tease mechanisms using creative memory."""
    current=str(current_topic or "").strip().rstrip(".!?")
    nxt=str(next_topic or "").strip().rstrip(".!?")
    if not nxt: raise RuntimeError("Continuation topic is empty.")
    try:
        from creative_memory import choose_tease_type
        tease_type=choose_tease_type(current,nxt)
    except Exception:
        tease_type="curiosity_connection"
    variants={
        "curiosity_connection": f"And once you know that, there's another everyday mystery hiding in plain sight: {nxt}?",
        "unexpected_consequence": f"But that isn't the only strange consequence. Wait until you see what happens with {nxt}.",
        "pattern_connection": f"And here's where it gets even stranger: the same idea shows up in {nxt}.",
        "challenge": f"Next time you see this, test yourself with one more mystery: {nxt}.",
        "observation_prompt": f"Keep an eye out for this one too—you've probably noticed it without realizing why: {nxt}?",
        "hidden_connection": f"There's a completely different everyday thing hiding the same kind of trick: {nxt}.",
        "unanswered_question": f"Okay, but that leaves one question worth chasing next: {nxt}?",
        "contrast": f"If that surprised you, the opposite happens for a very different reason: {nxt}.",
        "everyday_reveal": f"And there's another ordinary thing with an equally strange explanation: {nxt}.",
        "mystery_escalation": f"One mystery down. The next one gets even harder to explain: {nxt}?",
    }
    return variants.get(tease_type,variants["curiosity_connection"]),tease_type
def _lock_canonical_topic(script,current_topic,locked_topic=None):
    used=[str(current_topic)]; used.extend(x for x in _read_used() if not str(x).startswith(_PENDING_PREFIX))
    candidate=str(locked_topic or (script.get("next_short") or {}).get("topic","")).strip()
    if locked_topic:
        # reserve_next_short() is the authoritative validation point. Once it
        # creates the pending reservation, the successor remains metadata-only;
        # re-running novelty validation here can reject or replace a perfectly
        # valid reserved successor and break deterministic topic chaining.
        candidate=str(locked_topic).strip()
        if not validate_topic_for_pipeline(candidate,used=used,check_duplicate=False):
            raise RuntimeError(f"Reserved continuation topic failed basic pipeline validation: {candidate!r}")
    elif not validate_topic_for_pipeline(candidate,used=used,check_duplicate=True):
        candidate=_generate_topic(used); print("🛠️ Repaired invalid next_short.topic with topic engine: "+candidate)
    if _word_count(candidate)>7: raise RuntimeError("Generated next topic is too long for continuation metadata: "+candidate)
    script.setdefault("next_short",{})["topic"]=candidate; return candidate

def _strip_future_continuations_from_prior_scenes(script, future_topics):
    """Remove any model-authored future-topic handoff from the six spoken scenes."""
    topic_keys = [_normalise_topic_text(x) for x in (future_topics or []) if _normalise_topic_text(x)]
    teaser_patterns = (
        r"^and\s+once\s+you\s+know\s+that\b",
        r"^but\s+(?:that|this)\s+(?:isn't|is not)\s+the\s+only\b",
        r"^there(?:'s|\s+is)\s+another\b",
        r"^there(?:'s|\s+is)\s+a\s+(?:completely\s+different|different|another)\b",
        r"^one\s+mystery\s+down\b",
        r"^next\s+time\s+you\b",
        r"^next\s+(?:comes|up|is|one|mystery|question)\b",
        r"^keep\s+an\s+eye\s+out\s+for\s+this\s+one\b",
        r"^if\s+that\s+surprised\s+you\b",
        r"^okay,?\s+but\s+that\s+leaves\b",
        r"^one\s+more\s+mystery\b",
        r"^another\s+(?:everyday|ordinary)\s+(?:mystery|thing)\b",
        r"^the\s+same\s+(?:idea|trick)\s+(?:shows\s+up|appears)\s+in\b",
        r"^wait\s+until\s+you\s+see\s+what\s+happens\s+with\b",
        r"^up\s+next\b",
        r"^coming\s+next\b",
        r"^stay\s+tuned\b",
        r"^part\s+2\b",
    )
    removed = 0
    for scene in (script.get("scene_plan") or []):
        narration = str(scene.get("narration") or "").strip()
        if not narration:
            continue
        kept = []
        for sentence in _split_sentences(narration):
            normalized = _normalise_topic_text(sentence)
            exact_future_topic = any(key and key in normalized for key in topic_keys)
            sentence_words = _content_words(sentence)
            topic_overlap = any(
                len(sentence_words & _content_words(topic)) >= 2
                for topic in (future_topics or [])
                if _content_words(topic)
            )
            teaser = any(re.search(pattern, sentence, re.I) for pattern in teaser_patterns)
            if exact_future_topic or topic_overlap or teaser:
                removed += 1
                print("🧹 Removed future-topic continuation from six-scene Publish narration: " + sentence)
            else:
                kept.append(sentence)
        scene["narration"] = " ".join(kept).strip()
        scene["subtitle_text"] = scene["narration"]
    if removed:
        print(f"🧹 Removed {removed} future-topic continuation sentence(s) from six-scene story")
    return removed

def lock_next_topic(script,current_topic,locked_topic=None,stale_topics=None):
    """Lock the successor as metadata only; Publish has no spoken continuation scene."""
    previous=str((script.get("next_short") or {}).get("topic") or "").strip()
    stale_topics=[str(x).strip() for x in (stale_topics or []) if str(x).strip()]
    canonical=_lock_canonical_topic(script,current_topic,locked_topic=locked_topic)
    cleanup_topics=list(dict.fromkeys(
        ([previous] if _normalise_topic_text(previous) and _normalise_topic_text(previous) != _normalise_topic_text(current_topic) else [])
        + stale_topics + [canonical]
    ))
    _strip_future_continuations_from_prior_scenes(script, cleanup_topics)
    scenes=script.get("scene_plan") or []
    if len(scenes) != 6:
        raise RuntimeError(f"Publish Short requires exactly 6 scenes, got {len(scenes)}.")
    # The final scene is the complete current-topic payoff. No future topic is
    # spoken and no continuation bridge is inserted.
    script.pop("tease_type", None)
    if isinstance(script.get("next_short"), dict):
        script["next_short"].pop("teaser", None)
    print("🔒 Canonical next topic stored as metadata only: "+canonical)
    return script,canonical

