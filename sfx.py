"""Meme-only, narration-aware SFX system for Mint-YT-Factory.

Every scene receives at most one intentional meme-style reaction. Local meme clips
are preferred; if a category is missing, a short meme-style procedural stinger is
generated so the production pipeline remains reliable and never falls back to
generic stock SFX.
"""
from __future__ import annotations
import math, os, random, re, struct, wave

SAMPLE_RATE = 44100
DEFAULT_SCENE_DURATIONS = (3, 5, 7, 7, 8, 8, 7)

try:
    from sfx_runtime import prepare_real_sfx
except Exception:
    prepare_real_sfx = None
try:
    from sfx_reactions import ensure_reaction_assets
except Exception:
    ensure_reaction_assets = None

MEME_DEFAULTS = (
    "record_scratch", "cartoon_boing", "dramatic_reveal", "bruh",
    "windows_error", "vine_boom", "airhorn"
)

def _clean(text):
    return " ".join(str(text or "").split()).strip()

def _write_wav(path, samples):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(struct.pack("<h", max(-32767, min(32767, int(x)))) for x in samples))

def _env(i, n, attack=.02, release=.20):
    t = i / max(1, n)
    return min(1.0, t / attack, (1 - t) / release)

def _tone(freq, duration, volume=.5, decay=3, slide=0):
    n = max(1, int(duration * SAMPLE_RATE)); out = []; phase = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        phase += 2 * math.pi * max(25, freq + slide * i / max(1, n - 1)) / SAMPLE_RATE
        out.append(32767 * volume * _env(i, n) * math.exp(-decay * t) * math.sin(phase))
    return out

def _noise(duration, volume=.25, decay=5, seed=7):
    rng = random.Random(seed); n = max(1, int(duration * SAMPLE_RATE))
    return [32767 * volume * _env(i, n) * math.exp(-decay * i / SAMPLE_RATE) * rng.uniform(-1, 1) for i in range(n)]

def _mix(*parts):
    length = max(len(p) for p in parts)
    out = [0.0] * length
    for part in parts:
        for i, value in enumerate(part):
            out[i] += value
    return out

def _procedural_meme(kind):
    if kind == "vine_boom":
        return _mix(_tone(58, .42, .78, 3.8, -18), _noise(.42, .16, 11, 91))
    if kind == "bruh":
        return _tone(165, .34, .52, 4.2, -70)
    if kind == "metal_pipe":
        return _mix(_tone(920, .45, .38, 8, -250), _tone(220, .32, .35, 5, 40))
    if kind == "record_scratch":
        return _noise(.24, .46, 11, 33)
    if kind == "dramatic_reveal":
        return _tone(210, .62, .46, 1.8, 980)
    if kind == "windows_error":
        return _mix(_tone(780, .10, .35, 8, 0), [0]*int(.08*SAMPLE_RATE) + _tone(620, .16, .42, 7, 0))
    if kind == "sad_trombone":
        return _tone(330, .70, .42, 1.6, -170)
    if kind == "crowd_gasp":
        return _noise(.34, .28, 4.5, 61)
    if kind == "cartoon_boing":
        return _tone(180, .40, .52, 2.5, 620)
    if kind == "crickets":
        return _mix(_tone(4100, .18, .12, 18, 0), [0]*int(.20*SAMPLE_RATE) + _tone(3800, .18, .10, 18, 0))
    if kind == "airhorn":
        return _mix(_tone(440, .55, .46, 1.2, 30), _tone(660, .55, .24, 1.3, 10))
    return _tone(240, .30, .40, 4, 180)

def _scene_duration(scene, index):
    try:
        value = float(scene.get("duration_seconds", scene.get("duration")))
        if value > 0:
            return value
    except Exception:
        pass
    return float(DEFAULT_SCENE_DURATIONS[min(index, len(DEFAULT_SCENE_DURATIONS)-1)])

def _beat_position(scene, duration):
    narration = _clean(scene.get("narration", "")).lower()
    words = re.findall(r"\b[\w'-]+\b", narration)
    if not words:
        return int(max(.15, min(duration * .65, duration - .25)) * 1000)
    triggers = ("wait", "what", "no way", "seriously", "suddenly", "but then", "turns out", "actually", "insane", "ridiculous", "weird", "truth", "finally", "snap", "boom")
    positions = []
    for trigger in triggers:
        pos = narration.find(trigger)
        if pos >= 0:
            positions.append(len(re.findall(r"\b[\w'-]+\b", narration[:pos])))
    ratio = (min(positions) / max(1, len(words))) if positions else .70
    ratio = max(.24, min(.86, ratio))
    return int(max(.15, min(duration - .25, duration * ratio)) * 1000)

def _category(scene, index):
    cue = scene.get("sfx_cue", {})
    if isinstance(cue, dict) and cue.get("category"):
        return str(cue["category"])
    return MEME_DEFAULTS[min(index, len(MEME_DEFAULTS)-1)]

def generate_sfx(script, output_dir):
    scenes = script.get("scene_plan", []) if isinstance(script, dict) else []
    if len(scenes) != 7:
        raise RuntimeError("SFX generation requires exactly 7 scenes.")
    os.makedirs(output_dir, exist_ok=True)
    print("=" * 80)
    print("😂 MEME-ONLY SFX — LOCAL CLIPS + NARRATION-BEAT TIMING")
    print("=" * 80)

    real = []
    if prepare_real_sfx:
        try:
            real = prepare_real_sfx(script)
            print(f"😂 Local meme clips available: {sum(1 for p in real if p)}/{len(real)} scenes")
        except Exception as error:
            print(f"⚠️ Meme library unavailable; using meme-style stingers: {error}")

    reactions = {}
    if ensure_reaction_assets:
        try:
            reactions = ensure_reaction_assets()
        except Exception as error:
            print(f"⚠️ Reaction fallback unavailable: {error}")

    paths, plan = [], []
    for index, scene in enumerate(scenes):
        kind = _category(scene, index)
        duration = _scene_duration(scene, index)
        at_ms = _beat_position(scene, duration)
        path = real[index] if index < len(real) else None
        source = "local_meme_clip"

        # FAAA is a reaction category. Prefer a user-supplied local meme file;
        # otherwise keep the existing generated reaction as a production fallback.
        if kind == "faaa" and not path and reactions.get("faaa"):
            path = reactions["faaa"]; source = "reaction_fallback"

        if not (path and os.path.exists(path)):
            path = os.path.join(output_dir, f"scene_{index+1}_{kind}_meme.wav")
            _write_wav(path, _procedural_meme(kind))
            source = "meme_style_fallback"

        cue = {
            "enabled": True,
            "type": kind,
            "category": kind,
            "source": source,
            "at_ms": int(at_ms),
            "timing": "narration_beat",
            "meme_only": True,
            "intensity": "high" if kind in ("vine_boom", "metal_pipe", "airhorn", "dramatic_reveal") else "medium",
        }
        scene["sfx_cue"] = cue
        paths.append(path)
        plan.append({"scene": index + 1, **cue})
        print(f"Scene {index+1}: {kind} [{source}] @ {at_ms}ms")

    script["sfx_plan"] = plan
    script["sfx_mode"] = "meme_only"
    return paths
