from generate_script.interactive import (
    STORY_SCENE_WORD_BUDGETS,
    _retry_word_budget_guidance,
)


def test_story_scene_word_bands_remain_compatible_with_total_target():
    assert STORY_SCENE_WORD_BUDGETS == (
        (8, 18), (7, 22), (7, 22), (7, 22), (7, 22), (7, 22), (10, 28)
    )


def test_short_total_retry_adds_story_detail_instead_of_trimming():
    guidance = _retry_word_budget_guidance(
        "RuntimeError: Story narration total 79 words outside 80-120."
    )
    assert "Scene 1 = 10-14 words" in guidance
    assert "Scenes 2-6 = 12-16 words EACH" in guidance
    assert "add meaningful, factual cause-and-effect details" in guidance
    assert "do not pad with generic motivation" in guidance


def test_overlong_scene_retry_targets_that_scene():
    guidance = _retry_word_budget_guidance(
        "RuntimeError: Story scene 1 word count 19 outside 8-18."
    )
    assert "Scene 1 was overlength (19)" in guidance
    assert "shorten that scene" in guidance


def test_long_total_retry_preserves_factual_beats():
    guidance = _retry_word_budget_guidance(
        "RuntimeError: Story narration total 124 words outside 80-120."
    )
    assert "remove redundant wording" in guidance
