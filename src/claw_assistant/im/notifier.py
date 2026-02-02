"""IM 通知统一抽象：发送审批/待办通知；飞书 stub，钉钉/Discord 待实现。"""

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class IMNotifier(Protocol):
    """IM 通知接口：发送审批请求等；各端（飞书/钉钉/Discord）实现。"""

    def send_approval_request(
        self,
        approval_id: str,
        task_id: str,
        tool_name: str,
        summary: str,
        risk: str | None = None,
    ) -> None:
        """将待审批任务推送到 IM（文本/卡片）；失败仅打 log，不抛异常。"""
        ...


class NoOpNotifier:
    """空实现：不向任何 IM 推送。"""

    def send_approval_request(
        self,
        approval_id: str,
        task_id: str,
        tool_name: str,
        summary: str,
        risk: str | None = None,
    ) -> None:
        pass


class FeishuNotifier:
    """飞书通知 stub：占位实现，后续接 Webhook 或发消息 API。"""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = (config or {}).get("feishu") or {}
        self._webhook_url = (cfg.get("webhook_url") or "").strip() or None

    def send_approval_request(
        self,
        approval_id: str,
        task_id: str,
        tool_name: str,
        summary: str,
        risk: str | None = None,
    ) -> None:
        """占位：后续 POST 到飞书 Webhook 或发消息 API；当前仅 log。"""
        logger.debug(
            "feishu notifier stub: approval_id=%s task_id=%s tool=%s summary=%s",
            approval_id,
            task_id,
            tool_name,
            (summary or "")[:80],
        )
        if self._webhook_url:
            # 预留：后续 httpx.post(self._webhook_url, json={...})
            pass


def get_notifier(config: dict[str, Any] | None = None) -> IMNotifier:
    """根据 config.im.provider 返回对应 IM 通知实现；未配置或未知 provider 返回 NoOpNotifier。"""
    cfg = (config or {}).get("im") or {}
    provider = (cfg.get("provider") or "").strip().lower()
    if provider == "feishu":
        return FeishuNotifier(cfg)
    return NoOpNotifier()
