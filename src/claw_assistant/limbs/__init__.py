"""Limbs: 执行层，Content / Ops stub 等。"""

from claw_assistant.limbs.content import execute_content
from claw_assistant.limbs.ops import execute_ops

LIMB_REGISTRY: dict[str, callable] = {
    "content": execute_content,
    "ops": execute_ops,
}


def execute_limb(tool_name: str, params: dict) -> dict:
    """根据 tool_name 派发到对应 limb 执行。"""
    fn = LIMB_REGISTRY.get(tool_name)
    if not fn:
        return {"ok": False, "error": f"unknown limb: {tool_name}"}
    return fn(params)
