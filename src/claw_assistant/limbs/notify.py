"""Notify Limb：Phase 1 stub，通知/提醒类任务占位。"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def execute_notify(params: dict[str, Any]) -> dict[str, Any]:
    """执行 Notify 任务（stub）：打 log，返回固定结构。"""
    summary = params.get("summary", "")
    logger.info("notify limb executed (stub): summary=%s", summary[:100] if summary else "")
    return {
        "ok": True,
        "limb": "notify",
        "message": "stub executed",
        "summary": summary,
    }
