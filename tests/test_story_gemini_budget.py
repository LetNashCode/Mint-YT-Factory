"""Regression tests for the single run-wide Story Gemini budget."""
import ast
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

def test_story_gemini_entrypoints_are_budgeted_before_api_calls():
    root = Path(__file__).resolve().parents[1]
    for relative in ("interactive_topics.py", "generate_script/interactive.py", "stock_search.py"):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"), filename=relative)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute) or node.func.attr != "generate_content":
                continue
            parent = next(
                (
                    parent_node
                    for parent_node in ast.walk(tree)
                    if isinstance(parent_node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and any(child is node for child in ast.walk(parent_node))
                ),
                None,
            )
            assert parent is not None, f"unscoped Gemini call in {relative}"
            statements = []
            for child in ast.walk(parent):
                if isinstance(child, ast.stmt):
                    statements.append(child)
            prior = [s for s in statements if getattr(s, "lineno", 0) < node.lineno]
            assert prior, f"Gemini call has no preceding budget guard in {relative}"
            assert any(
                isinstance(s, ast.Expr)
                and isinstance(s.value, ast.Call)
                and isinstance(s.value.func, ast.Attribute)
                and s.value.func.attr == "consume"
                and isinstance(s.value.func.value, ast.Name)
                and s.value.func.value.id == "story_gemini_budget"
                for s in prior[-2:]
            ), f"Gemini call is not guarded by story_gemini_budget in {relative}"
