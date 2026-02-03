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
    assert "run_count" in data
    assert "run_count_by_limb" in data
    assert "run_count_by_channel" in data
    assert isinstance(data["events_count"], int)
    assert isinstance(data["run_count"], int)
    assert isinstance(data["run_count_by_limb"], dict)
    assert isinstance(data["run_count_by_channel"], dict)
    assert data["postmortem_last_24h"] <= data["postmortem_total"]


@pytest.mark.asyncio
async def test_get_convergence_suggestions(app) -> None:
    """GET /convergence/suggestions 返回 200 与 suggestions 列表（可收敛占位）。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r = await client.get("/convergence/suggestions")
    assert r.status_code == 200
    data = r.json()
    assert "suggestions" in data
    assert isinstance(data["suggestions"], list)


@pytest.mark.asyncio
async def test_app_with_alert_webhook_config() -> None:
    """含 checkpoint.alert_webhook_url 的 config 下 app 正常响应。"""
    from claw_assistant.server.app import create_app

    from tests.conftest import TEST_CONFIG

    config = {**TEST_CONFIG, "checkpoint": {**TEST_CONFIG["checkpoint"], "alert_webhook_url": "http://example.com/webhook"}}
    app = create_app(config=config)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r = await client.get("/metrics")
    assert r.status_code == 200
    assert "run_count" in r.json()


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
async def test_get_events_filter_by_task_id(app) -> None:
    """GET /events?task_id=xxx 仅返回该 task 的事件，用于单任务回放。"""
    from claw_assistant.governance.events import clear_events

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
        r_all = await client.get("/events")
    assert r_all.status_code == 200
    events_all = r_all.json().get("events", [])
    task_ids = [e.get("payload", {}).get("task_id") for e in events_all if e.get("payload", {}).get("task_id")]
    assert task_ids, "events should contain at least one task_id"
    target = task_ids[0]
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r_filtered = await client.get("/events", params={"task_id": target})
    assert r_filtered.status_code == 200
    events_filtered = r_filtered.json().get("events", [])
    assert all(e.get("payload", {}).get("task_id") == target for e in events_filtered)
    assert len(events_filtered) <= len(events_all)


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


# ---------- OpenClaw 治理桥（Phase 4）----------
@pytest.mark.asyncio
async def test_governance_before_tool_call_allow(app) -> None:
    """POST /governance/before_tool_call 对不需审批的 limb（ops）直接放行。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r = await client.post(
            "/governance/before_tool_call",
            json={"toolName": "ops", "params": {"summary": "部署"}, "agentId": "main"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data.get("block") is False
    assert "params" in data


@pytest.mark.asyncio
async def test_governance_before_tool_call_constitution_block() -> None:
    """宪法 forbid 该工具时 before_tool_call 返回 block true。"""
    from claw_assistant.server.app import create_app

    from tests.conftest import TEST_CONFIG

    config = {**TEST_CONFIG.copy(), "constitution": {"forbid": ["content"], "allow": [], "restrict": [], "intent_deviation": {"enabled": False}}}
    app = create_app(config=config)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r = await client.post(
            "/governance/before_tool_call",
            json={"toolName": "content", "params": {"summary": "发布"}, "agentId": "main"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data.get("block") is True
    assert "constitution" in (data.get("blockReason") or "").lower()


@pytest.mark.asyncio
async def test_governance_before_tool_call_content_approve_flow(app) -> None:
    """POST /governance/before_tool_call 对 content（需审批）挂起 → approve 解挂 → 返回放行。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        loop = asyncio.get_running_loop()
        before_future = loop.create_future()

        async def do_before() -> None:
            r = await client.post(
                "/governance/before_tool_call",
                json={"toolName": "content", "params": {"summary": "发布测试"}, "agentId": "main"},
            )
            before_future.set_result(r)

        asyncio.create_task(do_before())
        await asyncio.sleep(0.2)
        r_status = await client.get("/status")
        assert r_status.status_code == 200
        pending = r_status.json().get("pending", [])
        assert len(pending) >= 1
        approval_id = pending[0]["approval_id"]
        r_approve = await client.post("/approve", json={"approval_id": approval_id})
        assert r_approve.status_code == 200
        r_before = await asyncio.wait_for(before_future, timeout=5.0)
        assert r_before.status_code == 200
        body = r_before.json()
        assert body.get("block") is False
        assert "params" in body


@pytest.mark.asyncio
async def test_governance_after_tool_call(app) -> None:
    """POST /governance/after_tool_call 写 limb_executed 事件并调度 checkpoint。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r = await client.post(
            "/governance/after_tool_call",
            json={
                "toolName": "ops",
                "params": {"summary": "部署"},
                "result": {"ok": True},
                "agentId": "main",
                "toolCallId": "call-123",
            },
        )
        assert r.status_code == 200
        r_events = await client.get("/events", params={"limit": 20})
    assert r_events.status_code == 200
    events = r_events.json().get("events", [])
    limb_evts = [e for e in events if e.get("type") == "limb_executed" and e.get("payload", {}).get("task_id") == "call-123"]
    assert len(limb_evts) >= 1
    assert limb_evts[0]["payload"].get("source") == "openclaw"
    assert limb_evts[0]["payload"].get("tool_name") == "ops"


# ---------- 目标池（Phase 4 方向 B：目标入口小步）----------
@pytest.mark.asyncio
async def test_goals_api_post_and_list(app) -> None:
    """POST /goals 新增目标，GET /goals 返回列表（含新项）。"""
    from claw_assistant.goals import clear_goals

    clear_goals()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r = await client.post("/goals", json={"text": "本周完成内容发布"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("text") == "本周完成内容发布"
    assert data.get("status") == "pending"
    assert "id" in data
    assert "created_at" in data
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r2 = await client.get("/goals")
    assert r2.status_code == 200
    goals = r2.json().get("goals", [])
    assert any(g.get("text") == "本周完成内容发布" for g in goals)


@pytest.mark.asyncio
async def test_goals_api_patch_status(app) -> None:
    """PATCH /goals/:id 更新状态，GET /goals?status=done 可过滤。"""
    from claw_assistant.goals import clear_goals

    clear_goals()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r = await client.post("/goals", json={"text": "目标A"})
        assert r.status_code == 200
        goal_id = r.json()["id"]
        rp = await client.patch(f"/goals/{goal_id}", json={"status": "done"})
        assert rp.status_code == 200
        r2 = await client.get("/goals", params={"status": "done"})
    assert r2.status_code == 200
    done_list = r2.json().get("goals", [])
    assert len(done_list) >= 1
    assert any(g.get("id") == goal_id and g.get("status") == "done" for g in done_list)


@pytest.mark.asyncio
async def test_goals_api_get_intents(app) -> None:
    """GET /goals/:id/intents 返回该目标拆解出的 intent 列表（占位：单条=目标原文）。"""
    from claw_assistant.goals import clear_goals

    clear_goals()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r = await client.post("/goals", json={"text": "本周发布三条内容"})
        assert r.status_code == 200
        goal_id = r.json()["id"]
        r2 = await client.get(f"/goals/{goal_id}/intents")
    assert r2.status_code == 200
    data = r2.json()
    assert "intents" in data
    assert data["intents"] == ["本周发布三条内容"]


@pytest.mark.asyncio
async def test_goals_api_get_intents_404(app) -> None:
    """GET /goals/:id/intents 对不存在的 goal 返回 404。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
        r = await client.get("/goals/no-such-id/intents")
    assert r.status_code == 404
