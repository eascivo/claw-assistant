"""FastAPI：POST /run, GET /status, POST /approve, POST /reject；内部调 governance + limbs。"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from claw_assistant.config import load_config
from claw_assistant.governance.approval import ApprovalManager
from claw_assistant.governance.task_flow import run_task_flow


def create_app() -> FastAPI:
    approval_manager = ApprovalManager()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        # 可在此做清理

    app = FastAPI(title="claw-assistant", lifespan=lifespan)
    app.state.approval_manager = approval_manager

    class RunBody(BaseModel):
        intent: str

    @app.post("/run")
    async def api_run(body: RunBody) -> dict[str, Any]:
        """发起一次任务流；若需审批会挂起直到 approve/reject。成功与被拒绝均返回 200，body 内 ok 区分。"""
        manager: ApprovalManager = app.state.approval_manager
        out = await run_task_flow(
            body.intent,
            approval_manager=manager,
            config=load_config(),
            session_key=None,
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
