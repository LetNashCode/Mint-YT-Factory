import pytest

from generate_script import validate_opening_hook


def test_hook_gate_accepts_concrete_curiosity_opening():
    result = validate_opening_hook(
        "Your metal zipper feels colder than plastic, even in the same room. Here's why."
    )
    assert result["score"] >= 7
    assert result["word_count"] <= 22


@pytest.mark.parametrize(
    "opening",
    [
        "Today we're going to talk about metal zippers.",
        "Did you know metal zippers can feel cold?",
        "",
    ],
)
def test_hook_gate_rejects_generic_or_empty_opening(opening):
    with pytest.raises(RuntimeError, match="Opening-hook quality gate rejected"):
        validate_opening_hook(opening)


def test_hook_gate_rejects_overlong_opening():
    opening = (
        "Imagine you are standing in a room and you pick up a metal zipper "
        "and start wondering why it feels much colder than plastic."
    )
    with pytest.raises(RuntimeError, match="longer than 22 words"):
        validate_opening_hook(opening)
