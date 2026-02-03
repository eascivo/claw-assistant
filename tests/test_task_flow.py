"""任务流单元测试。"""

import asyncio
import pytest
from claw_assistant.governance.approval import ApprovalManager
from claw_assistant.governance.task_flow import run_task_flow


@pytest.fixture
def config_no_approval() -> dict:
    return {
        "limbs": {
            "content": {
                "require_approval": False,
                "priority": 5,
            }
        }
    }


@pytest.fixture
def config_require_approval() -> dict:
    return {
        "limbs": {
            "content": {
                "require_approval": True,
                "priority": 5,
            }
        }
    }


@pytest.mark.asyncio
async def test_run_task_flow_no_approval(config_no_approval: dict) -> None:
    manager = ApprovalManager()
    out = await run_task_flow("发布一条测试", manager, config=config_no_approval)
    assert out.get("ok") is True
    assert "result" in out
    assert out["result"].get("limb") == "content"
    assert out["result"].get("summary") == "发布一条测试"


@pytest.mark.asyncio
async def test_run_task_flow_tool_ops(config_no_approval: dict) -> None:
    """多 Limb：tool_name=ops 时路由到 ops limb。"""
    config = {**config_no_approval, "limbs": {"content": {"require_approval": False}, "ops": {"require_approval": False}}}
    manager = ApprovalManager()
    out = await run_task_flow("部署测试", manager, config=config, tool_name="ops")
    assert out.get("ok") is True
    assert out["result"].get("limb") == "ops"
    assert out["result"].get("summary") == "部署测试"


@pytest.mark.asyncio
async def test_run_task_flow_tool_notify(config_no_approval: dict) -> None:
    """多 Limb：tool_name=notify 时路由到 notify limb。"""
    config = {
        **config_no_approval,
        "limbs": {
            "content": {"require_approval": False},
            "ops": {"require_approval": False},
            "notify": {"require_approval": False},
        },
    }
    manager = ApprovalManager()
    out = await run_task_flow("通知用户", manager, config=config, tool_name="notify")
    assert out.get("ok") is True
    assert out["result"].get("limb") == "notify"
    assert out["result"].get("summary") == "通知用户"


@pytest.mark.asyncio
async def test_run_task_flow_tool_inferred_from_intent(config_no_approval: dict) -> None:
    """未传 tool_name 时按 config.intent_tool_map 从 intent 推断 limb。"""
    config = {
        **config_no_approval,
        "limbs": {
            "content": {"require_approval": False},
            "ops": {"require_approval": False},
            "notify": {"require_approval": False},
        },
        "intent_tool_map": [
            {"pattern": r"发布|推送", "tool": "content"},
            {"pattern": r"部署|运维", "tool": "ops"},
            {"pattern": r"通知|提醒", "tool": "notify"},
        ],
    }
    manager = ApprovalManager()
    out = await run_task_flow("部署到生产环境", manager, config=config, tool_name=None)
    assert out.get("ok") is True
    assert out["result"].get("limb") == "ops"
    out2 = await run_task_flow("发布一条测试", manager, config=config, tool_name=None)
    assert out2.get("ok") is True
    assert out2["result"].get("limb") == "content"
    out3 = await run_task_flow("通知用户上线", manager, config=config, tool_name=None)
    assert out3.get("ok") is True
    assert out3["result"].get("limb") == "notify"


@pytest.mark.asyncio
async def test_run_task_flow_unknown_limb(config_no_approval: dict) -> None:
    """多 Limb：未知 tool_name 返回 error。"""
    manager = ApprovalManager()
    out = await run_task_flow("x", manager, config=config_no_approval, tool_name="unknown_limb")
    assert out.get("ok") is False
    assert "unknown limb" in out.get("error", "").lower()


@pytest.mark.asyncio
async def test_run_task_flow_channel_experimental(config_no_approval: dict) -> None:
    """Brain-B 影子：channel=experimental 时结果与事件带 channel 标记。"""
    from claw_assistant.governance.events import clear_events, get_events

    clear_events()
    manager = ApprovalManager()
    out = await run_task_flow(
        "影子测试",
        manager,
        config=config_no_approval,
        channel="experimental",
    )
    assert out.get("ok") is True
    assert out["result"].get("channel") == "experimental"
    events = get_events()
    limb_events = [e for e in events if e.get("type") == "limb_executed"]
    assert len(limb_events) >= 1
    assert limb_events[-1]["payload"].get("channel") == "experimental"


