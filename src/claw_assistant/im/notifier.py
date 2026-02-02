"""IM 通知统一抽象：发送审批/待办通知；飞书实装 Webhook，钉钉/Discord 待实现。"""

import logging
from typing import Any, Protocol

import httpx

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
    """飞书通知：自定义机器人 Webhook 发送审批/待办到群。"""

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
        """POST 到飞书自定义机器人 Webhook（msg_type=text）；失败仅打 log。"""
        if not self._webhook_url:
            logger.debug("feishu webhook_url not set, skip send")
            return
        text = f"【待审批】approval_id={approval_id}\ntask_id={task_id}\ntool={tool_name}\nsummary={summary or '-'}"
        if risk:
            text += f"\nrisk={risk}"
        payload: dict[str, Any] = {"msg_type": "text", "content": {"text": text}}
        try:
            resp = httpx.post(self._webhook_url, json=payload, timeout=5.0)
            if resp.status_code >= 400:
                logger.warning("feishu webhook returned %s: %s", resp.status_code, (resp.text or "")[:200])
        except Exception as e:
            logger.warning("feishu webhook failed: %s", e)


def get_notifier(config: dict[str, Any] | None = None) -> IMNotifier:
    """根据 config.im.provider 返回对应 IM 通知实现；未配置或未知 provider 返回 NoOpNotifier。"""
    cfg = (config or {}).get("im") or {}
    provider = (cfg.get("provider") or "").strip().lower()
    if provider == "feishu":
        return FeishuNotifier(cfg)
    return NoOpNotifier()
