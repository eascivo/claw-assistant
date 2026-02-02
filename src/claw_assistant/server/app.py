"""FastAPI：POST /run, GET /status, POST /approve, POST /reject；内部调 governance + limbs。"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from claw_assistant.config import load_config, resolve_tool_from_intent
from claw_assistant.governance.approval import ApprovalManager
from claw_assistant.governance.checkpoint import get_postmortems
from claw_assistant.governance.events import get_events
from claw_assistant.governance.task_flow import run_task_flow


def create_app(config: dict[str, Any] | None = None) -> FastAPI:
    """创建 FastAPI 应用；config 非空时作为注入配置（测试用），否则从 load_config() 读取。"""
    approval_manager = ApprovalManager()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
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
        """列出 World Checkpoint 触发的复盘记录。"""
        return {"postmortems": get_postmortems()}

    @app.get("/events")
    async def api_events(since_ts: float | None = None, limit: int = 200) -> dict[str, Any]:
        """时间轴事件：approval_requested / approval_resolved / limb_executed / postmortem。"""
        return {"events": get_events(since_ts=since_ts, limit=limit)}

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

    # Content Limb stub：由 daemon 自身提供，供 task_flow 内 in-process 调用，不暴露为 HTTP 也可；若需统一走 HTTP 可再加路由
    @app.get("/limb/content")
    def limb_content_stub() -> dict[str, Any]:
        """占位：Limb 实际在 task_flow 中 in-process 调用。"""
        return {"ok": True, "message": "stub"}

    return app
