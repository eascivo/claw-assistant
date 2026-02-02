"""ApprovalManager 单元测试。"""

import asyncio
import pytest
from claw_assistant.governance.approval import ApprovalManager, PendingApproval


@pytest.mark.asyncio
async def test_register_and_list_pending() -> None:
    manager = ApprovalManager()
    p = await manager.register(
        session_key="s1",
        tool_name="content",
        params={"summary": "发布一条测试"},
        risk="low",
    )
    assert p.approval_id
    assert p.tool_name == "content"
    assert p.summary == "发布一条测试"
    pending = await manager.list_pending()
    assert len(pending) == 1
    assert pending[0]["approval_id"] == p.approval_id


@pytest.mark.asyncio
async def test_resolve_approve() -> None:
    manager = ApprovalManager()
    p = await manager.register(None, "content", {"summary": "test"}, risk=None)
    aid = p.approval_id

    async def resolve_later() -> None:
        await asyncio.sleep(0.05)
        await manager.resolve(aid, "approve")

    asyncio.create_task(resolve_later())
    decision = await manager.wait(aid, timeout=1.0)
    assert decision == "approve"
    pending = await manager.list_pending()
    assert len(pending) == 0


@pytest.mark.asyncio
async def test_resolve_reject() -> None:
    manager = ApprovalManager()
    p = await manager.register(None, "content", {"summary": "test"})
    aid = p.approval_id

    async def resolve_later() -> None:
        await asyncio.sleep(0.05)
        await manager.resolve(aid, "reject")

    asyncio.create_task(resolve_later())
    decision = await manager.wait(aid, timeout=1.0)
    assert decision == "reject"


@pytest.mark.asyncio
async def test_resolve_unknown_id_returns_false() -> None:
    manager = ApprovalManager()
    ok = await manager.resolve("nonexistent-id", "approve")
    assert ok is False


@pytest.mark.asyncio
async def test_wait_unknown_id_returns_reject() -> None:
    manager = ApprovalManager()
    decision = await manager.wait("nonexistent-id", timeout=0.1)
    assert decision == "reject"
