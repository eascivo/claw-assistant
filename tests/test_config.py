"""config 模块单测：load_config、resolve_tool_from_intent 等。"""

import pytest

from claw_assistant.config import resolve_tool_from_intent


def test_resolve_tool_from_intent_empty_map_returns_default() -> None:
    """无 intent_tool_map 时返回默认 content。"""
    assert resolve_tool_from_intent("发布一条", {}, "content") == "content"
    assert resolve_tool_from_intent("部署服务", {}, "content") == "content"
    assert resolve_tool_from_intent("任意", {}, "ops") == "ops"


def test_resolve_tool_from_intent_matches_first() -> None:
    """按顺序匹配，先匹配先返回。"""
    config = {
        "intent_tool_map": [
            {"pattern": r"发布|推送", "tool": "content"},
            {"pattern": r"部署|运维", "tool": "ops"},
        ]
    }
    assert resolve_tool_from_intent("发布一条测试", config) == "content"
    assert resolve_tool_from_intent("推送文章", config) == "content"
    assert resolve_tool_from_intent("部署到生产", config) == "ops"
    assert resolve_tool_from_intent("运维巡检", config) == "ops"


def test_resolve_tool_from_intent_no_match_returns_default() -> None:
    """无匹配时返回 default_tool。"""
    config = {
        "intent_tool_map": [
            {"pattern": r"发布|推送", "tool": "content"},
            {"pattern": r"部署|运维", "tool": "ops"},
        ]
    }
    assert resolve_tool_from_intent("随便看看", config) == "content"
    assert resolve_tool_from_intent("随便看看", config, default_tool="ops") == "ops"


def test_resolve_tool_from_intent_invalid_pattern_skipped() -> None:
    """无效正则项被跳过，不抛错。"""
    config = {
        "intent_tool_map": [
            {"pattern": r"[invalid", "tool": "content"},
            {"pattern": r"部署", "tool": "ops"},
        ]
    }
    assert resolve_tool_from_intent("部署", config) == "ops"
    assert resolve_tool_from_intent("其他", config) == "content"


def test_resolve_tool_from_intent_empty_or_malformed_items_skipped() -> None:
    """空项或缺字段项被跳过。"""
    config = {
        "intent_tool_map": [
            {},
            {"pattern": "部署", "tool": ""},
            {"pattern": "", "tool": "ops"},
            {"pattern": "部署", "tool": "ops"},
        ]
    }
    assert resolve_tool_from_intent("部署", config) == "ops"
