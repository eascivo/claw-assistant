"""任务流：意图 → 宪法检查 → 审批（挂起/解挂）→ 幂等 → Limb 执行 → after_tool_call → World Checkpoint。"""

import logging
import uuid
from typing import Any

from claw_assistant.config import get_limb_config, load_config
from claw_assistant.governance.approval import ApprovalManager
from claw_assistant.governance.checkpoint import schedule_checkpoint
from claw_assistant.governance.events import append_event
from claw_assistant.governance.hooks import after_tool_call, before_tool_call
from claw_assistant.limbs import execute_limb

logger = logging.getLogger(__name__)


async def run_task_flow(
    intent: str,
    approval_manager: ApprovalManager,
    config: dict[str, Any] | None = None,
    session_key: str | None = None,
    channel: str = "main",
) -> dict[str, Any]:
    """
    主任务流：生成任务 → Constitution 检查 → 若需审批则挂起并 wait → 幂等检查 → 执行 Limb → World Check 占位。
    channel：main（生产）或 experimental（Brain-B 影子）；事件与结果带 channel 标记。
    返回 { "ok": True, "result": ... } 或 { "ok": False, "error": ... } 或 { "ok": False, "block_reason": ... }；
    若需审批则在内部 register 后 await wait，通过后再执行。
    """
    config = config or load_config()
    task_id = str(uuid.uuid4())
    tool_name = "content"
    params: dict[str, Any] = {"summary": intent}

    block, block_reason, params = before_tool_call(tool_name, params, config)
    if block:
        logger.warning("task blocked by hook: %s", block_reason)
        return {"ok": False, "block_reason": block_reason or "unknown"}

    limb_cfg = get_limb_config(config, tool_name)
    if limb_cfg and limb_cfg.get("require_approval"):
        pending = await approval_manager.register(
            session_key=session_key,
            tool_name=tool_name,
            params=params,
            task_id=task_id,
            risk=limb_cfg.get("risk"),
        )
        decision = await approval_manager.wait(pending.approval_id)
        if decision == "reject":
            return {"ok": False, "error": "rejected by human"}

    # 幂等占位：Phase 1 不实现
    result = execute_limb(tool_name, params)
    append_event(
        "limb_executed",
        {
            "task_id": task_id,
            "tool_name": tool_name,
            "summary": params.get("summary", ""),
            "ok": result.get("ok"),
            "channel": channel,
        },
    )
    after_tool_call(tool_name, params, result, config)
    schedule_checkpoint(tool_name, params, result, task_id, config)

    if result.get("ok"):
        result_with_channel = {**result, "channel": channel}
        return {"ok": True, "result": result_with_channel}
    return {"ok": False, "error": result.get("error", "limb execution failed")}
