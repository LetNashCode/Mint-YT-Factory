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
