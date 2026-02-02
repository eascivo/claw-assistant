"""事件存储单元测试。"""

import time

import pytest
from claw_assistant.governance.events import append_event, clear_events, get_events


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


def test_clear_events() -> None:
    append_event("a", {})
    clear_events()
    assert len(get_events()) == 0
