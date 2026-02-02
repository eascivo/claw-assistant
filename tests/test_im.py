"""IM 通知预留接口单元测试。"""

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
