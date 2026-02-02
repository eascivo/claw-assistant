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
