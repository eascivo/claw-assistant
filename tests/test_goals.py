"""目标池（goals）单测：add_goal、list_goals、update_goal_status。"""

import time

import pytest

from claw_assistant.goals import add_goal, clear_goals, list_goals, update_goal_status


def test_add_goal_returns_id_and_text() -> None:
    """add_goal 返回含 id、text、status、created_at 的字典。"""
    clear_goals()
    g = add_goal("本周完成内容发布")
    assert "id" in g
    assert g["text"] == "本周完成内容发布"
    assert g["status"] == "pending"
    assert "created_at" in g
    assert isinstance(g["created_at"], (int, float))


def test_list_goals_returns_all_by_default() -> None:
    """list_goals 默认返回全部目标，按创建时间倒序。"""
    clear_goals()
    add_goal("A")
    add_goal("B")
    out = list_goals()
    assert len(out) == 2
    assert out[0]["text"] == "B"
    assert out[1]["text"] == "A"


def test_list_goals_filter_by_status() -> None:
    """list_goals(status=...) 只返回该状态的目标。"""
    clear_goals()
    a = add_goal("一")
    add_goal("二")
    update_goal_status(a["id"], "done")
    pending = list_goals(status="pending")
    done = list_goals(status="done")
    assert len(pending) == 1
    assert pending[0]["text"] == "二"
    assert len(done) == 1
    assert done[0]["text"] == "一"


def test_update_goal_status() -> None:
    """update_goal_status 可把 status 改为 done 或 cancelled。"""
    clear_goals()
    g = add_goal("x")
    ok = update_goal_status(g["id"], "done")
    assert ok is True
    one = list_goals(status="done")
    assert len(one) == 1
    assert one[0]["status"] == "done"
    ok2 = update_goal_status(g["id"], "cancelled")
    assert ok2 is True
    cancelled = list_goals(status="cancelled")
    assert len(cancelled) == 1


def test_update_goal_status_unknown_id_returns_false() -> None:
    """不存在的 id 更新返回 False。"""
    clear_goals()
    assert update_goal_status("no-such-id", "done") is False
