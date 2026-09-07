"""Narration-aware meme SFX selector for Mint-YT-Factory.

The selector reacts to the *meaning and delivery beat* of the narration rather
than blindly matching physical words such as "crack" or "break".  This keeps
educational facts playful without accidentally adding literal crash/crack sounds.
"""
from __future__ import annotations
import hashlib
import re
from sfx_assets import ensure_sfx_assets

# Words here describe a comedic/story beat.  Physical-effect words are handled
# separately so a fact like "ice cubes crack" does not automatically trigger a
# loud impact sound.
KEYWORDS = {
    "bruh": ["what", "seriously", "really", "ridiculous", "absurd", "wrong", "wait", "how is that possible"],
    "cartoon_boing": ["funny", "quirky", "odd", "weird", "silly", "strange", "stretch", "bounce", "tiny", "squishy"],
    "record_scratch": ["but", "except", "actually", "turns out", "plot twist", "wait a second", "however"],
    "dramatic_reveal": ["reveal", "secret", "mystery", "answer", "the reason", "here's why", "turns out", "hidden"],
    "crowd_gasp": ["no way", "insane", "unexpected", "shocking", "suddenly", "you won't believe"],
    "vine_boom": ["boom", "shock", "impact", "truth", "finally", "mic drop", "big reveal"],
    "metal_pipe": ["hit", "drop", "slam", "crash"],
    "windows_error": ["wrong", "error", "doesn't work", "cannot", "impossible", "glitch"],
    "sad_trombone": ["fail", "failed", "oops", "bad news", "unfortunately"],
    "crickets": ["nothing", "silent", "awkward", "stops"],
    "airhorn": ["finally", "big win", "winner", "payoff", "ta da"],
    "faaa": ["faaa"],
}

# Literal physical-action words should NOT create a loud literal SFX by
# themselves.  E.g. "ice cubes crack" is a scientific description, not a cue
# for a crack/bang sound.
PHYSICAL_ONLY = re.compile(
    r"\b(crack|cracks|cracking|break|breaks|breaking|bang|hit|drop|fall|slam|crash)\b",
    re.I,
)


def _text(scene):
    return " ".join(
        str(scene.get(k, "")) for k in
        ("narration", "visual_prompt", "spoken_beat", "physical_action", "visual_action")
    ).lower()


def _category_for_scene(scene, index):
    text = _text(scene)
    scores = {}
    for category, words in KEYWORDS.items():
        score = 0
        for word in words:
            if " " in word:
                score += 2 * text.count(word)
            else:
                score += len(re.findall(r"\b" + re.escape(word) + r"\b", text))
        scores[category] = score

    physical_fact = bool(PHYSICAL_ONLY.search(text))
    if physical_fact:
        # Prefer a playful reaction when the narration merely describes a
        # physical phenomenon.  Never let "crack/break/drop" alone select a
        # literal impact sound.
        for literal in ("vine_boom", "metal_pipe"):
            scores[literal] = max(0, scores[literal] - 3)
        if scores["cartoon_boing"] == 0:
            scores["cartoon_boing"] = 1

    # Keep the rhythm varied and meme-like while remaining deterministic.
    defaults = ["record_scratch", "cartoon_boing", "dramatic_reveal", "bruh", "cartoon_boing", "crowd_gasp", "airhorn"]
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
