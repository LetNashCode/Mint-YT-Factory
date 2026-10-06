import pytest

import generate_script


def _script(*narration):
    return {"scene_plan": [{"narration": text} for text in narration]}


def test_reference_style_accepts_curiosity_assumption_correction_payoff():
    script = _script(
        "Ever notice how a cold glass suddenly gets covered in water?",
        "Most people think the glass is leaking, but that's not what's happening.",
        "Actually, the water is coming from the air around the glass.",
        "When warm air touches the cold surface, the moisture in it starts turning into droplets.",
        "And the colder the glass gets, the more moisture can collect on it.",
        "So the glass isn't leaking at all; it's basically pulling water out of the air.",
        "That is why a cold drink can leave a puddle even when you never spilled a drop.",
    )
    assert generate_script._validate_reference_story_style(
        script, "Why does a cold glass get wet?"
    ) is True


def test_reference_style_rejects_flat_lecture():
    script = _script(
        "Condensation is the process where water vapor changes into liquid.",
        "It happens when warm air contacts a cold surface.",
        "The water vapor loses energy and forms droplets.",
        "These droplets collect on the surface.",
        "This process is common in everyday life.",
        "The result is liquid water on the object.",
        "This is the basic explanation for condensation.",
    )
    with pytest.raises(RuntimeError, match="Reference-story"):
        generate_script._validate_reference_story_style(
            script, "Why does a cold glass get wet?"
        )


def test_reference_style_rejects_generic_topic_opening():
    script = _script(
        "Today we're going to talk about why your shoes smell.",
        "Most people think sweat itself is the problem, but that's not accurate.",
        "Actually, bacteria break down the sweat.",
        "When they feed on it, they produce smelly compounds.",
        "And those compounds can build up inside your shoes.",
        "That is why the smell can become surprisingly strong.",
        "Now you know why your shoes smell.",
    )
    with pytest.raises(RuntimeError, match="generic topic explanation"):
        generate_script._validate_reference_story_style(
            script, "Why do shoes smell?"
        )


def test_entertainment_validator_enforces_reference_style():
    script = _script(
        "Ever notice how a cold glass suddenly gets covered in water?",
        "Some people think the glass is leaking, but that's not accurate.",
        "Actually, the water is coming from the air around it.",
        "When warm air touches the cold surface, moisture starts becoming droplets.",
        "And as the surface gets colder, even more moisture can collect.",
        "You see, the glass is basically pulling water out of the air.",
        "That is why the puddle appears without anyone spilling a drink.",
    )
    assert generate_script._validate_entertainment(
        script, "Why does a cold glass get wet?"
    ) > 0
