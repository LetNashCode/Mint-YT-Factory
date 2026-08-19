"""
Mint-YT-Factory runtime polish layer.

Adds a connected continuation-topic strategy and stronger viewer hooks/CTAs
without changing the core research and publishing gates.
"""

import os
import re

try:
    from google import genai
    from google.genai import types

    import topics as _topics
    import generate_script as _generate_script_module

    _ORIGINAL_GENERATE_SCRIPT = _generate_script_module.generate_script
    _CONTINUATION_MODEL = "gemini-flash-lite-latest"
    _MAX_CONTINUATION_ATTEMPTS = 8

    def _clean_topic(value):
        value = str(value or "").strip()
        value = re.sub(r"```(?:text|json)?", "", value, flags=re.I)
        value = value.replace('"', "").replace("'", "")
        value = re.sub(
            r"^(topic|next topic|next_short|next short)\s*:\s*",
            "",
            value,
            flags=re.I,
        )
        value = re.sub(r"^\s*\d+[.\)\-:]\s*", "", value)
        value = " ".join(value.split())
        return value.rstrip(".!? ").strip()

    def _generate_continuation_topic(current_topic):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is missing for continuation topic.")

        try:
            used = list(_topics._load_used())
        except Exception:
            used = []

        previous = "\n".join(used[-80:])

        prompt = f"""
You are choosing the NEXT episode for a science-curiosity YouTube Shorts channel.

CURRENT EPISODE:
{current_topic}

CHANNEL PROMISE:
Things you've noticed but never looked up.

The next episode should make the viewer think:
"If I liked that mystery, I want to know this one too."

Create ONE new, highly clickable everyday science question that:
- naturally follows the curiosity of the current episode
- explores a DIFFERENT phenomenon, not the same explanation
- is observable by a normal person
- is researchable with credible scientific sources
- has strong visual potential
- sounds like a question a real person would ask
- is 6–12 words
- starts with Why or How

Do NOT make it a list, countdown, fact, health claim, or broad subject.
Do NOT merely reword the current topic.
Do NOT repeat anything in the previous-topic list.

PREVIOUS TOPICS:
{previous}

Return ONLY the question.
No quotes. No numbering. No explanation. No emoji. No question mark.
"""

        client = genai.Client(api_key=api_key)

        for attempt in range(1, _MAX_CONTINUATION_ATTEMPTS + 1):
            try:
                response = client.models.generate_content(
                    model=_CONTINUATION_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(temperature=0.95),
                )

                candidate = _clean_topic(getattr(response, "text", ""))
                if not candidate:
                    continue

                validation_used = used + [current_topic]
                if not _topics.validate_topic_for_pipeline(
                    candidate,
                    used=validation_used,
                    check_duplicate=True,
                ):
                    continue

                return candidate

            except Exception as error:
                print(
                    f"⚠️ Continuation topic attempt {attempt} failed: {error}"
                )

        fallback = _topics._generate_new_topic()
        if fallback:
            return fallback

        raise RuntimeError("Could not generate a valid continuation topic.")

    def _question_hook(topic):
        text = _clean_topic(topic)
        lower = text.lower()

        replacements = [
            ("why does ", "Have you ever wondered why "),
            ("why do ", "Have you ever wondered why "),
            ("why is ", "Have you ever wondered why "),
            ("why are ", "Have you ever wondered why "),
            ("why can ", "Have you ever wondered why "),
            ("how does ", "Have you ever wondered how "),
            ("how do ", "Have you ever wondered how "),
            ("how can ", "Have you ever wondered how "),
            ("how is ", "Have you ever wondered how "),
            ("how are ", "Have you ever wondered how "),
        ]

        for prefix, replacement in replacements:
            if lower.startswith(prefix):
                remainder = text[len(prefix):].strip()
                return replacement + remainder.rstrip(".!?") + "?"

        return f"Have you ever wondered why {text.lower().rstrip('.!?')}?"

    def _patch_scene_7(scene, next_topic):
        ending = str(scene.get("narration", "")).strip()

        # The original writer already creates a next-topic bridge. Remove that
        # old bridge so we never stack two CTAs and accidentally overrun 7 sec.
        ending = re.split(
            r"\b(?:but that leaves|and that raises|which leaves|the story ends here|that is the strange part)[^.!?]*",
            ending,
            maxsplit=1,
            flags=re.I,
        )[0].strip()

        ending = ending.rstrip(".!? ") + "."

        bridge = (
            " And if you want another everyday mystery, the next one is: "
            f"{next_topic}. Subscribe so you don't miss it."
        )

        scene["narration"] = ending + bridge
        scene["subtitle_text"] = scene["narration"]

        words = re.findall(r"\b[\w'-]+\b", scene["narration"])
        candidates = [word for word in words if len(word) >= 4] or words
        if candidates:
            strongest = max(candidates, key=len)
            scene["emphasis_word"] = strongest
            scene["caption_highlights"] = [
                {"word": strongest, "emphasis": "strong"}
            ]

    def _patched_generate_script(
        topic,
        config,
        research,
        extra_feedback="",
    ):
        continuation = _generate_continuation_topic(topic)

        print("=" * 80)
        print("🔗 CONTINUATION STRATEGY")
        print("=" * 80)
        print(f"Current topic: {topic}")
        print(f"Next connected topic: {continuation}")
        print("Goal: bingeable channel journey + subscriber CTA")
        print("=" * 80)

        script = _ORIGINAL_GENERATE_SCRIPT(
            topic,
            config,
            research,
            extra_feedback,
        )

        next_short = script.setdefault("next_short", {})
        next_short["topic"] = continuation
        next_short["teaser"] = f"A new everyday mystery: {continuation}."
        next_short["why_viewers_should_return"] = (
            "The next episode continues the same curiosity-first journey "
            "with a completely different everyday mystery."
        )
        next_short["subscription_cta"] = (
            "Subscribe so you don't miss the next mystery."
        )

        scenes = script.get("scene_plan", [])
        if len(scenes) >= 7 and isinstance(scenes[6], dict):
            _patch_scene_7(scenes[6], continuation)

        if scenes and isinstance(scenes[0], dict):
            hook = _question_hook(topic)
            scenes[0]["narration"] = hook
            scenes[0]["subtitle_text"] = hook
            hook_words = re.findall(r"\b[\w'-]+\b", hook)
            candidates = [word for word in hook_words if len(word) >= 4] or hook_words
            if candidates:
                strongest = max(candidates, key=len)
                scenes[0]["emphasis_word"] = strongest
                scenes[0]["caption_highlights"] = [
                    {"word": strongest, "emphasis": "strong"}
                ]

        publishing = script.setdefault("publishing", {})
        publishing["next_short_topic_in_description"] = False
        publishing["next_short_spoken_in_scene_7"] = True
        publishing["next_short_spoken_only_in_scene_7"] = True
        publishing["subscription_strategy"] = "connected_next_topic_plus_subscribe"
        publishing["hook_strategy"] = "direct_viewer_question"

        return script

    _generate_script_module.generate_script = _patched_generate_script
    print("✅ Mint-YT-Factory runtime continuation/hook patch loaded")

except Exception as _error:
    print(f"⚠️ Mint-YT-Factory runtime patch unavailable: {_error}")
