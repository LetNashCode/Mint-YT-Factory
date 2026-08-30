"""Meme-only SFX selector for Mint-YT-Factory."""
from __future__ import annotations
import hashlib
from sfx_assets import ensure_sfx_assets

KEYWORDS = {
    "vine_boom": ["boom", "shock", "snap", "crack", "bang", "suddenly", "impact", "truth", "finally"],
    "bruh": ["what", "seriously", "really", "ridiculous", "absurd", "wrong", "wait"],
    "metal_pipe": ["hit", "drop", "slam", "crash", "break", "fall"],
    "record_scratch": ["but", "except", "actually", "turns out", "plot twist", "wait"],
    "dramatic_reveal": ["reveal", "secret", "mystery", "why", "answer", "turns out"],
    "windows_error": ["wrong", "error", "doesn't", "cannot", "impossible", "weird"],
    "sad_trombone": ["fail", "failed", "oops", "bad news", "unfortunately"],
    "crowd_gasp": ["no way", "insane", "unexpected", "shocking", "suddenly"],
    "cartoon_boing": ["funny", "quirky", "odd", "bounce", "stretch", "silly"],
    "crickets": ["nothing", "silent", "awkward", "wait", "stops"],
    "airhorn": ["finally", "big", "huge", "winner", "payoff", "ta da"],
    "faaa": ["faaa"],
}

def _text(scene):
    return " ".join(
        str(scene.get(k, "")) for k in
        ("narration", "visual_prompt", "spoken_beat", "physical_action", "visual_action")
    ).lower()

def _category_for_scene(scene, index):
    text = _text(scene)
    scores = {k: sum(text.count(word) for word in words) for k, words in KEYWORDS.items()}
    # Scene-position defaults keep the Short rhythm meme-like rather than random.
    defaults = ["record_scratch", "cartoon_boing", "dramatic_reveal", "bruh", "windows_error", "vine_boom", "airhorn"]
    best = max(scores, key=scores.get)
    return best if scores[best] else defaults[min(index, len(defaults)-1)]

def select_sfx(script, library):
    result = []
    for index, scene in enumerate(script.get("scene_plan", [])):
        category = _category_for_scene(scene, index)
        paths = library.get(category, [])
        if not paths:
            result.append(None)
        else:
            digest = hashlib.sha1(f"{script.get('topic','')}:{index}:{category}".encode()).hexdigest()
            result.append(paths[int(digest[:8], 16) % len(paths)])
        scene["sfx_cue"] = {"enabled": True, "category": category, "meme_only": True}
    return result

def prepare_real_sfx(script):
    return select_sfx(script, ensure_sfx_assets())
