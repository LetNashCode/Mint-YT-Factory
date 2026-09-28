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
