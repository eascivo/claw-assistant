"""Content Limb：Phase 1 stub，仅打 log 并返回占位结果。"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def execute_content(params: dict[str, Any]) -> dict[str, Any]:
    """执行 Content 任务（stub）：打 log，返回固定结构。"""
    summary = params.get("summary", "")
    logger.info("content limb executed (stub): summary=%s", summary[:100] if summary else "")
    return {
        "ok": True,
        "limb": "content",
        "message": "stub executed",
        "summary": summary,
    }
