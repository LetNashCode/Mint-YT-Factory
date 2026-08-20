"""Story-first visual direction policy for Mint-YT-Factory.

This module patches the script generator at runtime so visual generation is
literal, cinematic, and recognizable instead of diagram-heavy.
"""

from __future__ import annotations


ALLOWED_IMAGE_STYLES = {
    "realistic_3d_render",
    "cinematic_photograph",
    "macro_photography",
}

POLICY = r'''

============================================================
VISUAL DIRECTOR POLICY — STORY FIRST, NOT TEXTBOOK
============================================================

The visuals are a major part of the storytelling. They must feel like real
shots from an entertaining documentary or cinematic YouTube Short, not slides
from a science textbook.

HARD RULES:

1. SHOW THE PHENOMENON LITERALLY.
If the narration describes a person touching metal, show a real hand touching
a real metal object. If it describes an animal, show the animal. If it
describes an object, show the object.

2. PREFER RECOGNIZABLE REAL-WORLD SCENES.
Use people, animals, objects, environments, experiments, machines, landscapes,
rooms, streets, believable laboratories, or other concrete scenes whenever
the narration allows it.

3. NEVER TURN AN EXPLANATION INTO A TEXTBOOK DIAGRAM.
Do NOT use scientific illustrations, infographic diagrams, flowcharts,
schematic drawings, anatomy diagrams, textbook cross-sections, arrows,
energy vectors, labeled parts, graphs, charts, equations, UI panels,
microscopic fantasy structures, or abstract concept art.

4. NEVER VISUALIZE AN UNSEEN MECHANISM AS IF IT WERE A CAMERA VIEW.
If a mechanism is invisible, show a believable physical consequence or a
grounded cinematic representation. Do not invent microscopic structures,
receptors, particles, forces, pathways, or internal anatomy unless the
narration explicitly requires an established visible structure.

5. DO NOT INVENT VISUAL FACTS.
The image must not imply a mechanism, object, experiment, location, researcher,
device, anatomy, or physical process that the supplied evidence does not
support.

6. KEEP THE VISUAL STORY MOVING.
Shot 1 establishes a recognizable moment. Shot 2 reveals a new detail,
reaction, consequence, comparison, perspective, or physical change.

7. REALISTIC STYLE DEFAULT.
Prefer realistic_3d_render or cinematic_photograph. Use macro_photography only
when a genuine close-up of a material, texture, surface, or small physical
detail adds storytelling value.

8. HUMAN-CENTERED VISUALS WHEN APPROPRIATE.
For everyday phenomena, prefer believable human actions, hands, faces,
reactions, objects being handled, and environments over abstract diagrams.

9. VISUAL PROMPTS MUST BE CONCRETE.
A good prompt clearly answers WHO/WHAT is visible, WHAT they are doing, WHERE
they are, WHAT changes, and WHAT the viewer should notice.

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

The image_prompt itself should contain only visible content. Do not put camera
settings, aspect ratios, captions, narration, or negative prompts inside it.
'''


def apply():
    import generate_script

    # Prevent Gemini from selecting diagram-heavy styles in the response schema.
    generate_script.VALID_IMAGE_STYLE = set(ALLOWED_IMAGE_STYLES)

    original = generate_script.build_system_prompt

    def build_system_prompt_with_visual_policy(*args, **kwargs):
        prompt = original(*args, **kwargs)
        if "VISUAL DIRECTOR POLICY — STORY FIRST, NOT TEXTBOOK" in prompt:
            return prompt
        marker = "============================================================\nIMAGE PROMPTS\n============================================================"
        if marker in prompt:
            return prompt.replace(marker, POLICY + "\n\n" + marker, 1)
        return prompt + POLICY

    generate_script.build_system_prompt = build_system_prompt_with_visual_policy

    print("🎬 Visual Director: STORY-FIRST policy enabled")
    print("   Allowed image styles: realistic_3d_render, cinematic_photograph, macro_photography")


apply()
