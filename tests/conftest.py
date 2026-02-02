"""Pytest 配置与共享 fixture；集成测试使用固定 config 隔离本地 config.yaml。"""

import pytest

# 集成测试专用配置：content 需审批、experimental 免审批、意图偏差关闭，与用例预期一致
TEST_CONFIG = {
    "server": {"host": "0.0.0.0", "port": 8080},
    "constitution": {
        "forbid": [],
        "allow": [],
        "restrict": [],
        "intent_deviation": {"enabled": False, "threshold": 0.5},
    },
    "checkpoint": {"threshold": 0.5, "delay_seconds": 0},
    "channels": {"experimental": {"require_approval": False}},
    "limbs": {
        "content": {
            "endpoint": "http://localhost:8080/limb/content",
            "require_approval": True,
            "priority": 5,
        },
        "ops": {
            "endpoint": "http://localhost:8080/limb/ops",
            "require_approval": False,
            "priority": 5,
        },
    },
}


@pytest.fixture
def app():
    """创建 FastAPI app，注入 TEST_CONFIG，与项目根 config.yaml 隔离。"""
    from claw_assistant.server.app import create_app

    return create_app(config=TEST_CONFIG.copy())
