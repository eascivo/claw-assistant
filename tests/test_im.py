"""IM 通知预留接口单元测试。"""

from unittest.mock import patch

import pytest
from claw_assistant.im.notifier import FeishuNotifier, NoOpNotifier, get_notifier


def test_get_notifier_no_config_returns_noop() -> None:
    n = get_notifier(None)
    assert isinstance(n, NoOpNotifier)
    n = get_notifier({})
    assert isinstance(n, NoOpNotifier)


def test_get_notifier_unknown_provider_returns_noop() -> None:
    n = get_notifier({"im": {"provider": "dingtalk"}})
    assert isinstance(n, NoOpNotifier)
    n = get_notifier({"im": {"provider": ""}})
    assert isinstance(n, NoOpNotifier)


def test_get_notifier_feishu_returns_feishu_notifier() -> None:
    n = get_notifier({"im": {"provider": "feishu"}})
    assert isinstance(n, FeishuNotifier)
    n = get_notifier({"im": {"provider": "Feishu"}})
    assert isinstance(n, FeishuNotifier)


def test_noop_notifier_send_approval_request_no_crash() -> None:
    n = NoOpNotifier()
    n.send_approval_request("a1", "t1", "content", "summary", risk="high")


def test_feishu_notifier_send_approval_request_no_crash() -> None:
    n = FeishuNotifier({"feishu": {}})
    n.send_approval_request("a1", "t1", "content", "summary", risk=None)
    n = FeishuNotifier({"im": {"feishu": {"webhook_url": "https://example.com/hook"}}})
    n.send_approval_request("a2", "t2", "ops", "deploy", risk="low")


def test_feishu_notifier_send_approval_request_posts_to_webhook() -> None:
    """配置 webhook_url 时，send_approval_request 向飞书 Webhook POST 文本消息。"""
    n = FeishuNotifier({"feishu": {"webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"}})
    with patch("claw_assistant.im.notifier.httpx.post") as mock_post:
        mock_post.return_value.status_code = 200
        n.send_approval_request("a1", "t1", "content", "发布一条测试", risk="high")
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
    body = call_args[1]["json"]
    assert body["msg_type"] == "text"
    assert "content" in body and "text" in body["content"]
    assert "a1" in body["content"]["text"] and "发布一条测试" in body["content"]["text"] and "high" in body["content"]["text"]
