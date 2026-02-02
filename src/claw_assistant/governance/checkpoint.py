"""World Checkpoint：延时校验、偏差计算、复盘写入。"""

import asyncio
import logging
from typing import Any, Callable

from claw_assistant.config import get_limb_config, load_config
from claw_assistant.governance.events import append_event

logger = logging.getLogger(__name__)

# 校验器： (tool_name, params, result) -> {"actual": number, "expected": number} 或 None（跳过）
ValidatorFn = Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any] | None]

_validators: dict[str, ValidatorFn] = {}
_postmortems: list[dict[str, Any]] = []


def register_validator(name: str, fn: ValidatorFn) -> None:
    """注册名为 name 的校验器。"""
    _validators[name] = fn


def get_postmortems() -> list[dict[str, Any]]:
    """返回已写入的复盘列表（内存，供 API/测试用）。"""
    return list(_postmortems)


def clear_postmortems() -> None:
    """清空复盘列表（仅测试用）。"""
    _postmortems.clear()


def _write_postmortem(
    tool_name: str,
    task_id: str,
    expected: float,
    actual: float,
    deviation: float,
    params: dict[str, Any],
    result: dict[str, Any],
) -> None:
    entry = {
        "tool_name": tool_name,
        "task_id": task_id,
        "expected": expected,
        "actual": actual,
        "deviation": deviation,
        "params": params,
        "result": result,
    }
    _postmortems.append(entry)
    append_event(
        "postmortem",
        {"tool_name": tool_name, "task_id": task_id, "expected": expected, "actual": actual, "deviation": deviation},
    )
    logger.warning(
        "world_checkpoint postmortem: tool=%s task_id=%s deviation=%.2f",
        tool_name,
        task_id,
        deviation,
    )


def deviation(expected: float, actual: float) -> float:
    """计算相对偏差 (actual - expected) / expected；expected=0 时返回 0。"""
    if expected == 0:
        return 0.0
    return (actual - expected) / expected


async def run_checkpoint(
    tool_name: str,
    params: dict[str, Any],
    result: dict[str, Any],
    task_id: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    执行一次校验：根据 limb 配置的 checkpoint 名调用校验器，计算偏差；
    若超过阈值则写复盘并返回 triggered=True。
    返回 { "deviation": float, "triggered": bool, "actual": number | None, "expected": number | None }。
    """
    config = config or load_config()
    limb = get_limb_config(config, tool_name)
    if not limb:
        return {"deviation": 0.0, "triggered": False}
    checkpoint_name = limb.get("checkpoint")
    if not checkpoint_name:
        return {"deviation": 0.0, "triggered": False}
    validator = _validators.get(checkpoint_name)
    if not validator:
        logger.debug("no validator for checkpoint %s", checkpoint_name)
        return {"deviation": 0.0, "triggered": False}
    try:
        out = validator(tool_name, params, result)
    except Exception as e:
        logger.exception("checkpoint validator failed: %s", e)
        return {"deviation": 0.0, "triggered": False}
    if not out or "actual" not in out or "expected" not in out:
        return {"deviation": 0.0, "triggered": False}
    expected = float(out["expected"])
    actual = float(out["actual"])
    deviation_val = deviation(expected, actual)
    cfg = config.get("checkpoint") or {}
    threshold = float(cfg.get("threshold") or 0.5)
    triggered = abs(deviation_val) > threshold
    if triggered:
        _write_postmortem(
            tool_name,
            task_id,
            expected,
            actual,
            deviation_val,
            params,
            result,
        )
    return {
        "deviation": deviation_val,
        "triggered": triggered,
        "actual": actual,
        "expected": expected,
    }


def schedule_checkpoint(
    tool_name: str,
    params: dict[str, Any],
    result: dict[str, Any],
    task_id: str,
    config: dict[str, Any] | None = None,
) -> None:
    """
    延时调度一次 World Checkpoint：在 delay_seconds 后执行 run_checkpoint。
    不阻塞；在后台 asyncio.create_task 中执行。
    """
    config = config or load_config()
    cfg = config.get("checkpoint") or {}
    delay = float(cfg.get("delay_seconds") or 0)
    if delay <= 0:
        asyncio.create_task(
            run_checkpoint(tool_name, params, result, task_id, config)
        )
        return

    async def _delayed() -> None:
        await asyncio.sleep(delay)
        await run_checkpoint(tool_name, params, result, task_id, config)

    asyncio.create_task(_delayed())


def _content_stub_validator(
    tool_name: str,
    params: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Stub 校验器：从 params.expectedWorldState 取期望值，从 result.mock_actual 取实际值。
    用于测试或占位；生产可替换为真实 API 拉取（如粉丝数）。
    """
    expected = params.get("expectedWorldState")
    if expected is None:
        return None
    try:
        expected_f = float(expected)
    except (TypeError, ValueError):
        return None
    actual = result.get("mock_actual", expected_f)
    try:
        actual_f = float(actual)
    except (TypeError, ValueError):
        return None
    return {"expected": expected_f, "actual": actual_f}


# 注册 stub 校验器，供 limb 配置 checkpoint: content_stub 使用
register_validator("content_stub", _content_stub_validator)
