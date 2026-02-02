"""事件存储单元测试。"""

import time

import pytest
from claw_assistant.governance.events import (
    append_event,
    clear_events,
    get_events,
    get_run_count_by_limb,
    get_run_count_by_channel,
)


def setup_function() -> None:
    clear_events()


def test_append_and_get_events() -> None:
    append_event("approval_requested", {"approval_id": "a1", "summary": "test"})
    append_event("approval_resolved", {"approval_id": "a1", "decision": "approve"})
    out = get_events()
    assert len(out) == 2
    assert out[0]["type"] == "approval_requested"
    assert out[0]["payload"]["approval_id"] == "a1"
    assert out[1]["type"] == "approval_resolved"
    assert "ts" in out[0]


def test_get_events_since_ts() -> None:
    t0 = time.time()
    append_event("a", {})
    time.sleep(0.01)
    t1 = time.time()
    append_event("b", {})
    out = get_events(since_ts=t1)
    assert len(out) == 1
    assert out[0]["type"] == "b"


def test_get_events_limit() -> None:
    for i in range(5):
        append_event("x", {"i": i})
    out = get_events(limit=2)
    assert len(out) == 2
    assert out[0]["payload"]["i"] == 3
    assert out[1]["payload"]["i"] == 4


def test_get_events_task_id() -> None:
    append_event("limb_executed", {"task_id": "t1", "tool_name": "content"})
    append_event("limb_executed", {"task_id": "t2", "tool_name": "ops"})
    append_event("approval_requested", {"task_id": "t1", "approval_id": "a1"})
    append_event("approval_resolved", {"approval_id": "a1", "decision": "approve"})
    out_all = get_events()
    assert len(out_all) == 4
    out_t1 = get_events(task_id="t1")
    assert len(out_t1) == 2
    assert all(e.get("payload", {}).get("task_id") == "t1" for e in out_t1)
    out_t2 = get_events(task_id="t2")
    assert len(out_t2) == 1
    assert out_t2[0]["payload"]["task_id"] == "t2"
    out_none = get_events(task_id="t0")
    assert len(out_none) == 0


def test_get_run_count_by_limb() -> None:
    append_event("limb_executed", {"tool_name": "content", "channel": "main"})
    append_event("limb_executed", {"tool_name": "content", "channel": "main"})
    append_event("limb_executed", {"tool_name": "ops", "channel": "experimental"})
    append_event("approval_requested", {"approval_id": "a1"})
    by_limb = get_run_count_by_limb()
    assert by_limb == {"content": 2, "ops": 1}


def test_get_run_count_by_channel() -> None:
    append_event("limb_executed", {"tool_name": "content", "channel": "main"})
    append_event("limb_executed", {"tool_name": "ops", "channel": "experimental"})
    append_event("limb_executed", {"tool_name": "content", "channel": "main"})
    by_channel = get_run_count_by_channel()
    assert by_channel == {"main": 2, "experimental": 1}


def test_get_run_count_by_limb_empty_returns_empty_dict() -> None:
    assert get_run_count_by_limb() == {}


def test_get_run_count_by_channel_missing_channel_uses_unknown() -> None:
    append_event("limb_executed", {"tool_name": "content"})
    by_channel = get_run_count_by_channel()
    assert by_channel == {"unknown": 1}


def test_clear_events() -> None:
    append_event("a", {})
    clear_events()
    assert len(get_events()) == 0
