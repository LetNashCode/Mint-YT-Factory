import json

import pytest

from story_media_quality import relevance_score, validate_groups, write_audit_report


def _groups(score=8.0):
    return [
        {"source_url": f"https://commons.example/{i}", "asset_key": f"wikimedia:photo:{i}", "score": score}
        for i in range(14)
    ]


def test_relevance_score_rewards_person_and_cues():
    assert relevance_score("Marie Curie", "Marie Curie laboratory", "Marie Curie in laboratory", "laboratory research", ["laboratory"]) >= 5


def test_validate_groups_accepts_14_unique_qualified_assets():
    validate_groups(_groups())


def test_validate_groups_rejects_duplicate_assets():
    groups = _groups()
    groups[-1]["source_url"] = groups[0]["source_url"]
    with pytest.raises(RuntimeError, match="Duplicate"):
        validate_groups(groups)


def test_validate_groups_rejects_low_score():
    with pytest.raises(RuntimeError, match="relevance"):
        validate_groups(_groups(score=4))


def test_audit_report_is_json(tmp_path):
    destination = tmp_path / "audit" / "visuals.json"
    write_audit_report([{"scene": 1, "score": 8}], str(destination))
    assert json.loads(destination.read_text()) == [{"scene": 1, "score": 8}]
