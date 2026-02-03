"""目标池（内存存储）：人类偶发设定的目标列表，供后续拆解为 intent 调用 POST /run。"""

import re
import time
import uuid
from typing import Any


_goals: list[dict[str, Any]] = []


def add_goal(text: str) -> dict[str, Any]:
    """新增一条目标，返回 { id, text, status, created_at }。status 初始为 pending。"""
    text = (text or "").strip()
    g = {
        "id": str(uuid.uuid4()),
        "text": text,
        "status": "pending",
        "created_at": time.time(),
    }
    _goals.append(g)
    return g


def get_goal(goal_id: str) -> dict[str, Any] | None:
    """按 id 返回目标，不存在返回 None。"""
    for g in _goals:
        if g.get("id") == goal_id:
            return g
    return None


def list_goals(status: str | None = None) -> list[dict[str, Any]]:
    """返回目标列表；status 非空时只返回该状态。按 created_at 倒序。"""
    out = _goals
    if status:
        out = [x for x in out if x.get("status") == status]
    return sorted(out, key=lambda x: x.get("created_at", 0), reverse=True)


def expand_goal_to_intents(goal_text: str, config: dict[str, Any] | None = None) -> list[str]:
    """
    将目标拆解为 intent 列表。
    - config 无或 goals.expand_strategy 非 "split"：返回单条 = 目标原文（passthrough）。
    - goals.expand_strategy == "split" 且 goals.expand_split_by 非空：按分隔符拆成多条，每段 strip 后非空即一条。
    """
    text = (goal_text or "").strip()
    if not text:
        return []
    goals_cfg = (config or {}).get("goals") or {}
    strategy = goals_cfg.get("expand_strategy") or "passthrough"
    split_by = goals_cfg.get("expand_split_by")
    if strategy == "split" and split_by and isinstance(split_by, list) and len(split_by) > 0:
        separators = [str(s) for s in split_by if s]
        if not separators:
            return [text]
        pattern = "|".join(re.escape(s) for s in separators)
        parts = re.split(pattern, text)
        intents = [p.strip() for p in parts if p.strip()]
        return intents if intents else [text]
    return [text]


def update_goal_status(goal_id: str, status: str) -> bool:
    """将指定 id 的目标状态更新为 status（done / cancelled）。不存在返回 False。"""
    for g in _goals:
        if g.get("id") == goal_id:
            g["status"] = status
            return True
    return False


def clear_goals() -> None:
    """清空目标池（仅测试用）。"""
    _goals.clear()