"""Hybrid visual casting for Mint-YT-Factory.

Pexels remains the first choice. When verified Pexels cannot represent the
physical beat, the existing AI image engine is used for that shot instead of
crashing or accepting an unrelated stock asset.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import uuid


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

    conceptual = (
        "nobody" in text or "no one" in text or "untouched" in text or
        "math" in text or "probability" in text or "chaos" in text or
        "physics" in text or "force" in text or "forces" in text or
        "invisible" in text or "why does" in text or "why do" in text or
        "only one way" in text or "hundreds of ways" in text
    )
    if conceptual:
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
            "Do not attempt to literally depict an invisible idea. Show a concrete, believable "
            "physical consequence or everyday demonstration that helps the viewer understand the "
            "spoken beat immediately. If the sentence says nobody touched something, show the object "
            "sitting untouched. If it describes math/chaos, show the physical object behaving in the "
            "described way. Never use diagrams or abstract glowing science graphics."
        )
    elif intent == "LITERAL_STATE":
        strategy = "Show the exact visible object and physical state described by the beat, prominently and unmistakably."
    else:
        strategy = "Show the exact physical object and action described by the beat, not merely the general topic."

    continuity = ""
    identity = script.get("visual_identity") if isinstance(script, dict) else None
    if isinstance(identity, dict):
        continuity = _clean(identity.get("style"), 300)

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
        "Use a playful, visually interesting composition when appropriate, but never sacrifice relevance.",
        f"Global visual style: {continuity}." if continuity else "",
        "Shot 1 establishes the beat clearly." if shot == 1 else "Shot 2 advances the same beat with a different close-up, angle, reaction, or physical reveal.",
        "No text, letters, numbers, labels, logos, captions, subtitles, UI, diagrams, arrows, formulas, charts, watermarks, fantasy effects, generic laboratory imagery, or unrelated objects.",
    ]), 2200)


def patch_hybrid_media(pexels_media, generate_images_module):
    """Install Pexels-first + AI fallback without changing main.py."""
    if getattr(pexels_media, "_mint_hybrid_media_v1", False):
        return

    # Preserve the already-installed state-aware Pexels selector.
    strict_selector = getattr(pexels_media, "_select", None)
    original_download = pexels_media.download
    original_credit = pexels_media.credit
    generated_files = []

    def hybrid_select(scene, visual, excluded_pages=None):
        selected = strict_selector(scene, visual, excluded_pages or set()) if strict_selector else None
        if selected:
            return selected

        intent = _visual_intent(scene, visual)
        print(f"   🧠 Visual intent: {intent}")
        print("   ⚠️ No sufficiently relevant Pexels asset — switching to AI visual generation")

        try:
            build_prompt = getattr(generate_images_module, "build_prompt")
            generate_image = getattr(generate_images_module, "generate_image")
            script = getattr(hybrid_select, "_script", {})
            scene_index = getattr(hybrid_select, "_scene_index", 1)
            shot_index = getattr(hybrid_select, "_shot_index", 1)
            prompt = _fallback_prompt(scene, visual, shot_index, script)
            # Use the existing production image dimensions and seed system.
            config = getattr(hybrid_select, "_config", {}) or {}
            image_cfg = config.get("image", {}) if isinstance(config, dict) else {}
            width = int(image_cfg.get("width", 1024) or 1024)
            height = int(image_cfg.get("height", 1792) or 1792)
            if width >= height:
                width, height = height, width
            generation = script.get("image_generation", {}) if isinstance(script, dict) else {}
            base_seed = int(generation.get("seed", 0) or 0)
            seed = base_seed + scene_index * 100 + shot_index

            # Let the existing AI engine keep its own semantic prompt builder if available.
            try:
                prompt = build_prompt(scene, visual, script, scene_index, shot_index)
            except Exception:
                pass
            # Add our intent correction after the engine's prompt.
            prompt = _fallback_prompt(scene, visual, shot_index, script) + " " + prompt
            data = generate_image(prompt, width, height, seed)
            fd, local_path = tempfile.mkstemp(prefix="mint_ai_visual_", suffix=".png")
            os.close(fd)
            with open(local_path, "wb") as handle:
                handle.write(data)
            generated_files.append(local_path)
            return {
                "kind": "ai_image",
                "photo": local_path,
                "page": "ai://generated",
                "photographer": "",
                "score": 10,
                "qc_reason": f"AI fallback generated for {intent} beat",
                "query": "AI visual fallback",
            }
        except Exception as exc:
            print(f"   ❌ AI visual fallback failed: {type(exc).__name__}: {exc}")
            return None

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
                import json
                json.dump({"type": "ai_image", "provider": "Pollinations/FLUX", "generated": True}, handle, ensure_ascii=False, indent=2)
            return
        return original_credit(path, kind, page, photographer)

    def wrapped_generate(script, output_dir, config, gim):
        # The original media generator calls _select without passing script/config.
        hybrid_select._script = script
        hybrid_select._config = config or {}
        try:
            scenes = script.get("scene_plan") or []
            original_select = pexels_media._select
            pexels_media._select = hybrid_select
            groups = original_generate(script, output_dir, config, gim)
            return groups
        finally:
            pexels_media._select = strict_selector
            for path in list(generated_files):
                try:
                    os.remove(path)
                except OSError:
                    pass
            generated_files.clear()

    original_generate = pexels_media.generate_media
    # Replace provider functions before original_generate executes.
    pexels_media.download = hybrid_download
    pexels_media.credit = hybrid_credit
    pexels_media.generate_media = wrapped_generate

    # Scene/shot indexes are inferred from the selector call order.
    counter = {"n": 0}
    base_hybrid_select = pexels_media._select
    def indexed_select(scene, visual, excluded_pages=None):
        counter["n"] += 1
        hybrid_select._scene_index = ((counter["n"] - 1) // 2) + 1
        hybrid_select._shot_index = ((counter["n"] - 1) % 2) + 1
        return hybrid_select(scene, visual, excluded_pages)
    pexels_media._select = indexed_select
    strict_selector = indexed_select

    pexels_media._mint_hybrid_media_v1 = True
    print("🧩 Hybrid media: Pexels verified VIDEO → Pexels verified PHOTO → AI generated visual")
