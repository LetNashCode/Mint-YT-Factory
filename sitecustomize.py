"""Mint-YT-Factory runtime quality layer.

This file augments the existing production modules without replacing their
research, validation, persistence, or publishing logic.
"""

import importlib.abc
import importlib.machinery
import sys


VIRAL_SCRIPT_RULES = r'''

============================================================
VIEWER RETENTION + ENTERTAINMENT LAYER
============================================================

This Short is competing for attention in a fast-scrolling feed.
Do NOT write it like an educational article being read aloud.
Write it like a clever friend just discovered something weird and
cannot wait to show it to you.

PRIMARY GOAL:
Make the viewer think "wait, WHAT?" at the start, "okay, but why?"
in the middle, and "ohhh!" at the payoff.

ENTERTAINMENT RULES:

1. EVERY SCENE MUST EARN ITS SCREEN TIME.
   No filler, throat-clearing, definitions, or generic transitions.

2. USE A CONVERSATIONAL, SLIGHTLY QUIRKY VOICE.
   Natural contractions are encouraged. Sound spoken, not written.
   Tiny playful phrases are allowed when they remain scientifically
   accurate and do not introduce a new factual claim.

3. BUILD A MICRO-PAYOFF EVERY FEW SECONDS.
   Each scene should reveal something new: a contradiction, visual
   change, surprising comparison, consequence, or reframe.
   Do not save ALL the interesting information for the final scene.

4. BAN ACADEMIC-SOUNDING NARRATION.
   Avoid repetitive phrases like "This phenomenon occurs because",
   "In conclusion", and "It is important to note".
   Replace them with natural spoken phrasing.

5. BAN GENERIC VIRAL BAIT.
   Never use "mind-blowing", "shocking truth", "you won't believe",
   "crazy", or "insane". The FACT is the entertainment.

6. USE ONE MEMORABLE HUMAN-SCALE ANALOGY WHEN IT HELPS.
   An analogy may simplify a verified mechanism, but must not create
   a new factual claim.

7. VARY SENTENCE LENGTH.
   Mix short punchy lines with slightly longer explanatory lines.
   Avoid identical sentence rhythms across scenes.

8. HOOK HARDER.
   Scene 1 should begin with the most relatable or surprising part of
   the verified story. Do not waste the first seconds introducing the
   topic by name unless the name itself is the surprise.

9. KEEP THE EXPLANATION SIMPLE, NOT CHILDISH.
   Use everyday words first. Technical words only when they clarify.

10. MAKE THE PAYOFF FEEL EARNED.
    Scene 5 or 6 should reframe the opening so the viewer understands
    the phenomenon differently than at second 1.

11. DO NOT FORCE JOKES.
    Quirky means personality, rhythm, and clever framing — not comedy
    sketches. Never sacrifice clarity or scientific accuracy for a joke.

12. THE LAST LINE MUST PAY OFF THE CURRENT STORY BEFORE THE NEXT TOPIC.
    The continuation hook should feel like one intriguing question,
    not a channel promotion.

13. IF THE TOPIC IS DRY, FIND THE HUMAN ANGLE INSIDE THE EVIDENCE:
    something people do, see, hear, touch, eat, use, or experience.

QUALITY TEST:
Would a viewer who has never heard of this channel want to send this
Short to a friend because the explanation is surprisingly fun?
If not, rewrite the narration before returning JSON.
'''


VIRAL_TOPIC_RULES = r'''

============================================================
HIGH-INTEREST TOPIC FILTER
============================================================

Prioritize MASS APPEAL, not merely scientific interest.
The best question is something a normal person has personally noticed
or experienced but never bothered to look up.

Strong topic ingredients:
- phones, headphones, TV, camera, mirror, clothes, food, kitchen,
  cars, traffic, sleep, sound, smell, light, weather, water,
  everyday objects, common body/perception experiences
- an obvious "I have seen that" moment
- a counterintuitive result
- an explanation that fits one simple chain
- a visually demonstrable reveal
- a payoff that makes the viewer notice the world differently afterward

Avoid topics that are merely "interesting science" but have weak human
recognition, weak visual potential, or a textbook feel.

Before accepting a candidate, ask:
"Would a random person recognize this situation in the first second?"
"Would they want the answer badly enough to wait 30–45 seconds?"
"Can the reveal be shown, not just described?"

Prefer the strongest candidate among valid researchable questions.
Do not choose a topic just because it sounds scientific.
'''


