import copy

import pytest


def valid_blueprint():
    return {
        "central_mystery": "Why a cold glass develops water droplets outside",
        "viewer_question": "Where does the water on the outside come from",
        "misconception_or_assumption": "People may assume water leaks through the glass",
        "first_reveal": "The glass stays dry inside its walls but droplets form outside",
        "mechanism": "Water vapor in nearby air cools and condenses on the cold surface",
        "unexpected_consequence": "The air itself supplies the water that gathers on the glass",
        "final_payoff": "The droplets came from invisible water vapor in the room air",
        "emotional_effect": "A familiar scene becomes a small satisfying surprise",
        "hook_observation": "A cold glass suddenly grows droplets on its outside surface",
        "factual_anchor": {
            "core_claim": "Water vapor condenses into liquid droplets on a cold glass",
            "basis": "General scientific principle; no source notes were supplied",
            "verification_needed": True,
        },
        "hook_payoff_connection": "The outside droplets are explained by vapor in the air condensing on the cold surface",
        "visual_feasibility": "Show a cold glass collecting visible droplets, then a close-up of condensation",
        "scene_progression": [
            {"scene": 1, "story_job": "Hook", "information_revealed": "Droplets appear on the outside of a cold glass", "question_left_open": "Where did the water come from", "narration_must_communicate": "The outside surface becomes wet"},
            {"scene": 2, "story_job": "Assumption", "information_revealed": "The glass is not leaking from inside", "question_left_open": "What else could supply the water", "narration_must_communicate": "The droplets form externally"},
            {"scene": 3, "story_job": "First reveal", "information_revealed": "Moisture is already present in the surrounding air", "question_left_open": "How does air moisture become liquid", "narration_must_communicate": "Air contains water vapor"},
            {"scene": 4, "story_job": "Mechanism", "information_revealed": "The cold surface cools nearby water vapor", "question_left_open": "What does cooling change", "narration_must_communicate": "Cooling allows vapor to condense"},
            {"scene": 5, "story_job": "Escalation", "information_revealed": "Tiny droplets gather into visible beads", "question_left_open": "How does this resolve the original mystery", "narration_must_communicate": "The visible water comes from the air"},
            {"scene": 6, "story_job": "Payoff", "information_revealed": "Condensation explains the droplets on the glass", "question_left_open": "None; the central question is answered", "narration_must_communicate": "The droplets came from water vapor in the room"},
        ],
    }


def test_blueprint_schema_requires_new_story_architecture_fields():
    import generate_script

    required = set(generate_script._blueprint_schema()["required"])
    assert {"hook_observation", "factual_anchor", "hook_payoff_connection", "visual_feasibility", "scene_progression"} <= required


def test_blueprint_quality_gate_accepts_complete_six_scene_blueprint():
    import generate_script

    assert generate_script._validate_blueprint(valid_blueprint())


def test_blueprint_quality_gate_rejects_missing_hook_observation():
    import generate_script

    blueprint = valid_blueprint()
    blueprint["hook_observation"] = ""
    with pytest.raises(RuntimeError, match="missing required beats"):
        generate_script._validate_blueprint(blueprint)


def test_blueprint_quality_gate_rejects_non_six_scene_progression():
    import generate_script

    blueprint = valid_blueprint()
    blueprint["scene_progression"].pop()
    with pytest.raises(RuntimeError, match="exactly 6 ordered scenes"):
        generate_script._validate_blueprint(blueprint)


def test_blueprint_quality_gate_rejects_scene_order_gaps():
    import generate_script

    blueprint = valid_blueprint()
    blueprint["scene_progression"][2]["scene"] = 4
    with pytest.raises(RuntimeError, match="numbered 1 through 6"):
        generate_script._validate_blueprint(blueprint)


def test_blueprint_quality_gate_rejects_repeated_scene_information():
    import generate_script

    blueprint = valid_blueprint()
    blueprint["scene_progression"][1]["information_revealed"] = blueprint["scene_progression"][0]["information_revealed"]
    with pytest.raises(RuntimeError, match="each scene must advance"):
        generate_script._validate_blueprint(blueprint)


def test_blueprint_quality_gate_requires_explicit_scene_six_closure():
    import generate_script

    blueprint = valid_blueprint()
    blueprint["scene_progression"][-1]["question_left_open"] = "What else might happen"
    with pytest.raises(RuntimeError, match="must explicitly close"):
        generate_script._validate_blueprint(blueprint)


def test_blueprint_quality_gate_requires_factual_anchor_shape():
    import generate_script

    blueprint = valid_blueprint()
    blueprint["factual_anchor"] = {"core_claim": "Condensation happens"}
    with pytest.raises(RuntimeError, match="factual_anchor needs"):
        generate_script._validate_blueprint(blueprint)


def test_blueprint_validator_still_rejects_retired_subject_bleed():
    import generate_script

    blueprint = valid_blueprint()
    blueprint["hook_observation"] = "An onion grows droplets outside the glass"
    with pytest.raises(RuntimeError, match="retired onion subject bleed"):
        generate_script._validate_blueprint(blueprint)



def test_blueprint_quality_gate_rejects_negated_closure():
    import generate_script

    blueprint = valid_blueprint()
    blueprint["scene_progression"][-1]["question_left_open"] = "The central question remains unanswered"
    with pytest.raises(RuntimeError, match="must explicitly close"):
        generate_script._validate_blueprint(blueprint)
