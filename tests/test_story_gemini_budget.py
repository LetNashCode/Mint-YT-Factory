"""Regression tests for the single run-wide Story Gemini budget."""
from pathlib import Path

import story_gemini_budget as budget


def setup_function():
    budget.reset()


def teardown_function():
    budget.reset()


def test_budget_is_shared_across_story_stages(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STORY_GEMINI_MAX_REQUESTS", "3")
    assert budget.begin() == {"limit": 3, "used": 0}

    assert budget.consume("topic_generation") == 1
    assert budget.consume("script_generation") == 2
    assert budget.consume("visual_verification") == 3

    try:
        budget.consume("stock_search")
    except RuntimeError as exc:
        assert "Story Gemini request budget exhausted" in str(exc)
    else:
        raise AssertionError("budget must stop the fourth Story Gemini request")

    assert budget.status() == {"limit": 3, "used": 3}
    assert (Path(".story_gemini_budget_deferred")).exists()


def test_budget_does_not_activate_outside_story_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STORY_GEMINI_MAX_REQUESTS", "1")
    assert budget.status() == {"limit": None, "used": 0}
    assert budget.consume("stock_search") == 0
    assert budget.status() == {"limit": None, "used": 0}
    assert not Path(".story_gemini_budget_deferred").exists()


def test_begin_resets_only_at_new_run():
    budget.begin()
    budget.consume("topic_generation")
    assert budget.status()["used"] == 1

    budget.begin()
    assert budget.status()["used"] == 0
