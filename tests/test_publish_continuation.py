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
