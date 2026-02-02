"""IM 通知预留接口：飞书先行，钉钉/Discord 等按同一接口扩展。"""

from claw_assistant.im.notifier import get_notifier

__all__ = ["get_notifier"]
