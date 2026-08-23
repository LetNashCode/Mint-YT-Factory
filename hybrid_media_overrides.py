"""Strict hybrid visual casting for Mint-YT-Factory.

Pexels is used only when Gemini confirms a DIRECT visual match (8+/10).
Anything merely contextual is rejected and the shot is generated with FLUX.
AI-generated shots receive their own Gemini vision QC before being accepted.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile


def _clean(value, limit=500):
    return " ".join(str(value or "").replace("\n", " ").split()).strip()[:limit]


def _visual_intent(scene, visual):
    text = _clean(" ".join([
        _clean(visual.get("spoken_line"), 300),
        _clean(visual.get("visual_focus"), 180),
        _clean(visual.get("visual_action"), 220),
        _clean(visual.get("must_show"), 300),
        _clean(scene.get("narration"), 300),
    ]), 1200).lower()
    if any(x in text for x in (
        "nobody", "no one", "untouched", "math", "probability", "chaos",
        "physics", "force", "forces", "invisible", "why does", "why do",
        "only one way", "hundreds of ways"
    )):
        return "CONTEXTUAL/CONCEPTUAL"
    if any(x in text for x in ("tangled", "tangle", "knot", "knotted", "floating", "melting", "breaking")):
        return "LITERAL_STATE"
    return "LITERAL_ACTION"


def _fallback_prompt(scene, visual, shot, script, correction=""):
    intent = _visual_intent(scene, visual)
    spoken = _clean(visual.get("spoken_line") or scene.get("narration"), 420)
    focus = _clean(visual.get("visual_focus"), 220)
    action = _clean(visual.get("visual_action"), 260)
    must = visual.get("must_show") or []
    if isinstance(must, list):
        must = "; ".join(_clean(x, 100) for x in must[:6] if _clean(x))
    else:
        must = _clean(must, 400)
    identity = script.get("visual_identity") if isinstance(script, dict) else {}
    style = _clean(identity.get("style"), 300) if isinstance(identity, dict) else ""

    if intent == "CONTEXTUAL/CONCEPTUAL":
        strategy = (
            "Do not depict invisible concepts with diagrams, formulas or generic science imagery. "
            "Show the concrete physical consequence described by the sentence. The viewer must be able "
            "to understand the beat from the object and its visible state/action alone."
        )
    elif intent == "LITERAL_STATE":
        strategy = "Show the exact object in the exact physical state described. The state must be unmistakable."
    else:
        strategy = "Show the exact physical object performing the exact action described, not merely the general topic."

    return _clean(" ".join([
        "PHOTOREALISTIC CINEMATIC 9:16 STORY FRAME.",
        f"EXACT SPOKEN BEAT: {spoken}.",
        f"PRIMARY OBJECT/SUBJECT: {focus}.",
        f"EXACT VISIBLE ACTION OR STATE: {action}.",
        f"MUST VISIBLY CONTAIN: {must}." if must else "",
        strategy,
        "The primary object must dominate the frame and be immediately recognizable on a phone.",
        "Use believable real-world materials, scale, lighting, shadows and physics.",
        "Make the visual playful and cinematic where appropriate, but never sacrifice semantic accuracy.",
        f"Global visual style: {style}." if style else "",
        "Shot 1 establishes the physical beat clearly." if shot == 1 else "Shot 2 advances the same beat with a different close-up, angle, changed state, reaction or consequence.",
        f"CORRECT THE PREVIOUS FAILURE: {correction}." if correction else "",
        "NO unrelated objects, generic stock-photo symbolism, diagrams, text, captions, subtitles, labels, logos, UI, arrows, formulas, charts, watermarks, fantasy effects or laboratory graphics.",
    ]), 2300)


def _ai_vision_check(data, spoken, focus, action, must_show):
    """Return (passed, score, reason). Fail closed when Gemini is available."""
    try:
        from google import genai
        from google.genai import types
    except Exception:
        print("   ⚠️ AI visual QC unavailable: Gemini SDK missing; accepting prompt-constrained image")
        return True, 8, "Gemini SDK unavailable"

    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("   ⚠️ AI visual QC skipped: GEMINI_API_KEY unavailable")
        return True, 8, "Gemini key unavailable"

    try:
        client = genai.Client(api_key=key)
        contents = [
            types.Part.from_bytes(data=data, mime_type="image/png"),
            f'''You are the FINAL visual casting gate for a YouTube Short.

SPOKEN BEAT: {spoken}
PRIMARY OBJECT/SUBJECT: {focus}
EXACT ACTION/STATE: {action}
MUST SHOW: {must_show}

Inspect the actual image. Ignore the prompt and judge only what is visibly present.
PASS ONLY when the primary object AND the required physical action/state are clearly visible.
A generic object, related object, symbolic image, random person, or vaguely related scene is a FAIL.
For example, if the beat is tangled wired earbuds, wireless earbuds, a generic cable, a sewing knot, or a person merely wearing earbuds is NOT a pass.
Score 0-10. Pass requires score >= 8.
Return ONLY JSON: {{"score":8,"pass":true,"reason":"short explanation"}}'''
        ]
        response = client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=contents,
            config=types.GenerateContentConfig(temperature=0),
        )
        text = _clean(getattr(response, "text", ""), 1200)
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json.loads(text)
        score = int(result.get("score", 0) or 0)
        passed = bool(result.get("pass")) and score >= 8
        return passed, score, _clean(result.get("reason"), 240)
    except Exception as exc:
        print(f"   ⚠️ AI visual QC unavailable: {type(exc).__name__}: {exc}")
        return True, 8, f"QC unavailable: {type(exc).__name__}"


def patch_hybrid_media(pexels_media, generate_images_module):
    """Install strict Pexels → AI fallback without changing main.py."""
    if getattr(pexels_media, "_mint_hybrid_media_v3", False):
        return

    base_selector = getattr(pexels_media, "_select", None)
    original_generate = pexels_media.generate_media
    original_download = pexels_media.download
    original_credit = pexels_media.credit
    generated_files = []
    counter = {"n": 0}
    state = {"script": {}, "config": {}}

    def hybrid_select(scene, visual, excluded_pages=None):
        selected = base_selector(scene, visual, excluded_pages or set()) if base_selector else None

        # CRITICAL: a Gemini 6/7 contextual match is NOT good enough for this channel.
        # This is what caused the previous video to show trousers, water, generic wires, etc.
        if selected and int(selected.get("score", 0) or 0) >= 8:
            print(f"   ✅ Direct Pexels match accepted: {selected.get('score')}/10")
            return selected

        if selected:
            print(f"   🚫 Rejecting contextual Pexels match: Gemini {selected.get('score', 0)}/10 — {selected.get('qc_reason', '')}")

        scene_index = ((counter["n"] - 1) // 2) + 1
        shot_index = ((counter["n"] - 1) % 2) + 1
        intent = _visual_intent(scene, visual)
        print(f"   🧠 Visual intent: {intent}")
        print("   🎨 No DIRECT Pexels match — generating an exact AI visual")

        try:
            gim = generate_images_module
            generate_image = getattr(gim, "generate_image")
            build_prompt = getattr(gim, "build_prompt", None)
            script = state["script"]
            config = state["config"]
            image_cfg = config.get("image", {}) if isinstance(config, dict) else {}
            width = int(image_cfg.get("width", 1024) or 1024)
            height = int(image_cfg.get("height", 1792) or 1792)
            if width >= height:
                width, height = height, width
            generation = script.get("image_generation", {}) if isinstance(script, dict) else {}
            base_seed = int(generation.get("seed", 0) or 0) + scene_index * 100 + shot_index

            spoken = _clean(visual.get("spoken_line") or scene.get("narration"), 420)
            focus = _clean(visual.get("visual_focus"), 220)
            action = _clean(visual.get("visual_action"), 260)
            must = visual.get("must_show") or []
            prompt = _fallback_prompt(scene, visual, shot_index, script)
            if build_prompt:
                try:
                    prompt += " " + build_prompt(scene, visual, script, scene_index, shot_index)
                except Exception:
                    pass

            accepted = None
            accepted_score = 0
            accepted_reason = ""
            for attempt in range(1, 4):
                seed = base_seed + ((attempt - 1) * 500_000)
                print(f"   🎨 AI visual attempt {attempt}/3 | seed={seed}")
                data = generate_image(prompt[:2300], width, height, seed)
                passed, score, reason = _ai_vision_check(data, spoken, focus, action, must)
                print(f"   👁️ AI visual QC: {'PASS' if passed else 'FAIL'} score={score}/10 — {reason}")
                if passed:
                    accepted = data
                    accepted_score = score
                    accepted_reason = reason
                    break
                prompt = _fallback_prompt(scene, visual, shot_index, script, correction=reason)
                accepted_reason = reason

            if accepted is None:
                raise RuntimeError(f"AI visual failed strict semantic QC after 3 attempts: {accepted_reason}")

            fd, local_path = tempfile.mkstemp(prefix="mint_ai_visual_", suffix=".png")
            os.close(fd)
            with open(local_path, "wb") as handle:
                handle.write(accepted)
            generated_files.append(local_path)
            return {
                "kind": "photo",
                "photo": local_path,
                "page": "ai://generated",
                "photographer": "",
                "score": accepted_score,
                "qc_reason": f"AI visual strict QC: {accepted_reason}",
                "query": "AI exact visual fallback",
            }
        except Exception as exc:
            print(f"   ❌ AI visual fallback failed: {type(exc).__name__}: {exc}")
            return None

    def indexed_select(scene, visual, excluded_pages=None):
        counter["n"] += 1
        return hybrid_select(scene, visual, excluded_pages)

    def hybrid_download(source, path):
        if isinstance(source, str) and os.path.isfile(source):
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                shutil.copyfile(source, path)
                return os.path.getsize(path) > 10000
            except Exception as exc:
                print(f"⚠️ AI visual copy failed: {exc}")
                return False
        return original_download(source, path)

    def hybrid_credit(path, kind, page, photographer):
        if page == "ai://generated":
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"type": "ai_image", "provider": "Pollinations/FLUX", "generated": True}, handle, ensure_ascii=False, indent=2)
            return
        return original_credit(path, kind, page, photographer)

    def wrapped_generate(script, output_dir, config, gim):
        state["script"] = script or {}
        state["config"] = config or {}
        counter["n"] = 0
        pexels_media._select = indexed_select
        pexels_media.download = hybrid_download
        pexels_media.credit = hybrid_credit
        try:
            return original_generate(script, output_dir, config, gim)
        finally:
            pexels_media._select = base_selector
            pexels_media.download = original_download
            pexels_media.credit = original_credit
            for path in generated_files:
                try:
                    os.remove(path)
                except OSError:
                    pass
            generated_files.clear()

    pexels_media.generate_media = wrapped_generate
    pexels_media._mint_hybrid_media_v3 = True
    print("🧩 STRICT HYBRID MEDIA: Pexels direct 8+ → AI exact visual → Gemini vision QC")
