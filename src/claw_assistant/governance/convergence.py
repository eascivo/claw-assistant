"""可收敛：复盘/告警 → 策略建议（占位）。供 Dashboard 或人工决策；后续可扩展为自动调参或写回 config。"""

from typing import Any


def get_convergence_suggestions(
    postmortems: list[dict[str, Any]],
    config: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """
    根据复盘列表与配置生成「收敛建议」占位列表。
    输入：复盘条数、告警阈值（config.checkpoint.alert_after_postmortem_count）。
    输出：建议列表，每项 { "id", "text", "source" }；后续可扩展偏差类型汇总、建议写回 config 等。
    """
    suggestions: list[dict[str, Any]] = []
    total = len(postmortems)
    cfg = (config or {}).get("checkpoint") or {}
    threshold = cfg.get("alert_after_postmortem_count")
    if threshold is not None and total > 0:
        try:
            n = int(threshold)
            if total >= n:
                suggestions.append({
                    "id": "postmortem_threshold",
                    "text": f"复盘条数已达 {total}，建议检查 checkpoint 阈值或复盘原因",
                    "source": "postmortem_summary",
                })
        except (TypeError, ValueError):
            pass
    return suggestions
