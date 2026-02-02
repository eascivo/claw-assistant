"""before_tool_call / after_tool_call 逻辑：宪法检查、审批挂起。"""

from typing import Any

from claw_assistant.config import get_limb_config, load_config


def before_tool_call(
    tool_name: str,
    params: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> tuple[bool, str | None, dict[str, Any]]:
    """
    执行前钩子：宪法检查 + 是否需要审批。
    返回 (block, block_reason, modified_params)。
    若 block=True，调用方不应执行工具；若 block=False，可使用 modified_params 继续。
    注意：审批挂起由调用方在拿到 require_approval 后调用 ApprovalManager 并 await wait，此处只做「是否需要审批」的判断。
    """
    config = config or load_config()
    limb = get_limb_config(config, tool_name)
    if limb is None:
        return False, None, params

    if _constitution_violation(tool_name, params, config):
        return True, "constitution", params

    # 仅返回是否需审批与参数，实际挂起在 task_flow 中做
    return False, None, params


def _constitution_violation(
    tool_name: str,
    params: dict[str, Any],
    config: dict[str, Any],
) -> bool:
    """占位：宪法规则检查，Phase 1 默认通过。"""
    # 可扩展：从 config 读 forbid / restrict 列表
    return False


def after_tool_call(
    tool_name: str,
    params: dict[str, Any],
    result: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> None:
    """执行后钩子：World Checkpoint 占位，仅打 log。"""
    # Phase 1: 不拉真实 API，仅占位
    pass
