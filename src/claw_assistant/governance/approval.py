"""ApprovalManager：内存实现，挂起任务等待 approve/reject。"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from claw_assistant.governance.events import append_event

logger = logging.getLogger(__name__)


@dataclass
class PendingApproval:
    """单条待审批记录。"""

    approval_id: str
    task_id: str
    tool_name: str
    summary: str
    risk: str | None
    session_key: str | None
    event: dict[str, Any]
    created_at: float
    _future: asyncio.Future[str] = field(repr=False)

    def to_public(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "task_id": self.task_id,
            "tool_name": self.tool_name,
            "summary": self.summary,
            "risk": self.risk,
        }


class ApprovalManager:
    """内存版审批管理器：register 挂起，wait 阻塞直到 resolve。"""

    def __init__(self) -> None:
        self._pending: dict[str, PendingApproval] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        session_key: str | None,
        tool_name: str,
        params: dict[str, Any],
        task_id: str | None = None,
        risk: str | None = None,
    ) -> PendingApproval:
        """注册一条待审批，返回 PendingApproval；调用方随后 await wait(approval_id)。"""
        import time

        approval_id = str(uuid.uuid4())
        task_id = task_id or str(uuid.uuid4())
        summary = params.get("summary", "") or str(params)[:200]
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        pending = PendingApproval(
            approval_id=approval_id,
            task_id=task_id,
            tool_name=tool_name,
            summary=summary,
            risk=risk,
            session_key=session_key,
            event={"tool_name": tool_name, "params": params},
            created_at=time.time(),
            _future=future,
        )
        async with self._lock:
            self._pending[approval_id] = pending
        append_event(
            "approval_requested",
            {"approval_id": approval_id, "task_id": task_id, "tool_name": tool_name, "summary": summary, "risk": risk},
        )
        logger.info("approval registered: %s", approval_id)
        return pending

    async def wait(self, approval_id: str, timeout: float = 300.0) -> str:
        """阻塞直到该审批被 resolve，返回 decision（'approve' | 'reject'）。超时返回 'reject'。"""
        async with self._lock:
            p = self._pending.get(approval_id)
        if not p:
            return "reject"
        try:
            return await asyncio.wait_for(p._future, timeout=timeout)
        except asyncio.TimeoutError:
            await self.resolve(approval_id, "reject")
            return "reject"

    async def resolve(self, approval_id: str, decision: str) -> bool:
        """解挂：decision 为 'approve' 或 'reject'。返回是否找到并已 resolve。"""
        async with self._lock:
            p = self._pending.pop(approval_id, None)
        if not p:
            return False
        if not p._future.done():
            p._future.set_result(decision)
        append_event("approval_resolved", {"approval_id": approval_id, "decision": decision})
        logger.info("approval resolved: %s -> %s", approval_id, decision)
        return True

    async def list_pending(self) -> list[dict[str, Any]]:
        """返回当前所有待审批的公开信息列表。"""
        async with self._lock:
            return [p.to_public() for p in self._pending.values()]

    async def get_pending(self, approval_id: str) -> PendingApproval | None:
        """根据 approval_id 取回 PendingApproval（用于解挂后继续执行）。"""
        async with self._lock:
            return self._pending.get(approval_id)
