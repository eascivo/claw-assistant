"""端到端集成测试：run → status → approve → 校验结果。"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from claw_assistant.server.app import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_run_then_approve_flow(app) -> None:
    """POST /run 挂起 → GET /status 有记录 → POST /approve 解挂 → /run 返回成功。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        loop = asyncio.get_running_loop()
        run_future = loop.create_future()

        async def do_run() -> None:
            r = await client.post("/run", json={"intent": "发布一条测试"})
            run_future.set_result(r)

        asyncio.create_task(do_run())
        # 等一小段时间让 run 内部 register 审批
        await asyncio.sleep(0.2)
        # 取待审批
        r_status = await client.get("/status")
        assert r_status.status_code == 200
        data = r_status.json()
        pending = data.get("pending", [])
        assert len(pending) >= 1
        approval_id = pending[0]["approval_id"]
        # 通过审批
        r_approve = await client.post("/approve", json={"approval_id": approval_id})
        assert r_approve.status_code == 200
        # 等待 run 完成
        r_run = await asyncio.wait_for(run_future, timeout=5.0)
        assert r_run.status_code == 200
        body = r_run.json()
        assert body.get("ok") is True
        assert body.get("result", {}).get("limb") == "content"


@pytest.mark.asyncio
async def test_run_then_reject_flow(app) -> None:
    """POST /run 挂起 → POST /reject → run 返回失败。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        loop = asyncio.get_running_loop()
        run_future = loop.create_future()

        async def do_run() -> None:
            r = await client.post("/run", json={"intent": "发布一条测试"})
            run_future.set_result(r)

        asyncio.create_task(do_run())
        await asyncio.sleep(0.2)
        r_status = await client.get("/status")
        assert r_status.status_code == 200
        pending = r_status.json().get("pending", [])
        assert len(pending) >= 1
        approval_id = pending[0]["approval_id"]
        r_reject = await client.post("/reject", json={"approval_id": approval_id})
        assert r_reject.status_code == 200
        r_run = await asyncio.wait_for(run_future, timeout=5.0)
        assert r_run.status_code == 200, r_run.text
        body = r_run.json()
        assert body.get("ok") is False
        assert "rejected" in body.get("error", "").lower()


@pytest.mark.asyncio
async def test_events_api_after_run(app) -> None:
    """run → approve 后 GET /events 包含 approval_requested / approval_resolved / limb_executed。"""
    from claw_assistant.governance.events import clear_events, get_events

    clear_events()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        loop = asyncio.get_running_loop()
        run_future = loop.create_future()

        async def do_run() -> None:
            r = await client.post("/run", json={"intent": "发布一条测试"})
            run_future.set_result(r)

        asyncio.create_task(do_run())
        await asyncio.sleep(0.2)
        pending = (await client.get("/status")).json().get("pending", [])
        assert len(pending) >= 1
        await client.post("/approve", json={"approval_id": pending[0]["approval_id"]})
        await asyncio.wait_for(run_future, timeout=5.0)
        r_events = await client.get("/events")
    assert r_events.status_code == 200
    events = r_events.json().get("events", [])
    types = [e["type"] for e in events]
    assert "approval_requested" in types
    assert "approval_resolved" in types
    assert "limb_executed" in types


@pytest.mark.asyncio
async def test_run_experimental_no_approval_when_skip(app) -> None:
    """experimental 免审批：channels.experimental.require_approval=false（默认）时单次 POST 即返回成功，事件含 channel。"""
    from claw_assistant.governance.events import clear_events, get_events

    clear_events()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r = await client.post("/run", json={"intent": "影子免审批", "channel": "experimental"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("result", {}).get("channel") == "experimental"
    events = get_events()
    limb_events = [e for e in events if e.get("type") == "limb_executed" and e.get("payload", {}).get("channel") == "experimental"]
    assert len(limb_events) >= 1