@pytest.mark.asyncio
async def test_run_task_flow_experimental_skip_approval(config_require_approval: dict) -> None:
    """experimental 免审批：limb 需审批但 channel=experimental 且 channels.experimental.require_approval=false 时不挂起。"""
    config = {**config_require_approval, "channels": {"experimental": {"require_approval": False}}}
    manager = ApprovalManager()
    out = await run_task_flow("影子测试", manager, config=config, channel="experimental")
    assert out.get("ok") is True
    assert out["result"].get("channel") == "experimental"
    pending = await manager.list_pending()
    assert len(pending) == 0


@pytest.mark.asyncio
async def test_run_task_flow_require_approval_then_approve(config_require_approval: dict) -> None:
    manager = ApprovalManager()

    async def approve_soon() -> None:
        await asyncio.sleep(0.1)
        pending = await manager.list_pending()
        if pending:
            await manager.resolve(pending[0]["approval_id"], "approve")

    asyncio.create_task(approve_soon())
    out = await run_task_flow("发布一条测试", manager, config=config_require_approval)
    assert out.get("ok") is True
    assert out["result"].get("limb") == "content"


@pytest.mark.asyncio
async def test_run_task_flow_constitution_block() -> None:
    """Constitution forbid 时直接返回 block_reason。"""
    manager = ApprovalManager()
    config = {
        "constitution": {"forbid": ["content"], "allow": [], "restrict": []},
        "limbs": {"content": {"require_approval": False}},
    }
    out = await run_task_flow("发布一条测试", manager, config=config)
    assert out.get("ok") is False
    assert out.get("block_reason") == "constitution"


@pytest.mark.asyncio
async def test_run_task_flow_intent_deviation_block(config_no_approval: dict) -> None:
    """Constitution intent_deviation 启用且 stub_score > threshold 时拦截。"""
    config = {
        **config_no_approval,
        "constitution": {
            "forbid": [],
            "restrict": [],
            "intent_deviation": {"enabled": True, "threshold": 0.5, "stub_score": 1.0},
        },
    }
    manager = ApprovalManager()
    out = await run_task_flow("发布一条测试", manager, config=config)
    assert out.get("ok") is False
    assert out.get("block_reason") == "constitution"


@pytest.mark.asyncio
async def test_run_task_flow_require_approval_then_reject(config_require_approval: dict) -> None:
    manager = ApprovalManager()

    async def reject_soon() -> None:
        await asyncio.sleep(0.1)
        pending = await manager.list_pending()
        if pending:
            await manager.resolve(pending[0]["approval_id"], "reject")

    asyncio.create_task(reject_soon())
    out = await run_task_flow("发布一条测试", manager, config=config_require_approval)
    assert out.get("ok") is False
    assert "rejected" in out.get("error", "").lower()


@pytest.mark.asyncio
async def test_run_task_flow_approval_only_critical_true_skips_non_critical(config_no_approval: dict) -> None:
    """审批策略收紧：approval_only_critical=True 时仅 limb require_approval 的挂起，其余自动放行。"""
    config = {**config_no_approval, "governance": {"approval_only_critical": True}}
    manager = ApprovalManager()
    out = await run_task_flow("发布一条测试", manager, config=config)
    assert out.get("ok") is True
    assert out["result"].get("limb") == "content"
    assert len(await manager.list_pending()) == 0


@pytest.mark.asyncio
async def test_run_task_flow_approval_only_critical_false_requires_all(config_no_approval: dict) -> None:
    """审批策略：approval_only_critical=False 时该 channel 下所有 limb 均挂起（更严格）。"""
    config = {
        **config_no_approval,
        "governance": {"approval_only_critical": False},
        "channels": {"main": {"require_approval": True}, "experimental": {"require_approval": False}},
    }
    manager = ApprovalManager()

    async def approve_soon() -> None:
        await asyncio.sleep(0.1)
        pending = await manager.list_pending()
        if pending:
            await manager.resolve(pending[0]["approval_id"], "approve")

    asyncio.create_task(approve_soon())
    out = await run_task_flow("发布一条测试", manager, config=config, channel="main")
    assert out.get("ok") is True
    assert out["result"].get("limb") == "content"
