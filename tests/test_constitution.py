"""Constitution 规则单元测试。"""

import pytest
from claw_assistant.governance.hooks import before_tool_call, constitution_violation


def test_constitution_forbid_blocks() -> None:
    config = {
        "constitution": {"forbid": ["delete_user_data"], "allow": [], "restrict": []},
        "limbs": {"content": {"require_approval": True}},
    }
    block, reason, _ = before_tool_call("delete_user_data", {"summary": "x"}, config)
    assert block is True
    assert reason == "constitution"
    assert constitution_violation("delete_user_data", {}, config) is True


def test_constitution_allow_not_in_forbid_passes() -> None:
    config = {
        "constitution": {"forbid": ["delete_user_data"], "allow": ["content"], "restrict": []},
        "limbs": {"content": {"require_approval": True}},
    }
    assert constitution_violation("content", {}, config) is False


def test_constitution_restrict_requires_approval_config() -> None:
    config = {
        "constitution": {
            "forbid": [],
            "allow": [],
            "restrict": [{"action": "content", "require_human": True}],
        },
        "limbs": {"content": {"require_approval": True}},
    }
    assert constitution_violation("content", {}, config) is False

    config_no_approval = {
        "constitution": {
            "forbid": [],
            "restrict": [{"action": "content", "require_human": True}],
        },
        "limbs": {"content": {"require_approval": False}},
    }
    assert constitution_violation("content", {}, config_no_approval) is True


def test_constitution_restrict_action_list_format() -> None:
    config = {
        "constitution": {"forbid": [], "restrict": ["content"]},
        "limbs": {"content": {"require_approval": True}},
    }
    assert constitution_violation("content", {}, config) is False


def test_constitution_intent_deviation_stub_blocks() -> None:
    """意图偏差分：enabled + stub_score > threshold 则拦截。"""
    config = {
        "constitution": {
            "forbid": [],
            "restrict": [],
            "intent_deviation": {"enabled": True, "threshold": 0.5, "stub_score": 1.0},
        },
        "limbs": {"content": {"require_approval": True}},
    }
    assert constitution_violation("content", {"summary": "x"}, config) is True
    block, reason, _ = before_tool_call("content", {"summary": "x"}, config)
    assert block is True
    assert reason == "constitution"


def test_constitution_intent_deviation_stub_passes() -> None:
    """意图偏差分：stub_score <= threshold 不拦截。"""
    config = {
        "constitution": {
            "forbid": [],
            "restrict": [],
            "intent_deviation": {"enabled": True, "threshold": 0.5, "stub_score": 0.0},
        },
        "limbs": {"content": {"require_approval": True}},
    }
    assert constitution_violation("content", {"summary": "x"}, config) is False


def test_constitution_intent_deviation_disabled() -> None:
    """意图偏差分：enabled=false 时不检查偏差。"""
    config = {
        "constitution": {
            "forbid": [],
            "restrict": [],
            "intent_deviation": {"enabled": False, "threshold": 0.5, "stub_score": 1.0},
        },
        "limbs": {"content": {}},
    }
    assert constitution_violation("content", {}, config) is False


def test_constitution_intent_deviation_zhipu_no_key() -> None:
    """意图偏差分：provider=zhipu 且未设置 ZHIPUAI_API_KEY 时返回 None，不拦截。"""
    import os
    os.environ.pop("ZHIPUAI_API_KEY", None)
    config = {
        "constitution": {
            "forbid": [],
            "restrict": [],
            "intent_deviation": {"enabled": True, "threshold": 0.5, "provider": "zhipu"},
        },
        "limbs": {"content": {}},
    }
    assert constitution_violation("content", {"summary": "x"}, config) is False
