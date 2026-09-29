from main import _strip_model_continuation_from_scene7


def test_scene7_removes_multiple_model_teasers():
    scene = {
        "narration": (
            "That is why the effect happens. "
            "And once you know that, there's another everyday mystery hiding in plain sight: why mirrors reverse things? "
            "But that isn't the only strange consequence. Wait until you see what happens with ice cubes."
        )
    }

    payoff = _strip_model_continuation_from_scene7(
        scene,
        ["Why do mirrors reverse things?"],
    )

    assert payoff == "That is why the effect happens."
    assert "another everyday mystery" not in payoff
    assert "ice cubes" not in payoff


def test_scene7_removes_canonical_topic_sentence_before_bridge():
    scene = {
        "narration": (
            "The reflection looks reversed because of how the mirror maps space. "
            "Next mystery: why do mirrors reverse things?"
        )
    }

    payoff = _strip_model_continuation_from_scene7(
        scene,
        ["Why do mirrors reverse things?"],
    )

    assert payoff == "The reflection looks reversed because of how the mirror maps space."



def test_publish_ending_contains_only_canonical_next_topic(monkeypatch):
    import main

    monkeypatch.setattr(
        main,
        "_generate_natural_bridge",
        lambda current, nxt: (f"Next up: {nxt}.", "test"),
    )

    script = {
        "topic": "Why does a kettle whistle",
        "next_short": {"topic": "Why does soda fizz"},
        "scene_plan": [
            {"narration": "Hook."},
            {"narration": "Setup."},
            {"narration": "Explanation."},
            {"narration": "Mechanism."},
            {"narration": "Escalation."},
            {"narration": "Final explanation."},
            {"narration": "That is why the kettle whistles."},
        ],
    }

    locked, next_topic = main.lock_next_topic(
        script,
        "Why does a kettle whistle",
        locked_topic="Why does soda fizz",
    )

    assert next_topic == "Why does soda fizz"
    assert locked["scene_plan"][-1]["narration"] == "Next up: Why does soda fizz."
    assert "kettle" not in locked["scene_plan"][-1]["narration"].lower()
    assert "soda fizz" not in locked["scene_plan"][-2]["narration"].lower()
    assert "kettle whistles" in locked["scene_plan"][-2]["narration"].lower()


def test_publish_removes_future_topic_intro_from_earlier_scene():
    import main

    script = {
        "topic": "Why does a kettle whistle",
        "next_short": {"topic": "Why does soda fizz"},
        "scene_plan": [
            {"narration": "Hook."},
            {"narration": "The mechanism is surprisingly simple. And once you know that, there's another everyday mystery hiding in plain sight: why does soda fizz?"},
            {"narration": "Final explanation."},
            {"narration": "The payoff."},
            {"narration": "More detail."},
            {"narration": "The answer."},
            {"narration": "Ending placeholder."},
        ],
    }

    removed = main._strip_future_continuations_from_prior_scenes(
        script, ["Why does soda fizz"]
    )

    assert removed == 1
    assert "soda fizz" not in script["scene_plan"][1]["narration"].lower()
    assert script["scene_plan"][-1]["narration"] == "Ending placeholder."


def test_publish_rejects_future_topic_inside_scene_6():
    import pytest
    import generate_script

    script = {
        "next_short": {"topic": "Why do clothes shrink in dryers"},
        "scene_plan": [
            {"narration": "Hook."},
            {"narration": "Setup."},
            {"narration": "Explanation."},
            {"narration": "Mechanism."},
            {"narration": "Escalation."},
            {"narration": "And once you know that, there's another mystery: why your favourite clothes shrink in dryers."},
            {"narration": "Final handoff."},
        ],
    }

    with pytest.raises(RuntimeError, match="Scene 6"):
        generate_script._validate_no_future_topic_in_story(script, "Why does a brush shed")



def test_publish_removes_generated_topic_after_reservation_overwrites_metadata(monkeypatch):
    import main

    monkeypatch.setattr(
        main,
        "_generate_natural_bridge",
        lambda current, nxt: (f"Next up: {nxt}.", "test"),
    )

    script = {
        "topic": "Why does a brush shed",
        # This is the writer's first continuation candidate. In production,
        # reserve_next_short() can replace it with the authoritative successor.
        "next_short": {"topic": "Why onion makes you cry"},
        "scene_plan": [
            {"narration": "Hook."},
            {"narration": "Setup."},
            {"narration": "Explanation."},
            {"narration": "Mechanism."},
            {"narration": "Escalation."},
            {"narration": "The answer is surprisingly simple. And once you know that, another mystery is why onion makes you cry."},
            {"narration": "Ending placeholder."},
        ],
    }

    locked, next_topic = main.lock_next_topic(
        script,
        "Why does a brush shed",
        locked_topic="Why do yawns spread",
        stale_topics=["Why onion makes you cry"],
    )

    assert next_topic == "Why do yawns spread"
    assert "onion makes you cry" not in " ".join(
        scene["narration"] for scene in locked["scene_plan"][:6]
    ).lower()
    assert locked["scene_plan"][-1]["narration"] == "Next up: Why do yawns spread."
    assert "onion makes you cry" not in locked["scene_plan"][-1]["narration"].lower()



