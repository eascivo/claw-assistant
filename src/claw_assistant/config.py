"""配置加载：YAML，limbs、require_approval 等。"""

from pathlib import Path
from typing import Any

import yaml


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """从 YAML 文件加载配置；若未指定则尝试 config.yaml / config.example.yaml。"""
    if path is None:
        base = Path.cwd()
        for name in ("config.yaml", "config.example.yaml"):
            p = base / name
            if p.exists():
                path = p
                break
        else:
            return _default_config()

    p = Path(path)
    if not p.exists():
        return _default_config()

    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else _default_config()


def _default_config() -> dict[str, Any]:
    return {
        "server": {"host": "0.0.0.0", "port": 8080},
        "limbs": {
            "content": {
                "endpoint": "http://localhost:8080/limb/content",
                "require_approval": True,
                "priority": 5,
            }
        },
        "constitution": {"forbid": [], "allow": [], "restrict": []},
        "checkpoint": {"threshold": 0.5, "delay_seconds": 0},
    }


def get_constitution(config: dict[str, Any]) -> dict[str, Any]:
    """返回 constitution 配置：forbid / allow / restrict。"""
    c = config.get("constitution") or {}
    return {
        "forbid": c.get("forbid") or [],
        "allow": c.get("allow") or [],
        "restrict": c.get("restrict") or [],
    }


def get_limb_config(config: dict[str, Any], tool_name: str) -> dict[str, Any] | None:
    """返回指定 limb（工具名）的配置，不存在则返回 None。"""
    limbs = config.get("limbs") or {}
    return limbs.get(tool_name)
