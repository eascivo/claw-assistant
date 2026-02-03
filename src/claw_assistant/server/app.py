"""FastAPI：POST /run, GET /status, POST /approve, POST /reject；内部调 governance + limbs。"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from claw_assistant.config import (
    get_channel_config,
    get_governance_config,
    get_limb_config,
    get_channel_from_agent_id,
    load_config,
    resolve_limb_from_openclaw_tool,
    resolve_tool_from_intent,
)
from claw_assistant.governance.approval import ApprovalManager
from claw_assistant.governance.checkpoint import get_postmortems, load_postmortems_from_file_into_memory, schedule_checkpoint
from claw_assistant.governance.convergence import get_convergence_suggestions
from claw_assistant.governance.events import (
    append_event,
    get_events,
    get_events_count,
    get_run_count,
    get_run_count_by_limb,
    get_run_count_by_channel,
)
from claw_assistant.goals import (
    add_goal as goals_add_goal,
    expand_goal_to_intents as goals_expand_to_intents,
    get_goal as goals_get_goal,
    list_goals as goals_list_goals,
    update_goal_status as goals_update_status,
)
from claw_assistant.governance.hooks import before_tool_call as governance_before_tool_call
from claw_assistant.governance.task_flow import run_task_flow
from claw_assistant.im.notifier import get_notifier


def create_app(config: dict[str, Any] | None = None) -> FastAPI:
    """创建 FastAPI 应用；config 非空时作为注入配置（测试用），否则从 load_config() 读取。"""
    approval_manager = ApprovalManager()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # 可选：启动时从 JSONL 加载复盘到内存（config.checkpoint.postmortem_sink=file 时）
        run_config = getattr(_app.state, "config", None) or load_config()
        if (run_config.get("checkpoint") or {}).get("postmortem_sink") == "file":
            n = load_postmortems_from_file_into_memory(run_config)
            if n:
                import logging
                logging.getLogger(__name__).info("postmortems loaded from file: %d", n)
        yield
        # 可在此做清理

    app = FastAPI(title="claw-assistant", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.approval_manager = approval_manager
    if config is not None:
        app.state.config = config

    class RunBody(BaseModel):
        intent: str
        channel: str = "main"  # main | experimental（Brain-B 影子）
        tool: str | None = None  # 路由到的 limb；省略时按 config.intent_tool_map 从 intent 推断

    @app.get("/health")
    async def api_health() -> dict[str, Any]:
        """健康检查，供负载均衡/监控探测。"""
        return {"status": "ok"}

    @app.get("/metrics")
    async def api_metrics() -> dict[str, Any]:
        """基础指标，供监控/可观测；含 postmortem_total、pending_count、postmortem_last_24h、events_count、run_count、run_count_by_limb、run_count_by_channel。"""
        import time

        run_config = getattr(app.state, "config", None) or load_config()
        postmortems = get_postmortems(run_config)
        total = len(postmortems)
        now = time.time()
        cutoff_24h = now - 86400.0
        last_24h = sum(1 for e in postmortems if e.get("created_at", 0) >= cutoff_24h)
        manager: ApprovalManager = app.state.approval_manager
        pending = await manager.list_pending()
        return {
            "postmortem_total": total,
            "postmortem_last_24h": last_24h,
            "pending_count": len(pending),
            "events_count": get_events_count(),
            "run_count": get_run_count(),
            "run_count_by_limb": get_run_count_by_limb(),
            "run_count_by_channel": get_run_count_by_channel(),
        }

    @app.post("/run")
    async def api_run(body: RunBody) -> dict[str, Any]:
        """发起一次任务流；若需审批会挂起直到 approve/reject。channel=experimental 为 Brain-B 影子；tool 省略时按 intent 推断 limb。"""
        manager: ApprovalManager = app.state.approval_manager
        run_config = getattr(app.state, "config", None) or load_config()
        tool_name = body.tool if (body.tool is not None and body.tool.strip() != "") else None
        out = await run_task_flow(
            body.intent,
            approval_manager=manager,
            config=run_config,
            session_key=None,
            channel=body.channel,
            tool_name=tool_name,
        )
        if not out.get("ok") and "block_reason" in out:
            raise HTTPException(status_code=403, detail=out)
        return out

    @app.get("/status")
    async def api_status() -> dict[str, Any]:
        """列出当前待审批。"""
        manager: ApprovalManager = app.state.approval_manager
        pending = await manager.list_pending()
        return {"pending": pending}

    @app.get("/postmortems")
    async def api_postmortems() -> dict[str, Any]:
        """列出 World Checkpoint 触发的复盘记录（内存 + 可选 JSONL 文件合并）；summary 含 total、last_24h 与可选告警。"""
        import time

        run_config = getattr(app.state, "config", None) or load_config()
        postmortems = get_postmortems(run_config)
        total = len(postmortems)
        now = time.time()
        cutoff_24h = now - 86400.0
        last_24h = sum(1 for e in postmortems if e.get("created_at", 0) >= cutoff_24h)
        summary: dict[str, Any] = {"total": total, "last_24h": last_24h}
        cfg = run_config.get("checkpoint") or {}
        threshold = cfg.get("alert_after_postmortem_count")
        if threshold is not None:
            try:
                n = int(threshold)
                summary["alert_threshold"] = n
                summary["alert"] = total >= n
            except (TypeError, ValueError):
                pass
        return {"postmortems": postmortems, "summary": summary}

    @app.get("/events")
    async def api_events(
        since_ts: float | None = None,
        limit: int = 200,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """时间轴事件：approval_requested / approval_resolved / limb_executed / postmortem。task_id 可选，用于单任务回放。"""
        events = get_events(since_ts=since_ts, limit=limit, task_id=task_id)
        return {"events": events}

    @app.get("/convergence/suggestions")
    async def api_convergence_suggestions() -> dict[str, Any]:
        """可收敛占位：根据复盘与告警配置返回建议列表；供 Dashboard 展示或人工决策，后续可扩展自动调参。"""
        run_config = getattr(app.state, "config", None) or load_config()
        postmortems = get_postmortems(run_config)
        suggestions = get_convergence_suggestions(postmortems, run_config)
        return {"suggestions": suggestions}

    # ---------- 目标池（Phase 4 方向 B：目标入口小步）----------
    class GoalBody(BaseModel):
        text: str

    @app.post("/goals")
    async def api_goals_post(body: GoalBody) -> dict[str, Any]:
        """新增一条目标；返回 { id, text, status, created_at }。"""
        g = goals_add_goal(body.text)
        return g

    @app.get("/goals")
    async def api_goals_list(status: str | None = None) -> dict[str, Any]:
        """目标列表；可选 status 过滤（pending / done / cancelled）。按创建时间倒序。"""
        goals = goals_list_goals(status=status)
        return {"goals": goals}

    class GoalStatusBody(BaseModel):
        status: str  # done | cancelled

    @app.patch("/goals/{goal_id}")
    async def api_goals_patch(goal_id: str, body: GoalStatusBody) -> dict[str, Any]:
        """更新目标状态（done / cancelled）。"""
        ok = goals_update_status(goal_id, body.status)
        if not ok:
            raise HTTPException(status_code=404, detail="goal not found")
        return {"ok": True}

    @app.get("/goals/{goal_id}/intents")
    async def api_goals_intents(goal_id: str) -> dict[str, Any]:
        """将目标拆解为 intent 列表（占位：当前返回单条 = 目标原文）。供定时/手动调用后对每条 intent 调 POST /run。"""
        goal = goals_get_goal(goal_id)
        if not goal:
            raise HTTPException(status_code=404, detail="goal not found")
        intents = goals_expand_to_intents(goal.get("text", ""))
        return {"intents": intents}

    class ApproveBody(BaseModel):
        approval_id: str

    @app.post("/approve")
    async def api_approve(body: ApproveBody) -> dict[str, Any]:
        """解挂：通过审批。"""
        manager: ApprovalManager = app.state.approval_manager
        ok = await manager.resolve(body.approval_id, "approve")
        if not ok:
            raise HTTPException(status_code=404, detail="approval not found")
        return {"ok": True, "decision": "approve"}

    @app.post("/reject")
    async def api_reject(body: ApproveBody) -> dict[str, Any]:
        """解挂：拒绝审批。"""
        manager: ApprovalManager = app.state.approval_manager
        ok = await manager.resolve(body.approval_id, "reject")
        if not ok:
            raise HTTPException(status_code=404, detail="approval not found")
        return {"ok": True, "decision": "reject"}

    # ---------- OpenClaw 治理桥（Phase 4 最小形态）----------
    class GovernanceBeforeToolCallBody(BaseModel):
        toolName: str
        params: dict[str, Any] = {}
        sessionKey: str | None = None
        agentId: str | None = None
        toolCallId: str | None = None

    class GovernanceAfterToolCallBody(BaseModel):
        toolName: str
        params: dict[str, Any] = {}
        result: dict[str, Any] | None = None
        error: str | None = None
        durationMs: float | None = None
        sessionKey: str | None = None
        agentId: str | None = None
        toolCallId: str | None = None

    @app.post("/governance/before_tool_call")
    async def api_governance_before_tool_call(body: GovernanceBeforeToolCallBody) -> dict[str, Any]:
        """
        OpenClaw Plugin 调用：宪法检查；若该 limb 需审批则挂起直到 approve/reject，再返回。
        返回 { block: bool, blockReason?: string, params?: object }。
        """
        import uuid

        run_config = getattr(app.state, "config", None) or load_config()
        manager: ApprovalManager = app.state.approval_manager
        limb_name = resolve_limb_from_openclaw_tool(body.toolName, run_config)
        channel = get_channel_from_agent_id(body.agentId, run_config)
        params = dict(body.params) if body.params else {}
        if "summary" not in params and body.params:
            params.setdefault("summary", str(body.params)[:200])

        block, block_reason, modified_params = governance_before_tool_call(limb_name, params, run_config)
        if block:
            return {"block": True, "blockReason": block_reason or "constitution"}

        limb_cfg = get_limb_config(run_config, limb_name)
        channel_cfg = get_channel_config(run_config, channel)
        governance = get_governance_config(run_config)
        channel_requires_approval = channel_cfg.get("require_approval", channel == "main")
        limb_is_critical = limb_cfg and limb_cfg.get("require_approval")
        need_approval = channel_requires_approval and (
            limb_is_critical if governance.get("approval_only_critical", True) else True
        )
        if need_approval:
            task_id = str(uuid.uuid4())
            pending = await manager.register(
                session_key=body.sessionKey,
                tool_name=limb_name,
                params=modified_params,
                task_id=task_id,
                risk=limb_cfg.get("risk") if limb_cfg else None,
            )
            get_notifier(run_config).send_approval_request(**pending.to_public())
            decision = await manager.wait(pending.approval_id)
            if decision == "reject":
                return {"block": True, "blockReason": "rejected by human"}

        return {"block": False, "params": modified_params}

    @app.post("/governance/after_tool_call")
    async def api_governance_after_tool_call(body: GovernanceAfterToolCallBody) -> dict[str, Any]:
        """
        OpenClaw Plugin 调用：写 limb_executed 事件、调度 World Checkpoint；不阻塞。
        """
        import uuid

        run_config = getattr(app.state, "config", None) or load_config()
        limb_name = resolve_limb_from_openclaw_tool(body.toolName, run_config)
        channel = get_channel_from_agent_id(body.agentId, run_config)
        task_id = (body.toolCallId or "").strip() or str(uuid.uuid4())
        result = body.result if body.result is not None else {}
        if body.error:
            result = {**result, "ok": False, "error": body.error}

        append_event(
            "limb_executed",
            {
                "task_id": task_id,
                "tool_name": limb_name,
                "summary": (body.params or {}).get("summary", ""),
                "ok": result.get("ok"),
                "channel": channel,
                "source": "openclaw",
            },
        )
        schedule_checkpoint(limb_name, body.params or {}, result, task_id, run_config)
        return {}

    # Content Limb stub：由 daemon 自身提供，供 task_flow 内 in-process 调用，不暴露为 HTTP 也可；若需统一走 HTTP 可再加路由
    @app.get("/limb/content")
    def limb_content_stub() -> dict[str, Any]:
        """占位：Limb 实际在 task_flow 中 in-process 调用。"""
        return {"ok": True, "message": "stub"}

    return app