def test_runtime_continuation_guard_forwards_stale_topics():
    import types
    import runtime_overrides

    calls = {}

    def original_lock(script, current_topic, locked_topic=None, stale_topics=None):
        calls["stale_topics"] = stale_topics
        return script, locked_topic

    fake_main = types.SimpleNamespace(lock_next_topic=original_lock)
    runtime_overrides.patch_continuation(fake_main)

    fake_main.lock_next_topic(
        {"scene_plan": []},
        "Why does a brush shed",
        locked_topic="Why do yawns spread",
        stale_topics=["Why onion makes you cry"],
    )

    assert calls["stale_topics"] == ["Why onion makes you cry"]


def test_publish_generation_contract_has_no_writer_owned_next_topic():
    import generate_script

    schema = generate_script._entertainment_schema()
    props = schema.get("properties", {})

    assert "next_short" not in props
    assert "next_short" not in schema.get("required", [])


def test_publish_story_blueprint_has_required_story_beats():
    import generate_script

    schema = generate_script._blueprint_schema()
    required = set(schema.get("required", []))

    assert {
        "central_mystery",
        "viewer_question",
        "misconception_or_assumption",
        "first_reveal",
        "mechanism",
        "unexpected_consequence",
        "final_payoff",
        "emotional_effect",
    } <= required


def test_publish_blueprint_is_passed_into_narration_prompt():
    import generate_script

    blueprint = {
        "central_mystery": "A kettle can whistle without a person blowing into it.",
        "viewer_question": "What makes the sound?",
        "misconception_or_assumption": "The steam itself is simply making noise.",
        "first_reveal": "The opening becomes unstable as pressure rises.",
        "mechanism": "Steam forces air through a narrow opening.",
        "unexpected_consequence": "The airflow can repeatedly interrupt itself.",
        "final_payoff": "The whistle is created by a feedback loop in the escaping steam.",
        "emotional_effect": "A familiar kitchen sound suddenly feels mechanical and strange.",
    }

    prompt = generate_script._entertainment_prompt(
        "Why does a kettle whistle",
        blueprint,
        "test feedback",
    )

    assert "STORY BLUEPRINT — SOURCE OF TRUTH" in prompt
    assert blueprint["final_payoff"] in prompt
    assert "test feedback" in prompt


def test_publish_visual_contract_rejects_static_duplicate_action():
    import generate_script

    entertainment = {
        "scene_plan": [{"narration": "The object changes."}] * 7,
    }
    visuals = {
        "scene_plan": [
            {
                "visuals": [
                    {
                        "visual_focus": "ice cube",
                        "visual_action": "sits in water",
                        "image_prompt": "close-up ice cube sitting in a glass of water",
                        "spoken_line": "The cube sits in water.",
                        "must_show": ["ice cube", "glass", "water"],
                        "must_not_show": ["person", "laboratory", "diagram"],
                    },
                    {
                        "visual_focus": "ice cube",
                        "visual_action": "sits in water",
                        "image_prompt": "close-up ice cube sitting in a glass of water",
                        "spoken_line": "The cube sits in water.",
                        "must_show": ["ice cube", "glass", "water"],
                        "must_not_show": ["person", "laboratory", "diagram"],
                    },
                ]
            }
        ] * 7
    }

    import pytest
    with pytest.raises(RuntimeError, match="does not advance"):
        generate_script._validate_visuals(visuals, entertainment, "Why does ice crack")


def test_publish_cleanup_catches_paraphrased_locked_successor():
    import main

    script = {
        "topic": "Why do telephone poles crack",
        "scene_plan": [
            {"narration": "Hook."},
            {"narration": "The wood stores tension, which makes you wonder why a guitar strings snap when the weather turns cold."},
            {"narration": "Explanation."},
            {"narration": "Mechanism."},
            {"narration": "Consequence."},
            {"narration": "Payoff."},
            {"narration": "Ending."},
        ],
    }

    removed = main._strip_future_continuations_from_prior_scenes(
        script, ["Why do guitar strings snap"]
    )

    assert removed == 1
    assert "guitar strings snap" not in script["scene_plan"][1]["narration"].lower()


def test_publish_future_topic_guard_rejects_generic_handoff_in_scene_6():
    import generate_script
    import pytest

    script = {
        "next_short": {},
        "scene_plan": [
            {"narration": "Hook."},
            {"narration": "Setup."},
            {"narration": "Explanation."},
            {"narration": "Mechanism."},
            {"narration": "Consequence."},
            {"narration": "That makes you wonder why this happens somewhere else."},
            {"narration": "Ending."},
        ],
    }

    with pytest.raises(RuntimeError, match="Scene 6"):
        generate_script._validate_no_future_topic_in_story(script, "Why do telephone poles crack")