VIRAL_IMAGE_RULES = r'''

============================================================
HIGH-RETENTION VISUAL DIRECTION
============================================================

The image must help win attention, not merely decorate narration.
Create an instantly readable visual moment with a clear subject and
one obvious action, contrast, transformation, or surprising detail.
Prefer relatable human-scale scenes, hands interacting with objects,
close-up physical mechanisms, before/after states, visible cause-and-
effect, expressive reactions, and concrete environments.

Use bright, believable, varied lighting and visually interesting
composition. Keep the production premium and coherent, but do NOT make
every shot dark, blue, moody, centered, or portrait-like.

AVOID unless the narration genuinely requires it:
- generic moody portraits
- empty rooms
- static centered faces staring at camera
- abstract sci-fi imagery
- meaningless glowing particles
- generic laboratory shots
- repeated split-screen faces
- giant cinematic close-ups that show no useful action

Every second visual should advance the idea rather than simply show the
same subject from another angle.

The viewer should understand the visual concept with sound OFF.

Do not render text, captions, logos, watermarks, UI, or labels into the
image.

============================================================
STORY-FIRST VISUAL HARD RULES
============================================================

The visuals must feel like real shots from an entertaining documentary
or cinematic Short, not slides from a science textbook.

1. SHOW THE PHENOMENON LITERALLY.
   If the narration describes a person touching metal, show a real hand
   touching a real metal object. If it describes an animal, show the
   animal. If it describes an object, show the object.

2. PREFER RECOGNIZABLE REAL-WORLD SCENES.
   Prefer people, animals, objects, environments, experiments, machines,
   landscapes, rooms, streets, or believable laboratories whenever the
   narration allows it.

3. NEVER TURN AN EXPLANATION INTO A TEXTBOOK DIAGRAM.
   Do NOT use scientific illustrations, infographic diagrams, flowcharts,
   schematic drawings, anatomy diagrams, textbook cross-sections, arrows,
   energy vectors, labeled parts, graphs, charts, equations, UI panels,
   microscopic fantasy structures, or abstract concept art.

4. NEVER VISUALIZE AN UNSEEN MECHANISM AS IF IT WERE A CAMERA VIEW.
   If a mechanism is invisible, show a believable physical consequence or
   grounded cinematic representation. Do not invent microscopic structures,
   receptors, particles, forces, pathways, or internal anatomy unless the
   narration explicitly requires an established visible structure.

5. DO NOT INVENT VISUAL FACTS.
   The image must not imply a mechanism, object, experiment, location,
   researcher, device, anatomy, or physical process unsupported by the
   supplied evidence.

6. SHOT 1 ESTABLISHES; SHOT 2 REVEALS.
   Shot 2 must change the visible detail, action, reaction, consequence,
   comparison, perspective, or physical state. Do not create two nearly
   identical stills.

7. REALISTIC STYLE DEFAULT.
   Prefer realistic_3d_render or cinematic_photograph. Use
   macro_photography only for a genuinely useful close-up of a material,
   texture, surface, or small physical detail.

8. HUMAN-CENTERED VISUALS WHEN APPROPRIATE.
   For everyday phenomena, prefer believable human actions, hands, faces,
   reactions, objects being handled, and environments over abstract diagrams.

9. VISUAL PROMPTS MUST BE CONCRETE.
   Clearly specify WHO/WHAT is visible, WHAT they are doing, WHERE they are,
   WHAT changes, and WHAT the viewer should notice.

BAD:
"A scientific diagram of thermal receptors detecting heat transfer."

GOOD:
"A person's fingertips touch a polished metal block on a wooden workbench,
with the hand immediately pulling back in surprise."

BAD:
"An animated thermal energy vector moving through a metal crystal."

GOOD:
"Extreme close-up of fingertips resting on a cold polished metal surface as
the hand reacts to the chill."

BAD:
"A cross-section of skin showing microscopic heat receptors."

GOOD:
"Close-up of fingertips touching the metal block, followed by a clear change
in the hand's reaction as it moves away from the surface."
'''


ALLOWED_IMAGE_STYLES = {
    "realistic_3d_render",
    "cinematic_photograph",
    "macro_photography",
}


def _patch(module):
    name = getattr(module, "__name__", "")

    if name == "topics":
        old_prompt = getattr(module, "SYSTEM_PROMPT", "")
        if VIRAL_TOPIC_RULES not in old_prompt:
            module.SYSTEM_PROMPT = old_prompt + VIRAL_TOPIC_RULES
        return

    if name == "generate_script":
        # Hard-disable diagram-oriented image styles at the schema level.
        module.VALID_IMAGE_STYLE = set(ALLOWED_IMAGE_STYLES)

        old_builder = getattr(module, "build_system_prompt", None)
        if old_builder and not getattr(old_builder, "_mint_viral", False):
            def build_system_prompt_with_viral_rules():
                return old_builder() + VIRAL_SCRIPT_RULES + VIRAL_IMAGE_RULES
            build_system_prompt_with_viral_rules._mint_viral = True
            module.build_system_prompt = build_system_prompt_with_viral_rules
        return

    if name == "generate_images":
        old_builder = getattr(module, "build_prompt", None)
        if old_builder and not getattr(old_builder, "_mint_viral", False):
            def build_prompt_with_viral_direction(*args, **kwargs):
                prompt = old_builder(*args, **kwargs)
                return prompt + " " + VIRAL_IMAGE_RULES
            build_prompt_with_viral_direction._mint_viral = True
            module.build_prompt = build_prompt_with_viral_direction
        return

    if name == "tts":
        module.NARRATION_SPEED = 1.0
        return


class _MintQualityLoader(importlib.abc.Loader):
    def __init__(self, original_loader):
        self.original_loader = original_loader

    def create_module(self, spec):
        creator = getattr(self.original_loader, "create_module", None)
        if creator:
            return creator(spec)
        return None

    def exec_module(self, module):
        self.original_loader.exec_module(module)
        _patch(module)


class _MintQualityFinder(importlib.abc.MetaPathFinder):
    TARGETS = {"topics", "generate_script", "generate_images", "tts"}

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in self.TARGETS:
            return None

        try:
            sys.meta_path.remove(self)
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        finally:
            if self not in sys.meta_path:
                sys.meta_path.insert(0, self)

        if spec is None or spec.loader is None:
            return spec

        spec.loader = _MintQualityLoader(spec.loader)
        return spec


if not any(isinstance(x, _MintQualityFinder) for x in sys.meta_path):
    sys.meta_path.insert(0, _MintQualityFinder())
