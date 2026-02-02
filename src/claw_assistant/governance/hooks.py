"""before_tool_call / after_tool_call 逻辑：宪法检查、审批挂起。"""

from typing import Any

from claw_assistant.config import get_constitution, get_limb_config, load_config


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
    if constitution_violation(tool_name, params, config):
        return True, "constitution", params
    limb = get_limb_config(config, tool_name)
    if limb is None:
        return False, None, params

    # 仅返回是否需审批与参数，实际挂起在 task_flow 中做
    return False, None, params


def _intent_deviation_score(tool_name: str, params: dict[str, Any], config: dict[str, Any]) -> float | None:
    """
    意图偏差分（0~1）；未启用或无得分时返回 None。
    支持 stub_score（测试用）、provider=zhipu（智谱，需环境变量 ZHIPUAI_API_KEY，base_url 可用 config 或 ZHIPUAI_BASE_URL）。
    """
    rules = get_constitution(config)
    dev = rules.get("intent_deviation") or {}
    if not dev.get("enabled"):
        return None
    stub = dev.get("stub_score")
    if stub is not None:
        return float(stub)
    if dev.get("provider") == "zhipu":
        from claw_assistant.governance.intent_deviation import intent_deviation_score_zhipu
        return intent_deviation_score_zhipu(tool_name, params, config)
    return None


def constitution_violation(
    tool_name: str,
    params: dict[str, Any],
    config: dict[str, Any],
) -> bool:
    """
    宪法规则检查。
    - forbid: 工具名在此列表则一律禁止。
    - restrict: 工具名在此列表则必须配置 require_approval，否则禁止。
    - intent_deviation: 可选；enabled 且偏差分 > threshold 则禁止（当前支持 stub_score，后续可接 LLM）。
    - allow: 仅作白名单参考，当前不强制（与 forbid 配合时可扩展）。
    """
    rules = get_constitution(config)
    if tool_name in (rules.get("forbid") or []):
        return True
    restrict = rules.get("restrict") or []
    restrict_actions = [r.get("action") if isinstance(r, dict) else r for r in restrict]
    if tool_name in restrict_actions:
        limb = get_limb_config(config, tool_name)
        if not limb or not limb.get("require_approval"):
            return True
    score = _intent_deviation_score(tool_name, params, config)
    if score is not None:
        threshold = float((rules.get("intent_deviation") or {}).get("threshold", 0.5))
        if score > threshold:
            return True
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
