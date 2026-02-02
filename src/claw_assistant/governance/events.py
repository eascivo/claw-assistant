"""事件存储：审批 requested/resolved、limb 执行、postmortem，供 Dashboard 时间轴。"""

import time
from typing import Any

_events: list[dict[str, Any]] = []
_max_events = 10_000


def append_event(event_type: str, payload: dict[str, Any]) -> None:
    """追加一条事件；类型如 approval_requested / approval_resolved / limb_executed / postmortem。"""
    global _events
    entry = {
        "ts": time.time(),
        "type": event_type,
        "payload": payload,
    }
    _events.append(entry)
    if len(_events) > _max_events:
        _events[:] = _events[-_max_events:]


def get_events(
    since_ts: float | None = None,
    limit: int = 200,
    task_id: str | None = None,
) -> list[dict[str, Any]]:
    """返回事件列表，按时间正序。since_ts 为可选起始时间戳，limit 限制条数，task_id 可选用于单任务回放。"""
    out = list(_events)
    if since_ts is not None:
        out = [e for e in out if e["ts"] >= since_ts]
    if task_id is not None:
        out = [e for e in out if e.get("payload", {}).get("task_id") == task_id]
    return out[-limit:] if limit else out


def get_events_count() -> int:
    """返回当前事件总数，供 GET /metrics 等可观测用。"""
    return len(_events)


def get_run_count() -> int:
    """返回已完成执行次数（limb_executed 事件数），供 GET /metrics 等可观测用。"""
    return sum(1 for e in _events if e.get("type") == "limb_executed")


def clear_events() -> None:
    """清空事件（仅测试用）。"""
    global _events
    _events.clear()
