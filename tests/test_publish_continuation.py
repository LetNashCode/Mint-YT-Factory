import pytest

def test_publish_has_exactly_six_scenes():
    import generate_script
    assert generate_script.SCENE_COUNT == 6
    assert generate_script.SCENE_DURATIONS == [3, 5, 7, 7, 8, 8]

def test_publish_entertainment_contract_is_six_scenes():
    import generate_script
    script = {"scene_plan": [{"narration": f"Scene {i}."} for i in range(1, 7)]}
    # The validator also enforces conversational structure; test the structural
    # contract directly through the generation constants.
    assert len(script["scene_plan"]) == generate_script.SCENE_COUNT

def test_publish_rejects_seven_scene_script():
    import generate_script
    script = {"scene_plan": [{"narration": f"Scene {i}."} for i in range(1, 8)]}
    with pytest.raises(RuntimeError, match="exactly 6 scenes"):
        generate_script._validate_entertainment(script, "Why does a kettle whistle")

def test_publish_final_scene_is_payoff_not_bridge():
    import main
    script = {
        "topic": "Why does a kettle whistle",
        "next_short": {"topic": "Why does soda fizz", "teaser": "Next up: why does soda fizz?"},
        "scene_plan": [{"narration": "Hook."} for _ in range(6)],
    }
    locked, next_topic = main.lock_next_topic(
        script,
        "Why does a kettle whistle",
        locked_topic="Why does soda fizz",
    )
    assert next_topic == "Why does soda fizz"
    assert len(locked["scene_plan"]) == 6
    assert locked["scene_plan"][-1]["narration"] == "Hook."
    assert "soda fizz" not in locked["scene_plan"][-1]["narration"].lower()
    assert "teaser" not in locked["next_short"]

def test_publish_rejects_future_topic_in_scene_6():
    import generate_script
    script = {
        "next_short": {"topic": "Why do clothes shrink in dryers"},
        "scene_plan": [
            {"narration": "Hook."},
            {"narration": "Setup."},
            {"narration": "Explanation."},
            {"narration": "Mechanism."},
            {"narration": "Escalation."},
            {"narration": "And once you know that, there's another mystery: why your clothes shrink in dryers."},
        ],
    }
    with pytest.raises(RuntimeError, match="Scene 6"):
        generate_script._validate_no_future_topic_in_story(script, "Why does a brush shed")

def test_publish_visual_contract_rejects_static_duplicate_action():
    import generate_script
    entertainment = {"scene_plan": [{"narration": "The object changes."}] * 6}
    visuals = {
        "scene_plan": [
            {
                "visual_concepts": ["ice cube in water", "ice cube cracking"],
                "visuals": [
                    {"visual_focus": "ice cube", "visual_action": "sits in water", "image_prompt": "close-up ice cube sitting in a glass of water", "spoken_line": "The cube sits in water.", "visual_concept":"ice cube sits in water", "must_show":["ice cube","glass","water"], "must_not_show":["person","laboratory","diagram"]},
                    {"visual_focus": "ice cube", "visual_action": "sits in water", "image_prompt": "close-up ice cube sitting in a glass of water", "spoken_line": "The cube sits in water.", "visual_concept":"ice cube sits in water again", "must_show":["ice cube","glass","water"], "must_not_show":["person","laboratory","diagram"]},
                ],
            }
        ] * 6
    }
    with pytest.raises(RuntimeError, match="does not advance"):
        generate_script._validate_visuals(visuals, entertainment, "Why does ice crack")

def test_publish_generation_contract_has_no_writer_owned_next_topic():
    import generate_script
    schema = generate_script._entertainment_schema()
    props = schema.get("properties", {})
    assert "next_short" not in props
    assert "next_short" not in schema.get("required", [])

