"""可收敛建议单元测试。"""

import pytest
from claw_assistant.governance.convergence import get_convergence_suggestions


def test_get_convergence_suggestions_empty_postmortems_returns_empty() -> None:
    out = get_convergence_suggestions([], None)
    assert out == []


def test_get_convergence_suggestions_no_threshold_returns_empty() -> None:
    out = get_convergence_suggestions([{"task_id": "t1"}], {})
    assert out == []


def test_get_convergence_suggestions_under_threshold_returns_empty() -> None:
    config = {"checkpoint": {"alert_after_postmortem_count": 3}}
    out = get_convergence_suggestions([{"task_id": "t1"}, {"task_id": "t2"}], config)
    assert out == []


def test_get_convergence_suggestions_at_or_over_threshold_returns_one() -> None:
    config = {"checkpoint": {"alert_after_postmortem_count": 2}}
    out = get_convergence_suggestions([{"task_id": "t1"}, {"task_id": "t2"}], config)
    assert len(out) == 1
    assert out[0]["id"] == "postmortem_threshold"
    assert "复盘条数已达 2" in out[0]["text"]
    assert out[0]["source"] == "postmortem_summary"


def test_get_convergence_suggestions_invalid_threshold_returns_empty() -> None:
    config = {"checkpoint": {"alert_after_postmortem_count": "nope"}}
    out = get_convergence_suggestions([{"task_id": "t1"}, {"task_id": "t2"}], config)
    assert out == []
