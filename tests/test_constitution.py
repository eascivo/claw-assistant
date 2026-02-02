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
