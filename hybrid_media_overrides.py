"""Hybrid visual casting for Mint-YT-Factory.

Pexels is first. If verified Pexels cannot represent the beat, the existing
AI image engine generates that shot instead of accepting unrelated stock or
crashing the production run.
"""
from __future__ import annotations

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


def _fallback_prompt(scene, visual, shot, script):
    intent = _visual_intent(scene, visual)
    spoken = _clean(visual.get("spoken_line") or scene.get("narration"), 420)
    focus = _clean(visual.get("visual_focus"), 220)
    action = _clean(visual.get("visual_action"), 260)
    must = visual.get("must_show") or []
    if isinstance(must, list):
        must = "; ".join(_clean(x, 100) for x in must[:6] if _clean(x))
    else:
        must = _clean(must, 400)

    if intent == "CONTEXTUAL/CONCEPTUAL":
        strategy = (
            "Do not literally depict invisible ideas. Show a concrete believable physical consequence "
            "or everyday demonstration that makes the spoken beat obvious. If the sentence says nobody "
            "touched something, show the object sitting untouched. If it describes math or chaos, show "
            "the physical object behaving that way. Never use diagrams or abstract science graphics."
        )
    elif intent == "LITERAL_STATE":
        strategy = "Show the exact visible object and physical state described by the beat, prominently and unmistakably."
    else:
        strategy = "Show the exact physical object and action described by the beat, not merely the general topic."

    identity = script.get("visual_identity") if isinstance(script, dict) else {}
    style = _clean(identity.get("style"), 300) if isinstance(identity, dict) else ""

    return _clean(" ".join([
        "PHOTOREALISTIC CINEMATIC PORTRAIT 9:16 STORY FRAME.",
        f"VISUAL INTENT: {intent}.",
        f"SPOKEN BEAT: {spoken}.",
        f"PRIMARY SUBJECT: {focus}.",
        f"PHYSICAL ACTION OR STATE: {action}.",
        f"MUST VISIBLY CONTAIN: {must}." if must else "",
        strategy,
        "Main subject fills enough of the frame to be instantly recognizable on a phone.",
        "Real-world materials, believable scale, natural cinematic lighting, realistic shadows and physics.",
        "Use a playful visually interesting composition when appropriate, but never sacrifice relevance.",
        f"Global visual style: {style}." if style else "",
        "Shot 1 establishes the beat clearly." if shot == 1 else "Shot 2 advances the same beat with a different close-up, angle, reaction, or physical reveal.",
        "No text, letters, numbers, labels, logos, captions, subtitles, UI, diagrams, arrows, formulas, charts, watermarks, fantasy effects, generic laboratory imagery, or unrelated objects.",
    ]), 2200)


def patch_hybrid_media(pexels_media, generate_images_module):
    """Install Pexels-first + AI fallback without changing main.py."""
    if getattr(pexels_media, "_mint_hybrid_media_v2", False):
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
        if selected:
            return selected

        scene_index = ((counter["n"] - 1) // 2) + 1
        shot_index = ((counter["n"] - 1) % 2) + 1
        intent = _visual_intent(scene, visual)
        print(f"   🧠 Visual intent: {intent}")
        print("   ⚠️ No sufficiently relevant Pexels asset — generating a matching AI visual")

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
            seed = int(generation.get("seed", 0) or 0) + scene_index * 100 + shot_index

            prompt = _fallback_prompt(scene, visual, shot_index, script)
            if build_prompt:
                try:
                    prompt += " " + build_prompt(scene, visual, script, scene_index, shot_index)
                except Exception:
                    pass

            data = generate_image(prompt[:2200], width, height, seed)
            fd, local_path = tempfile.mkstemp(prefix="mint_ai_visual_", suffix=".png")
            os.close(fd)
            with open(local_path, "wb") as handle:
                handle.write(data)
            generated_files.append(local_path)
            return {
                "kind": "photo",
                "photo": local_path,
                "page": "ai://generated",
                "photographer": "",
                "score": 10,
                "qc_reason": f"AI fallback generated for {intent} visual intent",
                "query": "AI visual fallback",
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
    pexels_media._mint_hybrid_media_v2 = True
    print("🧩 Hybrid media: Pexels verified VIDEO → Pexels verified PHOTO → AI generated visual")
