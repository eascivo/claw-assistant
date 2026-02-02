"""端到端集成测试：run → status → approve → 校验结果。app 使用 tests/conftest.py 注入的 TEST_CONFIG。"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_get_health(app) -> None:
    """GET /health 返回 200 与 status ok，供负载均衡/监控探测。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r = await client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


@pytest.mark.asyncio
async def test_get_metrics(app) -> None:
    """GET /metrics 返回基础指标：postmortem_total、pending_count、postmortem_last_24h。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r = await client.get("/metrics")
    assert r.status_code == 200
    data = r.json()
    assert "postmortem_total" in data
    assert "postmortem_last_24h" in data
    assert "pending_count" in data
    assert isinstance(data["postmortem_total"], int)
    assert isinstance(data["postmortem_last_24h"], int)
    assert isinstance(data["pending_count"], int)
    assert "events_count" in data
    assert isinstance(data["events_count"], int)
    assert data["postmortem_last_24h"] <= data["postmortem_total"]


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


@pytest.mark.asyncio
async def test_run_tool_ops(app) -> None:
    """POST /run tool=ops 时路由到 ops limb，免审批即返回。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r = await client.post("/run", json={"intent": "部署测试", "channel": "experimental", "tool": "ops"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("result", {}).get("limb") == "ops"


@pytest.mark.asyncio
async def test_run_tool_notify(app) -> None:
    """POST /run tool=notify 时路由到 notify limb，免审批即返回。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r = await client.post("/run", json={"intent": "通知用户", "channel": "experimental", "tool": "notify"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("result", {}).get("limb") == "notify"


@pytest.mark.asyncio
async def test_run_tool_inferred_from_intent() -> None:
    """未传 tool 时按 config.intent_tool_map 从 intent 推断 limb。"""
    from tests.conftest import TEST_CONFIG

    config = {
        **TEST_CONFIG.copy(),
        "intent_tool_map": [
            {"pattern": r"发布|推送", "tool": "content"},
            {"pattern": r"部署|运维", "tool": "ops"},
            {"pattern": r"通知|提醒", "tool": "notify"},
        ],
    }
    from claw_assistant.server.app import create_app

    app = create_app(config=config)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r = await client.post("/run", json={"intent": "部署到生产", "channel": "experimental"})
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        assert body.get("result", {}).get("limb") == "ops"
        r2 = await client.post("/run", json={"intent": "提醒管理员", "channel": "experimental"})
        assert r2.status_code == 200
        assert r2.json().get("result", {}).get("limb") == "notify"


@pytest.mark.asyncio
async def test_get_postmortems_returns_summary(app) -> None:
    """GET /postmortems 返回 postmortems 与 summary（含 total），供收益指标/告警用。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r = await client.get("/postmortems")
    assert r.status_code == 200
    data = r.json()
    assert "postmortems" in data
    assert "summary" in data
    assert "total" in data["summary"]
    assert "last_24h" in data["summary"]
    assert isinstance(data["summary"]["total"], int)
    assert isinstance(data["summary"]["last_24h"], int)
    assert data["summary"]["total"] == len(data["postmortems"])
    assert data["summary"]["last_24h"] <= data["summary"]["total"]


@pytest.mark.asyncio
async def test_get_postmortems_summary_alert_when_over_threshold() -> None:
    """当 config.checkpoint.alert_after_postmortem_count 存在且 total >= 阈值时，summary.alert 为 true。"""
    from tests.conftest import TEST_CONFIG

    config = {
        **TEST_CONFIG.copy(),
        "checkpoint": {"threshold": 0.5, "delay_seconds": 0, "alert_after_postmortem_count": 0},
    }
    from claw_assistant.server.app import create_app

    app = create_app(config=config)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r = await client.get("/postmortems")
    assert r.status_code == 200
    data = r.json()
    assert data["summary"]["total"] >= 0
    assert "alert_threshold" in data["summary"]
    assert data["summary"]["alert_threshold"] == 0
    assert data["summary"]["alert"] is True
