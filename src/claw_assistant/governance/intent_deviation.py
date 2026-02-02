"""意图偏差分：智谱等 LLM 调用。API key 用环境变量，base_url 可配置或 env 覆盖。"""

import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# 环境变量：API key（必填）；base_url（可选，用于替换默认地址）
ZHIPU_API_KEY_ENV = "ZHIPUAI_API_KEY"
ZHIPU_BASE_URL_ENV = "ZHIPUAI_BASE_URL"
DEFAULT_ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"


def get_zhipu_base_url(config: dict[str, Any]) -> str:
    """优先 config.intent_deviation.base_url，其次 env ZHIPUAI_BASE_URL，再次默认。"""
    dev = (config.get("constitution") or {}).get("intent_deviation") or {}
    url = dev.get("base_url") or os.environ.get(ZHIPU_BASE_URL_ENV) or DEFAULT_ZHIPU_BASE_URL
    return url.rstrip("/")


def intent_deviation_score_zhipu(
    tool_name: str,
    params: dict[str, Any],
    config: dict[str, Any],
) -> float | None:
    """
    调用智谱 Chat Completions 计算意图偏差分（0~1）。
    需要环境变量 ZHIPUAI_API_KEY；base_url 可用 config 或 ZHIPUAI_BASE_URL 覆盖。
    无 key 或调用失败时返回 None。
    """
    api_key = os.environ.get(ZHIPU_API_KEY_ENV)
    if not api_key:
        logger.debug("intent_deviation zhipu: %s not set", ZHIPU_API_KEY_ENV)
        return None
    dev = (config.get("constitution") or {}).get("intent_deviation") or {}
    model = dev.get("model", "glm-4-flash")
    base_url = get_zhipu_base_url(config)
    url = f"{base_url}/chat/completions"
    intent = params.get("summary", "") or str(params)[:500]
    user_content = (
        f"工具名：{tool_name}\n"
        f"意图/摘要：{intent}\n"
        f"参数摘要：{str(params)[:300]}\n\n"
        "请判断「参数与意图」的偏差程度，仅输出一个 0 到 1 之间的小数，0 表示完全一致，1 表示完全偏离。不要输出其他文字。"
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": user_content}],
        "max_tokens": 32,
        "temperature": 0.1,
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("intent_deviation zhipu request failed: %s", e)
        return None
    choices = data.get("choices") or []
    if not choices:
        return None
    content = (choices[0].get("message") or {}).get("content") or ""
    match = re.search(r"0?\.\d+|1\.0?|1", content.strip())
    if not match:
        return None
    score = float(match.group())
    return max(0.0, min(1.0, score))
